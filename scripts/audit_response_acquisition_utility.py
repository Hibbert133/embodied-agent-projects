"""Read-only actual acquisition/continue branches with exactly matched prior states."""
import argparse
from collections import Counter
import gzip
from itertools import zip_longest
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.report_action_response import load,matching_audit,sha,case_metrics

TARGETS=("RESPONSE_SET","G_OPTIMAL")
REFERENCE="CACHE_ONLY"
SOURCE_ROOT=ROOT/"outputs/action_response/development_v1/action_response_20261014T104928Z_1c3798544481"
AUDIT=ROOT/"outputs/action_response/analysis_v1/audit.json"
AUDIT_SHA="f3309b30c8e167d148975a781da02e75013d761ca840fa6d0130cee7bcc1c0b8"
UNIT=("stream","task","scenario","episode_in_stream")
PREFIX_FIELDS=("command","raw_policy","before","after","rng_before","rng_after")


def unit(record):return tuple(record[k] for k in UNIT)


def eligibility(target,reference):
    if target["method"] not in TARGETS or reference["method"]!=REFERENCE:raise ValueError("foreign method pairing")
    if any(target[k]!=reference[k] for k in (*UNIT,"seed","operator_id_oracle")):raise ValueError("foreign unit/operator pairing")
    if target["cache_before"] is None or reference["cache_before"] is None:return "NO_OLD_CACHE"
    if target["cache_before"]!=reference["cache_before"]:return "UNEQUAL_OLD_CACHE"
    if target["initial"]!=reference["initial"] or target["initial_rng_hash"]!=reference["initial_rng_hash"]:raise ValueError("matched source initialization differs")
    a,b=target["trace"][:6],reference["trace"][:6]
    if len(a)!=6 or len(b)!=6:return "SHORT_PREFIX"
    if any(r["phase"]!="PREFIX_POLICY" for r in a) or any(r["phase"]!="POLICY" for r in b):return "DIFFERENT_PREFIX_PROGRAM"
    if any({k:x[k] for k in PREFIX_FIELDS}!={k:y[k] for k in PREFIX_FIELDS} for x,y in zip(a,b)):
        return "DIFFERENT_PHYSICAL_PREFIX"
    if any(a[-1]["after"][k] for k in ("success","terminated","truncated")):return "ENDED_BY_SHARED_PREFIX"
    return "MATCHED"


def comparison(target,reference):
    if eligibility(target,reference)!="MATCHED":raise ValueError("cannot infer unrecorded alternative branch")
    a,b=case_metrics(target),case_metrics(reference)
    observed="HELPFUL" if a["success"] and not b["success"] else "HARMFUL" if b["success"] and not a["success"] else "BOTH_SUCCESS" if a["success"] else "BOTH_FAILED"
    first=next(d for d in target["decisions"] if d.get("validation") is not None)
    return {**{k:target[k] for k in (*UNIT,"seed","operator_id_oracle")},"method":target["method"],
        "target_success":a["success"],"reference_success":b["success"],"target_stopped":a["stopped"],"reference_stopped":b["stopped"],
        "target_total_steps":a["total_steps"],"reference_total_steps":b["total_steps"],
        "target_remaining_steps":a["total_steps"]-6,"reference_remaining_steps":b["total_steps"]-6,
        "step_difference":a["total_steps"]-b["total_steps"],"extra_probe_steps":a["micro_steps"]+a["fixed_probe_steps"],
        "paired_outcome":observed,"first_validation_action":first["action"],
        "first_validation_status":first["validation"]["assessment"]["status"],
        "matched_prefix_steps":6,"oracle_pairing_not_agent_evidence":True}


def summarize(rows):
    n=len(rows);counts=Counter(r["paired_outcome"] for r in rows)
    return {"cases":n,"target_successes":sum(r["target_success"] for r in rows),"reference_successes":sum(r["reference_success"] for r in rows),
        "target_stops":sum(r["target_stopped"] for r in rows),"reference_stops":sum(r["reference_stopped"] for r in rows),
        "paired_outcomes":dict(counts),"mean_step_difference":sum(r["step_difference"] for r in rows)/n if n else None,
        "mean_extra_probe_steps":sum(r["extra_probe_steps"] for r in rows)/n if n else None,
        "target_total_steps":sum(r["target_total_steps"] for r in rows),"reference_total_steps":sum(r["reference_total_steps"] for r in rows),
        "mean_target_total_steps":sum(r["target_total_steps"] for r in rows)/n if n else None,
        "mean_reference_total_steps":sum(r["reference_total_steps"] for r in rows)/n if n else None,
        "mean_target_remaining_steps":sum(r["target_remaining_steps"] for r in rows)/n if n else None,
        "mean_reference_remaining_steps":sum(r["reference_remaining_steps"] for r in rows)/n if n else None}


def records(method):
    with gzip.open(SOURCE_ROOT/("episodes_"+method+".jsonl.gz"),"rt",encoding="utf-8") as handle:
        for line in handle:yield json.loads(line)


def aligned_population(targets,references,method,expected_units,identity):
    seen=set()
    for target,reference in zip_longest(targets,references):
        if target is None or reference is None:raise ValueError("unequal original populations")
        if target["method"]!=method or reference["method"]!=REFERENCE:raise ValueError("foreign original method")
        if any(record[k]!=v for record in (target,reference) for k,v in identity.items()):raise ValueError("foreign source identity")
        key=unit(target)
        if key!=unit(reference) or key in seen or key not in expected_units:raise ValueError("unaligned or duplicate original unit")
        seen.add(key)
        yield target,reference
    if seen!=expected_units:raise ValueError("incomplete original population")


def analyze():
    manifest=load(SOURCE_ROOT/"manifest.json");audit=load(AUDIT);matching_audit(manifest,audit)
    if sha(AUDIT)!=AUDIT_SHA:raise ValueError("registered original audit changed")
    for name,expected in audit["artifact_sha256"].items():
        if sha(SOURCE_ROOT/name)!=expected:raise ValueError("original audited bytes changed")
    for name,expected in manifest["input_sha256"].items():
        if sha(ROOT/name)!=expected:raise ValueError("original frozen inputs changed")
    results={};excluded={};details=[];excluded_cases=[]
    identity={k:manifest[k] for k in ("experiment_run_id","manifest_id","source_git_commit")}
    config=manifest["config"]
    expected_units={(s,t,c,e) for s in range(config["streams"]) for t in config["tasks"]
                    for c in config["scenarios"] for e in range(config["episodes_per_stream_task"])}
    for method in TARGETS:
        rejected=Counter();paired=[];population=0
        for target,reference in aligned_population(records(method),records(REFERENCE),method,expected_units,identity):
            population+=1;reason=eligibility(target,reference)
            if reason=="MATCHED":paired.append(comparison(target,reference))
            else:
                rejected[reason]+=1
                excluded_cases.append({**{k:target[k] for k in (*UNIT,"seed","operator_id_oracle")},"method":method,"reason":reason})
        if population!=288:raise ValueError("registered original population required")
        results[method]={"overall":summarize(paired),"episode_one":summarize([r for r in paired if r["episode_in_stream"]==1]),
            "by_task":{t:summarize([r for r in paired if r["task"]==t]) for t in manifest["config"]["tasks"]},
            "by_scenario":{s:summarize([r for r in paired if r["scenario"]==s]) for s in manifest["config"]["scenarios"]},
            "by_stream":{str(s):summarize([r for r in paired if r["stream"]==s]) for s in range(8)}}
        excluded[method]={"original_units":population,"reasons":dict(rejected)};details.extend(paired)
    return {**{k:manifest[k] for k in ("experiment_run_id","manifest_id","source_git_commit")},"primary_audit_sha256":AUDIT_SHA,
        "analysis_source_sha256":sha(Path(__file__)),"protocol_sha256":sha(ROOT/"docs/research/response_acquisition_utility_audit_v1.md"),
        "analysis_git_commit":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
        "reference":REFERENCE,"results":results,"excluded":excluded,"paired_cases":details,"excluded_cases":excluded_cases,
        "new_robot_steps":0,"new_api_calls":0,"new_resets":0,"new_models_or_thresholds_fitted":0,
        "registered_prior_cost_per_method":{"steps":21010,"controlled_resets":288},
        "scope":"Actual recorded branch outcomes only after exactly matched old cache and six policy steps. Acquisition includes motion and changed controller; no pure-information attribution, counterfactual dynamics replay, natural-memory records or independent confirmatory inference."}


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--output",type=Path,required=True);args=p.parse_args()
    output=args.output.resolve()
    if output.exists() or output==SOURCE_ROOT or SOURCE_ROOT in output.parents:raise FileExistsError("new external analysis required")
    result=analyze();output.mkdir(parents=True,exist_ok=False)
    (output/"audit.json").write_bytes((json.dumps(result,indent=2,ensure_ascii=False)+"\n").encode("utf-8"))
    print(json.dumps(result["results"]))

"""One-shot evaluator-only reuse analysis of saved inverse parameter differences."""
import argparse
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime,timezone
import gzip
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.run_forward_prediction import check_clean,git,digest,manifest_digest
from scripts.run_action_response import load_bank,write_json
from scripts.run_acquisition_value import normal
from src.analysis.inverse_residuals import OracleActuation,decompose_oracle_prefix,COMPONENTS
from src.probe.continuous import ContinuousTransition
from src.probe.operator_identification import visible_samples

CONFIG=ROOT/"configs/inverse_error_attribution/development_v1.json"
PROTOCOL=ROOT/"docs/protocols/inverse_error_attribution_v1.md"
NOTE=ROOT/"docs/research/inverse_error_accounting_v1.md"
IDENTITY=("analysis_run_id","manifest_id","source_git_commit")


def validate(c):
    if c.get("protocol_id")!="oracle_inverse_error_attribution_v1" or c.get("expected_pairs")!=192 or c.get("prefix_boundaries")!=[8,16] or c.get("methods_used")!=["DIRECT_G8","PASSIVE_G16"]:
        raise ValueError("registered oracle reuse design required")
    if c.get("tasks")!=["push-v3","reach-v3","door-open-v3"] or any(c.get(k)!=0 for k in ("new_environment_steps","api_calls","controller_fits")):
        raise ValueError("no new simulation, calls or fits permitted")
    if [(s["id"],s["streams"],s["futures"],s["source_episodes"],s["source_steps"]) for s in c["sources"]]!=[("DISCOVERY_REUSE",8,4,672,101069),("LATER_REUSE",16,2,1152,133450)]:
        raise ValueError("complete two-cohort source population required")
    if c.get("forward_model_sha256")!="b3f2d7e69316dba65e722d74d49df25c7d651043e78bf4c0f6e1d37f1e599c80" or (c["source_bank_steps"],c["source_bank_resets"],c["nominal_source_steps"],c["nominal_source_resets"])!=(234519,1824,21010,288):
        raise ValueError("fixed nominal and complete prior-source fees required")


def prepare():
    check_clean(); c=json.loads(CONFIG.read_text(encoding="utf-8")); validate(c)
    parent=ROOT/c["output_root"]
    if list(parent.glob("*/manifest.json")): raise FileExistsError("one-shot analysis already prepared")
    names=git("ls-files","src","scripts","tests").splitlines()+[CONFIG.relative_to(ROOT).as_posix(),PROTOCOL.relative_to(ROOT).as_posix(),NOTE.relative_to(ROOT).as_posix(),"AGENTS.md",".gitattributes","requirements.txt"]
    commit=git("rev-parse","HEAD"); stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    m={"analysis_run_id":f"inverse_attribution_{stamp}_{commit[:12]}","source_git_commit":commit,"config":c,
       "input_sha256":{n:digest(ROOT/n) for n in names},"versions":{n:importlib.metadata.version(n) for n in ("numpy","scipy")}}
    m["manifest_id"]=manifest_digest(m); output=parent/m["analysis_run_id"]; output.mkdir(parents=True,exist_ok=False)
    write_json(output/"manifest.json",m); print(output/"manifest.json")


def load(path):
    m=json.loads(path.read_text(encoding="utf-8")); validate(m["config"])
    if manifest_digest(m)!=m["manifest_id"] or any(digest(ROOT/n)!=h for n,h in m["input_sha256"].items()): raise ValueError("frozen analysis bytes changed")
    if any(importlib.metadata.version(n)!=v for n,v in m["versions"].items()): raise ValueError("frozen numeric version changed")
    return m


def sources(config):
    result=[]
    for declared in config["sources"]:
        path=ROOT/declared["manifest_path"]; audit_path=ROOT/declared["audit_path"]
        if digest(path)!=declared["manifest_sha256"] or digest(audit_path)!=declared["audit_sha256"]: raise ValueError("declared source bytes differ")
        source=json.loads(path.read_text(encoding="utf-8")); audit=json.loads(audit_path.read_text(encoding="utf-8"))
        if manifest_digest(source)!=source["manifest_id"] or audit["integrity"]!="PASSED" or audit["episodes"]!=declared["source_episodes"] or audit["controlled_steps"]!=declared["source_steps"] or any(source[k]!=audit[k] for k in ("experiment_run_id","manifest_id","source_git_commit")):
            raise ValueError("complete matching historical source required")
        for name,expected in source["input_sha256"].items():
            data=subprocess.check_output(["git","show",source["source_git_commit"]+":"+name],cwd=ROOT)
            if hashlib.sha256(data).hexdigest()!=expected: raise ValueError("historical frozen Git source changed")
        for name,expected in audit["artifact_sha256"].items():
            if digest(path.parent/name)!=expected: raise ValueError("historical audited raw bytes changed")
        for name in ("src/probe/operator_identification.py","src/probe/forward_prediction.py"):
            if digest(ROOT/name)!=source["input_sha256"][name]: raise ValueError("reused predictor mathematics changed")
        if source["config"]["forward_model_sha256"]!=config["forward_model_sha256"]: raise ValueError("mixed nominal forward models")
        models,_,_=load_bank(source["config"])
        result.append((declared,path,source,audit,models))
    return result


def extract_pairs(config,verified_sources):
    fields=("before","after","command","raw_policy","noise_before_hash","noise_after_hash","executed_action_oracle")
    pairs=[]
    for declared,path,source,audit,models in verified_sources:
        for stream in range(declared["streams"]):
            records={}
            with gzip.open(path.parent/f"episodes_{stream:02}.jsonl.gz","rt",encoding="utf-8") as handle:
                for record in map(json.loads,handle):
                    if record["method"] not in config["methods_used"]: continue
                    if record["stream"]!=stream or record["operator_id_oracle"]!="A": raise ValueError("foreign source branch")
                    key=(record["task"],record["replicate"],record["method"])
                    if key in records: raise ValueError("duplicate source branch")
                    records[key]={**record,"trace":record["trace"][:16]}
            if len(records)!=3*declared["futures"]*2: raise ValueError("source branch population incomplete")
            private=next(v for v in source["operators_oracle"][stream]["states_oracle"] if v["id"]=="A")
            oracle=OracleActuation(private["matrix_xy"],private["bias_xy"])
            for task in config["tasks"]:
                for future in range(declared["futures"]):
                    direct=records[(task,future,"DIRECT_G8")]; passive=records[(task,future,"PASSIVE_G16")]
                    for name in ("initial","initial_physics_witness_oracle","eight_physics_witness_oracle"):
                        if direct[name]!=passive[name]: raise ValueError("declared common-prefix witness differs")
                    n=min(16,len(direct["trace"]),len(passive["trace"]))
                    for i in range(n):
                        if any(direct["trace"][i][f]!=passive["trace"][i][f] for f in fields): raise ValueError("listed common-policy history differs")
                    builds={}
                    for boundary in (8,16):
                        candidates=[d for d in passive["decisions"] if d["action"]=="BUILD_GAUSSIAN" and d["at_host_calls"]==boundary]
                        if len(candidates)>1: raise ValueError("duplicate saved source reference")
                        if candidates: builds[boundary]=candidates[0]
                    old=[d for d in direct["decisions"] if d["action"]=="BUILD_GAUSSIAN" and d["at_host_calls"]==8]
                    if 8 in builds and (len(old)!=1 or old[0]["controller"]!=builds[8]["controller"]): raise ValueError("source C8 controller mismatch")
                    blocks={}
                    for boundary,build in builds.items():
                        trace=passive["trace"][:boundary]
                        if len(trace)!=boundary or [r["host_calls"] for r in trace]!=list(range(1,boundary+1)): raise ValueError("source decision boundary differs")
                        samples=visible_samples([ContinuousTransition(tuple(r["command"]),tuple(r["before"]["observation"]),tuple(r["after"]["observation"])) for r in trace])
                        blocks[boundary]={"samples":samples,"executed_actions":[trace[s.step-1]["executed_action_oracle"] for s in samples],
                                          "saved_parameters":build["controller"]["mean"],"covariance_trace":float(np.trace(build["controller"]["covariance"]))}
                    identity={"cohort":declared["id"],"stream":stream,"task":task,"future":future,"source_manifest_id":source["manifest_id"]}
                    pairs.append({**identity,"direct_outcome":direct["outcome"],"passive_outcome":passive["outcome"],"oracle":oracle,"blocks":blocks})
    if len(pairs)!=192: raise ValueError("all 192 historical pairs required")
    return pairs


def summarize(rows):
    groups=defaultdict(list)
    for row in rows: groups[(row["cohort"],row["task"])].append(row)
    result=[]
    for (cohort,task),part in sorted(groups.items()):
        eligible=[r for r in part if set(r["prefixes"])=={"8","16"}]
        item={"cohort":cohort,"task":task,"pairs":len(part),"complete_saved_pairs":len(eligible),
              "loss_improved":sum(r["passive_outcome"]["deadline_loss"]<r["direct_outcome"]["deadline_loss"] for r in part),
              "loss_worsened":sum(r["passive_outcome"]["deadline_loss"]>r["direct_outcome"]["deadline_loss"] for r in part),
              "direct_success_passive_failure":sum(r["direct_outcome"]["success"] and not r["passive_outcome"]["success"] for r in part),"prefixes":{}}
        for boundary in ("8","16"):
            blocks=[r["prefixes"][boundary] for r in part if boundary in r["prefixes"]]
            item["prefixes"][boundary]={"blocks":len(blocks),
                **{k:float(np.mean([b[k] for b in blocks])) if blocks else None for k in ("gain_error_frobenius","bias_error_norm","scaled_parameter_error_norm","residual_rmse_m")},
                "signed_contribution_means":{k:float(np.mean([b["signed_scaled_error_contributions"][k] for b in blocks])) if blocks else None for k in COMPONENTS}}
        item["gain_error_worsened_while_covariance_shrank"]=sum(r["prefixes"]["16"]["gain_error_frobenius"]>r["prefixes"]["8"]["gain_error_frobenius"] and r["prefixes"]["16"]["covariance_trace"]<r["prefixes"]["8"]["covariance_trace"] for r in eligible)
        result.append(item)
    return result


def analyze(path):
    check_clean(); manifest=load(path); output=path.parent
    if (output/"status.json").exists(): raise FileExistsError("one-shot analysis cannot restart")
    identity={k:manifest[k] for k in IDENTITY}; status={**identity,"status":"RUNNING","new_environment_steps":0,"api_calls":0,"controller_fits":0}
    write_json(output/"status.json",status)
    try:
        verified=sources(manifest["config"]); pairs=extract_pairs(manifest["config"],verified); rows=[]
        model_by_source={declared["id"]:models for declared,_,_,_,models in verified}
        for pair in pairs:
            prefixes={}
            for boundary,block in pair["blocks"].items():
                prefixes[str(boundary)]={**decompose_oracle_prefix(model_by_source[pair["cohort"]][pair["task"]],block["samples"],block["executed_actions"],pair["oracle"],block["saved_parameters"]),"covariance_trace":block["covariance_trace"]}
            rows.append({k:normal(v) for k,v in pair.items() if k not in ("oracle","blocks")}|{"prefixes":prefixes})
        blocks=[b for row in rows for b in row["prefixes"].values()]
        result={**identity,"role":"EVALUATOR_ONLY_POST_HOC_SOURCE_REUSE","pairs":192,"analyzed_prefixes":len(blocks),"rows":rows,"group_summaries":summarize(rows),
                "maximum_identity_errors":{k:max(b["identity_errors"][k] for b in blocks) for k in ("residual_max_abs","secant_max_abs","parameter_max_abs")},
                "source_git_inputs_verified":sum(len(source["input_sha256"]) for _,_,source,_,_ in verified),
                "diagnostic_pseudoinverse_evaluations":len(blocks),"new_environment_steps":0,"api_calls":0,"controller_fits":0,
                "scope":"Frozen nominal predictor accounting relative to registered float32 actuator parameters; not physical cause identification, a new estimator, task-utility certificate or independent confirmation."}
        write_json(output/"results.json",result); status.update(status="COMPLETED_ORACLE_ACCOUNTING",pairs=192,analyzed_prefixes=len(blocks)); write_json(output/"status.json",status)
        print(json.dumps({"status":status["status"],"pairs":192,"prefixes":len(blocks),"maximum_identity_errors":result["maximum_identity_errors"]}))
    except BaseException as exc:
        status.update(status="FAILED_PARTIAL",error_type=type(exc).__name__,error=str(exc)); write_json(output/"status.json",status); raise


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("command",choices=("prepare","run")); parser.add_argument("--manifest",type=Path)
    args=parser.parse_args()
    if args.command=="prepare": prepare()
    elif args.manifest: analyze(args.manifest.resolve())
    else: parser.error("run requires --manifest")

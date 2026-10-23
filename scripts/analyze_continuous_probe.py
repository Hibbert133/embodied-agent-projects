"""Audit observation/RNG continuity and replay decisions without new rollouts."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
from scripts.run_continuous_probe import load_manifest,summarize,state_hash,normalized
from scripts.build_autoresearch_benchmark import get_conditions
from src.probe.continuous import StepObservation,ContinuousTransition,ContinuousEvidence,symmetric_program
from src.probe.continuous_baselines import METHODS,decision
from src.probe.directional import ProbeResult,PROBE_DIRECTIONS,estimate_planar_bias
from src.task_metrics import extract_push_positions


def rng_hash(rng):
    return hashlib.sha256(json.dumps(rng.bit_generator.state,sort_keys=True).encode()).hexdigest()


def verify(m,events,status,summary):
    c=m["config"]
    identity={k:m[k] for k in ("experiment_run_id","manifest_id","source_git_commit")}
    if any(any(r.get(k)!=v for k,v in identity.items()) for r in events+[status,summary]):
        raise ValueError("provenance mismatch")
    if [r["sequence"] for r in events]!=list(range(1,len(events)+1)):
        raise ValueError("event sequence mismatch")
    grouped={}
    for r in events:
        key=r["seed"],r["condition_oracle"],r["method"]
        grouped.setdefault(key,[]).append(r)
    expected={(s,k,method) for s in range(8700,8708) for k in c["conditions"] for method in METHODS}
    if set(grouped)!=expected: raise ValueError("episode population mismatch")
    conditions={x.condition_id:x for x in get_conditions(0)}
    outcomes=[]; prefixes={}; initial_hashes={}; task_steps=0
    for seed in range(8700,8708):
        for condition_index,condition in enumerate(c["conditions"]):
            for method in METHODS:
                group=grouped[seed,condition,method]
                if [r["kind"] for r in group[:2]]!=["probe","decision"] or group[-1]["kind"]!="outcome" or any(r["kind"]!="step" for r in group[2:-1]):
                    raise ValueError("episode chronology mismatch")
                if [r["sequence"] for r in group]!=list(range(group[0]["sequence"],group[-1]["sequence"]+1)):
                    raise ValueError("interleaved episode")
                probe,chosen,outcome=group[0],group[1],group[-1]
                steps=group[2:-1]; initial=StepObservation(**probe["initial"]); handoff=StepObservation(**probe["handoff"])
                initial_hashes.setdefault(seed,set()).add(state_hash(initial.observation))
                evidence=None; inference=None; n_probe=0
                if method.startswith("CONT_"):
                    raw=probe["continuous"]
                    rows=tuple(ContinuousTransition(tuple(t["command"]),tuple(t["before"]),tuple(t["after"])) for t in raw["transitions"])
                    evidence=ContinuousEvidence(rows,StepObservation(**raw["final"]),raw["stop_reason"],raw["requested_steps"])
                    n_probe=len(rows)
                    if not 1<=n_probe<=16 or evidence.requested_steps!=16 or probe["reset_transitions"] is not None or probe["reset_inference"] is not None:
                        raise ValueError("continuous probe schema mismatch")
                    previous=initial.observation
                    for row,command in zip(rows,symmetric_program()):
                        if row.before!=previous or row.command!=command:
                            raise ValueError("continuous probe chain/command mismatch")
                        previous=row.after
                    if previous!=handoff.observation or evidence.final!=handoff:
                        raise ValueError("probe handoff mismatch")
                    expected_stop="SUCCESS" if handoff.success else "TERMINATED" if handoff.terminated else "TRUNCATED" if handoff.truncated else "PROGRAM_COMPLETE"
                    if evidence.stop_reason!=expected_stop or (expected_stop=="PROGRAM_COMPLETE" and n_probe!=16):
                        raise ValueError("probe stop mismatch")
                    prefixes.setdefault((seed,condition),set()).add(json.dumps(raw,sort_keys=True))
                elif method=="RESET_REFERENCE":
                    if probe["continuous"] is not None or handoff!=initial:
                        raise ValueError("reference must restart from initial state")
                    transitions=[ProbeResult(**r) for r in probe["reset_transitions"]]
                    if len(transitions)!=4: raise ValueError("reference probe population")
                    for row,(direction,command) in zip(transitions,PROBE_DIRECTIONS):
                        if row.seed!=seed or row.direction!=direction or row.steps!=4 or not np.array_equal(row.commanded_action,command*np.float32(.2)):
                            raise ValueError("reference probe protocol mismatch")
                        if not np.allclose(row.start_gripper_position,initial.observation[:3],rtol=0,atol=1e-12):
                            raise ValueError("reference reset mismatch")
                    inference=estimate_planar_bias(transitions).to_dict()
                    if normalized(inference)!=probe["reset_inference"]: raise ValueError("reference inference mismatch")
                    n_probe=16
                else:
                    if any(probe[k] is not None for k in ("continuous","reset_transitions","reset_inference")) or handoff!=initial:
                        raise ValueError("no-probe evidence mismatch")
                rebuilt=decision(method,evidence,inference)
                if normalized(rebuilt)!=chosen["decision"]:
                    raise ValueError("visible-only decision replay mismatch")
                noise_seed=int(np.random.SeedSequence([seed,condition_index,0xC71]).generate_state(1)[0])
                rng=np.random.default_rng(noise_seed)
                host_calls=n_probe if method.startswith("CONT_") else 0
                for _ in range(host_calls): rng.normal(0,.05,3)
                if probe["host_calls"]!=host_calls or probe["rng_handoff"]!=rng_hash(rng):
                    raise ValueError("handoff RNG/counter mismatch")
                previous=state_hash(handoff.observation)
                ended=handoff.success or handoff.terminated or handoff.truncated
                success=handoff.success; first_success=0 if success else None
                for i,row in enumerate(steps,1):
                    if ended: raise ValueError("step after terminal event")
                    if row["decision_sequence"]!=chosen["sequence"] or row["task_step"]!=i or row["host_calls"]!=host_calls+i:
                        raise ValueError("task counter/decision mismatch")
                    if row["before_hash"]!=previous: raise ValueError("task observation chain broken")
                    if row["rng_before"]!=rng_hash(rng): raise ValueError("task RNG reseed/discontinuity")
                    rng.normal(0,.05,3)
                    if row["rng_after"]!=rng_hash(rng): raise ValueError("task RNG advance mismatch")
                    if len(row["command"])!=4 or not np.isfinite(row["command"]).all(): raise ValueError("invalid task command")
                    if any(type(row[k]) is not bool for k in ("success","terminated","truncated")): raise ValueError("invalid terminal flags")
                    ended=row["success"] or row["terminated"] or row["truncated"]
                    success=row["success"]; previous=row["after_hash"]
                    if success: first_success=i
                if n_probe+len(steps)>500 or (not ended and n_probe+len(steps)!=500): raise ValueError("episode budget/stop mismatch")
                _,start_obj,_=extract_push_positions(np.array(initial.observation))
                _,end_obj,_=extract_push_positions(np.array(handoff.observation))
                fit=rebuilt["fit"]
                error=float(np.linalg.norm(np.array(fit["bias_in_command_units"])-conditions[condition].parameters["bias"][:2])) if fit and fit["valid"] else None
                expected_values={"decision_sequence":chosen["sequence"],"success":success,
                    "success_equal_484_task_steps":first_success is not None and first_success<=484,
                    "probe_success":handoff.success,"probe_steps":n_probe,"task_steps":len(steps),"total_steps":n_probe+len(steps),
                    "environment_resets":5 if method=="RESET_REFERENCE" else 1,"actuator_resets":5 if method=="RESET_REFERENCE" else 1,
                    "host_calls":host_calls+len(steps),"initial_state_hash":state_hash(initial.observation),
                    "handoff_hash":state_hash(handoff.observation),"final_hash":previous,"offset_error_oracle":error,
                    "probe_object_displacement":float(np.linalg.norm(end_obj-start_obj))}
                if any(outcome.get(k)!=v for k,v in expected_values.items()): raise ValueError("outcome reconstruction mismatch")
                outcomes.append(outcome); task_steps+=len(steps)
    if any(len(v)!=1 for v in prefixes.values()) or any(len(v)!=1 for v in initial_hashes.values()):
        raise ValueError("paired prefix/initial state mismatch")
    stats=summarize(outcomes,c)
    if stats!=summary["statistics"]: raise ValueError("summary statistics mismatch")
    expected_status="COMPLETED_FEASIBILITY_PASS" if stats["gate_passed"] else "COMPLETED_FEASIBILITY_FAILED"
    values={"status":expected_status,"complete_units":32,"physical_steps":sum(r["total_steps"] for r in outcomes),
        "environment_resets":288,"api_calls":0,"memory_writes":0}
    if values["physical_steps"]>80000 or any(status.get(k)!=v or summary.get(k)!=v for k,v in values.items()):
        raise ValueError("completion/physical accounting mismatch")
    return {**identity,**values,"integrity":"PASSED","statistics":stats,"replayed_decisions":160,
            "verified_task_steps":task_steps,"continuous_handoffs":96,
            "audit_scope":"Visible decisions, hash-chain continuity, complete actuator RNG consumption, budgets and statistics. Task dynamics are not resimulated."}


def analyze(path):
    m=load_manifest(path); output=path.parent
    events=[json.loads(x) for x in (output/"events.jsonl").read_text().splitlines()]
    result=verify(m,events,json.loads((output/"status.json").read_text()),json.loads((output/"summary.json").read_text()))
    result["artifact_sha256"]={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()}
    return result


def report(r):
    lines=["# Continuous-probe matched-budget result","",f'Status: `{r["status"]}`. Integrity: `{r["integrity"]}`.',"",
           "Eight independent task seeds x four contexts; five baselines. All states included, 500 total steps each.","",
           "| Method | Success / 32 | Mean total steps | Resets | Valid fits | Mean offset error | Success with 484 task steps |",
           "|---|---:|---:|---:|---:|---:|---:|"]
    for name,v in r["statistics"]["methods"].items():
        error=f'{v["mean_offset_error_oracle"]:.4f}' if v["mean_offset_error_oracle"] is not None else "n/a"
        lines.append(f'| {name} | {v["successful"]} | {v["mean_total_steps"]:.2f} | {v["environment_resets"]} | {v["valid_fits"]} | {error} | {v["success_equal_484_task_steps"]} |')
    lines += ["","The final column is secondary: equal policy-step cap permits additional probe cost. RESET_REFERENCE is privileged by resets.",""]
    for name,v in r["statistics"]["contrasts_vs_cont_no_correction"].items():
        low,high=v["cluster_interval_975"]
        lines.append(f'- {name} vs probe-without-correction: {100*v["difference"]:+.2f} pp; 97.5% seed-cluster interval [{100*low:.2f}, {100*high:.2f}] pp.')
    lines += ["",f'Passing standard estimators: `{r["statistics"]["passing_estimators"]}`.',"",
              f'{r["replayed_decisions"]} decisions replayed; {r["continuous_handoffs"]} continuous handoffs and {r["verified_task_steps"]} task-step RNG/observation links verified.',
              f'Physical steps: {r["physical_steps"]}; explicit resets: {r["environment_resets"]}.',"",r["audit_scope"],"",
              "This is standard-baseline development evidence, not a new algorithm, multi-task validation, or publication readiness.",""]
    return "\n".join(lines)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--manifest",type=Path,required=True); p.add_argument("--output",type=Path,required=True)
    a=p.parse_args(); source=a.manifest.resolve(); output=a.output.resolve()
    if output==source.parent or source.parent in output.parents: raise ValueError("audit must remain outside immutable collection")
    result=analyze(source); output.mkdir(parents=True,exist_ok=False)
    (output/"audit.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    (output/"report.md").write_text(report(result),encoding="utf-8"); print(report(result))

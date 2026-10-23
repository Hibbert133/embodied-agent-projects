"""Frozen calibrated continuous-task comparison with lossless episode logs."""
import argparse
from dataclasses import asdict
from datetime import datetime,timezone
import gzip
import importlib.metadata
import json
from pathlib import Path
import random
import statistics
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
from scripts.run_evidence_persistence import git,digest,manifest_digest,check_clean,append
from scripts.run_probemem_acr_utility_stability import _write_json
from scripts.run_response_calibration import audit as calibration_audit
from scripts.run_continuous_probe import LiveHost,state_hash,normalized
from scripts.build_autoresearch_benchmark import get_conditions
from src.probe.continuous import collect_continuous,symmetric_program
from src.probe.continuous_baselines import decision as online_decision
from src.probe.response_calibration import ResponseModel,infer_offset
from src.planar_recovery import estimate_planar_correction
from src.recovery_agent import DEFAULT_CORRECTION_MAGNITUDES
from src.perturbations import BiasNoisePerturbation
from src.rollout import create_push_environment,create_push_policy

METHODS=("NO_PROBE","CONT_NO_CORRECTION","CONT_DYNAMIC","PRIOR_AFFINE","PRIOR_NEAREST")
CONFIG=ROOT/"configs/calibrated_tasks/development_v1.json"
PROTOCOL=ROOT/"docs/protocols/calibrated_continuous_task_utility_v1.md"


def validate(c):
    if (c["seed_start"],c["num_seeds"],tuple(c["methods"]),c["conditions"],c["noise_std"],c["total_steps"],
        c["probe_steps"],c["post_probe_reserve"],c["offline_steps"],c["offline_resets"],c["maximum_physical_steps"],
        c["api_calls"],c["memory_writes"]) != (9100,16,METHODS,["fault_01","fault_02","fault_03","fault_04"],.05,500,16,484,2304,144,160000,0,0):
        raise ValueError("frozen calibrated-task configuration mismatch")


def load_model(c):
    qualified=calibration_audit(ROOT/c["calibration_manifest"])
    if qualified["status"]!="COMPLETED_QUALIFICATION_PASS": raise ValueError("calibration is not qualified")
    path=ROOT/c["model_path"]
    if digest(path)!=qualified["model_sha256"]: raise ValueError("qualified model hash mismatch")
    saved=json.loads(path.read_text())
    return ResponseModel(**saved["model"]),digest(path)


def load(path):
    m=json.loads(path.read_text()); validate(m["config"])
    if manifest_digest(m)!=m["manifest_id"]: raise ValueError("manifest hash mismatch")
    for p,sha in m["input_sha256"].items():
        if digest(ROOT/p)!=sha: raise ValueError(f"frozen input changed: {p}")
    return m


def prepare():
    check_clean(); c=json.loads(CONFIG.read_text()); validate(c)
    _,model_sha=load_model(c)
    root=ROOT/c["output_root"]
    if list(root.glob("*/manifest.json")): raise FileExistsError("protocol already frozen")
    commit=git("rev-parse","HEAD"); stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    names=git("ls-files","src","scripts").splitlines()+[CONFIG.relative_to(ROOT).as_posix(),PROTOCOL.relative_to(ROOT).as_posix(),
        "requirements.txt",c["model_path"],c["calibration_manifest"]]
    m={"experiment_run_id":f"calibrated_tasks_{stamp}_{commit[:12]}","source_git_commit":commit,"config":c,
       "model_sha256":model_sha,"input_sha256":{p:digest(ROOT/p) for p in names},
       "versions":{p:importlib.metadata.version(p) for p in ("metaworld","mujoco","numpy")}}
    m["manifest_id"]=manifest_digest(m); output=root/m["experiment_run_id"]; output.mkdir(parents=True,exist_ok=False)
    _write_json(output/"manifest.json",m); print(output/"manifest.json")


def plan(method,evidence,model):
    if method not in METHODS: raise ValueError("unknown calibrated-task baseline")
    if evidence and evidence.stop_reason!="PROGRAM_COMPLETE":
        return {"correction":[0.,0.,0.,0.],"fit":{"valid":False,"reason":"TERMINAL_PROBE","bias_in_command_units":None}}
    if not method.startswith("PRIOR_"): return online_decision(method,evidence)
    kind="affine" if method=="PRIOR_AFFINE" else "nearest"
    bias=infer_offset(model,evidence,method=kind)
    correction=estimate_planar_correction({"inference":{"estimated_drift_per_step":bias,"axis_response_gain":[1.,1.],"residual":0.}},
                                          allowed_magnitudes=DEFAULT_CORRECTION_MAGNITUDES).simultaneous_correction
    return {"correction":list(correction),"fit":{"valid":True,"reason":f"FROZEN_PRIOR_{kind.upper()}","bias_in_command_units":list(bias)}}


def summarize(rows,c):
    seeds=range(9100,9116)
    expected={(s,k,m) for s in seeds for k in c["conditions"] for m in METHODS}
    indexed={(r["seed"],r["condition_oracle"],r["method"]):r for r in rows}
    if len(rows)!=320 or set(indexed)!=expected: raise ValueError("incomplete/duplicate calibrated task population")
    metrics={}
    for method in METHODS:
        rs=[r for r in rows if r["method"]==method]; prior=method.startswith("PRIOR_")
        errors=[r["offset_error_oracle"] for r in rs if r["offset_error_oracle"] is not None]
        mean=statistics.fmean(r["total_steps"] for r in rs)
        metrics[method]={"successful":sum(r["success"] for r in rs),"mean_online_steps":mean,
            "offline_steps":2304 if prior else 0,"offline_resets":144 if prior else 0,
            "mean_amortized_steps":mean+(36 if prior else 0),"mean_amortized_resets":3.25 if prior else 1.,
            "success_equal_484_policy_steps":sum(r["success_equal_484_policy_steps"] for r in rs),
            "valid_fits":len(errors),"mean_offset_error_oracle":statistics.fmean(errors) if errors else None}
    contrasts={}
    for baseline in METHODS:
        if baseline=="PRIOR_AFFINE": continue
        cluster=[statistics.fmean(int(indexed[s,k,"PRIOR_AFFINE"]["success"])-int(indexed[s,k,baseline]["success"]) for k in c["conditions"]) for s in seeds]
        rng=random.Random(c["bootstrap_seed"])
        draws=sorted(statistics.fmean(rng.choices(cluster,k=16)) for _ in range(c["bootstrap_samples"]))
        contrasts[baseline]={"difference":statistics.fmean(cluster),"per_seed":cluster,
            "cluster_bootstrap_95":[draws[int(.025*(len(draws)-1))],draws[int(.975*(len(draws)-1))]]}
    gates={"evidence_utility":contrasts["CONT_NO_CORRECTION"]["cluster_bootstrap_95"][0]>0,
           "no_probe_count":metrics["PRIOR_AFFINE"]["successful"]>=metrics["NO_PROBE"]["successful"],
           "dynamic_count":metrics["PRIOR_AFFINE"]["successful"]>=metrics["CONT_DYNAMIC"]["successful"]}
    return {"methods":metrics,"affine_minus_baseline":contrasts,"gates":gates,"gate_passed":all(gates.values()),"independent_seed_clusters":16}


def run(path):
    check_clean(); m=load(path); c=m["config"]
    if git("rev-parse","HEAD")!=m["source_git_commit"]: raise ValueError("source commit mismatch")
    model,model_sha=load_model(c)
    if model_sha!=m["model_sha256"]: raise ValueError("model changed after task freeze")
    output=path.parent
    if (output/"status.json").exists(): raise FileExistsError("one-shot task run cannot restart")
    identity={k:m[k] for k in ("experiment_run_id","manifest_id","source_git_commit")}
    status={**identity,"status":"RUNNING","complete_units":0,"episodes":0,"physical_steps":0,"environment_resets":0,"api_calls":0,"memory_writes":0}
    _write_json(output/"status.json",status); rows=[]
    conditions={x.condition_id:x for x in get_conditions(0)}
    try:
        with gzip.open(output/"episodes.jsonl.gz","wt",encoding="utf-8") as handle:
            for seed in range(9100,9116):
                for index,condition in enumerate(c["conditions"]):
                    bias=conditions[condition].parameters["bias"]
                    noise_seed=int(np.random.SeedSequence([seed,index,0xC81]).generate_state(1)[0])
                    initial_hashes=set(); prefixes=set()
                    for method in METHODS:
                        episode_index=status["episodes"]+1
                        key={**identity,"episode_index":episode_index,"seed":seed,"condition_oracle":condition,"method":method,"model_sha256":model_sha}
                        env=create_push_environment(seed)
                        try:
                            host=LiveHost(env,BiasNoisePerturbation(bias,.05),seed,noise_seed); initial=host.current
                            initial_hashes.add(state_hash(initial.observation)); evidence=None
                            if method!="NO_PROBE":
                                evidence=collect_continuous(host.step,initial,symmetric_program(),remaining_budget=500,task_reserve=484)
                                prefixes.add(json.dumps(evidence.to_dict(),sort_keys=True))
                            handoff=host.current; probe_steps=evidence.steps if evidence else 0
                            probe={"initial":asdict(initial),"handoff":asdict(handoff),"evidence":evidence.to_dict() if evidence else None,
                                   "host_calls":host.calls,"rng_handoff":host.rng_hash()}
                            chosen=plan(method,evidence,model)
                            append(output/"decisions.jsonl",{**key,"probe":probe,"decision":chosen})
                            trace=[]; policy=create_push_policy(); first_success=0 if handoff.success else None
                            while not (host.current.success or host.current.terminated or host.current.truncated) and probe_steps+len(trace)<500:
                                before=host.current; before_rng=host.rng_hash()
                                command=np.asarray(policy.get_action(np.array(before.observation)),dtype=np.float32)+np.array(chosen["correction"],dtype=np.float32)
                                after=host.step(command)
                                trace.append({"before_hash":state_hash(before.observation),"after_hash":state_hash(after.observation),
                                    "rng_before":before_rng,"rng_after":host.rng_hash(),"host_calls":host.calls,"command":command.tolist(),
                                    "success":after.success,"terminated":after.terminated,"truncated":after.truncated})
                                if after.success: first_success=len(trace)
                            fit=chosen["fit"]
                            error=float(np.linalg.norm(np.array(fit["bias_in_command_units"])-bias[:2])) if fit and fit["valid"] else None
                            outcome={**key,"success":host.current.success,"success_equal_484_policy_steps":first_success is not None and first_success<=484,
                                "probe_steps":probe_steps,"task_steps":len(trace),"total_steps":probe_steps+len(trace),"environment_resets":host.resets,
                                "actuator_resets":1,"host_calls":host.calls,"initial_hash":state_hash(initial.observation),
                                "handoff_hash":state_hash(handoff.observation),"final_hash":state_hash(host.current.observation),"offset_error_oracle":error}
                            record={**key,"probe":probe,"decision":chosen,"task_trace":trace,"outcome":outcome}
                            handle.write(json.dumps(record)+"\n"); handle.flush(); rows.append(outcome)
                            status["episodes"]+=1; status["physical_steps"]+=outcome["total_steps"]; status["environment_resets"]+=host.resets
                        finally: env.close()
                    if len(initial_hashes)!=1 or len(prefixes)!=1: raise ValueError("paired initial state/probe mismatch")
                    status["complete_units"]+=1; _write_json(output/"status.json",status)
                    print(f"Completed {seed}/{condition}: {status['complete_units']}/64",flush=True)
        if status["physical_steps"]>160000: raise ValueError("physical task budget exceeded")
        result=summarize(rows,c); status["status"]="COMPLETED_FEASIBILITY_PASS" if result["gate_passed"] else "COMPLETED_FEASIBILITY_FAILED"
        _write_json(output/"summary.json",{**status,"statistics":result}); _write_json(output/"status.json",status)
        print(json.dumps({"status":status["status"],"gates":result["gates"]}))
    except BaseException as exc:
        status.update(status="INCOMPLETE",error_type=type(exc).__name__,error=str(exc)); _write_json(output/"status.json",status)
        raise


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__); g=p.add_mutually_exclusive_group(required=True)
    g.add_argument("--prepare",action="store_true"); g.add_argument("--manifest",type=Path); a=p.parse_args()
    prepare() if a.prepare else run(a.manifest.resolve())

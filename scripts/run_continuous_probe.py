"""One-shot continuous-probe baseline collection and artifact replay audit."""
from __future__ import annotations
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import random
import statistics
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
from scripts.run_evidence_persistence import git,digest,manifest_digest,check_clean
from scripts.run_probemem_acr_utility_stability import _write_json
from scripts.build_autoresearch_benchmark import get_conditions
from src.probe.continuous import StepObservation,ContinuousTransition,ContinuousEvidence,collect_continuous,symmetric_program
from src.probe.continuous_baselines import METHODS,decision
from src.probe.directional import run_symmetric_probes,estimate_planar_bias
from src.perturbations import BiasNoisePerturbation
from src.rollout import create_push_environment,create_push_policy
from src.task_metrics import extract_push_positions

CONFIG=ROOT/"configs/continuous_probe/development_v1.json"
PROTOCOL=ROOT/"docs/protocols/continuous_probe_development_v1.md"


def normalized(x):
    return json.loads(json.dumps(x))


def state_hash(observation):
    return hashlib.sha256(json.dumps(list(observation),separators=(",",":")).encode()).hexdigest()


def validate(c):
    if (c["seed_start"],c["num_seeds"],tuple(c["methods"]),c["conditions"],c["noise_std"],
        c["total_steps"],c["probe_steps"],c["post_probe_reserve"],c["maximum_physical_steps"],
        c["api_calls"],c["memory_writes"]) != (8700,8,METHODS,["fault_01","fault_02","fault_03","fault_04"],.05,500,16,484,80000,0,0):
        raise ValueError("frozen continuous-probe configuration mismatch")


def load_manifest(path):
    m=json.loads(path.read_text())
    validate(m["config"])
    if manifest_digest(m)!=m["manifest_id"]:
        raise ValueError("manifest mismatch")
    for name,sha in m["input_sha256"].items():
        if digest(ROOT/name)!=sha:
            raise ValueError(f"frozen input changed: {name}")
    return m


def prepare():
    check_clean()
    c=json.loads(CONFIG.read_text()); validate(c)
    root=ROOT/c["output_root"]
    if list(root.glob("*/manifest.json")):
        raise FileExistsError("protocol already prepared")
    commit=git("rev-parse","HEAD")
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    names=git("ls-files","src","scripts").splitlines()+[CONFIG.relative_to(ROOT).as_posix(),PROTOCOL.relative_to(ROOT).as_posix(),"requirements.txt"]
    m={"experiment_run_id":f"continuous_probe_{stamp}_{commit[:12]}","source_git_commit":commit,"config":c,
       "input_sha256":{n:digest(ROOT/n) for n in names},
       "versions":{p:importlib.metadata.version(p) for p in ("metaworld","mujoco","numpy")}}
    m["manifest_id"]=manifest_digest(m)
    output=root/m["experiment_run_id"]; output.mkdir(parents=True,exist_ok=False)
    _write_json(output/"manifest.json",m)
    print(output/"manifest.json")


class LiveHost:
    """One environment reset and one actuator reset; step preserves both states."""
    def __init__(self,env,fault,seed,noise_seed):
        self.env,self.fault=env,fault
        observation,_=env.reset(seed=seed)
        fault.reset(noise_seed)
        self.current=StepObservation(tuple(observation),False,False,False)
        self.calls=0
        self.resets=1

    def rng_hash(self):
        return hashlib.sha256(json.dumps(self.fault._rng.bit_generator.state,sort_keys=True).encode()).hexdigest()

    def step(self,command):
        if self.current.terminated or self.current.truncated or self.current.success:
            raise ValueError("cannot step an ended episode")
        acted=self.fault.apply(np.asarray(command,dtype=np.float32))
        observation,_,terminated,truncated,info=self.env.step(np.clip(acted,self.env.action_space.low,self.env.action_space.high))
        self.calls+=1
        self.current=StepObservation(tuple(observation),bool(terminated),bool(truncated),bool(info.get("success",False)))
        return self.current


def summarize(rows,c):
    expected={(s,k,m) for s in range(8700,8708) for k in c["conditions"] for m in METHODS}
    indexed={(r["seed"],r["condition_oracle"],r["method"]):r for r in rows}
    if set(indexed)!=expected or len(rows)!=len(expected):
        raise ValueError("incomplete/duplicate outcome population")
    metrics={}
    for method in METHODS:
        rs=[r for r in rows if r["method"]==method]
        errors=[r["offset_error_oracle"] for r in rs if r["offset_error_oracle"] is not None]
        metrics[method]={"successful":sum(r["success"] for r in rs),
            "success_equal_484_task_steps":sum(r["success_equal_484_task_steps"] for r in rs),
            "mean_total_steps":statistics.fmean(r["total_steps"] for r in rs),
            "environment_resets":sum(r["environment_resets"] for r in rs),
            "valid_fits":len(errors),"mean_offset_error_oracle":statistics.fmean(errors) if errors else None,
            "mean_probe_object_displacement":statistics.fmean(r["probe_object_displacement"] for r in rs),
            "probe_successes":sum(r["probe_success"] for r in rs)}
    contrasts={}
    for method in ("CONT_STATIC","CONT_DYNAMIC"):
        clusters=[statistics.fmean(int(indexed[s,k,method]["success"])-int(indexed[s,k,"CONT_NO_CORRECTION"]["success"])
                                   for k in c["conditions"]) for s in range(8700,8708)]
        rng=random.Random(c["bootstrap_seed"])
        draws=sorted(statistics.fmean(rng.choices(clusters,k=8)) for _ in range(c["bootstrap_samples"]))
        contrasts[method]={"difference":statistics.fmean(clusters),"per_seed":clusters,
            "cluster_interval_975":[draws[int(.0125*(len(draws)-1))],draws[int(.9875*(len(draws)-1))]]}
    passing=[m for m in contrasts if contrasts[m]["cluster_interval_975"][0]>0 and metrics[m]["successful"]>=metrics["NO_PROBE"]["successful"]]
    return {"methods":metrics,"contrasts_vs_cont_no_correction":contrasts,"passing_estimators":passing,
            "gate_passed":bool(passing),"independent_seed_clusters":8}


def run(path):
    check_clean(); m=load_manifest(path)
    if git("rev-parse","HEAD")!=m["source_git_commit"]:
        raise ValueError("source commit mismatch")
    output=path.parent; c=m["config"]
    if (output/"status.json").exists():
        raise FileExistsError("one-shot run cannot restart")
    identity={k:m[k] for k in ("experiment_run_id","manifest_id","source_git_commit")}
    status={**identity,"status":"RUNNING","complete_units":0,"physical_steps":0,"environment_resets":0,"api_calls":0,"memory_writes":0}
    _write_json(output/"status.json",status)
    conditions={x.condition_id:x for x in get_conditions(0)}
    rows=[]; sequence=0
    try:
        with (output/"events.jsonl").open("w",encoding="utf-8") as handle:
            def emit(kind,payload):
                nonlocal sequence
                sequence+=1
                row={**identity,"sequence":sequence,"kind":kind,**payload}
                handle.write(json.dumps(row)+"\n")
                if kind!="step": handle.flush()
                return sequence
            for seed in range(8700,8708):
                for condition_index,condition in enumerate(c["conditions"]):
                    bias=conditions[condition].parameters["bias"]
                    noise_seed=int(np.random.SeedSequence([seed,condition_index,0xC71]).generate_state(1)[0])
                    initial_hashes=set(); continuous_prefixes=set()
                    for method in METHODS:
                        key={"seed":seed,"condition_oracle":condition,"method":method}
                        reset_rows=None; inference=None; evidence=None
                        if method=="RESET_REFERENCE":
                            probe_env=create_push_environment(seed)
                            try:
                                group=run_symmetric_probes(lambda:create_push_environment(seed),seed=seed,
                                    perturbation_factory=lambda:BiasNoisePerturbation(bias,.05),magnitude=.2,steps=4,
                                    perturbation_seed=noise_seed,shared_env=probe_env)
                            finally: probe_env.close()
                            reset_rows=[r.to_dict() for r in group]
                            inference=estimate_planar_bias(group).to_dict()
                            if sum(r.steps for r in group)!=16: raise ValueError("reference probe incomplete")
                        env=create_push_environment(seed)
                        try:
                            host=LiveHost(env,BiasNoisePerturbation(bias,.05),seed,noise_seed)
                            initial=host.current
                            initial_hashes.add(state_hash(initial.observation))
                            if method.startswith("CONT_"):
                                evidence=collect_continuous(host.step,initial,symmetric_program(),remaining_budget=500,task_reserve=484)
                                continuous_prefixes.add(json.dumps(evidence.to_dict(),sort_keys=True))
                            probe_steps=evidence.steps if evidence else 16 if reset_rows else 0
                            handoff=host.current
                            _,initial_obj,_=extract_push_positions(np.array(initial.observation))
                            _,current_obj,_=extract_push_positions(np.array(handoff.observation))
                            displacement=float(np.linalg.norm(current_obj-initial_obj))
                            emit("probe",{**key,"initial":asdict(initial),"handoff":asdict(handoff),
                                "continuous":evidence.to_dict() if evidence else None,"reset_transitions":reset_rows,
                                "reset_inference":inference,"host_calls":host.calls,"rng_handoff":host.rng_hash()})
                            d=decision(method,evidence,inference)
                            decision_sequence=emit("decision",{**key,"decision":d})
                            policy=create_push_policy(); task_steps=0; first_success_task=0 if handoff.success else None
                            while not (host.current.success or host.current.terminated or host.current.truncated) and probe_steps+task_steps<500:
                                before=host.current; before_rng=host.rng_hash()
                                command=np.asarray(policy.get_action(np.array(before.observation)),dtype=np.float32)+np.array(d["correction"],dtype=np.float32)
                                after=host.step(command); task_steps+=1
                                emit("step",{**key,"decision_sequence":decision_sequence,"task_step":task_steps,
                                    "host_calls":host.calls,"before_hash":state_hash(before.observation),"after_hash":state_hash(after.observation),
                                    "rng_before":before_rng,"rng_after":host.rng_hash(),"command":command.tolist(),
                                    "success":after.success,"terminated":after.terminated,"truncated":after.truncated})
                                if after.success: first_success_task=task_steps
                            fit=d["fit"]
                            error=float(np.linalg.norm(np.array(fit["bias_in_command_units"])-bias[:2])) if fit and fit["valid"] else None
                            row={**key,"decision_sequence":decision_sequence,"success":host.current.success,
                                "success_equal_484_task_steps":first_success_task is not None and first_success_task<=484,
                                "probe_success":handoff.success,"probe_steps":probe_steps,"task_steps":task_steps,
                                "total_steps":probe_steps+task_steps,"environment_resets":5 if reset_rows else host.resets,
                                "actuator_resets":5 if reset_rows else 1,"host_calls":host.calls,
                                "initial_state_hash":state_hash(initial.observation),"handoff_hash":state_hash(handoff.observation),
                                "final_hash":state_hash(host.current.observation),"offset_error_oracle":error,
                                "probe_object_displacement":displacement}
                            emit("outcome",row); rows.append(row)
                            status["physical_steps"]+=row["total_steps"]; status["environment_resets"]+=row["environment_resets"]
                        finally: env.close()
                    if len(initial_hashes)!=1 or len(continuous_prefixes)!=1: raise ValueError("paired reset/prefix mismatch")
                    status["complete_units"]+=1; _write_json(output/"status.json",status)
                    print(f"Completed {seed}/{condition}: {status['complete_units']}/32",flush=True)
        if status["physical_steps"]>80000: raise ValueError("physical budget exceeded")
        summary=summarize(rows,c)
        status["status"]="COMPLETED_FEASIBILITY_PASS" if summary["gate_passed"] else "COMPLETED_FEASIBILITY_FAILED"
        _write_json(output/"summary.json",{**status,"statistics":summary}); _write_json(output/"status.json",status)
        print(json.dumps({"status":status["status"],"passing_estimators":summary["passing_estimators"]}))
    except BaseException as exc:
        status.update(status="INCOMPLETE",error_type=type(exc).__name__,error=str(exc)); _write_json(output/"status.json",status)
        raise


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    g=p.add_mutually_exclusive_group(required=True); g.add_argument("--prepare",action="store_true"); g.add_argument("--manifest",type=Path)
    args=p.parse_args()
    prepare() if args.prepare else run(args.manifest.resolve())

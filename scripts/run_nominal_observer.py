"""Frozen multi-task nominal-observer feasibility collection; no API or correction."""
import argparse
from dataclasses import asdict
from datetime import datetime,timezone
import gzip
import importlib.metadata
import inspect
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
from scripts.run_evidence_persistence import git,digest,manifest_digest,check_clean,append
from scripts.run_probemem_acr_utility_stability import _write_json
from scripts.run_continuous_probe import LiveHost,state_hash,normalized
from src.probe.continuous import ContinuousTransition,symmetric_program
from src.probe.frame_identification import NominalARX,canonical_hash
from src.probe.nominal_observer import NominalObserver,passive_affine_fit,mean_blocks
from src.perturbations import BiasNoisePerturbation
from src.rollout.task_registry import TASK_POLICIES,create_task_environment,create_task_policy

CONFIG=ROOT/"configs/nominal_observer/qualification_v1.json"
PROTOCOL=ROOT/"docs/protocols/nominal_observer_qualification_v1.md"
PROGRAMS=("POLICY_ONLY","PROBE_THEN_POLICY")


def validate(c):
    if (c["protocol_id"],c["seed_start"],c["num_seeds"],c["reserved_seeds"],tuple(c["tasks"]),tuple(c["programs"]),
        c["noise_std"],c["total_steps"],c["probe_steps"],c["block_size"],c["snapshot_steps"],
        c["maximum_physical_steps"],c["maximum_p90_episode_block_error"],c["minimum_scored_episodes_per_stratum"],
        c["legacy_offline_steps"],c["legacy_offline_resets"],c["api_calls"],c["memory_writes"],c["model_refits"]) != (
        "nominal_observer_qualification_v1",10000,16,[10016,10199],tuple(TASK_POLICIES),PROGRAMS,.05,500,16,4,
        [8,16,32,64,128,256],48000,.10,16,2304,144,0,0,0):
        raise ValueError("frozen observer-qualification configuration changed")


def policy_hashes(tasks):
    return {task:digest(Path(inspect.getfile(type(create_task_policy(task))))) for task in tasks}


def model(c):
    saved=json.loads((ROOT/c["model_path"]).read_text(encoding="utf-8"))
    if canonical_hash(saved["model"])!=c["model_sha256"]: raise ValueError("frozen nominal model mismatch")
    return NominalARX(**saved["model"])


def identity(m):
    return {key:m[key] for key in ("experiment_run_id","manifest_id","source_git_commit")}


def prepare():
    check_clean();c=json.loads(CONFIG.read_text());validate(c);model(c)
    root=ROOT/c["output_root"]
    if list(root.glob("*/manifest.json")): raise FileExistsError("observer protocol already frozen")
    commit=git("rev-parse","HEAD");stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    names=git("ls-files","src","scripts","tests").splitlines()+[
        CONFIG.relative_to(ROOT).as_posix(),PROTOCOL.relative_to(ROOT).as_posix(),"requirements.txt",c["model_path"]]
    m={"experiment_run_id":f"nominal_observer_{stamp}_{commit[:12]}","source_git_commit":commit,"config":c,
       "input_sha256":{name:digest(ROOT/name) for name in names},"policy_sha256":policy_hashes(c["tasks"]),
       "versions":{p:importlib.metadata.version(p) for p in ("metaworld","mujoco","numpy","gymnasium")}}
    m["manifest_id"]=manifest_digest(m);output=root/m["experiment_run_id"];output.mkdir(parents=True,exist_ok=False)
    _write_json(output/"manifest.json",m);print(output/"manifest.json")


def load(path):
    m=json.loads(path.read_text(encoding="utf-8"));validate(m["config"])
    if manifest_digest(m)!=m["manifest_id"]: raise ValueError("manifest identity changed")
    for name,sha in m["input_sha256"].items():
        if digest(ROOT/name)!=sha: raise ValueError(f"frozen source/model changed: {name}")
    if policy_hashes(m["config"]["tasks"])!=m["policy_sha256"]: raise ValueError("installed fixed policy changed")
    return m


def noise_seed(seed,task_index):
    return int(np.random.SeedSequence([seed,task_index,0x0B51]).generate_state(1)[0])


def population(c):
    return [(seed,task,program) for seed in range(c["seed_start"],c["seed_start"]+c["num_seeds"])
            for task in c["tasks"] for program in PROGRAMS]


def summarize(rows,c):
    if [(r["seed"],r["task"],r["program"]) for r in rows]!=population(c): raise ValueError("complete qualification population mismatch")
    strata={};gates={};snapshots={}
    for task in c["tasks"]:
        for program in PROGRAMS:
            key=f"{task}|{program}";selected=[r for r in rows if r["task"]==task and r["program"]==program]
            scores=[r["maximum_block_error"] for r in selected if r["maximum_block_error"] is not None]
            p90=float(np.quantile(scores,.9,method="linear")) if scores else None
            phases={}
            for phase in ("PROBE","MIXED","POLICY"):
                values=[block["nominal_mean_error_inf"] for r in selected for block in r["blocks"] if block["phase"]==phase]
                phases[phase]={"blocks":len(values),"mean_error":float(np.mean(values)) if values else None,
                               "p90_error":float(np.quantile(values,.9,method="linear")) if values else None}
            strata[key]={"episodes":16,"scored_episodes":len(scores),"p90_episode_max_error":p90,
                "maximum_episode_error":max(scores) if scores else None,"mean_episode_max_error":float(np.mean(scores)) if scores else None,
                "known_nominal_successes":sum(r["success"] for r in selected),"physical_steps":sum(r["total_steps"] for r in selected),
                "phase_block_descriptives":phases}
            gates[key]=len(scores)==16 and p90 is not None and p90<=c["maximum_p90_episode_block_error"]
            snapshots[key]={}
            for step in c["snapshot_steps"]:
                observed=[s for r in selected for s in r["snapshots"] if s["step"]==step]
                valid=[s for s in observed if s["fit"]["valid"]]
                errors=[s["nominal_identity_error_inf"] for s in valid]
                snapshots[key][str(step)]={"observed":len(observed),"missing_after_stop":16-len(observed),"valid_fits":len(valid),
                    "mean_identity_error_inf":float(np.mean(errors)) if errors else None,
                    "p90_identity_error_inf":float(np.quantile(errors,.9,method="linear")) if errors else None}
    return {"strata":strata,"gates":gates,"gate_passed":all(gates.values()),"passive_snapshots":snapshots,
        "independent_seed_clusters":16,"physical_observation_contract_qualified":False,"probability_guarantee":False,
        "no_measurement_cases":[{k:r[k] for k in ("seed","task","program")} for r in rows if r["maximum_block_error"] is None]}


def run(path):
    check_clean();m=load(path);c=m["config"];frozen=model(c)
    if git("rev-parse","HEAD")!=m["source_git_commit"]: raise ValueError("collection source commit mismatch")
    output=path.parent
    if (output/"status.json").exists(): raise FileExistsError("one-shot qualification cannot restart")
    status={**identity(m),"status":"RUNNING","episodes":0,"physical_steps":0,"environment_resets":0,
        "snapshots":0,"api_calls":0,"memory_writes":0,"nominal_model_refits":0}
    _write_json(output/"status.json",status);outcomes=[];initial_groups={}
    try:
        with gzip.open(output/"episodes.jsonl.gz","wt",encoding="utf-8") as handle:
            for seed,task,program in population(c):
                key={**identity(m),"episode_index":status["episodes"]+1,"seed":seed,"task":task,"program":program,
                     "model_sha256":c["model_sha256"]}
                env=create_task_environment(task,seed);host=None;trace=[];saved_snapshots=[];samples=[]
                try:
                    host=LiveHost(env,BiasNoisePerturbation([0.,0.,0.,0.],.05),seed,noise_seed(seed,c["tasks"].index(task)))
                    initial=host.current;observer=NominalObserver(frozen);policy=create_task_policy(task)
                    initial_groups.setdefault((seed,task),set()).add(state_hash(initial.observation))
                    commands=symmetric_program() if program=="PROBE_THEN_POLICY" else ()
                    def step(sent,phase,raw_policy=None):
                        before=host.current;before_rng=host.rng_hash();after=host.step(sent)
                        transition=ContinuousTransition(tuple(float(x) for x in sent),before.observation,after.observation)
                        inverse=observer.observe(transition,phase=phase)
                        if inverse: samples.append(inverse)
                        trace.append({"before":asdict(before),"after":asdict(after),"command":list(transition.command),
                            "phase":phase,"raw_policy":raw_policy,"host_calls":host.calls,"rng_before":before_rng,"rng_after":host.rng_hash(),
                            "inverse_sample":inverse.to_dict() if inverse else None})
                        if host.calls in c["snapshot_steps"]:
                            fit=normalized(passive_affine_fit(samples))
                            declaration={**key,"step":host.calls,"fit":fit,"samples_seen":len(samples),
                                "rng_hash":host.rng_hash(),"observation_hash":state_hash(host.current.observation)}
                            append(output/"snapshots.jsonl",declaration)  # precedes next step and evaluator matrix-error label
                            error=float(np.max(np.abs(np.asarray(fit["matrix"])-np.array([[1.,0.,0.],[0.,1.,0.]])))) if fit["valid"] else None
                            saved_snapshots.append({"step":host.calls,"fit":fit,"nominal_identity_error_inf":error})
                            status["snapshots"]+=1
                    for sent in commands:
                        if host.current.success or host.current.terminated or host.current.truncated: break
                        step(np.asarray(sent,dtype=np.float32),"PROBE")
                    probe_steps=host.calls
                    handoff={"host_calls":host.calls,"observation":asdict(host.current),"rng_hash":host.rng_hash()}
                    while not (host.current.success or host.current.terminated or host.current.truncated) and host.calls<500:
                        raw=np.asarray(policy.get_action(np.array(host.current.observation)),dtype=np.float32)
                        step(np.clip(raw,-1,1),"POLICY",raw.tolist())
                    blocks=mean_blocks(samples);score=max((b["nominal_mean_error_inf"] for b in blocks),default=None)
                    outcome={**key,"success":host.current.success,"total_steps":host.calls,"probe_steps":probe_steps,
                        "environment_resets":host.resets,"actuator_resets":1,"blocks":blocks,"maximum_block_error":score,
                        "inverse_samples":len(samples),"incomplete_block_samples":len(samples)%4,"snapshots":saved_snapshots,
                        "missing_snapshot_steps":[t for t in c["snapshot_steps"] if t>host.calls]}
                    record={**key,"initial":asdict(initial),"handoff":handoff,"trace":trace,"outcome":outcome}
                    handle.write(json.dumps(record,allow_nan=False)+"\n");handle.flush();outcomes.append(outcome)
                    status["episodes"]+=1;status["physical_steps"]+=host.calls;status["environment_resets"]+=host.resets
                except BaseException as exc:
                    append(output/"failed_episode.jsonl",{**key,"error_type":type(exc).__name__,"error":str(exc),"partial_trace":trace,
                        "partial_host_calls":host.calls if host else 0,"partial_environment_resets":host.resets if host else 0})
                    status["partial_physical_steps"]=host.calls if host else 0
                    status["partial_environment_resets"]=host.resets if host else 0
                    raise
                finally:env.close()
                _write_json(output/"status.json",status)
                if status["episodes"]%6==0:print(f"Completed seed {seed}: {status['episodes']}/96 episodes",flush=True)
        if any(len(values)!=1 for values in initial_groups.values()): raise ValueError("paired task initial states differ")
        if status["physical_steps"]>c["maximum_physical_steps"]:raise ValueError("physical budget exceeded")
        statistics=summarize(outcomes,c)
        status["status"]="COMPLETED_FEASIBILITY_PASS" if statistics["gate_passed"] else "COMPLETED_FEASIBILITY_FAILED"
        _write_json(output/"summary.json",{**status,"statistics":statistics});_write_json(output/"status.json",status)
        print(json.dumps({"status":status["status"],"gates":statistics["gates"]}))
    except BaseException as exc:
        status.update(status="INCOMPLETE",error_type=type(exc).__name__,error=str(exc));_write_json(output/"status.json",status)
        raise


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True)
    g.add_argument("--prepare",action="store_true");g.add_argument("--manifest",type=Path);a=p.parse_args()
    prepare() if a.prepare else run(a.manifest.resolve())

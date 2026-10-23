"""One-shot train/calibrate/qualify standard visible forward predictors."""
import argparse
from dataclasses import asdict
from datetime import datetime,timezone
import gzip
import importlib.metadata
import json
from pathlib import Path
import sys
from time import perf_counter_ns
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import numpy as np
from scripts.run_evidence_persistence import git,digest,manifest_digest,check_clean
from scripts.run_probemem_acr_utility_stability import _write_json
from scripts.run_continuous_probe import LiveHost,state_hash,normalized
from scripts.run_nominal_observer import policy_hashes,model,identity
from src.probe.continuous import ContinuousTransition,symmetric_program
from src.probe.forward_prediction import METHODS,ForwardQuery,ForwardHistory,TrainingSample,fit_models,Predictors,conformal_radius
from src.perturbations import BiasNoisePerturbation
from src.rollout.task_registry import create_task_environment,create_task_policy

CONFIG=ROOT/"configs/forward_prediction/baselines_v1.json"
PROTOCOL=ROOT/"docs/protocols/forward_prediction_baselines_v1.md"
STAGES=("TRAIN","CALIBRATION","QUALIFICATION")
PROGRAMS=("POLICY_ONLY","PROBE_THEN_POLICY")
TASKS=("push-v3","reach-v3","door-open-v3")


def validate(c):
    expected={"protocol_id":"forward_prediction_baselines_v1","stages":dict(zip(STAGES,(10200,10300,10400))),
        "num_seeds_per_stage":16,"reserved_seeds":[10416,10599],"tasks":list(TASKS),"programs":list(PROGRAMS),
        "methods":list(METHODS),"noise_std":.05,"total_steps":500,"probe_steps":16,"history_warmup_steps":2,
        "ridge":.001,"nearest_neighbors":16,"alpha":.1,"maximum_radius_m":.001,"minimum_covered_per_stratum":15,
        "maximum_physical_steps":144000,"maximum_environment_resets":288,"legacy_offline_steps":2304,"legacy_offline_resets":144,
        "model_path":"outputs/frame_evidence/development_v1/frame_evidence_20261014T041345Z_82a3dd1469d4/nominal_arx.json",
        "model_sha256":"f9f8f8b772e94d0639655b508c0038950b5fca0e85d21f03be0ad1454cf08019",
        "output_root":"outputs/forward_prediction/baselines_v1","api_calls":0,"memory_writes":0,"policy_weight_updates":0}
    if c!=expected:raise ValueError("frozen forward-prediction configuration changed")


def population(c,stage):
    if stage not in STAGES:raise ValueError("unknown stage")
    return [(seed,task,program) for seed in range(c["stages"][stage],c["stages"][stage]+16) for task in TASKS for program in PROGRAMS]


def noise_seed(seed,task):
    return int(np.random.SeedSequence([seed,TASKS.index(task),0xF001]).generate_state(1)[0])


def prepare():
    check_clean();c=json.loads(CONFIG.read_text());validate(c);model(c)
    root=ROOT/c["output_root"]
    if list(root.glob("*/manifest.json")):raise FileExistsError("forward protocol already frozen")
    commit=git("rev-parse","HEAD");stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    names=git("ls-files","src","scripts","tests").splitlines()+[
        CONFIG.relative_to(ROOT).as_posix(),PROTOCOL.relative_to(ROOT).as_posix(),"requirements.txt",c["model_path"]]
    m={"experiment_run_id":f"forward_prediction_{stamp}_{commit[:12]}","source_git_commit":commit,"config":c,
       "input_sha256":{n:digest(ROOT/n) for n in names},"policy_sha256":policy_hashes(TASKS),
       "versions":{p:importlib.metadata.version(p) for p in ("metaworld","mujoco","numpy","gymnasium")}}
    m["manifest_id"]=manifest_digest(m);output=root/m["experiment_run_id"];output.mkdir(parents=True,exist_ok=False)
    _write_json(output/"manifest.json",m);print(output/"manifest.json")


def load(path):
    m=json.loads(path.read_text(encoding="utf-8"));validate(m["config"])
    if manifest_digest(m)!=m["manifest_id"]:raise ValueError("manifest changed")
    if any(digest(ROOT/n)!=sha for n,sha in m["input_sha256"].items()):raise ValueError("frozen input changed")
    if policy_hashes(TASKS)!=m["policy_sha256"]:raise ValueError("installed fixed policy changed")
    return m


def collect_stage(m,stage,output,status,emit,predictors=None,model_sha=None,calibration_sha=None):
    if (stage=="TRAIN")!=(predictors is None) or stage=="QUALIFICATION" and calibration_sha is None:
        raise ValueError("stage/model/calibration order mismatch")
    samples={task:[] for task in TASKS};outcomes=[];initials={}
    with gzip.open(output/(stage+".jsonl.gz"),"wt",encoding="utf-8") as handle:
        for index,(seed,task,program) in enumerate(population(m["config"],stage),1):
            key={**identity(m),"stage":stage,"episode_index":96*STAGES.index(stage)+index,"seed":seed,"task":task,"program":program}
            env=create_task_environment(task,seed);host=None;trace=[];declaration=None
            try:
                host=LiveHost(env,BiasNoisePerturbation([0.,0.,0.,0.],.05),seed,noise_seed(seed,task))
                initial=host.current;history=ForwardHistory(initial.observation);policy=create_task_policy(task)
                initials.setdefault((seed,task),set()).add(state_hash(initial.observation));errors={name:[] for name in METHODS}
                def step(sent,phase,raw=None):
                    nonlocal declaration
                    before=host.current;query=history.request(sent)
                    predictions=predictors[task].predict(query) if query is not None and predictors is not None else None
                    declaration=emit({**key,"step":host.calls+1,"command":list(history.pending),"phase":phase,
                        "observation_sha256":state_hash(before.observation),"rng_hash":host.rng_hash(),
                        "query":asdict(query) if query else None,"predictions":predictions,"model_sha256":model_sha,
                        "calibration_sha256":calibration_sha})
                    # This durable declaration exists before the sole physical execution.
                    after=host.step(declaration["command"]);after_ns=perf_counter_ns()
                    target=history.observe(ContinuousTransition(tuple(declaration["command"]),before.observation,after.observation))
                    if query is not None and stage=="TRAIN":samples[task].append(TrainingSample(query,target))
                    if predictions:
                        for name,value in predictions.items():errors[name].append(float(np.max(np.abs(np.asarray(value)-target))))
                    trace.append({"before":asdict(before),"after":asdict(after),"raw_policy":raw,"rng_after":host.rng_hash(),
                                  "prediction_sequence":declaration["sequence"],"after_ns":after_ns,"target_xy":list(target)})
                commands=symmetric_program() if program=="PROBE_THEN_POLICY" else ()
                for sent in commands:
                    if host.current.success or host.current.terminated or host.current.truncated:break
                    step(np.asarray(sent,dtype=np.float32),"PROBE")
                probe_steps=host.calls;handoff={"host_calls":host.calls,"observation":asdict(host.current),"rng_hash":host.rng_hash()}
                while not(host.current.success or host.current.terminated or host.current.truncated) and host.calls<500:
                    raw=np.asarray(policy.get_action(np.array(host.current.observation)),dtype=np.float32)
                    step(np.clip(raw,-1,1),"POLICY",raw.tolist())
                outcome={**key,"success":host.current.success,"total_steps":host.calls,"probe_steps":probe_steps,
                    "environment_resets":host.resets,"actuator_resets":1,"prediction_steps":max(host.calls-2,0) if predictors else 0,
                    "maximum_errors":{name:max(values,default=None) for name,values in errors.items()},
                    "rmse_inf":{name:float(np.sqrt(np.mean(np.square(values)))) if values else None for name,values in errors.items()}}
                record={**key,"initial":asdict(initial),"handoff":handoff,"trace":trace,"outcome":outcome}
                handle.write(json.dumps(record,allow_nan=False)+"\n");handle.flush();outcomes.append(outcome)
                status["episodes"]+=1;status["physical_steps"]+=host.calls;status["environment_resets"]+=host.resets
                _write_json(output/"status.json",status)
            except BaseException as exc:
                failure={**key,"error_type":type(exc).__name__,"error":str(exc),"partial_trace":trace,"pending_declaration":declaration,
                    "completed_host_calls":host.calls if host else 0,"completed_resets":host.resets if host else 0,
                    "unconfirmed_reset_or_step_attempt":True}
                _write_json(output/"failed_episode.json",failure)
                status["partial_physical_steps"]=failure["completed_host_calls"];status["partial_environment_resets"]=failure["completed_resets"]
                raise
            finally:env.close()
            if index%6==0:print(f"{stage}: {index}/96 episodes",flush=True)
    if any(len(v)!=1 for v in initials.values()):raise ValueError("paired initial state changed")
    return outcomes,samples


def calibration(m,rows,model_sha,last_sequence):
    radii={}
    for task in TASKS:
        for program in PROGRAMS:
            selected=[r for r in rows if r["task"]==task and r["program"]==program]
            if len(selected)!=16:raise ValueError("incomplete calibration group")
            radii[task+"|"+program]={name:conformal_radius([r["maximum_errors"][name] for r in selected]) for name in METHODS}
    return {**identity(m),"model_sha256":model_sha,"last_calibration_prediction_sequence":last_sequence,
            "alpha":.1,"radii":radii,"exchangeability_verified":False,"physical_response_qualified":False}


def summarize(m,rows,calibrated):
    result={};gates={name:True for name in METHODS}
    for task in TASKS:
        for program in PROGRAMS:
            key=task+"|"+program;selected=[r for r in rows if r["task"]==task and r["program"]==program]
            if len(selected)!=16:raise ValueError("incomplete qualification group")
            result[key]={}
            for name in METHODS:
                scores=[r["maximum_errors"][name] for r in selected];finite=[x for x in scores if x is not None]
                radius=calibrated["radii"][key][name]["radius"]
                covered=sum(x is not None and radius is not None and x<=radius for x in scores)
                passing=radius is not None and radius<=.001 and covered>=15 and len(finite)==16
                gates[name]=gates[name] and passing
                result[key][name]={"observed_episodes":len(finite),"covered":covered,"denominator":16,"radius_m":radius,
                    "mean_episode_max_error_m":float(np.mean(finite)) if finite else None,
                    "p90_episode_max_error_m":float(np.quantile(finite,.9,method="linear")) if finite else None,
                    "worst_episode_error_m":max(finite,default=None),"mean_rmse_inf_m":float(np.mean([r["rmse_inf"][name] for r in selected if r["rmse_inf"][name] is not None])) if finite else None,
                    "prediction_steps":sum(r["prediction_steps"] for r in selected),"precision_and_coverage_gate":passing}
    contrasts={}
    for name in METHODS[1:]:
        paired=[]
        for seed in range(10400,10416):
            selected=[r for r in rows if r["seed"]==seed]
            complete=all(r["maximum_errors"][name] is not None and r["maximum_errors"]["LEGACY_ARX"] is not None for r in selected)
            paired.append(float(np.mean([r["maximum_errors"][name]-r["maximum_errors"]["LEGACY_ARX"] for r in selected])) if complete else None)
        interval=None;difference=None
        if all(x is not None for x in paired):
            rng=np.random.default_rng(0xF002);draws=np.mean(rng.choice(paired,size=(10000,16),replace=True),axis=1)
            interval=np.quantile(draws,[.025,.975],method="linear").tolist();difference=float(np.mean(paired))
        contrasts[name]={"per_seed_mean_max_error_difference_m":paired,"mean_difference_m":difference,
            "paired_seed_bootstrap_95_m":interval,"missing_seed_contrasts":sum(x is None for x in paired)}
    return {"strata":result,"method_gates":gates,"passing_forward_models":[k for k,v in gates.items() if v],
        "contrasts_vs_legacy":contrasts,"independent_test_seed_clusters":16,
        "physical_response_qualified":False,"probability_guarantee":False,"control_gain_evaluated":False}


def run(path):
    check_clean();m=load(path);output=path.parent
    if git("rev-parse","HEAD")!=m["source_git_commit"]:raise ValueError("collection source mismatch")
    if (output/"status.json").exists():raise FileExistsError("one-shot forward collection cannot restart")
    status={**identity(m),"status":"RUNNING","stage":"TRAIN","episodes":0,"physical_steps":0,"environment_resets":0,"api_calls":0,"memory_writes":0}
    _write_json(output/"status.json",status);sequence=0
    try:
        with (output/"predictions.jsonl").open("x",encoding="utf-8") as declarations:
            def emit(record):
                nonlocal sequence
                sequence+=1;record={**record,"sequence":sequence,"before_ns":perf_counter_ns()}
                declarations.write(json.dumps(record,allow_nan=False)+"\n");declarations.flush()
                return record
            training,samples=collect_stage(m,"TRAIN",output,status,emit)
            fitted={task:fit_models(samples[task]) for task in TASKS};del samples
            saved={**identity(m),"training_artifact_sha256":digest(output/"TRAIN.jsonl.gz"),
                   "last_training_prediction_sequence":sequence,"models":fitted}
            _write_json(output/"models.json",saved);model_sha=digest(output/"models.json")
            saved=json.loads((output/"models.json").read_text());frozen=model(m["config"])
            predictors={task:Predictors(saved["models"][task],frozen) for task in TASKS}
            status["stage"]="CALIBRATION"
            calibration_rows,_=collect_stage(m,"CALIBRATION",output,status,emit,predictors,model_sha)
            calibrated=calibration(m,calibration_rows,model_sha,sequence)
            calibrated["calibration_artifact_sha256"]=digest(output/"CALIBRATION.jsonl.gz")
            _write_json(output/"calibration.json",calibrated);calibration_sha=digest(output/"calibration.json")
            calibrated=json.loads((output/"calibration.json").read_text());status["stage"]="QUALIFICATION"
            qualification,_=collect_stage(m,"QUALIFICATION",output,status,emit,predictors,model_sha,calibration_sha)
        if digest(output/"models.json")!=model_sha or digest(output/"calibration.json")!=calibration_sha:raise ValueError("frozen fitted artifacts changed")
        if status["physical_steps"]>144000 or status["environment_resets"]!=288 or status["episodes"]!=288:raise ValueError("collection budget/population mismatch")
        statistics=summarize(m,qualification,calibrated)
        status.update(status="COMPLETED_FEASIBILITY_PASS" if statistics["passing_forward_models"] else "COMPLETED_FEASIBILITY_FAILED",stage="COMPLETE")
        costs={stage:{"physical_steps":sum(r["total_steps"] for r in rows),"environment_resets":96,
                     "successes":sum(r["success"] for r in rows),"probe_steps":sum(r["probe_steps"] for r in rows)}
               for stage,rows in zip(STAGES,(training,calibration_rows,qualification))}
        _write_json(output/"summary.json",{**status,"statistics":statistics,"stage_costs":costs,"model_sha256":model_sha,"calibration_sha256":calibration_sha})
        _write_json(output/"status.json",status);print(json.dumps({"status":status["status"],"method_gates":statistics["method_gates"]}))
    except BaseException as exc:
        status.update(status="INCOMPLETE",error_type=type(exc).__name__,error=str(exc));_write_json(output/"status.json",status);raise


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True)
    g.add_argument("--prepare",action="store_true");g.add_argument("--manifest",type=Path);a=p.parse_args()
    prepare() if a.prepare else run(a.manifest.resolve())

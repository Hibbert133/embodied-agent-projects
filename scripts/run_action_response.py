"""One-shot chronological response-validation simulation, with fixed policies."""
from __future__ import annotations
import argparse
from contextlib import ExitStack
from dataclasses import asdict
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
from time import perf_counter_ns

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
from scripts.run_evidence_persistence import git,digest,manifest_digest,check_clean
from scripts.run_continuous_probe import LiveHost,state_hash,normalized
from src.rollout.task_registry import create_task_environment,create_task_policy
from scripts.run_nominal_observer import policy_hashes
from src.operator_perturbations_v1 import AffineNoisePerturbation
from src.probe.continuous import ContinuousTransition,symmetric_program
from src.probe.forward_prediction import ForwardHistory
from src.probe.operator_identification import OperatorSample,infer_operator,identity_controller,encode_controller,affine_controller
from src.probe.action_response_validity import CachedPoint,residual_design,action_envelope,assess,choose_primitive,PRIMITIVES,forecast

TASKS=("push-v3","reach-v3","door-open-v3")
SCENARIOS=("STATIONARY","MIXED")
METHODS=("NO_PROBE","FIXED8","FIXED16","FIXED8_WIDE","FIXED16_WIDE","CACHE_ONLY","PERIODIC2","PERIODIC3",
         "RECENT_WINDOW","RESIDUAL_CUSUM","G_OPTIMAL","RESPONSE_SET","RESPONSE_POINT","RESPONSE_GEOMETRY","RESPONSE_NO_COST","ORACLE16")
GUARDED=("G_OPTIMAL","RESPONSE_SET","RESPONSE_POINT","RESPONSE_GEOMETRY","RESPONSE_NO_COST")
CONFIG=ROOT/"configs/action_response/development_v1.json"
PROTOCOL=ROOT/"docs/protocols/action_response_development_v1.md"
IDENTITY=("experiment_run_id","manifest_id","source_git_commit")


def identity(value):return {k:value[k] for k in IDENTITY}


def write_json(path,value):
    path.write_bytes((json.dumps(normalized(value),indent=2,ensure_ascii=False,allow_nan=False)+"\n").encode("utf-8"))


def validate(c):
    expected={"protocol_id":"action_response_development_v1","seed_start":10800,"streams":8,"episodes_per_stream_task":6,
        "reserved_seeds":[10944,11199],"tasks":list(TASKS),"scenarios":list(SCENARIOS),"methods":list(METHODS),
        "noise_std":.05,"noise_namespace":42803,"operator_generation_seed":42801,"total_steps":500,
        "prefix_steps":6,"maximum_micro_steps":16,"reserved_task_steps":32,"maximum_physical_steps":2304000,
        "maximum_environment_resets":4608,"bootstrap_samples":10000,"bootstrap_seed":20261014,
        "forward_offline_steps":21010,"forward_offline_resets":288,"api_calls":0,"memory_writes":0,"policy_weight_updates":0}
    if any(c.get(k)!=v for k,v in expected.items()):raise ValueError("frozen response protocol changed")
    if c["forward_model_sha256"]!="b3f2d7e69316dba65e722d74d49df25c7d651043e78bf4c0f6e1d37f1e599c80":raise ValueError("frozen model bank changed")


def load_bank(c):
    path=ROOT/c["forward_model_path"];audit_path=ROOT/c["forward_audit_path"]
    audit=json.loads(audit_path.read_text(encoding="utf-8"));saved=json.loads(path.read_text(encoding="utf-8"))
    if audit["integrity"]!="PASSED" or digest(path)!=c["forward_model_sha256"] or audit["model_sha256"]!=c["forward_model_sha256"]:
        raise ValueError("matching complete forward bank required")
    if any(saved[k]!=audit[k] for k in IDENTITY) or audit["physical_steps"]!=21010 or audit["environment_resets"]!=288:
        raise ValueError("forward source identity/cost changed")
    if any(digest(path.parent/name)!=sha for name,sha in audit["artifact_sha256"].items()):raise ValueError("forward source bytes changed")
    return {task:saved["models"][task]["LINEAR_ARX"] for task in TASKS},path.parent,audit


def nominal_reference_profile(models,source,audit):
    """Only the first six CALIBRATION steps, never qualification/outcome scores."""
    declarations={}
    with (source/"predictions.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            row=json.loads(line)
            if row.get("stage")=="CALIBRATION" and row["step"]<=6:declarations[row["sequence"]]=row
    scores={task:{} for task in TASKS};included=[];seen=set()
    with gzip.open(source/"CALIBRATION.jsonl.gz","rt",encoding="utf-8") as handle:
        for line in handle:
            record=json.loads(line);key=(record["seed"],record["task"],record["program"])
            if record["stage"]!="CALIBRATION" or key in seen or not 10300<=record["seed"]<10316:raise ValueError("calibration-only population changed")
            seen.add(key);trace=record["trace"][:6]
            if len(trace)!=6:raise ValueError("initial calibration prefix missing")
            errors=[]
            for index,row in enumerate(trace,1):
                declaration=declarations[row["prediction_sequence"]]
                if declaration["step"]!=index or any(declaration[k]!=record[k] for k in ("seed","task","program")):raise ValueError("source prediction prefix changed")
                if index<3:continue
                target=np.array(row["after"]["observation"][:2])-row["before"]["observation"][:2]
                prediction=np.array(declaration["predictions"]["LINEAR_ARX"])
                if not np.allclose(target,row["target_xy"],atol=1e-14,rtol=1e-12):raise ValueError("source visible target changed")
                errors.append(target-prediction)
            score=float(np.mean(np.square(errors)))
            scores[record["task"]].setdefault(record["seed"],[]).append(score)
            included.append({"seed":record["seed"],"task":record["task"],"program":record["program"],"prefix_residual_squared_mean":score})
    expected={(s,t,p) for s in range(10300,10316) for t in TASKS for p in ("POLICY_ONLY","PROBE_THEN_POLICY")}
    if seen!=expected or any(len(rows)!=2 for task in scores.values() for rows in task.values()):raise ValueError("source calibration clusters incomplete")
    rms={task:max(1e-6,float(np.sqrt(np.mean([max(values) for values in rows.values()])))) for task,rows in scores.items()}
    return {"source_identity":identity(audit),"source_audit_sha256":digest(ROOT/json.loads(CONFIG.read_text())["forward_audit_path"]),
        "source_calibration_sha256":digest(source/"CALIBRATION.jsonl.gz"),"source_predictions_sha256":digest(source/"predictions.jsonl"),
        "procedure":"Initial six steps; real history warmup two; paired-program max squared RMS within each nominal calibration seed, then RMS over sixteen seed clusters.",
        "rms_m":rms,"included_prefixes":included,"confidence_qualified":False,"probability_guarantee":False,
        "scale_is_not_a_verified_error_bound":True,"new_environment_steps":0}


def operators(c):
    rng=np.random.default_rng(c["operator_generation_seed"]);rows=[]
    def rotation(angle):return np.array([[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]])
    for stream in range(8):
        angle=rng.uniform(-.6,.6);gain=rng.uniform(.7,1.35,2);shear=rng.uniform(-.2,.2)
        matrix=rotation(angle)@np.diag(gain)@np.array([[-1. if stream%2 else 1.,shear],[0.,1.]])
        bias=rng.uniform(-.18,.18,2)
        family=("BIAS_SHIFT","GAIN_COUPLING","PARITY_CHANGE")[stream%3]
        if stream%3==0:
            changed=matrix.copy();changed_bias=bias.copy();changed_bias[stream%2]=-.22 if bias[stream%2]>=0 else .22
        elif stream%3==1:
            changed=rotation(.55 if stream%2 else -.55)@matrix@np.diag([.85,1.1]);changed_bias=rng.uniform(-.18,.18,2)
        else:
            changed=matrix@np.diag([-1.,1.]);changed_bias=rng.uniform(-.18,.18,2)
        gradual=rotation(.25 if stream%2 else -.25)@changed@np.diag([1.08,.92]);gradual_bias=np.clip(changed_bias+rng.uniform(-.04,.04,2),-.24,.24)
        abrupt=int(rng.integers(1,4));middle=int(rng.integers(abrupt+1,5))
        states=[]
        for name,m,b in (("A",matrix,bias),("B",changed,changed_bias),("MID",(changed+gradual)/2,(changed_bias+gradual_bias)/2),("C",gradual,gradual_bias)):
            singular=np.linalg.svd(m,compute_uv=False)
            if np.max(np.abs(m))>2 or np.max(np.abs(b))>.3 or singular[-1]<.35 or singular[0]>2:raise ValueError("registered evaluator operator domain failure")
            states.append({"id":name,"matrix_xy":m.tolist(),"bias_xy":b.tolist()})
        rows.append({"stream":stream,"family_oracle":family,"abrupt_episode_oracle":abrupt,"middle_episode_oracle":middle,
            "states_oracle":states,"schedule_oracle":["A" if e<abrupt else "B" if e<middle else "MID" if e==middle else "C" for e in range(6)]})
    return rows


def environment_seed(stream,task,episode):return 10800+stream*18+TASKS.index(task)*6+episode
def actuator_seed(seed,task):return int(np.random.SeedSequence([seed,TASKS.index(task),42803]).generate_state(1)[0])


def prepare():
    check_clean();c=json.loads(CONFIG.read_text());validate(c);models,source,audit=load_bank(c)
    profile=nominal_reference_profile(models,source,audit);bank=operators(c)
    parent=ROOT/c["output_root"]
    if list(parent.glob("*/manifest.json")):raise FileExistsError("response protocol already frozen")
    commit=git("rev-parse","HEAD");stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    names=git("ls-files","src","scripts","tests").splitlines()+[CONFIG.relative_to(ROOT).as_posix(),PROTOCOL.relative_to(ROOT).as_posix(),
        "requirements.txt",c["forward_model_path"],c["forward_audit_path"],(source/"CALIBRATION.jsonl.gz").relative_to(ROOT).as_posix(),
        (source/"predictions.jsonl").relative_to(ROOT).as_posix()]
    profile_bytes=(json.dumps(normalized(profile),indent=2,ensure_ascii=False)+"\n").encode("utf-8")
    m={"experiment_run_id":f"action_response_{stamp}_{commit[:12]}","source_git_commit":commit,"config":c,
       "input_sha256":{name:digest(ROOT/name) for name in names},"policy_sha256":policy_hashes(TASKS),"operators_oracle":bank,
       "nominal_profile_sha256":hashlib.sha256(profile_bytes).hexdigest(),
       "versions":{p:importlib.metadata.version(p) for p in ("metaworld","mujoco","gymnasium","numpy","scipy")}}
    m["manifest_id"]=manifest_digest(m);out=parent/m["experiment_run_id"];out.mkdir(parents=True,exist_ok=False)
    (out/"nominal_profile.json").write_bytes(profile_bytes);write_json(out/"manifest.json",m);print(out/"manifest.json")


def load(path):
    m=json.loads(path.read_text(encoding="utf-8"));validate(m["config"])
    if manifest_digest(m)!=m["manifest_id"] or any(digest(ROOT/name)!=sha for name,sha in m["input_sha256"].items()):raise ValueError("frozen response source changed")
    if operators(m["config"])!=m["operators_oracle"] or policy_hashes(TASKS)!=m["policy_sha256"]:raise ValueError("operator bank/policy changed")
    if digest(path.parent/"nominal_profile.json")!=m["nominal_profile_sha256"]:raise ValueError("nominal scale changed before execution")
    return m


def cached(value):return CachedPoint(**value) if value is not None else None
def saved_cache(value):return normalized(asdict(value)) if value is not None else None


def agent_validation(method,model,previous,samples,sigma,micro_steps,remaining):
    if method not in GUARDED or type(previous) is not CachedPoint:raise ValueError("agent validation needs its own earlier point")
    if type(remaining) is not int or not 0<=remaining<=500 or any(s.step>500-remaining for s in samples):raise ValueError("future samples or invalid current budget")
    if type(micro_steps) is not int or not 0<=micro_steps<=16:raise ValueError("invalid micro-probe count")
    design=residual_design(model,previous,samples,mask_responses=method=="RESPONSE_GEOMETRY")
    envelope=action_envelope(model,previous)
    mode="GAUSSIAN" if method=="G_OPTIMAL" else "POINT" if method=="RESPONSE_POINT" else "SET"
    assessment=assess(design,envelope,sigma,mode)
    base={"assessment":assessment,"residual_groups":normalized(asdict(design)),"envelope":normalized(envelope),"physical_response_qualified":False}
    force=method=="RESPONSE_NO_COST" and micro_steps<16
    if not force and assessment["status"]=="COMPATIBLE":return {**base,"action":"REUSE_CACHE","program_id":None}
    if not force and assessment["status"] in ("INCOMPATIBLE","CONTRACT_REJECTED"):
        return {**base,"action":"REFRESH_FIXED16","program_id":None}
    if assessment["status"]=="NUMERICAL_FAILURE":return {**base,"action":"STOP_NUMERICAL","program_id":None}
    if micro_steps>=16:return {**base,"action":"REFRESH_FIXED16","program_id":None}
    acquired=choose_primitive(design,envelope,sigma,remaining_steps=remaining,reserved_task_steps=32,
                             mode="GAUSSIAN" if method=="G_OPTIMAL" or force and assessment["status"]=="CONTRACT_REJECTED" else "SET")
    return {**base,**acquired}


def run_episode(m,key,operator,state,model,sigma,emit):
    if key["method"] not in METHODS:raise ValueError("unregistered causal method")
    env=create_task_environment(key["task"],key["seed"]);host=None;trace=[];decisions=[];samples=[];fit=None
    cache_before=saved_cache(state["cache"]);version_before=state["version"];previous=state["cache"]
    try:
        host=LiveHost(env,AffineNoisePerturbation(operator["matrix_xy"],operator["bias_xy"],.05),key["seed"],actuator_seed(key["seed"],key["task"]))
        history=ForwardHistory(host.current.observation);initial=host.current;policy=create_task_policy(key["task"])
        controller=previous.controller if previous is not None else identity_controller();last=None;micro=0;reused=False;refresh=False
        def ended():return host.current.success or host.current.terminated or host.current.truncated
        def choose(action,**values):
            nonlocal last
            declaration={**key,"at_host_calls":host.calls,"observation_sha256":state_hash(host.current.observation),"rng_hash":host.rng_hash(),
                "action":action,"controller":normalized(controller),"cache_snapshot":saved_cache(state["cache"]),"cache_version":state["version"],**values}
            last=emit("DECISION",declaration);decisions.append(last)
            last=json.loads(json.dumps(last,allow_nan=False))
            return last
        def step(command,phase,raw=None):
            before=host.current;sent=np.asarray(command,dtype=np.float32);query=history.request(sent)
            reference=state["cache"] if state["cache"] is not None else CachedPoint(((1.,0.),(0.,1.)),(0.,0.))
            prediction=forecast(model,reference,query).tolist() if query is not None else None
            intent=emit("STEP_INTENT",{**key,"at_host_calls":host.calls,"decision_sequence":last["sequence"],"phase":phase,
                "before_observation_sha256":state_hash(before.observation),"rng_before":host.rng_hash(),"command":sent.tolist(),"raw_policy":raw,
                "forecast_xy":prediction,"forecast_point":saved_cache(reference),"cache_version":state["version"],
                "forward_query":normalized(asdict(query)) if query is not None else None})
            # Actual execution consumes the durable intent JSON, not a new choice.
            intent=json.loads(json.dumps(intent,allow_nan=False));after=host.step(intent["command"])
            transition=ContinuousTransition(tuple(intent["command"]),before.observation,after.observation)
            target=history.observe(transition)
            if query is not None:samples.append(OperatorSample(host.calls,query,target))
            trace.append({"intent_sequence":intent["sequence"],"decision_sequence":last["sequence"],"phase":phase,"command":intent["command"],
                "raw_policy":raw,"before":asdict(before),"after":asdict(after),"rng_before":intent["rng_before"],"rng_after":host.rng_hash(),
                "host_calls":host.calls,"intent_saved_ns":intent["saved_ns"],"completed_ns":perf_counter_ns(),"target_xy":list(target),
                "forecast_xy":prediction,"forecast_point":intent["forecast_point"]})
        def program(commands,phase):
            for command in commands:
                if ended() or host.calls>=500:break
                step(command,phase)
        def policy_step(phase="POLICY"):
            raw=np.asarray(policy.get_action(np.array(host.current.observation)),dtype=np.float32)
            sent=encode_controller(last["controller"],raw)
            step(sent,phase,raw.tolist())
        def fresh(length=16,magnitude=.2):
            nonlocal controller,fit,refresh
            if ended():return
            if host.calls+length+32>500:
                controller=None;choose("STOP_BUDGET");return
            start=host.calls;refresh=True
            choose("REQUEST_FIXED_PROBE",probe_steps=length,magnitude=magnitude)
            program(symmetric_program(magnitude,steps_per_direction=length//4),"FIXED_PROBE")
            if ended():return
            fit=infer_operator(model,tuple(s for s in samples if s.step>start))
            if fit["valid"]:
                state["cache"]=CachedPoint(fit["matrix_xy"],fit["bias_xy"]);state["version"]+=1
                state["last_update_episode"]=key["episode_in_stream"];controller=state["cache"].controller
                choose("RUN_NEW_POINT",fit=fit)
            else:
                controller=None;choose("STOP_POINT_FIT",fit=fit)
        method=key["method"];episode=key["episode_in_stream"]
        if method=="ORACLE16":
            choose("ORACLE_EVALUATOR_PROBE",oracle_only=True,probe_steps=16,magnitude=.2)
            program(symmetric_program(),"FIXED_PROBE")
            controller=affine_controller(np.array(operator["matrix_xy"],dtype=np.float32),np.array(operator["bias_xy"],dtype=np.float32),source="ORACLE_EVALUATOR")
            choose("RUN_ORACLE_EVALUATOR",oracle_only=True)
        elif method.startswith("FIXED"):
            fresh(8 if method.startswith("FIXED8") else 16,.4 if method.endswith("WIDE") else .2)
        elif method=="NO_PROBE":
            controller=identity_controller();choose("RUN_UNCORRECTED")
        elif method=="RECENT_WINDOW":
            choose("RUN_RECENT_POINT" if previous else "RUN_UNCORRECTED")
        elif previous is None or method.startswith("PERIODIC") and episode%int(method[-1])==0:
            fresh()
        elif method in ("CACHE_ONLY","PERIODIC2","PERIODIC3"):
            reused=True;choose("REUSE_CACHE_WITHOUT_VALIDATION")
        else:
            choose("REQUEST_VISIBLE_PREFIX",prefix_steps=6)
            for _ in range(6):
                if ended():break
                policy_step("PREFIX_POLICY")
            if not ended():
                if method=="RESIDUAL_CUSUM":
                    design=residual_design(model,previous,tuple(samples))
                    # Registered scalar Page-style positive residual accumulation;
                    # this is not claimed to be Bayesian or optimal change detection.
                    error=[]
                    for sample in samples:
                        residual=np.array(sample.displacement)-forecast(model,previous,sample.query)
                        error.append(float(np.max(np.abs(residual)))/sigma)
                    accumulated=0.
                    for score in error:accumulated=max(0.,accumulated+score-1.)
                    decision={"action":"REFRESH_FIXED16" if accumulated>4 else "REUSE_CACHE","residual_scores":error,
                              "cusum_score":accumulated,"threshold":4.,"reference_rms_m":sigma,"physical_response_qualified":False}
                    choose(decision["action"],validation=decision)
                    if decision["action"]=="REUSE_CACHE":reused=True
                    else:fresh()
                elif method in GUARDED:
                    while not ended():
                        decision=agent_validation(method,model,previous,tuple(samples),sigma,micro,500-host.calls)
                        if decision["action"].startswith("STOP"):controller=None
                        choose(decision["action"],validation=decision,micro_steps=micro)
                        action=decision["action"]
                        if action=="REUSE_CACHE":reused=True;break
                        if action in ("REFRESH_FIXED16","REFRESH_NUMERICAL_DESIGN"):
                            fresh();break
                        if action.startswith("STOP"):
                            break
                        before_micro=host.calls;program(PRIMITIVES[decision["program_id"]],"MICRO_PROBE");micro+=host.calls-before_micro
                    if ended():choose("EPISODE_ENDED_DURING_EVIDENCE")
                else:raise ValueError("unknown causal method")
        if last is None:choose("EPISODE_ALREADY_ENDED")
        task_start=host.calls
        while not ended() and host.calls<500 and last["controller"] is not None:
            if method=="RECENT_WINDOW" and host.calls and host.calls%16==0:
                fit=infer_operator(model,tuple(samples[-64:]))
                if fit["valid"]:
                    state["cache"]=CachedPoint(fit["matrix_xy"],fit["bias_xy"]);state["version"]+=1
                    state["last_update_episode"]=episode;controller=state["cache"].controller
                    choose("RUN_RECENT_POINT",fit=fit)
                else:choose("REJECT_UPDATE_RETAIN_POINT",fit=fit)
            policy_step()
        outcome={**key,"success":host.current.success,"total_steps":host.calls,"environment_resets":1,"actuator_resets":1,
            "prefix_steps":sum(r["phase"]=="PREFIX_POLICY" for r in trace),"micro_steps":sum(r["phase"]=="MICRO_PROBE" for r in trace),
            "fixed_probe_steps":sum(r["phase"]=="FIXED_PROBE" for r in trace),"policy_steps":sum(r["phase"]=="POLICY" for r in trace),
            "stopped":last["controller"] is None,"reused_cache":reused,"requested_fixed_refresh":refresh,
            "point_fit_failures":sum(d.get("fit") is not None and not d["fit"]["valid"] for d in decisions),
            "cache_updates":state["version"]-version_before,"final_action":last["action"],"task_start_calls":task_start}
        return {**key,"initial":asdict(initial),"initial_rng_hash":trace[0]["rng_before"] if trace else host.rng_hash(),
            "trace":trace,"decisions":decisions,"cache_before":cache_before,"cache_after":saved_cache(state["cache"]),
            "cache_version_before":version_before,"cache_version_after":state["version"],"outcome":outcome}
    except BaseException as exc:
        raise EpisodeFailure({**key,"error_type":type(exc).__name__,"error":str(exc),"partial_trace":trace,"decisions":decisions,
            "completed_steps":host.calls if host else 0,"completed_resets":host.resets if host else 0,"unconfirmed_attempt":True}) from exc
    finally:env.close()


class EpisodeFailure(RuntimeError):
    def __init__(self,value):self.record=value;super().__init__(value["error"])


def summarize(m,rows):
    if len(rows)!=4608:raise ValueError("full response population required")
    by={(r["stream"],r["task"],r["scenario"],r["episode_in_stream"],r["method"]):r for r in rows}
    expected={(s,t,c,e,p) for s in range(8) for t in TASKS for c in SCENARIOS for e in range(6) for p in METHODS}
    if set(by)!=expected:raise ValueError("duplicate/missing chronological units")
    metrics={}
    for method in METHODS:
        selected=[r for r in rows if r["method"]==method];offline=0 if method in ("NO_PROBE","ORACLE16") else 21010
        metrics[method]={"successes":sum(r["success"] for r in selected),"denominator":288,"stops":sum(r["stopped"] for r in selected),
            "mean_online_steps":float(np.mean([r["total_steps"] for r in selected])),
            "mean_probe_steps":float(np.mean([r["micro_steps"]+r["fixed_probe_steps"] for r in selected])),
            "reused_cases":sum(r["reused_cache"] for r in selected),"point_fit_failures":sum(r["point_fit_failures"] for r in selected),
            "cache_updates":sum(r["cache_updates"] for r in selected),"offline_steps":offline,"offline_resets":0 if not offline else 288,
            "mean_amortized_steps":float(np.mean([r["total_steps"] for r in selected]))+offline/288,
            "success_by_task":{t:sum(r["success"] for r in selected if r["task"]==t) for t in TASKS},
            "success_by_scenario":{c:sum(r["success"] for r in selected if r["scenario"]==c) for c in SCENARIOS}}
    contrasts={}
    for baseline in ("FIXED16","FIXED8_WIDE","FIXED16_WIDE","PERIODIC2","G_OPTIMAL"):
        values=[float(np.mean([int(by[s,t,c,e,"RESPONSE_SET"]["success"])-int(by[s,t,c,e,baseline]["success"]) for t in TASKS for c in SCENARIOS for e in range(6)])) for s in range(8)]
        cost=[float(np.mean([by[s,t,c,e,"RESPONSE_SET"]["total_steps"]-by[s,t,c,e,baseline]["total_steps"] for t in TASKS for c in SCENARIOS for e in range(6)])) for s in range(8)]
        rng=np.random.default_rng(20261014);indices=rng.integers(0,8,(10000,8))
        contrasts[baseline]={"success_difference":float(np.mean(values)),"stream_success_difference":values,
            "stream_bootstrap_99_success":np.quantile(np.array(values)[indices].mean(axis=1),[.005,.995]).tolist(),
            "mean_step_difference":float(np.mean(cost)),"stream_bootstrap_99_steps":np.quantile(np.array(cost)[indices].mean(axis=1),[.005,.995]).tolist()}
    candidate=metrics["RESPONSE_SET"]
    competing=("NO_PROBE","FIXED8","FIXED16","FIXED8_WIDE","FIXED16_WIDE","CACHE_ONLY","PERIODIC2","PERIODIC3","RECENT_WINDOW","RESIDUAL_CUSUM","G_OPTIMAL")
    dominated=[b for b in competing if metrics[b]["successes"]>=candidate["successes"] and metrics[b]["mean_amortized_steps"]<candidate["mean_amortized_steps"]]
    competitive=not dominated and all(candidate["successes"]>=metrics[b]["successes"] and candidate["mean_amortized_steps"]<metrics[b]["mean_amortized_steps"] for b in ("FIXED16","FIXED8_WIDE","FIXED16_WIDE","G_OPTIMAL"))
    return {"methods":metrics,"primary_contrasts":contrasts,"dominating_admissible_baselines":dominated,"strong_baseline_competitive_gate":competitive,
        "independent_stream_clusters":8,"physical_response_qualified":False,"probability_guarantee":False,"algorithm_novelty_established":False}


def run(path):
    check_clean();m=load(path);models,_,_=load_bank(m["config"]);profile=json.loads((path.parent/"nominal_profile.json").read_text())
    if git("rev-parse","HEAD")!=m["source_git_commit"]:raise ValueError("source changed before one-shot response run")
    out=path.parent
    if (out/"status.json").exists():raise FileExistsError("one-shot response experiment cannot restart")
    status={**identity(m),"status":"RUNNING","episodes":0,"physical_steps":0,"environment_resets":0,"api_calls":0,"memory_writes":0}
    write_json(out/"status.json",status);sequence=0;outcomes=[]
    try:
        with ExitStack() as stack:
            events=stack.enter_context(gzip.open(out/"events.jsonl.gz","wt",encoding="utf-8"))
            handles={p:stack.enter_context(gzip.open(out/("episodes_"+p+".jsonl.gz"),"wt",encoding="utf-8")) for p in METHODS}
            def emit(kind,row):
                nonlocal sequence
                sequence+=1;event={**row,"event":kind,"sequence":sequence,"saved_ns":perf_counter_ns()}
                events.write(json.dumps(normalized(event),allow_nan=False)+"\n");events.flush();return normalized(event)
            for stream in range(8):
                operator_bank=m["operators_oracle"][stream]
                for task in TASKS:
                    for scenario in SCENARIOS:
                        for method in METHODS:
                            state={"cache":None,"version":0,"last_update_episode":None}
                            for episode in range(6):
                                seed=environment_seed(stream,task,episode)
                                label="A" if scenario=="STATIONARY" else operator_bank["schedule_oracle"][episode]
                                operator=next(o for o in operator_bank["states_oracle"] if o["id"]==label)
                                key={**identity(m),"episode_index":len(outcomes)+1,"stream":stream,"task":task,"scenario":scenario,
                                     "method":method,"episode_in_stream":episode,"seed":seed,"operator_id_oracle":label}
                                record=run_episode(m,key,operator,state,models[task],profile["rms_m"][task],emit)
                                handles[method].write(json.dumps(normalized(record),allow_nan=False)+"\n");handles[method].flush()
                                outcomes.append(record["outcome"]);status["episodes"]+=1;status["physical_steps"]+=record["outcome"]["total_steps"];status["environment_resets"]+=1
                                write_json(out/"status.json",status)
                        print(f"Completed stream={stream} task={task} scenario={scenario}: {status['episodes']}/4608",flush=True)
        stats=summarize(m,outcomes)
        if status["physical_steps"]>2304000:raise ValueError("collection physical budget exceeded")
        status["status"]="COMPLETED_COMPETITIVE_PASS" if stats["strong_baseline_competitive_gate"] else "COMPLETED_COMPETITIVE_FAILED"
        write_json(out/"status.json",status);write_json(out/"summary.json",{**status,"statistics":stats})
        print(json.dumps({"status":status["status"],"episodes":status["episodes"],"physical_steps":status["physical_steps"]}))
    except BaseException as exc:
        status.update(status="INCOMPLETE",error_type=type(exc).__name__)
        if isinstance(exc,EpisodeFailure):
            write_json(out/"failed_episode.json",exc.record)
            status.update(partial_completed_steps=exc.record["completed_steps"],partial_completed_resets=exc.record["completed_resets"],unconfirmed_attempt=True)
        write_json(out/"status.json",status);raise


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--prepare",action="store_true");p.add_argument("--manifest",type=Path);a=p.parse_args()
    if a.prepare:prepare()
    elif a.manifest:run(a.manifest.resolve())
    else:p.error("choose --prepare or --manifest")

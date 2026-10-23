"""Prospective unknown-affine task bridge using saved point-controller choices."""
import argparse
from contextlib import ExitStack
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
from scripts.run_nominal_observer import policy_hashes,identity
from scripts.run_calibrated_tasks import load_model as legacy_load,plan as legacy_plan
from src.probe.continuous import ContinuousTransition,ContinuousEvidence,symmetric_program
from src.probe.operator_identification import visible_samples,infer_operator,affine_controller,identity_controller,encode_controller
from src.operator_perturbations_v1 import AffineNoisePerturbation
from src.rollout.task_registry import create_task_environment,create_task_policy

CONFIG=ROOT/"configs/forward_operator/task_utility_v1.json"
PROTOCOL=ROOT/"docs/protocols/forward_operator_task_utility_v1.md"
METHODS=("NO_PROBE","PROBE8_NO_CORRECTION","PROBE16_NO_CORRECTION","DYNAMIC_OLS16","PRIOR_AFFINE16","PRIOR_NEAREST16",
         "FWD_LINEAR8","FWD_LINEAR16","FWD_QUADRATIC8","FWD_QUADRATIC16","PASSIVE_LINEAR","ORACLE16")
TASKS=("push-v3","reach-v3","door-open-v3")
OPERATORS=("NOMINAL","GAIN_COUPLED","ROTATED_GAIN","REFLECTED_SHEAR")
POINT_METHODS=("FWD_LINEAR8","FWD_LINEAR16","FWD_QUADRATIC8","FWD_QUADRATIC16","PASSIVE_LINEAR")


def validate(c):
    values=(c["protocol_id"],c["seed_start"],c["num_seeds"],c["reserved_seeds"],tuple(c["tasks"]),tuple(c["methods"]),
            c["noise_std"],c["total_steps"],c["maximum_physical_steps"],c["maximum_environment_resets"],
            c["passive_update_period"],c["passive_history_samples"],c["optimizer_max_nfev"],c["bootstrap_samples"],c["bootstrap_seed"],
            c["forward_prior_steps"],c["forward_prior_resets"],c["legacy_prior_steps"],c["legacy_prior_resets"],
            c["api_calls"],c["memory_writes"],c["policy_weight_updates"],c["physical_response_qualified"])
    if values!=("forward_operator_task_utility_v1",10600,8,[10608,10799],TASKS,METHODS,.05,500,576000,1152,
                16,64,64,10000,20261014,21010,288,2304,144,0,0,0,False):raise ValueError("frozen operator task configuration changed")
    matrices=[[[1,0],[0,1]],[[.75,.25],[-.15,1.2]],[[.9583626120567514,-.4814520185216386],[.7221780277824578,.6389084080378343]],[[-.8,.2],[.15,.9]]]
    biases=[[0,0],[.14,-.14],[-.18,0],[0,-.198]]
    expected=[{"id":name,"matrix_xy":a,"bias_xy":b} for name,a,b in zip(OPERATORS,matrices,biases)]
    if c["operators_oracle"]!=expected:raise ValueError("frozen evaluator operator population changed")


def load_priors(c):
    if digest(ROOT/c["forward_model_path"])!=c["forward_model_sha256"]:raise ValueError("frozen forward model changed")
    audit=json.loads((ROOT/c["forward_audit_path"]).read_text());saved=json.loads((ROOT/c["forward_model_path"]).read_text())
    if audit["integrity"]!="PASSED" or audit["model_sha256"]!=c["forward_model_sha256"] or any(saved[k]!=audit[k] for k in identity(audit)):
        raise ValueError("matching forward source audit required")
    source=(ROOT/c["forward_model_path"]).parent
    if audit["physical_steps"]!=21010 or audit["environment_resets"]!=288 or any(digest(source/name)!=sha for name,sha in audit["artifact_sha256"].items()):
        raise ValueError("forward source collection/provenance changed")
    old=json.loads((ROOT/"configs/calibrated_tasks/development_v1.json").read_text());legacy,sha=legacy_load(old)
    if sha!=c["legacy_model_sha256"] or digest(ROOT/c["legacy_model_path"])!=sha:raise ValueError("legacy model changed")
    return {"forward":saved["models"],"legacy":legacy}


def prepare():
    check_clean();c=json.loads(CONFIG.read_text());validate(c);load_priors(c)
    root=ROOT/c["output_root"]
    if list(root.glob("*/manifest.json")):raise FileExistsError("operator task protocol already frozen")
    commit=git("rev-parse","HEAD");stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    refs=[CONFIG.relative_to(ROOT).as_posix(),PROTOCOL.relative_to(ROOT).as_posix(),"requirements.txt",
          c["forward_model_path"],c["forward_audit_path"],c["legacy_model_path"],"configs/calibrated_tasks/development_v1.json"]
    refs.append(json.loads((ROOT/"configs/calibrated_tasks/development_v1.json").read_text())["calibration_manifest"])
    names=git("ls-files","src","scripts","tests").splitlines()+refs
    m={"experiment_run_id":f"forward_operator_{stamp}_{commit[:12]}","source_git_commit":commit,"config":c,
       "input_sha256":{name:digest(ROOT/name) for name in names},"policy_sha256":policy_hashes(TASKS),
       "versions":{p:importlib.metadata.version(p) for p in ("metaworld","mujoco","gymnasium","numpy","scipy")}}
    m["manifest_id"]=manifest_digest(m);output=root/m["experiment_run_id"];output.mkdir(parents=True,exist_ok=False)
    _write_json(output/"manifest.json",m);print(output/"manifest.json")


def load(path):
    m=json.loads(path.read_text(encoding="utf-8"));validate(m["config"])
    if manifest_digest(m)!=m["manifest_id"]:raise ValueError("manifest identity changed")
    if any(digest(ROOT/name)!=sha for name,sha in m["input_sha256"].items()):raise ValueError("frozen task input changed")
    if policy_hashes(TASKS)!=m["policy_sha256"]:raise ValueError("installed policy changed")
    return m


def noise_seed(seed,task,operator_index):return int(np.random.SeedSequence([seed,TASKS.index(task),operator_index,0xF091]).generate_state(1)[0])


def probe_program(method):
    if method not in METHODS:raise ValueError("unknown task method")
    if method in ("NO_PROBE","PASSIVE_LINEAR"):return ()
    return symmetric_program(steps_per_direction=2 if method.endswith("8") or method=="PROBE8_NO_CORRECTION" else 4)


def population(c):return [(seed,task,operator,method) for seed in range(10600,10608) for task in TASKS for operator in OPERATORS for method in METHODS]


def choose_agent_plan(method,task,transitions,final,priors,previous=None):
    """No seed, condition, actual perturbation object or future outcome argument."""
    if method not in METHODS or method=="ORACLE16":raise ValueError("agent cannot use evaluator method")
    previous=identity_controller() if previous is None else previous
    if previous["source"]=="ORACLE_EVALUATOR":raise ValueError("Oracle controller cannot enter agent history")
    if final.success or final.terminated or final.truncated:
        return {"status":"EPISODE_ALREADY_ENDED","controller":previous,"fit":None,"physical_response_qualified":False}
    if method in ("NO_PROBE","PROBE8_NO_CORRECTION","PROBE16_NO_CORRECTION"):
        return {"status":"READY","controller":identity_controller(),"fit":None,"physical_response_qualified":False}
    if method in ("DYNAMIC_OLS16","PRIOR_AFFINE16","PRIOR_NEAREST16"):
        evidence=ContinuousEvidence(tuple(transitions),final,"PROGRAM_COMPLETE",16)
        name={"DYNAMIC_OLS16":"CONT_DYNAMIC","PRIOR_AFFINE16":"PRIOR_AFFINE","PRIOR_NEAREST16":"PRIOR_NEAREST"}[method]
        chosen=legacy_plan(name,evidence,priors["legacy"])
        controller={"source":"LEGACY_OFFSET","matrix_xy":np.eye(2).tolist(),"offset":chosen["correction"]}
        return {"status":"REGISTERED_LEGACY_FALLBACK" if chosen["fit"] and not chosen["fit"]["valid"] else "READY",
                "controller":controller,"fit":chosen["fit"],"physical_response_qualified":False}
    samples=visible_samples(transitions);kind="LINEAR_ARX" if "LINEAR" in method else "QUADRATIC_STATE"
    if method=="PASSIVE_LINEAR":samples=samples[-64:]
    fit=infer_operator(priors["forward"][task][kind],samples)
    if not fit["valid"]:
        return {"status":"UPDATE_REJECTED_RETAIN_PRIOR" if method=="PASSIVE_LINEAR" else "ABSTAIN_POINT_FIT",
                "controller":previous if method=="PASSIVE_LINEAR" else None,"fit":fit,"physical_response_qualified":False}
    return {"status":"READY_POINT_ESTIMATE","controller":affine_controller(fit["matrix_xy"],fit["bias_xy"]),"fit":fit,"physical_response_qualified":False}


def evaluator_plan(operator):
    return {"status":"ORACLE_EVALUATOR_ONLY","controller":affine_controller(np.array(operator["matrix_xy"],dtype=np.float32),np.array(operator["bias_xy"],dtype=np.float32),source="ORACLE_EVALUATOR"),
            "fit":None,"physical_response_qualified":False,"oracle_only":True}


def run_episode(m,key,operator,priors,emit):
    env=create_task_environment(key["task"],key["seed"]);host=None;trace=[];transitions=[];decisions=[];last=None;pending=None
    try:
        host=LiveHost(env,AffineNoisePerturbation(operator["matrix_xy"],operator["bias_xy"]),key["seed"],noise_seed(key["seed"],key["task"],OPERATORS.index(operator["id"])))
        initial=host.current;policy=create_task_policy(key["task"]);method=key["method"];program=probe_program(method)
        if len(program)>500:raise ValueError("probe exceeds remaining budget")
        def step(sent,phase,raw=None,decision_sequence=None):
            before=host.current;before_rng=host.rng_hash();before_ns=perf_counter_ns();after=host.step(sent)
            row=ContinuousTransition(tuple(float(x) for x in sent),before.observation,after.observation);transitions.append(row)
            trace.append({"before":asdict(before),"after":asdict(after),"command":list(row.command),"phase":phase,"raw_policy":raw,
                "rng_before":before_rng,"rng_after":host.rng_hash(),"host_calls":host.calls,"before_ns":before_ns,"after_ns":perf_counter_ns(),
                "decision_sequence":decision_sequence})
        for sent in program:
            if host.current.success or host.current.terminated or host.current.truncated:break
            step(np.array(sent,dtype=np.float32),"PROBE")
        probe_steps=host.calls;handoff={"host_calls":host.calls,"observation":asdict(host.current),"rng_hash":host.rng_hash()}
        def choose():
            nonlocal last,pending
            begin=perf_counter_ns()
            if method=="ORACLE16":chosen=evaluator_plan(operator)
            elif method=="PASSIVE_LINEAR" and not transitions:chosen={"status":"INITIAL_UNCORRECTED","controller":identity_controller(),"fit":None,"physical_response_qualified":False}
            else:chosen=choose_agent_plan(method,key["task"],transitions,host.current,priors,last["choice"]["controller"] if last else None)
            pending={**key,"at_host_calls":host.calls,"observation_sha256":state_hash(host.current.observation),"rng_hash":host.rng_hash(),
                     "choice":normalized(chosen),"fit_elapsed_ms":(perf_counter_ns()-begin)/1e6}
            last=emit(pending);decisions.append(last)
            # The executor consumes this JSON round trip, exactly what was saved.
            last=json.loads(json.dumps(last,allow_nan=False))
        choose()
        while not(host.current.success or host.current.terminated or host.current.truncated) and host.calls<500 and last["choice"]["controller"] is not None:
            if method=="PASSIVE_LINEAR" and host.calls and host.calls%16==0 and last["at_host_calls"]!=host.calls:choose()
            raw=np.asarray(policy.get_action(np.array(host.current.observation)),dtype=np.float32)
            sent=encode_controller(last["choice"]["controller"],raw)
            step(sent,"POLICY",raw.tolist(),last["sequence"])
        latest=last["choice"];fit=latest["fit"];parameter_error=None
        controller=latest["controller"]
        if controller is not None and controller["source"]=="ESTIMATED_AFFINE":
            inferred=np.linalg.inv(np.array(controller["matrix_xy"]));bias=-inferred@np.array(controller["offset"][:2])
            truth=np.column_stack((np.array(operator["matrix_xy"],dtype=np.float32),np.array(operator["bias_xy"],dtype=np.float32)))
            parameter_error=float(np.max(np.abs(np.column_stack((inferred,bias))-truth)))
        outcome={**key,"success":host.current.success,"probe_steps":probe_steps,"task_steps":host.calls-probe_steps,"total_steps":host.calls,
            "environment_resets":host.resets,"actuator_resets":1,"stopped_point_fit":latest["controller"] is None,
            "invalid_fit_choices":sum(d["choice"]["fit"] is not None and not d["choice"]["fit"].get("valid",False) for d in decisions),
            "controller_choices":len(decisions),"final_status":latest["status"],"parameter_error_oracle":parameter_error}
        return {**key,"initial":asdict(initial),"handoff":handoff,"trace":trace,"decisions":decisions,"outcome":outcome}
    except BaseException as exc:
        failure={**key,"error_type":type(exc).__name__,"error":str(exc),"partial_trace":trace,"pending_decision":pending,
                 "completed_host_calls":host.calls if host else 0,"completed_resets":host.resets if host else 0,"unconfirmed_reset_or_step_attempt":True}
        raise EpisodeFailure(failure) from exc
    finally:env.close()


class EpisodeFailure(RuntimeError):
    def __init__(self,record):super().__init__(record["error"]);self.record=record


def summarize(m,rows):
    c=m["config"];expected=population(c)
    if [(r["seed"],r["task"],r["operator_oracle"],r["method"]) for r in rows]!=expected:raise ValueError("complete task population required")
    indexed={(r["seed"],r["task"],r["operator_oracle"],r["method"]):r for r in rows};metrics={}
    for method in METHODS:
        selected=[r for r in rows if r["method"]==method];forward=method in POINT_METHODS;legacy=method.startswith("PRIOR_")
        offline=21010 if forward else 2304 if legacy else 0;resets=288 if forward else 144 if legacy else 0
        mean=float(np.mean([r["total_steps"] for r in selected]))
        metrics[method]={"successes":sum(r["success"] for r in selected),"denominator":96,"mean_online_steps":mean,
            "mean_probe_steps":float(np.mean([r["probe_steps"] for r in selected])),"stopped_point_fits":sum(r["stopped_point_fit"] for r in selected),
            "invalid_fit_choices":sum(r["invalid_fit_choices"] for r in selected),"offline_steps":offline,"offline_resets":resets,
            "mean_amortized_steps":mean+offline/96,"mean_amortized_resets":1+resets/96,
            "task_successes":{task:sum(r["success"] for r in selected if r["task"]==task) for task in TASKS},
            "operator_successes":{op:sum(r["success"] for r in selected if r["operator_oracle"]==op) for op in OPERATORS}}
    contrasts={};useful=[];dominated={}
    for method in POINT_METHODS:
        baseline="NO_PROBE" if method=="PASSIVE_LINEAR" else "PROBE8_NO_CORRECTION" if method.endswith("8") else "PROBE16_NO_CORRECTION"
        paired=[float(np.mean([int(indexed[s,t,o,method]["success"])-int(indexed[s,t,o,baseline]["success"]) for t in TASKS for o in OPERATORS])) for s in range(10600,10608)]
        rng=np.random.default_rng(20261014);draws=np.mean(rng.choice(paired,size=(10000,8),replace=True),axis=1)
        interval=np.quantile(draws,[.005,.995],method="linear").tolist()
        passing=interval[0]>0 and metrics[method]["successes"]>=metrics["NO_PROBE"]["successes"]
        contrasts[method]={"baseline":baseline,"difference":float(np.mean(paired)),"per_seed":paired,"seed_cluster_bootstrap_99":interval,"point_task_bridge_gate":passing}
        if passing:useful.append(method)
        dominated[method]=[other for other in POINT_METHODS if other!=method and metrics[other]["successes"]>=metrics[method]["successes"] and metrics[other]["mean_amortized_steps"]<metrics[method]["mean_amortized_steps"]]
    return {"methods":metrics,"matched_motion_contrasts":contrasts,"useful_point_methods":useful,"dominated_by_same_prior_methods":dominated,
            "independent_seed_clusters":8,"physical_response_qualified":False,"probability_guarantee":False,"algorithm_novelty_established":False}


def run(path):
    check_clean();m=load(path);priors=load_priors(m["config"]);output=path.parent
    if git("rev-parse","HEAD")!=m["source_git_commit"]:raise ValueError("collection source mismatch")
    if (output/"status.json").exists():raise FileExistsError("one-shot operator task run cannot restart")
    status={**identity(m),"status":"RUNNING","episodes":0,"physical_steps":0,"environment_resets":0,"api_calls":0,"memory_writes":0}
    _write_json(output/"status.json",status);sequence=0;outcomes=[];initials={}
    try:
        with ExitStack() as stack:
            handles={method:stack.enter_context(gzip.open(output/("episodes_"+method+".jsonl.gz"),"wt",encoding="utf-8")) for method in METHODS}
            choices=stack.enter_context((output/"decisions.jsonl").open("x",encoding="utf-8"))
            def emit(record):
                nonlocal sequence
                sequence+=1;record={**record,"sequence":sequence,"saved_ns":perf_counter_ns()}
                choices.write(json.dumps(record,allow_nan=False)+"\n");choices.flush();return record
            for index,(seed,task,operator,method) in enumerate(population(m["config"]),1):
                key={**identity(m),"episode_index":index,"seed":seed,"task":task,"operator_oracle":operator,"method":method}
                injected=m["config"]["operators_oracle"][OPERATORS.index(operator)]
                record=run_episode(m,key,injected,priors,emit);handle=handles[method]
                handle.write(json.dumps(record,allow_nan=False)+"\n");handle.flush();outcome=record["outcome"];outcomes.append(outcome)
                initials.setdefault((seed,task,operator),set()).add(state_hash(record["initial"]["observation"]))
                status["episodes"]+=1;status["physical_steps"]+=outcome["total_steps"];status["environment_resets"]+=outcome["environment_resets"]
                _write_json(output/"status.json",status)
                if index%12==0:print(f"Completed unit {index//12}/96 ({index}/1152 episodes)",flush=True)
        if any(len(v)!=1 for v in initials.values()) or status["physical_steps"]>576000 or status["environment_resets"]!=1152:raise ValueError("initial state/budget mismatch")
        statistics=summarize(m,outcomes);status["status"]="COMPLETED_POINT_UTILITY_PASS" if statistics["useful_point_methods"] else "COMPLETED_POINT_UTILITY_FAILED"
        _write_json(output/"summary.json",{**status,"statistics":statistics});_write_json(output/"status.json",status)
        print(json.dumps({"status":status["status"],"useful_point_methods":statistics["useful_point_methods"]}))
    except BaseException as exc:
        if isinstance(exc,EpisodeFailure):
            _write_json(output/"failed_episode.json",exc.record);status["partial_physical_steps"]=exc.record["completed_host_calls"];status["partial_environment_resets"]=exc.record["completed_resets"]
        status.update(status="INCOMPLETE",error_type=type(exc).__name__,error=str(exc));_write_json(output/"status.json",status);raise


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True)
    g.add_argument("--prepare",action="store_true");g.add_argument("--manifest",type=Path);a=p.parse_args()
    prepare() if a.prepare else run(a.manifest.resolve())

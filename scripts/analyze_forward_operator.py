"""Independent visible history and command replay of affine task experiments."""
import argparse
from contextlib import ExitStack
from dataclasses import asdict
import gzip
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import numpy as np
from scripts import run_forward_operator as runner
from scripts.analyze_forward_prediction import bases,expanded
from scripts.run_continuous_probe import state_hash,normalized
from src.probe.continuous import StepObservation,ContinuousTransition
from src.probe.forward_prediction import ForwardQuery
from src.probe.operator_identification import OperatorSample,sample_digest
from src.rollout.task_registry import create_task_policy


def hash_rng(rng):return hashlib.sha256(json.dumps(rng.bit_generator.state,sort_keys=True).encode()).hexdigest()


def independent_fit_loss(model,samples,parameters):
    p=np.array(parameters).reshape(2,3);values=[]
    for sample in samples:
        q=normalized(asdict(sample.query));mean=np.clip(p@np.array([*q["command"][:2],1.]),-1,1)
        q["command"][:2]=mean.tolist();z=(bases(q,model["method"])-model["mean"])/model["scale"]
        prediction=expanded(z,model["method"])@np.array(model["coefficients"])
        values.append(prediction-np.array(sample.displacement))
    return float(np.sqrt(np.mean(np.square(values))))


def verify_record(m,record,priors,previous_after_ns=0):
    key={k:record[k] for k in (*runner.identity(m),"episode_index","seed","task","operator_oracle","method")}
    if any(key[k]!=v for k,v in runner.identity(m).items()) or any(record["outcome"][k]!=v for k,v in key.items()):raise ValueError("record provenance mismatch")
    method=key["method"];operator=m["config"]["operators_oracle"][runner.OPERATORS.index(key["operator_oracle"])]
    initial=StepObservation(**record["initial"]);current=initial;history=[];samples=[];transitions=[];policy=create_task_policy(key["task"])
    rng=np.random.default_rng(runner.noise_seed(key["seed"],key["task"],runner.OPERATORS.index(key["operator_oracle"])))
    program=runner.probe_program(method);n_probe=record["outcome"]["probe_steps"];decisions=record["decisions"];cursor=0;selected=None
    if not 0<=n_probe<=len(program):raise ValueError("probe budget mismatch")
    handoff=record["handoff"]
    if n_probe==0 and handoff!=normalized({"host_calls":0,"observation":asdict(initial),"rng_hash":hash_rng(rng)}):raise ValueError("initial handoff mismatch")
    def take_choices(calls,following_ns):
        nonlocal cursor,selected
        due=calls==n_probe and selected is None or method=="PASSIVE_LINEAR" and calls and calls%16==0 and selected["at_host_calls"]!=calls
        if not due:return
        if cursor>=len(decisions):raise ValueError("missing saved choice")
        d=decisions[cursor];cursor+=1
        if any(d.get(k)!=v for k,v in key.items()) or d["at_host_calls"]!=calls or d["observation_sha256"]!=state_hash(current.observation) or d["rng_hash"]!=hash_rng(rng):
            raise ValueError("choice provenance/past prefix mismatch")
        if not isinstance(d["fit_elapsed_ms"],(float,int)) or not np.isfinite(d["fit_elapsed_ms"]) or d["fit_elapsed_ms"]<0:raise ValueError("invalid fit latency")
        if d["saved_ns"]>=following_ns or d["saved_ns"]<=previous_after_ns:raise ValueError("choice not before execution")
        if method=="ORACLE16":expected=runner.evaluator_plan(operator)
        elif method=="PASSIVE_LINEAR" and not transitions:expected={"status":"INITIAL_UNCORRECTED","controller":runner.identity_controller(),"fit":None,"physical_response_qualified":False}
        else:expected=runner.choose_agent_plan(method,key["task"],transitions,current,priors,selected["choice"]["controller"] if selected else None)
        if d["choice"]!=normalized(expected):raise ValueError("choice does not use registered past-only planner")
        controller=d["choice"]["controller"]
        if method!="ORACLE16" and (d["choice"].get("oracle_only") or controller and controller["source"]=="ORACLE_EVALUATOR"):
            raise ValueError("Oracle entered agent controller")
        fit=d["choice"]["fit"]
        if method in runner.POINT_METHODS and fit is not None:
            seen=samples[-64:] if method=="PASSIVE_LINEAR" else samples
            if fit["sample_digest"]!=sample_digest(seen) or fit["samples"]!=len(seen) or fit["physical_response_qualified"] is not False or fit["probability_guarantee"] is not False:
                raise ValueError("fit consumed future/unqualified samples")
            kind="LINEAR_ARX" if "LINEAR" in method else "QUADRATIC_STATE"
            for trial in fit.get("optimizer_trials",[]):
                loss=independent_fit_loss(priors["forward"][key["task"]][kind],seen,trial["parameters"])
                if not np.isclose(loss,trial["residual_rmse_m"],rtol=1e-9,atol=1e-12):raise ValueError("independent forward fit loss mismatch")
        selected=d
    for index,row in enumerate(record["trace"],1):
        before=StepObservation(**row["before"]);after=StepObservation(**row["after"])
        if before!=current or before.success or before.terminated or before.truncated or row["host_calls"]!=index:raise ValueError("state/counter/termination continuity mismatch")
        if not previous_after_ns<row["before_ns"]<row["after_ns"]:raise ValueError("step chronology mismatch")
        if index<=n_probe:
            expected=list(program[index-1]);phase="PROBE"
            if row["raw_policy"] is not None or row["decision_sequence"] is not None:raise ValueError("controller attached to probe")
        else:
            take_choices(index-1,row["before_ns"])
            if selected is None or selected["choice"]["controller"] is None:raise ValueError("execution after missing/abstained choice")
            raw=np.asarray(policy.get_action(np.array(before.observation)),dtype=np.float32)
            if row["raw_policy"]!=raw.tolist():raise ValueError("fixed policy changed")
            # Independent execution arithmetic, not the collector's encoder.
            wanted=np.clip(raw,-1,1).astype(float);controller=selected["choice"]["controller"]
            wanted[:2]=np.array(controller["matrix_xy"])@wanted[:2]+np.array(controller["offset"][:2])
            expected=np.clip(wanted,-1,1).astype(np.float32).tolist();phase="POLICY"
            if row["decision_sequence"]!=selected["sequence"]:raise ValueError("executor did not use saved choice")
        if row["command"]!=expected or row["phase"]!=phase:raise ValueError("actual bounded command/phase mismatch")
        if row["rng_before"]!=hash_rng(rng):raise ValueError("RNG was reseeded")
        rng.normal(0,.05,3)
        if row["rng_after"]!=hash_rng(rng):raise ValueError("RNG advance mismatch")
        delta=(np.array(after.observation[:3])-before.observation[:3]).tolist()
        if len(history)>=2:samples.append(OperatorSample(index,ForwardQuery(tuple(before.observation),tuple(history[-1]),tuple(history[-2]),tuple(expected)),tuple(delta[:2])))
        transitions.append(ContinuousTransition(tuple(expected),before.observation,after.observation));history=(history+[delta])[-2:];current=after;previous_after_ns=row["after_ns"]
        if index==n_probe and handoff!=normalized({"host_calls":index,"observation":asdict(after),"rng_hash":hash_rng(rng)}):raise ValueError("continuous handoff mismatch")
    total=len(record["trace"])
    if selected is None:take_choices(total,float("inf"))
    if cursor!=len(decisions):raise ValueError("extra/future controller choice")
    ended=current.success or current.terminated or current.truncated;last=selected["choice"]
    if total>500 or not ended and total<500 and last["controller"] is not None:raise ValueError("budget/stopping mismatch")
    if program and n_probe<len(program) and not any(handoff["observation"][name] for name in ("success","terminated","truncated")):raise ValueError("incomplete probe")
    parameter_error=None;controller=last["controller"]
    if controller and controller["source"]=="ESTIMATED_AFFINE":
        matrix=np.linalg.inv(np.array(controller["matrix_xy"]));bias=-matrix@np.array(controller["offset"][:2])
        truth=np.column_stack((np.array(operator["matrix_xy"],dtype=np.float32),np.array(operator["bias_xy"],dtype=np.float32)))
        parameter_error=float(np.max(np.abs(np.column_stack((matrix,bias))-truth)))
    outcome={**key,"success":current.success,"probe_steps":n_probe,"task_steps":total-n_probe,"total_steps":total,
        "environment_resets":1,"actuator_resets":1,"stopped_point_fit":last["controller"] is None,
        "invalid_fit_choices":sum(d["choice"]["fit"] is not None and not d["choice"]["fit"].get("valid",False) for d in decisions),
        "controller_choices":len(decisions),"final_status":last["status"],"parameter_error_oracle":parameter_error}
    if outcome!=record["outcome"]:raise ValueError("outcome/parameter/cost reconstruction mismatch")
    return outcome,previous_after_ns


def analyze(path):
    m=runner.load(path);priors=runner.load_priors(m["config"]);root=path.parent;rows=[];sequence=0;after_ns=0;initials={};latencies={name:[] for name in runner.METHODS}
    with ExitStack() as stack:
        handles={name:stack.enter_context(gzip.open(root/("episodes_"+name+".jsonl.gz"),"rt",encoding="utf-8")) for name in runner.METHODS}
        declarations=stack.enter_context((root/"decisions.jsonl").open(encoding="utf-8"))
        for index,(seed,task,operator,method) in enumerate(runner.population(m["config"]),1):
            record=json.loads(next(handles[method]))
            if record["episode_index"]!=index or (record["seed"],record["task"],record["operator_oracle"],record["method"])!=(seed,task,operator,method):raise ValueError("population/order mismatch")
            for saved in record["decisions"]:
                declared=json.loads(next(declarations));sequence+=1
                if saved!=declared or saved["sequence"]!=sequence:raise ValueError("saved decision log mismatch")
                latencies[method].append(saved["fit_elapsed_ms"])
            outcome,after_ns=verify_record(m,record,priors,after_ns);rows.append(outcome)
            initials.setdefault((seed,task,operator),set()).add(state_hash(record["initial"]["observation"]))
        if next(declarations,None) is not None or any(next(h,None) is not None for h in handles.values()):raise ValueError("extra/future cases/decisions")
    if len(rows)!=1152 or any(len(v)!=1 for v in initials.values()):raise ValueError("paired initial population mismatch")
    statistics=runner.summarize(m,rows);status=json.loads((root/"status.json").read_text());summary=json.loads((root/"summary.json").read_text())
    expected={**runner.identity(m),"status":"COMPLETED_POINT_UTILITY_PASS" if statistics["useful_point_methods"] else "COMPLETED_POINT_UTILITY_FAILED",
              "episodes":1152,"physical_steps":sum(r["total_steps"] for r in rows),"environment_resets":1152,"api_calls":0,"memory_writes":0}
    if expected["physical_steps"]>576000 or summary["statistics"]!=statistics or any(any(v.get(k)!=x for k,x in expected.items()) for v in (status,summary)):raise ValueError("registered status/statistics/accounting mismatch")
    timing={name:{"choices":len(v),"median_ms":float(np.median(v)),"p90_ms":float(np.quantile(v,.9,method="linear")),"maximum_ms":max(v)} for name,v in latencies.items()}
    return {**expected,"integrity":"PASSED","statistics":statistics,"choice_latency":timing,"saved_choices_checked":sequence,
        "visible_steps_checked":expected["physical_steps"],"continuous_probe_handoffs":sum(r["probe_steps"]>0 for r in rows),
        "forward_prior_steps":21010,"forward_prior_resets":288,"legacy_prior_steps":2304,"legacy_prior_resets":144,
        "artifact_sha256":{p.name:runner.digest(p) for p in root.iterdir() if p.is_file()},
        "scope":"Independent histories, visible fit inputs/losses, execution arithmetic, state/RNG and cost replay; registered optimizers/statistical summaries reused. No dynamics resimulation. Point utility is not physical confidence or algorithm novelty."}


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--manifest",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    a=p.parse_args();source,output=a.manifest.resolve(),a.output.resolve()
    if output==source.parent or source.parent in output.parents:raise ValueError("audit must be outside collection")
    result=analyze(source);output.mkdir(parents=True,exist_ok=False)
    (output/"audit.json").write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({k:result[k] for k in ("status","integrity","physical_steps","saved_choices_checked")}))

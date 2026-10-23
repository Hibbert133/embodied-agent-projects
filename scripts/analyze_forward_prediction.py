"""Independent visible-feature, training-source, calibration and chronology audit."""
import argparse
from dataclasses import asdict
import gzip
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import numpy as np
from scripts import run_forward_prediction as runner
from scripts.run_continuous_probe import state_hash,normalized
from src.probe.continuous import StepObservation,symmetric_program
from src.probe.forward_prediction import vector
from src.rollout.task_registry import create_task_policy


def hash_rng(rng):return hashlib.sha256(json.dumps(rng.bit_generator.state,sort_keys=True).encode()).hexdigest()


def bases(q,name):
    old=np.array(q["last_displacement"]);prior=np.array(q["prior_displacement"]);sent=np.array(q["command"])
    if name=="LINEAR_ARX":return np.concatenate((old,prior,sent))
    state=np.array(q["observation"]);hand=state[:3]
    return np.array([*hand,*old,*prior,*sent,state[3],*(state[4:7]-hand),*(state[-3:]-hand)])


def expanded(z,name):
    return np.array([1.,*z,*([z[a]*z[b] for a in range(20) for b in range(a,20)] if name=="QUADRATIC_STATE" else [])])


class IndependentPredictors:
    def __init__(self,models,legacy):
        if set(models)!=set(runner.TASKS) or any(set(v)!=set(runner.METHODS[1:]) for v in models.values()):raise ValueError("registered task/model set mismatch")
        self.models={task:{name:{k:np.asarray(v) if k in ("mean","scale","inputs","targets","coefficients") else v for k,v in values.items()}
                     for name,values in model.items()} for task,model in models.items()}
        self.legacy=legacy

    def predict(self,task,q):
        a,b,c=np.array(self.legacy.inertia),np.array(self.legacy.response),np.array(self.legacy.intercept)
        predictions={"LEGACY_ARX":a@q["last_displacement"][:2]+b@q["command"][:2]+c}
        for name,values in self.models[task].items():
            z=(bases(q,name)-values["mean"])/values["scale"]
            if name=="NEAREST_STATE":
                d=np.sum((values["inputs"]-z)**2,axis=1);indices=np.argsort(d,kind="stable")[:16]
                w=1/(d[indices]+1e-6);prediction=np.sum(values["targets"][indices]*w[:,None],axis=0)/w.sum()
            else:prediction=expanded(z,name)@values["coefficients"]
            predictions[name]=prediction
        return predictions


def verify_record(m,r,declarations,predictors,model_sha,calibration_sha,previous_after_ns=0):
    stage=r["stage"];key={k:r[k] for k in (*runner.identity(m),"stage","episode_index","seed","task","program")}
    if any(r[k]!=v for k,v in runner.identity(m).items()) or any(r["outcome"][k]!=v for k,v in key.items()):raise ValueError("episode provenance mismatch")
    before=StepObservation(**r["initial"]);vector(before.observation,39);deltas=[];samples=[];errors={name:[] for name in runner.METHODS}
    if len(declarations)!=len(r["trace"]):raise ValueError("prediction/transition count mismatch")
    rng=np.random.default_rng(runner.noise_seed(r["seed"],r["task"]));policy=create_task_policy(r["task"])
    n_probe=r["outcome"]["probe_steps"];probe=symmetric_program() if r["program"]=="PROBE_THEN_POLICY" else ()
    if not 0<=n_probe<=len(probe):raise ValueError("invalid probe budget")
    handoff=r["handoff"]
    if n_probe==0 and handoff!=normalized({"host_calls":0,"observation":asdict(before),"rng_hash":hash_rng(rng)}):raise ValueError("initial handoff mismatch")
    for index,(row,d) in enumerate(zip(r["trace"],declarations),1):
        if any(d.get(k)!=v for k,v in key.items()):raise ValueError("prediction provenance mismatch")
        if row["before"]!=normalized(asdict(before)) or any((before.success,before.terminated,before.truncated)):raise ValueError("state continuity/termination mismatch")
        after=StepObservation(**row["after"]);vector(after.observation,39)
        phase="PROBE" if index<=n_probe else "POLICY"
        if phase=="PROBE":
            sent=list(probe[index-1]);raw=None
        else:
            raw=np.asarray(policy.get_action(np.array(before.observation)),dtype=np.float32).tolist()
            sent=np.clip(np.array(raw,dtype=np.float32),-1,1).tolist()
        if row["raw_policy"]!=raw:raise ValueError("fixed policy changed")
        expected_query={"observation":list(before.observation),"last_displacement":deltas[-1],"prior_displacement":deltas[-2],"command":sent} if len(deltas)>=2 else None
        expected={**key,"step":index,"command":sent,"phase":phase,"observation_sha256":state_hash(before.observation),
            "rng_hash":hash_rng(rng),"query":expected_query,"model_sha256":model_sha if stage!="TRAIN" else None,
            "calibration_sha256":calibration_sha if stage=="QUALIFICATION" else None,
            "sequence":row["prediction_sequence"],"before_ns":d.get("before_ns"),"predictions":d.get("predictions")}
        if d!=expected:raise ValueError("future/input/source prediction declaration mismatch")
        if not previous_after_ns<d["before_ns"]<row["after_ns"]:raise ValueError("prediction was not before execution")
        predictions=predictors.predict(r["task"],expected_query) if expected_query is not None and stage!="TRAIN" else None
        if predictions is None:
            if d["predictions"] is not None:raise ValueError("warmup/train prediction invented")
        elif d["predictions"] is None or set(d["predictions"])!=set(predictions) or any(not np.allclose(d["predictions"][name],v,rtol=1e-10,atol=1e-12) for name,v in predictions.items()):
            raise ValueError("independent forward prediction mismatch")
        delta=(np.array(after.observation[:3])-before.observation[:3]).tolist();target=delta[:2]
        if row["target_xy"]!=target:raise ValueError("visible target mismatch")
        if expected_query is not None and stage=="TRAIN":samples.append((r["task"],expected_query,target))
        if predictions is not None:
            for name in runner.METHODS:errors[name].append(float(np.max(np.abs(np.array(d["predictions"][name])-target))))
        rng.normal(0,.05,3)
        if row["rng_after"]!=hash_rng(rng):raise ValueError("RNG continuity mismatch")
        if index==n_probe and handoff!=normalized({"host_calls":index,"observation":asdict(after),"rng_hash":hash_rng(rng)}):raise ValueError("probe handoff mismatch")
        deltas=(deltas+[delta])[-2:];before=after;previous_after_ns=row["after_ns"]
    total=len(r["trace"])
    ended=before.success or before.terminated or before.truncated
    if total>500 or not ended and total!=500:raise ValueError("episode budget/stopping mismatch")
    if len(probe) and n_probe<16 and not any(handoff["observation"][k] for k in ("success","terminated","truncated")):raise ValueError("incomplete probe program")
    expected={**key,"success":before.success,"total_steps":total,"probe_steps":n_probe,"environment_resets":1,"actuator_resets":1,
        "prediction_steps":max(total-2,0) if stage!="TRAIN" else 0,
        "maximum_errors":{name:max(v,default=None) for name,v in errors.items()},
        "rmse_inf":{name:float(np.sqrt(np.mean(np.square(v)))) if v else None for name,v in errors.items()}}
    if expected!=r["outcome"]:raise ValueError("outcome/scoring mismatch")
    return expected,samples,previous_after_ns,state_hash(r["initial"]["observation"])


def verify_training(saved,samples):
    for task in runner.TASKS:
        rows=[(q,y) for t,q,y in samples if t==task];target=np.array([y for _,y in rows])
        if len(rows)<32:raise ValueError("insufficient training population")
        for name in runner.METHODS[1:]:
            values=saved["models"][task][name];inputs=np.array([bases(q,name) for q,_ in rows])
            if values["method"]!=name or values["physical_response_qualified"] is not False or values["probability_guarantee"] is not False:raise ValueError("model scope improperly qualified")
            mean=inputs.mean(axis=0);scale=inputs.std(axis=0);scale=np.where(scale>1e-6,scale,1.)
            if values["training_samples"]!=len(rows) or not np.array_equal(values["mean"],mean) or not np.array_equal(values["scale"],scale):raise ValueError("training-only scaling/source mismatch")
            z=(inputs-mean)/scale
            if name=="NEAREST_STATE":
                if values["neighbors"]!=16 or not np.array_equal(values["inputs"],z) or not np.array_equal(values["targets"],target):raise ValueError("nearest training source mismatch")
            else:
                x=np.array([expanded(row,name) for row in z]);penalty=.001*np.eye(x.shape[1]);penalty[0,0]=0
                coefficient=np.linalg.solve(x.T@x+penalty,x.T@target)
                if values["ridge"]!=.001 or values["feature_count"]!=x.shape[1] or not np.allclose(values["coefficients"],coefficient,rtol=1e-9,atol=1e-11):raise ValueError("training ridge source mismatch")
                if not np.isclose(values["training_rmse"],np.sqrt(np.mean((x@coefficient-target)**2)),rtol=1e-10,atol=1e-12):raise ValueError("training residual mismatch")


def analyze(path):
    m=runner.load(path);root=path.parent;legacy=runner.model(m["config"])
    saved=json.loads((root/"models.json").read_text());cal=json.loads((root/"calibration.json").read_text())
    model_sha=runner.digest(root/"models.json");cal_sha=runner.digest(root/"calibration.json")
    for obj in (saved,cal):
        if any(obj.get(k)!=v for k,v in runner.identity(m).items()):raise ValueError("fitted artifact provenance mismatch")
    if saved["training_artifact_sha256"]!=runner.digest(root/"TRAIN.jsonl.gz") or cal["calibration_artifact_sha256"]!=runner.digest(root/"CALIBRATION.jsonl.gz") or cal["model_sha256"]!=model_sha:
        raise ValueError("frozen fit/calibration association changed")
    predictors=IndependentPredictors(saved["models"],legacy);sequence=0;after_ns=0;stages={};all_samples=[];costs={};handoffs=0
    with (root/"predictions.jsonl").open(encoding="utf-8") as predictions:
        for stage_index,stage in enumerate(runner.STAGES):
            outcomes=[];initials={};expected_population=runner.population(m["config"],stage)
            with gzip.open(root/(stage+".jsonl.gz"),"rt",encoding="utf-8") as handle:
                for index,line in enumerate(handle,1):
                    record=json.loads(line)
                    if index>96 or record["stage"]!=stage or record["episode_index"]!=stage_index*96+index or (record["seed"],record["task"],record["program"])!=expected_population[index-1]:raise ValueError("stage/population/order mismatch")
                    declarations=[]
                    for _ in record["trace"]:
                        declaration=json.loads(next(predictions));sequence+=1
                        if declaration["sequence"]!=sequence:raise ValueError("prediction sequence mismatch")
                        declarations.append(declaration)
                    outcome,samples,after_ns,initial=verify_record(m,record,declarations,predictors,model_sha,cal_sha,after_ns)
                    outcomes.append(outcome);all_samples.extend(samples);initials.setdefault((record["seed"],record["task"]),set()).add(initial)
                    handoffs+=int(record["program"]=="PROBE_THEN_POLICY")
            if len(outcomes)!=96 or any(len(v)!=1 for v in initials.values()):raise ValueError("stage completeness/paired initial mismatch")
            stages[stage]=outcomes
            costs[stage]={"physical_steps":sum(r["total_steps"] for r in outcomes),"environment_resets":96,
                "successes":sum(r["success"] for r in outcomes),"probe_steps":sum(r["probe_steps"] for r in outcomes)}
            if stage=="TRAIN":
                if saved["last_training_prediction_sequence"]!=sequence:raise ValueError("model freeze chronology mismatch")
                verify_training(saved,all_samples);all_samples=[]
            if stage=="CALIBRATION":
                # Independently calculate the finite-sample rank: n=16, alpha=.1 ->16.
                if cal["last_calibration_prediction_sequence"]!=sequence or cal["alpha"]!=.1:raise ValueError("calibration freeze chronology mismatch")
                expected=runner.calibration(m,outcomes,model_sha,sequence);expected["calibration_artifact_sha256"]=runner.digest(root/"CALIBRATION.jsonl.gz")
                if cal!=expected:raise ValueError("calibration artifact mismatch")
                for key,methods in cal["radii"].items():
                    task,program=key.split("|");selected=[r for r in outcomes if r["task"]==task and r["program"]==program]
                    for name,v in methods.items():
                        scores=[r["maximum_errors"][name] for r in selected]
                        if all(s is not None for s in scores) and (v["rank"]!=16 or v["radius"]!=max(scores)):raise ValueError("trajectory quantile mismatch")
        if next(predictions,None) is not None:raise ValueError("unused/future prediction declarations")
    statistics=runner.summarize(m,stages["QUALIFICATION"],cal)
    status=json.loads((root/"status.json").read_text());summary=json.loads((root/"summary.json").read_text())
    counts={"status":"COMPLETED_FEASIBILITY_PASS" if statistics["passing_forward_models"] else "COMPLETED_FEASIBILITY_FAILED",
        "stage":"COMPLETE","episodes":288,"physical_steps":sum(v["physical_steps"] for v in costs.values()),"environment_resets":288,"api_calls":0,"memory_writes":0}
    if counts["physical_steps"]>144000 or any(any(obj.get(k)!=v for k,v in {**runner.identity(m),**counts}.items()) for obj in (status,summary)):raise ValueError("status/accounting mismatch")
    if summary["statistics"]!=statistics or summary["stage_costs"]!=costs or summary["model_sha256"]!=model_sha or summary["calibration_sha256"]!=cal_sha:raise ValueError("registered summary mismatch")
    return {**runner.identity(m),**counts,"integrity":"PASSED","statistics":statistics,"stage_costs":costs,
        "model_sha256":model_sha,"calibration_sha256":cal_sha,"prediction_declarations_checked":sequence,
        "continuous_handoffs":handoffs,"training_sources_recomputed":True,"installed_policy_hashes_checked":m["policy_sha256"],
        "old_offline_steps":2304,"old_offline_resets":144,
        "artifact_sha256":{p.name:runner.digest(p) for p in root.iterdir() if p.is_file()},
        "scope":"No task dynamics resimulation. Independent visible features, fit/target sources and prediction arithmetic; trajectory calibration and shared summary checks. Nominal empirical coverage is not fault-transfer, actuator-response or control qualification."}


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--manifest",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    a=p.parse_args();source,output=a.manifest.resolve(),a.output.resolve()
    if output==source.parent or source.parent in output.parents:raise ValueError("audit must be outside collection")
    result=analyze(source);output.mkdir(parents=True,exist_ok=False)
    (output/"audit.json").write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({k:result[k] for k in ("status","integrity","physical_steps","prediction_declarations_checked")}))

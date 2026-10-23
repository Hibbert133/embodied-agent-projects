"""Read-only numerical audit, independent of collector, fitter and evaluator.

Reconstructs causal regressions from TRAIN, and each qualification estimate,
penalty, grouped interval and cost. It does not call the production fit/infer
functions or run robot physics. Shared schema validation is not a second model.
"""
import argparse
from collections import Counter
import gzip
import json
import math
from pathlib import Path
import sys
from time import perf_counter_ns
import numpy as np
from scipy.optimize import least_squares

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.analysis import selected_response_io_v1 as io
from src.probe.selected_response_reference_v1 import METHODS, validate_model
from src.probe.local_reprobe_v1 import SelectedAnchorWindow

ALL = (*METHODS,"SAVED_C8","RELOCATION_INTEGRAL")


def require(value,message):
    if not value:raise ValueError(message)


def close(left,right):
    require(np.shape(left) == np.shape(right) and np.allclose(left,right,atol=2e-8,rtol=2e-7),"independent numeric reconstruction differs")


def same(left,right):
    require(left == right,"independent allocation, field or count differs")


def lines(path):
    with gzip.open(path,"rt",encoding="utf-8") as handle:
        for line in handle:yield json.loads(line)


def features(window):
    history = np.array(window["entry_history"])
    return np.r_[(history[-1,:3]-window["anchor"])/.015,
        np.diff(history[:,:3],axis=0).ravel()/.003,(history[-1,:3]-[0.,.7,.35])/[.45,.25,.20]]


def mean_clip(value):
    a,b = (-1-value)/.05,(1-value)/.05
    cdf = np.vectorize(lambda x:.5*math.erfc(-float(x)/math.sqrt(2)),otypes=[float])
    lo,hi = cdf(a),cdf(b);slope = hi-lo
    return value*slope+.05*(np.exp(-a*a/2)-np.exp(-b*b/2))/math.sqrt(2*math.pi)+1-hi-lo,slope


def train_check(samples,model):
    validate_model(model);n = len(samples);same(n,model["training_trajectories"])
    require(n >= 160,"insufficient nominal windows")
    states = np.array([features(s) for s in samples]);method = model["method"]
    state_count = dict(zip(METHODS,(0,12,15)))[method];basis_count = 4 if method == METHODS[2] else 1
    basis = np.c_[np.ones(n),states[:,12:]] if basis_count == 4 else np.ones((n,1))
    inputs = np.array([mean_clip(np.array(s["commands"])[:,:2])[0].ravel() for s in samples])
    nuisance = np.c_[np.ones(n),states[:,:state_count]]
    expanded = (basis[:,:,None]*inputs[:,None,:]).reshape(n,16*basis_count)
    centered = expanded-expanded.mean(axis=0);scale = np.linalg.norm(centered,axis=0)
    residual_input = expanded-nuisance@np.linalg.lstsq(nuisance,expanded,rcond=None)[0]
    singular = np.linalg.svd(residual_input/np.where(scale > 0,scale,1.),compute_uv=False)
    state_rank = int(np.linalg.matrix_rank(nuisance));conditional_rank = int(np.linalg.matrix_rank(np.c_[nuisance,expanded])-state_rank)
    same(model["training_input_rank"],int(np.linalg.matrix_rank(np.c_[np.ones(n),expanded])))
    same(model["training_state_rank"],state_rank);same(model["training_conditional_input_rank"],conditional_rank)
    require(conditional_rank == 16*basis_count and singular[-1] >= 1e-6 and singular[0]/singular[-1] <= 1e6,"unqualified excitation")
    close(model["training_conditional_input_condition"],singular[0]/singular[-1]);close(model["training_conditional_minimum_singular"],singular[-1])
    observed = np.array([np.diff(np.array([s["entry_history"][-1],*s["observations"]])[:,:2],axis=0).ravel() for s in samples])
    prediction = np.zeros((n,16));offset = np.zeros(16);state = np.zeros((16,15));impulse = np.zeros((4,16,16))
    for end in range(2,17,2):
        design = np.c_[nuisance,(basis[:,:,None]*inputs[:,None,:end]).reshape(n,basis_count*end)]
        penalty = .001*np.eye(design.shape[1]);penalty[0,0] = 0.
        beta = np.linalg.lstsq(np.vstack((design,penalty)),np.vstack((observed[:,end-2:end],np.zeros((design.shape[1],2)))),rcond=None)[0]
        offset[end-2:end] = beta[0];state[end-2:end,:state_count] = beta[1:state_count+1].T
        for k in range(basis_count):impulse[k,end-2:end,:end] = beta[1+state_count+k*end:1+state_count+(k+1)*end].T
        prediction[:,end-2:end] = design@beta
    errors = observed-prediction;cov = errors.T@errors/(n-state_rank-conditional_rank)
    cov = .95*cov+.05*np.diag(np.diag(cov))+1e-12*np.eye(16)
    for key,value in (("offset",offset),("state_response",state),("impulse_basis",impulse),("covariance",cov),
        ("training_joint_rmse_m",np.sqrt(np.mean(errors**2)))):close(model[key],value)
    poses = np.array([s["entry_history"][-1][:3] for s in samples])
    close(model["training_hand_min"],poses.min(axis=0));close(model["training_hand_max"],poses.max(axis=0))
    return {"task":model["task"],"method":method,"windows":n,"regressions":8}


def check_models(path):
    manifest,_ = io.load(path);bank,done = io.bank(path,require_audit=False);folder = path.parent
    output = folder/"model_audit";output.mkdir();started = perf_counter_ns();identity = {k:manifest[k] for k in io.IDENTITY}
    try:
        samples = {task:[] for task in io.TASKS};count = 0
        for row in lines(folder/"train/cases.jsonl.gz"):
            count += 1;same(row["variant"],"TRAIN");same(row["fault_oracle"],io.NOMINAL)
            if row["complete_window"]:samples[row["task"]].append(row["reacquisition"]["public"]["nominal_trajectory"])
        same(count,bank["training_attempts"])
        checks = [train_check(samples[task],bank["models"][task][method]) for task in io.TASKS for method in METHODS]
        result = {**identity,"integrity":"PASSED","models_sha256":done["models_sha256"],"train_audit_sha256":bank["train_audit_sha256"],
            "models":checks,"new_robot_steps":0,"new_api_calls":0,"audit_completed_ns":perf_counter_ns(),"wall_ns":perf_counter_ns()-started}
        io.write(output/"record_audit.json",result);return result
    except BaseException as error:
        io.write(output/"failed_audit.json",{**identity,"integrity":"FAILED","error":type(error).__name__,"message":str(error)})
        raise


def inference(model,window):
    SelectedAnchorWindow.from_mapping(window);validate_model(model)
    pose = np.array(window["entry_history"][-1][:3]);s = features(window)
    if np.any(pose < np.array(model["training_hand_min"])-.01) or np.any(pose > np.array(model["training_hand_max"])+.01):
        return {"valid":False,"reason":"OUTSIDE_OBSERVED_TRAINING_POSE_BOX","nfev":0}
    basis = np.array(model["impulse_basis"]);h = basis[0]+np.einsum("k,kij->ij",s[12:],basis[1:])
    baseline = np.array(model["offset"])+np.array(model["state_response"])@s
    x = np.c_[np.array(window["commands"])[:,:2],np.ones(8)]
    y = np.diff(np.array([window["entry_history"][-1],*window["observations"]])[:,:2],axis=0).ravel()
    chol = np.linalg.cholesky(model["covariance"])
    linear = np.linalg.solve(chol,np.column_stack([h@(x@b.reshape(2,3).T).ravel() for b in np.eye(6)]))
    norms = np.linalg.norm(linear,axis=0);rank = int(np.linalg.matrix_rank(linear))
    condition = float(np.linalg.cond(linear/np.where(norms > 0,norms,1.)))
    if rank != 6 or not math.isfinite(condition) or condition > 1e6:
        return {"valid":False,"reason":"INSUFFICIENT_LEARNED_RESPONSE_SUPPORT","nfev":0}
    def prediction(p):return baseline+h@mean_clip(x@p.reshape(2,3).T)[0].ravel()
    def residual(p):return np.linalg.solve(chol,prediction(p)-y)
    def jacobian(p):
        slope = mean_clip(x@p.reshape(2,3).T)[1]
        return np.linalg.solve(chol,np.column_stack([h@((x@b.reshape(2,3).T)*slope).ravel() for b in np.eye(6)]))
    lower = np.array([-2.,-2.,-.3,-2.,-2.,-.3]);upper = -lower
    start = np.linalg.lstsq(linear,np.linalg.solve(chol,y-baseline),rcond=None)[0]
    fitted = least_squares(residual,np.clip(start,lower+1e-9,upper-1e-9),jac=jacobian,bounds=(lower,upper),
        ftol=1e-8,xtol=1e-8,gtol=1e-8,max_nfev=64)
    p = fitted.x.reshape(2,3);singular = np.linalg.svd(p[:,:2],compute_uv=False)
    valid = bool(fitted.success and singular[-1] >= .25 and singular[0] <= 4.)
    return {"valid":valid,"reason":"WORKING_SELECTED_RESPONSE_FIT" if valid else "OPTIMIZER_OR_INVERSE_DOMAIN_FAILURE",
        "matrix_xy":p[:,:2].tolist(),"bias_xy":p[:,2].tolist(),"nfev":int(fitted.nfev),
        "residual_rmse_m":float(np.sqrt(np.mean((prediction(fitted.x)-y)**2)))}


def case_check(source,saved,models,config):
    for key in ("unit","task","seed","variant","planned_boundary","boundary_ready","complete_window","collection_stop_reason", "success","total_steps","reposition_steps","probe_steps"):
        same(source[key],saved[key])
    same(saved["group"],source["unit"]//9);same(set(saved["fits"]),set(ALL));same(set(saved["errors"]),set(ALL))
    nfev = 0
    for method in ALL:
        estimate = saved["fits"][method]
        if not source["boundary_ready"]:expected = {"valid":False,"reason":"PLANNED_BOUNDARY_UNAVAILABLE","nfev":0}
        elif method in METHODS:
            public = source["reacquisition"]["public"]
            expected = ({"valid":False,"reason":"NO_COMPLETE_WINDOW:"+public["reason"],"nfev":0} if public["window"] is None else
                        inference(models[source["task"]][method],public["window"]))
        elif method == "SAVED_C8":
            fit = next(e["payload"]["fit"] for e in source["prefix"]["public"]["events"] if e["kind"] == "FIT_RESULT" and e["payload"]["at_calls"] == 8)
            expected = {"valid":True,"reason":"SAVED_PRECHANGE_C8","nfev":0,"matrix_xy":fit["matrix_xy"],"bias_xy":fit["bias_xy"]}
        else:
            evidence = source["reacquisition"]["public"]["relocation_evidence"]
            if evidence is None:expected = {"valid":False,"reason":"NO_RELOCATION_EVIDENCE","nfev":0}
            else:
                correction = evidence["controller"];a = np.linalg.solve(correction["matrix_xy"],np.eye(2))
                expected = {"valid":True,"reason":"SAVED_PREPROBE_INTEGRAL","nfev":0,"matrix_xy":a,"bias_xy":-a@correction["offset"][:2]}
        for key in ("valid","reason"):same(estimate[key],expected[key])
        # Independent numerical solves can terminate at a different evaluation
        # count; verify bounded saved counters, and disclose both actual totals.
        require(type(estimate["nfev"]) is int and 0 <= estimate["nfev"] <= 64,"invalid saved optimization count")
        if expected["nfev"] == 0:same(estimate["nfev"],0)
        nfev += expected["nfev"]
        for key in ("matrix_xy","bias_xy","residual_rmse_m"):
            if key in expected:close(estimate[key],expected[key])
        if estimate["valid"]:
            truth = io.destination(source);a = float(np.linalg.norm(np.array(estimate["matrix_xy"])-truth["matrix_xy"]))
            b = float(np.linalg.norm(np.array(estimate["bias_xy"])-truth["bias_xy"]))
        else:a,b = config["invalid_matrix_error"],config["invalid_bias_error"]
        same(saved["errors"][method]["penalty_applied"],not estimate["valid"])
        for key,value in (("matrix_error",a),("bias_error",b),("score",a+b/config["bias_score_scale"])):close(saved["errors"][method][key],value)
    return nfev


def summary_check(rows,summary,config,bank,audit):
    same(len(rows),len(config["qualify_cases"]))
    for method,result in zip(ALL,summary["methods"]):
        same(method,result["method"]);same(result["attempts"],len(rows))
        same(result["valid"],sum(r["fits"][method]["valid"] for r in rows))
        for key in ("score","matrix_error","bias_error"):close(result[key],sum(r["errors"][method][key] for r in rows)/len(rows))
        available = [r for r in rows if r["fits"][method]["valid"]]
        for key in ("score","matrix_error","bias_error"):
            if available:close(result["valid_only_means"][key],sum(r["errors"][method][key] for r in available)/len(available))
            else:same(result["valid_only_means"][key],None)
        same(result["reasons"],dict(Counter(r["fits"][method]["reason"] for r in rows)))
    same(len(summary["methods"]),5);same(len(summary["strata"]),6)
    complete_ok = valid_ok = True
    for result,(task,variant) in zip(summary["strata"],[(t,v) for t in io.TASKS for v in ("UNCHANGED","CHANGED")]):
        subset = [r for r in rows if (r["task"],r["variant"]) == (task,variant)]
        n = len(subset);complete = sum(r["complete_window"] for r in subset)
        valid = sum(r["complete_window"] and r["fits"][config["candidate"]]["valid"] for r in subset)
        same(result,{"task":task,"condition":variant,"attempts":n,"complete":complete,"candidate_valid_complete":valid,
            "complete_fraction":complete/n if n else 0.,"candidate_valid_fraction_complete":valid/complete if complete else 0.,
            "candidate_valid_fraction_all":valid/n if n else 0.})
        complete_ok &= result["complete_fraction"] >= config["minimum_complete_fraction_each_task_condition"]
        valid_ok &= result["candidate_valid_fraction_complete"] >= config["minimum_valid_fraction_complete"]
    groups = sorted({r["group"] for r in rows});rng = np.random.default_rng(config["bootstrap_seed"])
    draws = rng.integers(0,len(groups),(config["bootstrap_replicates"],len(groups)))
    better = True;same(len(summary["contrasts"]),2)
    for result,reference in zip(summary["contrasts"],("SELECTED_HISTORY","RELOCATION_INTEGRAL")):
        values = [sum(r["errors"][config["candidate"]]["score"]-r["errors"][reference]["score"] for r in rows if r["group"] == group)/sum(r["group"] == group for r in rows) for group in groups]
        intervals = np.quantile([np.mean([values[i] for i in draw]) for draw in draws],[.025,.975])
        same(result["reference"],reference);same(result["candidate"],config["candidate"]);same(result["groups"],len(groups))
        close(result["group_differences"],values);close(result["mean_difference"],np.mean(values));close(result["ci95"],intervals)
        better &= bool(intervals[1] < 0)
    same(summary["gates"],{"complete_each_task_condition":bool(complete_ok),"valid_among_complete_each_task_condition":bool(valid_ok),"better_than_both_references":bool(better)})
    same(summary["qualification"],"QUALIFIED_IDENTIFICATION_ONLY" if complete_ok and valid_ok and better else "NOT_QUALIFIED")
    same(summary["failure_reasons"],dict(Counter(r["collection_stop_reason"] for r in rows)))
    same(summary["planned_boundary_unavailable"],sum(not r["boundary_ready"] for r in rows));same(summary["early_task_successes"],sum(r["success"] for r in rows))
    same(summary["task_utility_demonstrated"],False);same(summary["probability_guarantee"],False)
    fees = summary["costs"];train = bank["training_costs"];old = config["historical_nominal_cost"];n = len(rows);units = len({r["unit"] for r in rows})
    same(fees["actual_training_collection"],train);same(fees["actual_qualification_collection"],audit["costs"])
    same(fees["amortization_paired_units"],units);same(fees["new_api_calls"],0)
    same(fees["shared_collection_not_sum_of_method_accounts"],True)
    same(fees["baseline_accounts_end_at_saved_evidence_without_replaying_counterfactual_tasks"],True)
    same(len(fees["method_accounting"]),5)
    for method,result in zip(ALL,fees["method_accounting"]):
        learned = method in METHODS
        online = sum(r["total_steps"]-((r["probe_steps"]+r["reposition_steps"]) if method == "SAVED_C8" else r["probe_steps"] if method == "RELOCATION_INTEGRAL" else 0) for r in rows)
        nominal = train["total_steps"] if learned else 0;frames = train["lifecycle"]["counts"]["simulation_frames_completed"] if learned else 0
        resets = train["lifecycle"]["counts"]["reset_completed"] if learned else 0;controlled = train["lifecycle"]["by_phase"]["CONTROLLED_RESET"]["reset_completed"] if learned else 0
        same(result,{"method":method,"online_steps":online,"new_nominal_steps":nominal,"historical_steps":old["environment_steps"],
            "total_steps":online+nominal+old["environment_steps"],"steps_per_paired_unit":(online+nominal+old["environment_steps"])/units,
            "controlled_resets":n+controlled+old["controlled_resets"],"all_reset_calls":51*n+resets+old["all_reset_calls"],
            "simulation_frames":25500*n+5*online+frames+old["simulation_frames"],"new_response_model_fits":3 if learned else 0,
            "new_causal_output_regressions":24 if learned else 0,
            "online_inference_attempts":sum(r["complete_window"] for r in rows) if learned else 0,
            "online_optimizer_nfev":sum(r["fits"][method]["nfev"] for r in rows)})


def check_evaluation(path):
    manifest,_ = io.load(path);bank,done = io.bank(path);folder = path.parent;identity = {k:manifest[k] for k in io.IDENTITY}
    audit = io.read(folder/"qualify_audit/record_audit.json");summary = io.read(folder/"evaluation/summary.json")
    for record in (audit,summary):
        for k,v in identity.items():same(record[k],v)
    same(audit["integrity"],"PASSED");same(summary["models_sha256"],done["models_sha256"])
    same(summary["qualification_audit_sha256"],io.sha(folder/"qualify_audit/record_audit.json"))
    same(summary["estimates_sha256"],io.sha(folder/"evaluation/estimates.jsonl"))
    for name,value in audit["collection_artifact_sha256"].items():same(io.sha(folder/"qualify"/name),value)
    output = folder/"evaluation_audit";output.mkdir();started = perf_counter_ns()
    try:
        with (folder/"evaluation/estimates.jsonl").open(encoding="utf-8") as handle:rows = [json.loads(line) for line in handle]
        nfev = count = 0
        for count,source in enumerate(lines(folder/"qualify/cases.jsonl.gz"),1):
            require(count <= len(rows),"missing evaluated case")
            nfev += case_check(source,rows[count-1],bank["models"],manifest["config"])
        same(count,len(rows));summary_check(rows,summary,manifest["config"],bank,audit)
        result = {**identity,"integrity":"PASSED","cases":count,"independent_optimizer_nfev":nfev,
            "evaluation_summary_sha256":io.sha(folder/"evaluation/summary.json"),"new_robot_steps":0,"new_api_calls":0,
            "wall_ns":perf_counter_ns()-started}
        io.write(output/"record_audit.json",result);return result
    except BaseException as error:
        io.write(output/"failed_audit.json",{**identity,"integrity":"FAILED","error":type(error).__name__,"message":str(error)})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__);parser.add_argument("stage",choices=("models","evaluation"));parser.add_argument("--manifest",required=True,type=Path)
    args = parser.parse_args();result = (check_models if args.stage == "models" else check_evaluation)(args.manifest.resolve())
    print(json.dumps({"integrity":result["integrity"]}))

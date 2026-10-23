"""TRAIN-only fixed fitting, CAL description and independently grouped QUAL endpoints."""
from collections import Counter,defaultdict
from dataclasses import replace
import gzip
import json
from time import perf_counter_ns

import numpy as np

from src.analysis import response_qualification_io_v1 as io
from src.probe.response_qualification_model_v1 import VisibleTrajectory, samples, fit, predict

MODELS=("FROZEN_OLD_LINEAR_ARX","FRESH_LINEAR_ARX","FRESH_QUADRATIC_STATE")
MODES=("TRUE_INTERFACE","APPLIED_INPUT_DIAGNOSTIC","SENT_INPUT")
STAGES=("ALL_RESPONSE","FIXED_PROBE","PRE_BOUNDARY","MOVEMENT_ALL","LIFT","POST_LIFT","POST_TASK")


def visible(case):
    return VisibleTrajectory(case["task"],case["case_id"],case["split"],case["initial"]["observation"],
        [r["command"] for r in case["physical_rows"]],[r["after"]["observation"] for r in case["physical_rows"]])


def require_data(root,split):
    completion=io.read(root/split.lower()/"completion.json");audit=io.read(root/split.lower()/"audit.json")
    io.require(completion["status"]=="COLLECTED_FOR_INDEPENDENT_AUDIT" and audit["integrity"]=="PASSED","complete audited split required")
    for name,h in completion["artifact_sha256"].items():io.require(io.sha(root/split.lower()/name)==h,"split changed")


def train(manifest_path):
    manifest=io.load(manifest_path);root=manifest_path.parent;require_data(root,"TRAIN")
    output=root/"training";output.mkdir();start=perf_counter_ns();attempts=[];bank={};failure=None
    trajectories=[visible(r) for r in io.rows(root/"train/cases.jsonl.gz")]
    io.require(len(trajectories)==108 and all(t.split=="TRAIN" for t in trajectories),"all TRAIN trajectories required")
    old=io.read(io.ROOT/io.OLD_ARX)["models"]
    try:
        for task in io.TASKS:
            reference=old[task]["LINEAR_ARX"]
            bank[task]={"FROZEN_OLD_LINEAR_ARX":{**reference,"method":"FROZEN_OLD_LINEAR_ARX","task":task}}
            for kind in MODELS[1:]:
                attempt={"task":task,"method":kind,"status":"ATTEMPTED"};attempts.append(attempt)
                bank[task][kind]=fit([t for t in trajectories if t.task==task],task,kind);attempt["status"]="SAVED"
        io.write(output/"models.json",{"models":bank,"training_case_ids":[t.trajectory_id for t in trajectories],
            "source_train_sha256":io.sha(root/"train/cases.jsonl.gz"),"source_train_audit_sha256":io.sha(root/"train/audit.json"),
            "old_reference_sha256":io.OLD_ARX_SHA,"split_access":["TRAIN"],"fits":6})
    except BaseException as error:failure={"type":type(error).__name__,"message":str(error)}
    completion={**{k:manifest[k] for k in io.IDENTITY},"status":"MODELS_SAVED_TRAIN_ONLY" if failure is None else "TRAINING_FAILED_NO_REPAIR",
        "fit_attempts":len(attempts),"fit_results":sum(a["status"]=="SAVED" for a in attempts),"attempts":attempts,"failure":failure,
        "saved_ns":perf_counter_ns(),"wall_ns":perf_counter_ns()-start,"new_api_calls":0,"new_environment_steps":0,
        "artifact_sha256":{p.name:io.sha(p) for p in output.iterdir() if p.is_file()}}
    io.write(output/"completion.json",completion)
    if failure is not None:raise RuntimeError("TRAIN model failure retained: "+str(failure))


def calibrate(manifest_path):
    manifest=io.load(manifest_path);root=manifest_path.parent;require_data(root,"CAL")
    saved=io.read(root/"training/models.json");models=saved["models"];output=root/"calibration";output.mkdir();start=perf_counter_ns()
    cases=[]
    for case in io.rows(root/"cal/cases.jsonl.gz"):
        sample_rows=list(samples(visible(case)))
        for name in MODELS:
            errors=np.array([target-predict(models[case["task"]][name],query) for _,query,target in sample_rows])
            cases.append({"case_id":case["case_id"],"task":case["task"],"group":case["group"],"method":name,
                "n":len(errors),"rmse":None if not len(errors) else float(np.sqrt(np.mean(errors**2))),
                "maximum_l2":None if not len(errors) else float(np.max(np.linalg.norm(errors,axis=1))),
                "missing_reason":"FEWER_THAN_TWO_REAL_DISPLACEMENTS" if not len(errors) else None})
    summaries=[]
    for task in io.TASKS:
        for name in MODELS:
            part=[c for c in cases if c["task"]==task and c["method"]==name]
            summaries.append({"task":task,"method":name,"allocated_trajectories":18,"available_trajectories":sum(c["rmse"] is not None for c in part),
                "empirical_rmse_quantiles":{str(q):float(np.quantile([c["rmse"] for c in part if c["rmse"] is not None],q)) if any(c["rmse"] is not None for c in part) else None for q in (.5,.9,.95)}})
    io.write(output/"description.json",{"cases":cases,"summaries":summaries,"probability_guarantee":False,"safety_guarantee":False,
        "model_selection":False,"new_fits":0,"model_sha256":io.sha(root/"training/models.json")})
    io.write(output/"completion.json",{**{k:manifest[k] for k in io.IDENTITY},"status":"CAL_DESCRIPTION_SAVED_NO_REFIT",
        "saved_ns":perf_counter_ns(),"wall_ns":perf_counter_ns()-start,"new_api_calls":0,"new_environment_steps":0,"new_model_fits":0,
        "artifact_sha256":{"description.json":io.sha(output/"description.json")}})


def lock(manifest_path):
    manifest=io.load(manifest_path);root=manifest_path.parent
    io.require(not (root/"qual").exists(),"QUAL already opened")
    for p in ("training/audit.json","cal/audit.json","calibration/audit.json"):
        io.require(io.read(root/p)["integrity"]=="PASSED","independent pre-QUAL audits required")
    io.write(root/"qualification_lock.json",{**{k:manifest[k] for k in io.IDENTITY},"status":"FROZEN_BEFORE_QUAL_COLLECTION","saved_ns":perf_counter_ns(),
        "artifact_sha256":{p:io.sha(root/p) for p in ("training/models.json","training/completion.json","training/audit.json","cal/audit.json","calibration/description.json","calibration/completion.json","calibration/audit.json")}})


def stage_mapping(case):
    public=case["behavior"]["events"]
    entry=next((e["payload"] for e in public if e["kind"]=="ACQUISITION_ENTRY"),None)
    lifted=False if entry is None else entry["before"]["observation"][2]>=entry["anchor"][2]-.015
    out={}
    for row in case["physical_rows"]:
        phase=row["phase"]
        stage="FIXED_PROBE" if phase=="FIXED_PROBE" else "PRE_BOUNDARY" if phase=="POLICY" else "POST_TASK"
        if phase=="REPOSITION":
            stage="POST_LIFT" if lifted else "LIFT"
            lifted=lifted or row["after"]["observation"][2]>=entry["anchor"][2]-.015
        out[row["logical_step"]]=stage
    return out


def evaluate_case(case,models):
    step_rows=[];buckets=defaultdict(list);stages=stage_mapping(case)
    for i,query,target in samples(visible(case)):
        row=case["physical_rows"][i];fault=case["fault_oracle"]
        if case["fault_transition"] and i>=case["fault_transition"]["at_calls"]:fault=case["fault_transition"]["active_fault_oracle"]
        command=np.array(query.command);mapped=np.array(fault["matrix_xy"])@command[:2]+fault["bias_xy"]
        true=command.copy();true[:2]=np.clip(mapped,-1,1)
        inputs={"TRUE_INTERFACE":true,"APPLIED_INPUT_DIAGNOSTIC":row["executed_action_oracle"],"SENT_INPUT":command}
        stage=stages[i]
        for mode,value in inputs.items():
            q=replace(query,command=tuple(value))
            for name in MODELS:
                prediction=predict(models[name],q);error=target-prediction
                selected=["ALL_RESPONSE",stage]+(["MOVEMENT_ALL"] if stage in ("LIFT","POST_LIFT") else [])
                for label in selected:buckets[name,mode,label].append(error)
                step_rows.append({"case_id":case["case_id"],"step":i,"stage":stage,"method":name,"input_mode":mode,
                    "prediction":prediction.tolist(),"target":target.tolist(),"error":error.tolist(),
                    "transformed_input_outside_support":bool(np.any(abs(mapped)>1)),
                    "applied_input_semantics_changed":mode=="APPLIED_INPUT_DIAGNOSTIC"})
    metrics=[]
    for name in MODELS:
        for mode in MODES:
            for stage in STAGES:
                errors=buckets[name,mode,stage]
                metrics.append({"case_id":case["case_id"],"task":case["task"],"group":case["group"],"unit":case["unit"],
                    "condition":case["variant"],"method":name,"input_mode":mode,"stage":stage,"n":len(errors),
                    "rmse":None if not errors else float(np.sqrt(np.mean(np.array(errors)**2))),
                    "missing_reason":"NO_EXECUTED_RESPONSE_IN_STAGE" if not errors else None})
    return step_rows,metrics


def statistics(metrics,case_registry):
    io.require(len(case_registry)==108 and len({r["case_id"] for r in case_registry})==108,"all QUAL cases required")
    primary=[r for r in metrics if r["stage"]=="POST_TASK" and r["input_mode"]=="TRUE_INTERFACE"]
    index={(r["case_id"],r["method"]):r for r in primary};groups=[]
    for group in range(18):
        ids=[r["case_id"] for r in case_registry if r["group"]==group]
        values={name:[index[c,name]["rmse"] for c in ids if index[c,name]["rmse"] is not None] for name in MODELS}
        io.require(len(ids)==6,"six registered units per group")
        groups.append({"group":group,"planned_units":6,"available_units":len(values[MODELS[0]]),
            "mean_rmse":{name:None if not v else float(np.mean(v)) for name,v in values.items()}})
    complete=all(g["available_units"]>0 for g in groups)
    means={name:None if not complete else float(np.mean([g["mean_rmse"][name] for g in groups])) for name in MODELS}
    diff=ci=None
    if complete:
        delta=np.array([g["mean_rmse"][MODELS[2]]-g["mean_rmse"][MODELS[1]] for g in groups])
        rng=np.random.default_rng(20261025);draws=np.concatenate([rng.choice(np.arange(s,18,3),size=(10000,6),replace=True) for s in range(3)],axis=1)
        diff=float(delta.mean());ci=np.quantile(delta[draws].mean(axis=1),[.025,.975]).tolist()
    cells=[]
    for task in io.TASKS:
        for condition in ("UNCHANGED","CHANGED"):
            part=[r for r in primary if r["task"]==task and r["condition"]==condition]
            values={name:[r["rmse"] for r in part if r["method"]==name and r["rmse"] is not None] for name in MODELS}
            # One trajectory for each group in a task/condition cell.
            cell_means={name:None if not v else float(np.mean(v)) for name,v in values.items()}
            available=len(values[MODELS[0]])
            cells.append({"task":task,"condition":condition,"allocated":18,"available":available,"means":cell_means,
                "quadratic_not_worse_than_both":bool(available and cell_means[MODELS[2]]<=max(cell_means[MODELS[0]],cell_means[MODELS[1]]))})
    requirements={"all_18_groups_have_observed_primary_response":complete,"all_six_cells_available":all(c["available"]>0 for c in cells),
        "primary_95_upper_below_zero":ci is not None and ci[1]<0,
        "quadratic_overall_mean_below_old_linear":complete and means[MODELS[2]]<means[MODELS[0]],
        "no_cell_worse_than_both_linears":all(c["quadratic_not_worse_than_both"] for c in cells)}
    return {"qualification":"PASSED_PREDICTIVE_QUALIFICATION_ONLY" if all(requirements.values()) else "NOT_QUALIFIED",
        "requirements":requirements,"means":means,"primary_difference":diff,"primary_group_bootstrap_95":ci,
        "groups":groups,"task_condition_cells":cells,"allocated_executions":108,"independent_groups":18,
        "no_task_utility_or_safety_or_novelty_claim":True}


def evaluate(manifest_path):
    manifest=io.load(manifest_path);root=manifest_path.parent;require_data(root,"QUAL");io.phase_gate(root,"QUAL")
    output=root/"evaluation";output.mkdir();start=perf_counter_ns();models=io.read(root/"training/models.json")["models"]
    metrics=[];registry=[]
    with gzip.open(output/"step_predictions.jsonl.gz","xt",encoding="utf-8") as log:
        for case in io.rows(root/"qual/cases.jsonl.gz"):
            steps,cells=evaluate_case(case,models[case["task"]]);metrics.extend(cells)
            for row in steps:log.write(json.dumps(row,separators=(",",":"),allow_nan=False)+"\n")
            registry.append({k:case[k] for k in ("case_id","group","unit","task","variant","success","total_steps","reposition_steps","task_steps","stop_reason")})
    result=statistics(metrics,registry)
    io.write(output/"trajectory_metrics.json",metrics);io.write(output/"case_registry.json",registry);io.write(output/"statistics.json",result)
    io.write(output/"completion.json",{**{k:manifest[k] for k in io.IDENTITY},"status":"COMPLETE_QUALIFICATION_EVALUATION","wall_ns":perf_counter_ns()-start,
        "new_api_calls":0,"new_environment_steps":0,"new_model_fits":0,"artifact_sha256":{p.name:io.sha(p) for p in output.iterdir() if p.is_file()}})
    print(json.dumps({"qualification":result["qualification"],"primary_difference":result["primary_difference"],"interval":result["primary_group_bootstrap_95"]}),flush=True)

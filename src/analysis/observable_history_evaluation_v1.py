"""TRAIN-only fixed predictors; descriptive CAL; independent-group TEST endpoints."""
from collections import defaultdict
from dataclasses import asdict
import gzip
import json
import subprocess
from time import perf_counter_ns
import numpy as np

from src.analysis import observable_history_io_v1 as io
from src.probe.observable_history_model_v1 import HistoryTrajectory,fit_linear,gru_normalization,predict,targets

STAGES=("ALL_RESPONSE","FIXED_PROBE","PRE_BOUNDARY","MOVEMENT_ALL","LIFT","POST_LIFT","MEASUREMENT","POST_TASK")
CONTEXTS=("NOMINAL_UNCHANGED","NOMINAL_CHANGED","BIASED_UNCHANGED","BIASED_CHANGED")


def visible(case):
    return HistoryTrajectory(case["task"],case["case_id"],case["split"],case["initial"]["observation"],
        [r["command"] for r in case["physical_rows"]],[r["after"]["observation"] for r in case["physical_rows"]])


def require_data(root,split):
    completion=io.read(root/split.lower()/"completion.json");audit=io.read(root/split.lower()/"audit.json")
    io.require(completion["status"]=="COLLECTED_FOR_INDEPENDENT_AUDIT" and audit["integrity"]=="PASSED","complete independently audited data required")
    for n,h in completion["artifact_sha256"].items():io.require(io.sha(root/split.lower()/n)==h,"split changed")


def worker(mode,bundle,models,output,log):
    runtime=io.read(io.RUNTIME)
    for n,h in runtime["file_sha256"].items():io.require(io.sha(n)==h,"frozen training runtime changed")
    command=[str(io.TRAIN_PYTHON),str(io.ROOT/"scripts/train_observable_history_gru_v1.py"),mode,"--output",str(output)]
    if bundle is not None:command.extend(["--bundle",str(bundle)])
    if models is not None:command.extend(["--models",str(models)])
    with log.open("x",encoding="utf-8") as handle:
        result=subprocess.run(command,cwd=io.ROOT,stdout=handle,stderr=subprocess.STDOUT,timeout=7200,check=False)
    io.require(result.returncode==0,"isolated TRAIN/forward worker failed; preserve log without retry")


def train(manifest_path):
    m=io.load(manifest_path);root=manifest_path.parent;require_data(root,"TRAIN");output=root/"training";output.mkdir();start=perf_counter_ns()
    records=list(io.rows(root/"train/cases.jsonl.gz"));io.require(len(records)==216,"all TRAIN allocations required")
    attempts=[];models={};entries=[];failure=None
    try:
        for b,bank in enumerate(io.PROGRAMS):
            models[bank]={}
            for j,task in enumerate(io.TASKS):
                ts=[visible(c) for c in records if c["task"]==task and c["measurement_program"]==bank]
                io.require(len(ts)==36 and all(t.split=="TRAIN" for t in ts),"complete matching source-bank TRAIN")
                models[bank][task]={}
                for name in io.MODELS[:3]:
                    a={"source_bank":bank,"task":task,"method":name,"status":"ATTEMPTED"};attempts.append(a)
                    models[bank][task][name]=fit_linear(ts,task,name);a["status"]="SAVED"
                entries.append({"task":task,"source_bank":bank,"trajectories":[asdict(t) for t in ts],"statistics":gru_normalization(ts,task),
                    "initialization_seed":202610260+3*b+j,"sampling_seed":202610270+3*b+j})
        io.write(output/"public_train_bundle.json",{"schema":"PUBLIC_TRAIN_BUNDLE_V1","entries":entries})
        worker("train",output/"public_train_bundle.json",None,output/"gru",output/"gru_process.txt")
        result=io.read(output/"gru/completion.json");io.require(result["status"]=="TWELVE_GRU_MODELS_SAVED","GRU completion required")
        for e in entries:
            for name in io.MODELS[3:]:models[e["source_bank"]][e["task"]][name]=io.read(output/"gru"/(e["source_bank"]+"_"+e["task"]+"_"+name+".json"))
        io.write(output/"models.json",{"models":models,"training_case_ids":[c["case_id"] for c in records],"split_access":["TRAIN"],"fits":30,
            "source_train_sha256":io.sha(root/"train/cases.jsonl.gz"),"source_train_audit_sha256":io.sha(root/"train/audit.json"),"runtime_sha256":io.sha(io.RUNTIME)})
    except BaseException as error:failure={"type":type(error).__name__,"message":str(error)}
    io.write(output/"completion.json",{**{k:m[k] for k in io.IDENTITY},"status":"THIRTY_MODELS_SAVED_TRAIN_ONLY" if failure is None else "TRAINING_FAILED_NO_REPAIR",
        "linear_attempts":attempts,"linear_fits_attempted":len(attempts),"linear_fits_saved":sum(a["status"]=="SAVED" for a in attempts),
        "failure":failure,"saved_ns":perf_counter_ns(),"wall_ns":perf_counter_ns()-start,"new_api_calls":0,"new_environment_steps":0,
        "artifact_sha256":{p.relative_to(output).as_posix():io.sha(p) for p in output.rglob("*") if p.is_file()}})
    if failure is not None:raise RuntimeError("TRAIN failure retained without repair: "+str(failure))


def stages(case):
    entry=next((e["payload"] for e in case["behavior"]["events"] if e["kind"]=="ACQUISITION_ENTRY"),None)
    lifted=False if entry is None else entry["before"]["observation"][2]>=entry["anchor"][2]-.015
    out=[]
    for r in case["physical_rows"]:
        phase=r["phase"]
        label={"FIXED_PROBE":"FIXED_PROBE","POLICY":"PRE_BOUNDARY","MEASURE_FEEDBACK":"MEASUREMENT","MEASURE_BALANCED":"MEASUREMENT","TASK_AFTER_MEASUREMENT":"POST_TASK"}.get(phase)
        if phase=="REPOSITION":
            label="POST_LIFT" if lifted else "LIFT";lifted=lifted or r["after"]["observation"][2]>=entry["anchor"][2]-.015
        io.require(label is not None,"unknown executed phase");out.append(label)
    return out


def case_metrics(case,models,step_log=None):
    t=visible(case);target=targets(t);labels=stages(case)[2:];metrics=[]
    for bank in io.PROGRAMS:
        for name in io.MODELS:
            predictions=predict(models[bank][case["task"]][name],t);errors=target-predictions
            for label in STAGES:
                mask=np.array([label=="ALL_RESPONSE" or label==stage or label=="MOVEMENT_ALL" and stage in ("LIFT","POST_LIFT") for stage in labels],bool)
                value=errors[mask];n=len(value)
                metrics.append({"case_id":case["case_id"],"task":case["task"],"group":case["group"],"unit":case["unit"],"context":case["context"],
                    "measurement_program":case["measurement_program"],"source_bank":bank,"method":name,"input_mode":"SENT_INPUT","stage":label,"n":n,
                    "rmse":None if not n else float(np.sqrt(np.mean(value**2))),"missing_reason":None if n else "NO_EXECUTED_COMMON_RESPONSE_IN_STAGE"})
            if step_log is not None:
                for k,(p,y,err) in enumerate(zip(predictions,target,errors)):
                    step_log.write(json.dumps({"case_id":case["case_id"],"source_bank":bank,"method":name,"step":k+2,"stage":labels[k],"prediction":p.tolist(),"target":y.tolist(),"error":err.tolist()},separators=(",",":"),allow_nan=False)+"\n")
    return metrics


def statistics(metrics,registry):
    io.require(len(registry)==432 and len({c["case_id"] for c in registry})==432,"all TEST allocations required")
    primary=[r for r in metrics if r["stage"]=="POST_TASK"]
    index={(r["case_id"],r["source_bank"],r["method"]):r for r in primary}
    io.require(len(index)==len(primary)==432*10,"primary model population")
    by_case={}
    for c in registry:
        values={name:[index[c["case_id"],b,name]["rmse"] for b in io.PROGRAMS] for name in io.MODELS}
        flags=[v is not None for value in values.values() for v in value];io.require(all(flags) or not any(flags),"unequal model response populations")
        by_case[c["case_id"]]={name:None if not all(flags) else float(np.mean(value)) for name,value in values.items()}
    def means(cases):
        available=[c for c in cases if by_case[c["case_id"]][io.MODELS[0]] is not None]
        return len(available),{name:None if not available else float(np.mean([by_case[c["case_id"]][name] for c in available])) for name in io.MODELS}
    groups=[]
    for g in range(18):
        part=[c for c in registry if c["group"]==g];io.require(len(part)==24,"24 registered units/group")
        n,value=means(part);groups.append({"group":g,"boundary":(16,32,64)[g%3],"allocated":24,"available":n,"means":value})
    complete=all(g["available"] for g in groups);overall={name:None if not complete else float(np.mean([g["means"][name] for g in groups])) for name in io.MODELS}
    delta=ci=None
    if complete:
        d=np.array([g["means"]["GRU_WINDOW16"]-g["means"]["GRU_WINDOW1"] for g in groups]);rng=np.random.default_rng(20261028)
        draws=np.concatenate([rng.choice(np.arange(s,18,3),size=(10000,6),replace=True) for s in range(3)],axis=1)
        delta=float(np.mean(d));ci=np.quantile(d[draws].mean(axis=1),[.025,.975]).tolist()
    cells=[]
    for task in io.TASKS:
        for context in CONTEXTS:
            for program in io.PROGRAMS:
                part=[c for c in registry if (c["task"],c["context"],c["measurement_program"])==(task,context,program)];io.require(len(part)==18,"18 allocated group trajectories/cell")
                n,value=means(part);cells.append({"task":task,"context":context,"measurement_program":program,"allocated":18,"available":n,"means":value,
                    "gru16_not_worse_than_both_linears":bool(n and value["GRU_WINDOW16"]<=max(value["HISTORY_LINEAR10"],value["STATE_LINEAR20"]))})
    requirements={"all_18_groups_have_paired_response":bool(complete),"all_24_cells_nonempty":all(c["available"] for c in cells),
        "primary_95_upper_below_zero":ci is not None and ci[1]<0,
        "gru16_overall_below_history_linear10":bool(complete and overall["GRU_WINDOW16"]<overall["HISTORY_LINEAR10"]),
        "gru16_overall_below_state_linear20":bool(complete and overall["GRU_WINDOW16"]<overall["STATE_LINEAR20"]),
        "no_cell_worse_than_both_linears":all(c["gru16_not_worse_than_both_linears"] for c in cells)}
    transfer=[]
    for name in io.MODELS:
        stream=[];cross={}
        for source in io.PROGRAMS:
            for deploy in io.PROGRAMS:
                vals=[]
                for g in range(18):
                    xs=[index[c["case_id"],source,name]["rmse"] for c in registry if c["group"]==g and c["measurement_program"]==deploy]
                    xs=[x for x in xs if x is not None];vals.append(None if not xs else float(np.mean(xs)))
                cross[source+"->"+deploy]={"groups_available":sum(x is not None for x in vals),"group_means":vals,"mean":None if any(x is None for x in vals) else float(np.mean(vals))}
        for g in range(18):
            values=[cross[a+"->"+b]["group_means"][g] for a,b in (("FEEDBACK8","FEEDBACK8"),("FEEDBACK8","BALANCED8"),("BALANCED8","FEEDBACK8"),("BALANCED8","BALANCED8"))]
            stream.append(None if any(x is None for x in values) else values[0]-values[1]-values[2]+values[3])
        transfer.append({"method":name,"crosses":cross,"group_difference_in_differences":stream,"descriptive_interaction_mean":None if any(x is None for x in stream) else float(np.mean(stream))})
    return {"qualification":"PASSED_PREDICTIVE_QUALIFICATION_ONLY" if all(requirements.values()) else "NOT_QUALIFIED","requirements":requirements,"means":overall,
        "primary_difference":delta,"primary_group_bootstrap_95":ci,"groups":groups,"task_context_program_cells":cells,"source_transfer":transfer,
        "allocated_executions":432,"available_primary_trajectories":sum(v[io.MODELS[0]] is not None for v in by_case.values()),"independent_groups":18,"source_banks_are_not_independent_replicates":True,
        "no_task_utility_or_safety_or_novelty_claim":True}


def calibrate(manifest_path):
    m=io.load(manifest_path);root=manifest_path.parent;require_data(root,"CAL");output=root/"calibration";output.mkdir();start=perf_counter_ns()
    models=io.read(root/"training/models.json")["models"];rows=[];public=[]
    for c in io.rows(root/"cal/cases.jsonl.gz"):
        rows.extend(r for r in case_metrics(c,models) if r["stage"]=="ALL_RESPONSE");public.append(asdict(visible(c)))
    io.require(len(rows)==1080,"full CAL allocation")
    summaries=[]
    for task in io.TASKS:
        for bank in io.PROGRAMS:
            for name in io.MODELS:
                part=[r for r in rows if r["task"]==task and r["source_bank"]==bank and r["method"]==name];values=[r["rmse"] for r in part if r["rmse"] is not None]
                summaries.append({"task":task,"source_bank":bank,"method":name,"allocated":36,"available":len(values),"empirical_rmse_quantiles":{str(q):None if not values else float(np.quantile(values,q)) for q in (.5,.9,.95)}})
    io.write(output/"description.json",{"cases":rows,"summaries":summaries,"model_sha256":io.sha(root/"training/models.json"),"new_fits":0,"model_selection":False,"safety_guarantee":False,"probability_guarantee":False})
    io.write(output/"public_forward_bundle.json",{"schema":"PUBLIC_FORWARD_BUNDLE_V1","trajectories":public})
    worker("forward",output/"public_forward_bundle.json",root/"training/models.json",output/"torch_forward_audit.json",output/"torch_process.txt")
    io.write(output/"completion.json",{**{k:m[k] for k in io.IDENTITY},"status":"CAL_DESCRIPTION_SAVED_NO_REFIT","wall_ns":perf_counter_ns()-start,"saved_ns":perf_counter_ns(),"new_environment_steps":0,"new_api_calls":0,
        "artifact_sha256":{p.name:io.sha(p) for p in output.iterdir() if p.is_file()}})


def lock(manifest_path):
    m=io.load(manifest_path);root=manifest_path.parent;io.require(not (root/"test").exists(),"TEST already opened")
    paths=("training/models.json","training/completion.json","training/audit.json","cal/audit.json","calibration/description.json","calibration/completion.json","calibration/audit.json")
    for n in ("training/audit.json","cal/audit.json","calibration/audit.json"):io.require(io.read(root/n)["integrity"]=="PASSED","pre-TEST audits required")
    io.write(root/"test_lock.json",{**{k:m[k] for k in io.IDENTITY},"status":"FROZEN_BEFORE_TEST","saved_ns":perf_counter_ns(),"artifact_sha256":{n:io.sha(root/n) for n in paths}})


def evaluate(manifest_path):
    m=io.load(manifest_path);root=manifest_path.parent;require_data(root,"TEST");io.phase_gate(root,"TEST");output=root/"evaluation";output.mkdir();start=perf_counter_ns()
    models=io.read(root/"training/models.json")["models"];metrics=[];registry=[];public=[]
    with gzip.open(output/"step_predictions.jsonl.gz","xt",encoding="utf-8") as log:
        for c in io.rows(root/"test/cases.jsonl.gz"):
            metrics.extend(case_metrics(c,models,log));public.append(asdict(visible(c)))
            registry.append({k:c[k] for k in ("case_id","group","unit","task","context","measurement_program","planned_boundary","success","total_steps","reposition_steps","measurement_steps","task_steps","stop_reason")})
    result=statistics(metrics,registry);io.write(output/"trajectory_metrics.json",metrics);io.write(output/"case_registry.json",registry);io.write(output/"statistics.json",result)
    io.write(output/"public_forward_bundle.json",{"schema":"PUBLIC_FORWARD_BUNDLE_V1","trajectories":public})
    worker("forward",output/"public_forward_bundle.json",root/"training/models.json",output/"torch_forward_audit.json",output/"torch_process.txt")
    io.write(output/"completion.json",{**{k:m[k] for k in io.IDENTITY},"status":"COMPLETE_TEST_EVALUATION","wall_ns":perf_counter_ns()-start,"new_api_calls":0,"new_environment_steps":0,"new_model_fits":0,
        "artifact_sha256":{p.name:io.sha(p) for p in output.iterdir() if p.is_file()}})
    print(json.dumps({"qualification":result["qualification"],"primary_difference":result["primary_difference"],"interval":result["primary_group_bootstrap_95"]}),flush=True)

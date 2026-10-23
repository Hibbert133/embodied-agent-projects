"""Independent table reconstruction of all frozen movement/task statistics."""
import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import sys
from time import perf_counter_ns

import numpy as np

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.analysis import movement_task_io_v1 as io


def require(ok,message):
    if not ok:raise ValueError(message)


def check_statistics(rows, saved, config, arx_costs):
    io.validate(config);require(len(rows)==1296,"complete statistics population required")
    table={};expected={(s["unit"],s["variant"]):s for s in config["cases"]}
    for row in rows:
        key=(row["unit"],row["variant"])
        require(key in expected and key not in table and set(row)==set(io.COMPACT),"missing, duplicate or extra task row")
        require(all(type(row[k]) is type(v) and row[k]==v for k,v in expected[key].items()),"metadata changed")
        require(all(type(row[k]) is bool for k in ("completed","success","boundary_ready","stopped")) and row["completed"],"unfinished or nonboolean outcome")
        require(type(row["total_steps"]) is int and 0<=row["total_steps"]<=500
                and type(row["deadline_loss"]) is int and row["deadline_loss"]==(row["total_steps"] if row["success"] else 500)
                and not(row["stopped"] and row["success"]),"loss convention changed")
        for name in ("reposition_steps","task_steps","policy_queries","parameter_fit_attempts","parameter_fit_results",
                     "optimizer_nfev","movement_fit_attempts","movement_fit_results","movement_optimizer_nfev"):
            require(type(row[name]) is int and row[name]>=0,"malformed cost")
        require(row["reposition_steps"]<=64 and row["reposition_steps"]+row["task_steps"]<=row["total_steps"]
                and row["parameter_fit_attempts"]==row["parameter_fit_results"] and row["movement_fit_attempts"]==row["movement_fit_results"]<=1
                and row["movement_optimizer_nfev"]<=row["optimizer_nfev"],"budget or fit counters changed")
        table[key]=row
    require(set(table)==set(expected),"missing task units")
    require(arx_costs["known_full_source_environment_steps"]==23314 and arx_costs["known_full_source_controlled_resets"]==432
            and arx_costs["direct_source_collection"]["all_reset_calls"] is None
            and arx_costs["direct_source_collection"]["simulation_frames"] is None,"unknown source costs became zero")
    methods={};metrics={}
    for method in io.METHODS:
        part=[table[u,c+"_"+method] for u in range(162) for c in io.CONDITIONS]
        array=np.array([[int(r["success"]),r["deadline_loss"],r["total_steps"]] for r in part],dtype=np.int64).reshape(54,6,3)
        metrics[method]=array
        charged_steps=27154 if method=="MOVE_ARX_KEEP" else 3840
        charged_resets=912 if method=="MOVE_ARX_KEEP" else 480
        methods[method]={"cases":324,"successes":int(array[:,:,0].sum()),"stops":sum(int(r["stopped"]) for r in part),
            "actions":dict(sorted(Counter(r["action"] for r in part).items())),
            **{"mean_"+name:float(np.mean([r[name] for r in part])) for name in ("deadline_loss","total_steps","reposition_steps","task_steps")},
            **{"total_"+name:int(np.sum([r[name] for r in part])) for name in ("policy_queries","parameter_fit_attempts","optimizer_nfev","movement_optimizer_nfev")},
            "historical_source_environment_steps":charged_steps,"historical_source_controlled_resets":charged_resets,
            "mean_amortized_actual_steps":float((array[:,:,2].sum()+charged_steps)/324),
            "by_condition_task":[]}
        for condition in io.CONDITIONS:
            for task in io.TASKS:
                sub=[r for r in part if r["task"]==task and r["variant"]==condition+"_"+method]
                require(len(sub)==54,"task/condition denominator changed")
                methods[method]["by_condition_task"].append({"condition":condition,"task":task,"cases":54,
                    "successes":sum(int(r["success"]) for r in sub),"mean_deadline_loss":float(np.mean([r["deadline_loss"] for r in sub]))})
    generator=np.random.default_rng(20261023)
    selections=[]
    for boundary in (16,32,64):
        stratum=sorted({s["unit"]//3 for s in config["cases"] if s["planned_boundary"]==boundary})
        require(len(stratum)==18,"boundary stratum changed")
        selections.append(np.array(stratum)[generator.integers(0,18,(10000,18))])
    selected=np.hstack(selections);contrasts=[]
    for k,(method,base) in enumerate(io.CONTRASTS):
        delta=metrics[method]-metrics[base];group_means=delta.mean(axis=1)
        resampled=group_means[selected].mean(axis=1)
        limits=np.percentile(resampled,[2.5,97.5],axis=0)
        contrasts.append({"method":method,"reference":base,"role":"PRIMARY" if k==0 else "SECONDARY_UNADJUSTED",
            "group_values":group_means.tolist(),"metrics":{name:{"difference":float(delta[:,:,j].mean()),
                "paired_group_percentile_95":limits[:,j].tolist()} for j,name in enumerate(("success_rate","deadline_loss","actual_steps"))},
            "success_to_failure":int(np.sum((metrics[base][:,:,0]==1)&(metrics[method][:,:,0]==0))),
            "failure_to_success":int(np.sum((metrics[base][:,:,0]==0)&(metrics[method][:,:,0]==1)))})
    rebuilt={"methods":methods,"contrasts":contrasts,"independent_groups":54,"boundary_strata_groups":[18,18,18],
        "primary_loss_upper_below_zero":bool(contrasts[0]["metrics"]["deadline_loss"]["paired_group_percentile_95"][1]<0),
        "primary_successes_not_lower":methods["MOVE_ARX_KEEP"]["successes"]>=methods["MOVE_INTEGRAL"]["successes"],
        "study_actual_control_steps":sum(r["total_steps"] for r in rows),"shared_historical_known_steps_once":27154,
        "shared_historical_controlled_resets_once":912,"historical_native_and_all_reset_total_unknown":True,
        "new_api_calls":0,"algorithm_novelty_demonstrated":False,"physical_model_transfer_qualified":False,
        "scope":"Fixed-method task comparisons; early successes and all failures retained; secondary intervals unadjusted; no adaptive acquisition claim."}
    leaves=0
    def compare(actual, expected):
        nonlocal leaves
        if type(expected) is dict:
            require(type(actual) is dict and set(actual)==set(expected),"statistics fields changed")
            for key in expected:compare(actual[key],expected[key])
        elif type(expected) is list:
            require(type(actual) is list and len(actual)==len(expected),"statistics dimensions changed")
            for a,b in zip(actual,expected):compare(a,b)
        elif type(expected) is float:
            require(type(actual) is float and np.isfinite(actual) and np.isclose(actual,expected,atol=2e-10,rtol=2e-10),"statistics arithmetic differs");leaves+=1
        else:require(type(actual) is type(expected) and actual==expected,"statistics labels or counts differ");leaves+=1
    compare(saved,rebuilt)
    return {"executions_checked":len(rows),"statistics_leaves_checked":leaves,"contrasts_checked":6,"independent_groups":54}


def audit(path):
    started=perf_counter_ns();manifest,_,_=io.load(path);folder=path.parent/"analysis"
    completed=io.read(folder/"completion.json");summary=io.read(folder/"summary.json")
    for value in (completed,summary):
        require(all(value[k]==manifest[k] for k in io.IDENTITY),"foreign statistics artifacts")
        require(value["status"]=="COMPLETE_FIXED_METHOD_TASK_COMPARISON","unfinished evaluation")
    require(set(completed["artifact_sha256"])=={"summary.json","all_cases.json","failures_and_rejections.json"},"missing evaluated cases")
    for name,expected in completed["artifact_sha256"].items():require(io.sha(folder/name)==expected,"evaluation artifact changed")
    record_path=path.parent/"audit/record_audit.json";checked=io.read(record_path)
    require(io.sha(record_path)==summary["record_audit_sha256"] and checked["integrity"]=="PASSED","missing record audit")
    for name,expected in checked["collection_artifact_sha256"].items():require(io.sha(path.parent/"collection"/name)==expected,"collection changed after audit")
    output=path.parent/"statistics_audit";output.mkdir()
    try:
        with gzip.open(path.parent/"collection/cases.jsonl.gz","rt",encoding="utf-8") as handle:rows=[io.compact(json.loads(v)) for v in handle]
        require(rows==checked["rows"]==io.read(folder/"all_cases.json"),"case list changed between stages")
        failures=[r for r in rows if not r["success"] or r["stopped"] or r["action"] in ("REJECT_ARX_KEEP_SAVED_C8","NO_LIVE_BOUNDARY","ENDED_NO_UPDATE")]
        require(failures==io.read(folder/"failures_and_rejections.json"),"failed or early-ended cases omitted")
        result=check_statistics(rows,summary["statistics"],manifest["config"],manifest["arx_source_receipt"]["costs"])
        require(summary["costs"]==checked["costs"] and summary["audit_computations"]==checked["audit_computations"],"costs changed after record audit")
        result={**{k:manifest[k] for k in io.IDENTITY},"integrity":"PASSED",**result,"record_audit_sha256":io.sha(record_path),
            "analysis_artifact_sha256":completed["artifact_sha256"],"wall_ns":perf_counter_ns()-started,"new_robot_steps":0,"new_api_calls":0}
        io.write(output/"check.json",result);return result
    except BaseException as error:
        io.write(output/"failed_audit.json",{"integrity":"FAILED","error":type(error).__name__,"message":str(error)});raise


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("manifest",type=Path)
    print(json.dumps(audit(parser.parse_args().manifest.resolve())))

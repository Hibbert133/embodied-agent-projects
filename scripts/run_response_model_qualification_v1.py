"""One-shot frozen response qualification; no online LLM dependency or call path."""
import argparse
from pathlib import Path
import sys
from time import perf_counter_ns
import traceback

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io


def pipeline(path):
    from src.analysis import response_qualification_collect_v1 as collect
    from src.analysis import response_qualification_evaluation_v1 as evaluation
    from src.analysis import response_qualification_audit_v1 as audit
    from scripts.report_response_model_qualification_v1 import report
    io.load(path);root=path.parent;start=perf_counter_ns();steps=[];failure=None;network={}
    actions=[("collect_train",lambda:collect.collect(path,"TRAIN")),("audit_train",lambda:audit.audit_split(path,"TRAIN")),
        ("train",lambda:evaluation.train(path)),("audit_models",lambda:audit.audit_models(path)),
        ("collect_cal",lambda:collect.collect(path,"CAL")),("audit_cal",lambda:audit.audit_split(path,"CAL")),
        ("calibrate",lambda:evaluation.calibrate(path)),("audit_calibration",lambda:audit.audit_calibration(path)),
        ("lock",lambda:evaluation.lock(path)),("collect_qual",lambda:collect.collect(path,"QUAL")),
        ("audit_qual",lambda:audit.audit_split(path,"QUAL")),("evaluate",lambda:evaluation.evaluate(path)),
        ("audit_numeric",lambda:audit.audit_numeric(path))]
    # Exclusive claim prevents repeating an interrupted frozen allocation.
    io.write(root/"pipeline_claim.json",{"started_ns":start,"source_git_commit":io.git("rev-parse","HEAD"),"automatic_restart":False})
    for name,action in actions:
        before=perf_counter_ns();entry={"stage":name,"started_ns":before,"status":"STARTED"};steps.append(entry)
        print("STAGE "+name,flush=True)
        io.write(root/"pipeline_progress.json",{"steps":steps},exclusive=False)
        try:
            with io.forbid_online_calls(network):action()
            entry["status"]="COMPLETE"
        except BaseException as error:
            failure={"stage":name,"type":type(error).__name__,"message":str(error),"traceback":traceback.format_exc()}
            entry["status"]="FAILED_RETAINED"
        entry["completed_ns"]=perf_counter_ns();entry["wall_ns"]=entry["completed_ns"]-before
        entry["attempted_network_calls"]=network["attempted_network_calls"]
        io.write(root/"pipeline_progress.json",{"steps":steps,"failure":failure},exclusive=False)
        if failure is not None:break
    io.write(root/"pipeline_completion.json",{"status":"COMPLETE" if failure is None else "INCOMPLETE_NO_RETRY",
        "steps":steps,"failure":failure,"wall_ns":perf_counter_ns()-start,"new_api_calls":0,
        "attempted_network_calls":sum(s["attempted_network_calls"] for s in steps)})
    report(path)
    if failure is not None:raise RuntimeError("Frozen experiment stopped; all partial records retained: "+str(failure))


def main():
    parser=argparse.ArgumentParser();parser.add_argument("action",choices=("prepare","run","collect","train","calibrate","lock","evaluate"))
    parser.add_argument("--manifest",type=Path);parser.add_argument("--split",choices=io.SPLITS);args=parser.parse_args()
    if args.action=="prepare":io.prepare();return
    if args.manifest is None:parser.error("--manifest required")
    path=args.manifest.resolve()
    if args.action=="run":pipeline(path)
    elif args.action=="collect":
        if args.split is None:parser.error("--split required")
        from src.analysis.response_qualification_collect_v1 import collect
        with io.forbid_online_calls({}):collect(path,args.split)
    else:
        from src.analysis import response_qualification_evaluation_v1 as evaluation
        with io.forbid_online_calls({}):getattr(evaluation,args.action)(path)


if __name__=="__main__":main()

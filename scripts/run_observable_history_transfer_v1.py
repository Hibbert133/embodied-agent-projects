"""One-shot observable-history study; scientific API transports fail closed."""
import argparse
from pathlib import Path
import sys
from time import perf_counter_ns
import traceback

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.analysis import observable_history_io_v1 as io


def pipeline(path):
    from src.analysis import observable_history_collect_v1 as collect
    from src.analysis import observable_history_evaluation_v1 as evaluation
    from src.analysis import observable_history_audit_v1 as audit
    from scripts.report_observable_history_transfer_v1 import report
    io.load(path);root=path.parent;start=perf_counter_ns();stages=[];failure=None;network={}
    actions=[("collect_train",lambda:collect.collect(path,"TRAIN")),("audit_train",lambda:audit.audit_split(path,"TRAIN")),
        ("train_thirty_models",lambda:evaluation.train(path)),("audit_models",lambda:audit.audit_models(path)),
        ("collect_cal",lambda:collect.collect(path,"CAL")),("audit_cal",lambda:audit.audit_split(path,"CAL")),
        ("calibrate",lambda:evaluation.calibrate(path)),("audit_calibration",lambda:audit.audit_calibration(path)),
        ("lock_test",lambda:evaluation.lock(path)),("collect_test",lambda:collect.collect(path,"TEST")),
        ("audit_test",lambda:audit.audit_split(path,"TEST")),("evaluate",lambda:evaluation.evaluate(path)),("audit_numeric",lambda:audit.audit_numeric(path))]
    io.write(root/"pipeline_claim.json",{"started_ns":start,"source_git_commit":io.git("rev-parse","HEAD"),"automatic_restart":False})
    for name,action in actions:
        before=perf_counter_ns();entry={"stage":name,"started_ns":before,"status":"STARTED"};stages.append(entry);print("STAGE "+name,flush=True)
        io.write(root/"pipeline_progress.json",{"stages":stages},exclusive=False)
        try:
            with io.forbid_online_calls(network):action()
            entry["status"]="COMPLETE"
        except BaseException as error:
            failure={"stage":name,"type":type(error).__name__,"message":str(error),"traceback":traceback.format_exc()};entry["status"]="FAILED_RETAINED"
        entry["completed_ns"]=perf_counter_ns();entry["wall_ns"]=entry["completed_ns"]-before;entry["attempted_network_calls"]=network["attempted_network_calls"]
        io.write(root/"pipeline_progress.json",{"stages":stages,"failure":failure},exclusive=False)
        if failure is not None:break
    io.write(root/"pipeline_completion.json",{"status":"COMPLETE" if failure is None else "INCOMPLETE_NO_RETRY","stages":stages,"failure":failure,
        "wall_ns":perf_counter_ns()-start,"new_api_calls":0,"attempted_network_calls":sum(s["attempted_network_calls"] for s in stages)})
    report(path)
    if failure is not None:raise RuntimeError("One-shot study stopped; partial evidence retained: "+str(failure))


def main():
    p=argparse.ArgumentParser();p.add_argument("action",choices=("prepare","run"));p.add_argument("--manifest",type=Path);args=p.parse_args()
    if args.action=="prepare":
        with io.forbid_online_calls({}):io.prepare()
    else:
        if args.manifest is None:p.error("--manifest required")
        pipeline(args.manifest.resolve())


if __name__=="__main__":main()

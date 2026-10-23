"""Summarize the complete audited task population without retuning or rerunning."""
import argparse
from pathlib import Path
import sys
from time import perf_counter_ns

ROOT = Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.analysis import movement_task_io_v1 as io
from src.analysis.movement_task_statistics_v1 import statistics


def evaluate(path):
    started = perf_counter_ns();manifest,_,_ = io.load(path)
    source = path.parent/"audit/record_audit.json";audit = io.read(source)
    if audit["integrity"] != "PASSED" or audit["executions"] != manifest["config"]["executions"]:raise ValueError("complete independent record audit required")
    for key in io.IDENTITY:
        if audit[key] != manifest[key]:raise ValueError("foreign record audit")
    for name,expected in audit["collection_artifact_sha256"].items():
        if io.sha(path.parent/"collection"/name) != expected:raise ValueError("audited task collection changed")
    output = path.parent/"analysis";output.mkdir()
    try:
        result = {**{k:manifest[k] for k in io.IDENTITY},"status":"COMPLETE_FIXED_METHOD_TASK_COMPARISON",
            "record_audit_sha256":io.sha(source),"statistics":statistics(audit["rows"],manifest["config"],manifest["arx_source_receipt"]["costs"]),
            "costs":audit["costs"],"audit_computations":audit["audit_computations"],"wall_ns":perf_counter_ns()-started}
        io.write(output/"summary.json",result)
        io.write(output/"all_cases.json",audit["rows"])
        io.write(output/"failures_and_rejections.json",[r for r in audit["rows"] if not r["success"] or r["stopped"] or
            r["action"] in ("REJECT_ARX_KEEP_SAVED_C8","NO_LIVE_BOUNDARY","ENDED_NO_UPDATE")])
        io.write(output/"completion.json",{**{k:manifest[k] for k in io.IDENTITY},"status":result["status"],
            "artifact_sha256":{p.name:io.sha(p) for p in output.iterdir() if p.is_file()}})
        return result
    except BaseException as error:
        io.write(output/"failed_evaluation.json",{"error":type(error).__name__,"message":str(error),"wall_ns":perf_counter_ns()-started});raise


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("manifest",type=Path)
    result=evaluate(parser.parse_args().manifest.resolve());print(result["status"])

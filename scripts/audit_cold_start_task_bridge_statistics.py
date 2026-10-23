"""Independent task statistics, gate and source-cost reconstruction; no simulation."""
import argparse
import json
import math
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from scripts import run_cold_start_task_bridge as run


def check_statistics(summary):
    rows = summary["cases"]; saved = summary["statistics"]; numeric = 0; max_error = 0.
    def compare(a, b):
        nonlocal numeric, max_error
        a,b = np.asarray(a,float),np.asarray(b,float)
        if a.shape != b.shape or not np.isfinite(a).all() or not np.isfinite(b).all(): raise ValueError("statistics shape or finite value differs")
        error = float(np.max(np.abs(a-b))); max_error = max(max_error,error); numeric += a.size
        if error > 1e-9: raise ValueError("independent statistics differ")
    index = {(r["stream"],r["task"],r["replicate"],r["method"]):r for r in rows}
    expected = {(s,t,f,m) for s in range(56) for t in run.TASKS for f in range(2) for m in run.METHODS}
    if len(rows) != 2688 or set(index) != expected: raise ValueError("statistics population differs")
    means = {}; successes = {}
    for name in run.METHODS:
        part = [r for r in rows if r["method"] == name]; cell = saved["methods"][name]
        for r in part:
            if type(r["success"]) is not bool or type(r["stopped"]) is not bool or r["stopped"] and r["success"] or r["deadline_loss"] != (r["total_steps"] if r["success"] else 500): raise ValueError("failure or stop penalty changed")
        successes[name] = sum(r["success"] for r in part); means[name] = math.fsum(r["deadline_loss"] for r in part)/336
        compare(cell["cases"],336); compare(cell["successes"],successes[name]); compare(cell["stops"],sum(r["stopped"] for r in part))
        for field in ("deadline_loss","total_steps","fixed_probe_steps"): compare(cell["mean_"+field],math.fsum(r[field] for r in part)/336)
        source = (3840,480) if name in ("JOINT8","JOINT_DROP2_8","SAME_DATA_POINT8") else (21010,288) if name in ("OLD_POINT8","OLD_G8","OLD_POINT16_CYCLE") else (0,0)
        compare(cell["source_steps"],source[0]); compare(cell["source_controlled_resets"],source[1])
        compare(cell["mean_amortized_actual_steps"],(math.fsum(r["total_steps"] for r in part)+source[0])/336)
        for task in run.TASKS:
            task_rows = [r for r in part if r["task"] == task]; v=cell["by_task"][task]
            compare(v["cases"],112); compare(v["successes"],sum(r["success"] for r in task_rows)); compare(v["mean_deadline_loss"],math.fsum(r["deadline_loss"] for r in task_rows)/112)
    rng = np.random.default_rng(20261017)
    even = rng.choice(np.arange(0,56,2),size=(10000,28),replace=True)
    odd = rng.choice(np.arange(1,56,2),size=(10000,28),replace=True); draws = np.hstack((even,odd))
    references = ("OLD_POINT8","SAME_DATA_POINT8","JOINT_DROP2_8","OLD_G8","OLD_POINT16_CYCLE","NO_PROBE","IDENTITY_AFTER8")
    if len(saved["contrasts"]) != 7: raise ValueError("registered comparisons dropped")
    primary_upper = None
    for i, base in enumerate(references):
        c = saved["contrasts"][i]
        if c["method"] != "JOINT8" or c["reference"] != base or c["role"] != ("PRIMARY" if i == 0 else "SECONDARY_UNADJUSTED"): raise ValueError("comparison identity differs")
        for j, (field, label) in enumerate((("success","success_rate"),("deadline_loss","deadline_loss"),("total_steps","actual_steps"))):
            sums = np.array([sum(int(index[s,t,f,"JOINT8"][field])-int(index[s,t,f,base][field]) for t in run.TASKS for f in (0,1)) for s in range(56)],dtype=np.int64)
            mean = int(sums.sum())/336; interval = np.percentile(sums[draws].sum(axis=1)/336,[2.5,97.5])
            compare(c["statistics"][label]["difference"],mean); compare(c["statistics"][label]["paired_stream_percentile_95"],interval)
            compare(np.asarray(c["stream_values"])[:,j],sums/6)
            if i == 0 and field == "deadline_loss": primary_upper = float(interval[1])
        harm = sum(index[s,t,f,base]["success"] and not index[s,t,f,"JOINT8"]["success"] for s in range(56) for t in run.TASKS for f in (0,1))
        rescue = sum(not index[s,t,f,base]["success"] and index[s,t,f,"JOINT8"]["success"] for s in range(56) for t in run.TASKS for f in (0,1))
        compare(c["success_to_failure"],harm); compare(c["failure_to_success"],rescue)
    requirements = {"primary_loss_upper_below_zero":primary_upper<0,"success_not_below_old_point8":successes["JOINT8"]>=successes["OLD_POINT8"],
                    "success_not_below_strong_controls":successes["JOINT8"]>=max(successes[n] for n in ("OLD_G8","OLD_POINT16_CYCLE")),
                    "mean_loss_not_above_strong_controls":means["JOINT8"]<=min(means[n] for n in ("OLD_G8","OLD_POINT16_CYCLE"))}
    if requirements != saved["component_gate"]["requirements"] or all(requirements.values()) != saved["component_gate"]["passed"]: raise ValueError("component gate differs")
    if saved["algorithm_novelty_established"] is not False or saved["probability_qualification"] is not False or saved["new_api_calls"] != 0:
        raise ValueError("bridge scope changed")
    return {"integrity":"PASSED","numeric_fields_checked":numeric,"max_absolute_difference":max_error,"comparisons":7,"cases":2688,"component_gate_passed":all(requirements.values()),"new_environment_steps":0}


def audit(path, record_path, output):
    if output.exists(): raise FileExistsError("new statistics audit output required")
    m=run.load(path); base=path.parent; a=json.loads(record_path.read_text(encoding="utf-8")); s=json.loads((base/"summary.json").read_text(encoding="utf-8"))
    if a["integrity"] != "PASSED" or any(a[k]!=m[k] or s[k]!=m[k] for k in run.IDENTITY) or run.digest(base/"summary.json") != a["artifact_sha256"]["summary.json"]:
        raise ValueError("matching complete record audit required")
    result={**{k:m[k] for k in run.IDENTITY},**check_statistics(s),"record_audit_sha256":run.digest(record_path),"summary_sha256":run.digest(base/"summary.json"),"script_sha256":run.digest(Path(__file__))}
    output.mkdir(parents=True,exist_ok=False);run.write_json(output/"check.json",result);print(json.dumps(result))


if __name__ == "__main__":
    p=argparse.ArgumentParser();p.add_argument("--manifest",type=Path,required=True);p.add_argument("--record-audit",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    args=p.parse_args();audit(args.manifest.resolve(),args.record_audit.resolve(),args.output.resolve())

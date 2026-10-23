"""Preserve every precision-gate failure and unstable passive snapshot; no fitting."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def case_diagnostic(record,threshold):
    outcome=record["outcome"]
    first=next((b for b in outcome["blocks"] if b["nominal_mean_error_inf"]>threshold),None)
    return {"episode_index":record["episode_index"],"seed":record["seed"],"task":record["task"],"program":record["program"],
        "nominal_task_success":outcome["success"],"maximum_block_error":outcome["maximum_block_error"],
        "precision_exceeded":outcome["maximum_block_error"] is None or outcome["maximum_block_error"]>threshold,
        "first_exceeded_block":first,"total_steps":outcome["total_steps"],
        "passive_snapshots":[{"step":s["step"],"valid":s["fit"]["valid"],"scaled_condition":s["fit"]["scaled_condition"],
                              "identity_matrix_error_inf":s["nominal_identity_error_inf"]} for s in outcome["snapshots"]]}


def analyze(manifest_path,audit_path):
    manifest=json.loads(manifest_path.read_text(encoding="utf-8"));audit=json.loads(audit_path.read_text(encoding="utf-8"))
    fields=("experiment_run_id","manifest_id","source_git_commit")
    if audit["integrity"]!="PASSED" or any(audit[k]!=manifest[k] for k in fields):raise ValueError("matching audit required")
    for name,sha in audit["artifact_sha256"].items():
        if digest(manifest_path.parent/name)!=sha:raise ValueError("audited source changed")
    threshold=manifest["config"]["maximum_p90_episode_block_error"]
    cases=[]
    with gzip.open(manifest_path.parent/"episodes.jsonl.gz","rt",encoding="utf-8") as handle:
        for line in handle:cases.append(case_diagnostic(json.loads(line),threshold))
    if len(cases)!=96:raise ValueError("diagnostic population incomplete")
    snapshots=[{"episode_index":r["episode_index"],"seed":r["seed"],"task":r["task"],"program":r["program"],**s}
               for r in cases for s in r["passive_snapshots"] if s["valid"]]
    return {**{k:manifest[k] for k in fields},"audit_sha256":digest(audit_path),"analysis_tool_sha256":digest(Path(__file__)),
        "frozen_error_threshold":threshold,"precision_exceeded_cases":sum(r["precision_exceeded"] for r in cases),
        "cases":cases,"largest_numeric_only_errors":sorted(snapshots,key=lambda r:r["identity_matrix_error_inf"],reverse=True)[:10],
        "new_physical_steps":0,"new_api_calls":0,"observer_or_threshold_refits":0,
        "scope":"Same immutable nominal trajectories. Precision failure and task success are separate; no new causal task-gain estimate."}


def report(result):
    lines=["# 观察精度失败逐例清单", "",f'运行 `{result["experiment_run_id"]}`；{result["precision_exceeded_cases"]}/96 轨迹超过冻结精度要求。',"",
        "任务本身可能成功；以下不改写任务成功标签。首次超标用于只读解释，不参与阈值或模型拟合。", "",
        "| 种子 | 任务 | 程序 | 最大块误差 | 首次超标结束步 | 首次阶段 | 任务成功 |", "|---|---|---|---:|---:|---|---|"]
    for r in result["cases"]:
        if not r["precision_exceeded"]:continue
        block=r["first_exceeded_block"]
        score=f'{r["maximum_block_error"]:.6f}' if r["maximum_block_error"] is not None else "无测量"
        lines.append(f'| {r["seed"]} | {r["task"]} | {r["program"]} | {score} | {block["end_step"] if block else "无"} | {block["phase"] if block else "无"} | {r["nominal_task_success"]} |')
    return "\n".join(lines)+"\n"


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--manifest",type=Path,required=True);p.add_argument("--audit",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    a=p.parse_args();source,audit,output=a.manifest.resolve(),a.audit.resolve(),a.output.resolve()
    if output==source.parent or source.parent in output.parents:raise ValueError("diagnosis must be outside collection")
    result=analyze(source,audit);output.mkdir(parents=True,exist_ok=False)
    (output/"diagnostics.json").write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    (output/"failure_cases.md").write_text(report(result),encoding="utf-8")
    print(json.dumps({"precision_exceeded_cases":result["precision_exceeded_cases"],"largest_numeric_error":result["largest_numeric_only_errors"][0]}))

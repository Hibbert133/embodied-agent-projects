"""Read-only causal input-scope replay of the immutable finite-frame experiment."""
import argparse
from datetime import datetime,timezone
from fractions import Fraction
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.probe.action_support import CommandSupport,assess_query,command


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RankReplay:
    """Independent rational Gaussian elimination, unlike the geometry checker."""
    def __init__(self,commands=()):
        self.rows=[]
        for value in commands: self.add(value)

    def reduced(self,value):
        c=command(value)
        row=[Fraction.from_float(c[0]),Fraction.from_float(c[1]),Fraction(1)]
        for pivot,basis in self.rows:
            factor=row[pivot]
            row=[v-factor*b for v,b in zip(row,basis)]
        return row

    def contains(self,value):
        return not any(self.reduced(value))

    def add(self,value):
        row=self.reduced(value)
        if not any(row): return
        pivot=next(i for i,v in enumerate(row) if v)
        scale=row[pivot]; row=[v/scale for v in row]
        self.rows=[(p,[v-b[pivot]*r for v,r in zip(b,row)]) for p,b in self.rows]
        self.rows.append((pivot,row)); self.rows.sort(key=lambda value:value[0])


def episode(record):
    declaration=record["declaration"]
    raw=declaration["evidence"]
    probe=tuple(tuple(t["command"]) for t in raw["transitions"]) if raw else ()
    n_probe=len(probe)
    if n_probe != record["outcome"]["probe_steps"] or n_probe > len(record["steps"]):
        raise ValueError("source probe association mismatch")
    history=list(probe); frozen=CommandSupport(probe); independent=RankReplay(probe)
    if frozen.rank!=len(independent.rows): raise ValueError("independent input-rank disagreement")
    gaps=0; causal_gaps=0; near_misses=0; first=None; first_causal=None; max_distance=0.
    for step,row in enumerate(record["steps"][n_probe:],1):
        if row["host_calls"]!=n_probe+step: raise ValueError("source task-step order mismatch")
        q=row["command"]
        result=assess_query(frozen,q)
        frozen_ref=RankReplay(probe).contains(q)
        if result["structurally_supported"] != frozen_ref:
            raise ValueError("independent exact command-support disagreement")
        outside=not result["structurally_supported"]
        gaps+=outside; near_misses+=outside and result["numerically_near_span"]
        max_distance=max(max_distance,result["outside_span_norm"])
        if outside and first is None:
            first={"task_step":step,"command":q,"nullspace_witness":result["nullspace_witness"]}
        # Inspect BEFORE adding the command currently being executed. Earlier
        # task commands are available; later trajectory data never enter this check.
        supported_before=independent.contains(q)
        if len(independent.rows)<3:
            causal=assess_query(CommandSupport(tuple(history)),q)
            if causal["structurally_supported"] != supported_before:
                raise ValueError("causal prefix rank disagreement")
        causal_gaps+=not supported_before
        if not supported_before and first_causal is None:
            first_causal={"task_step":step,"previous_command_count":len(history),"command":q}
        history.append(tuple(q)); independent.add(q)
    return {"episode_index":record["episode_index"],"seed":record["seed"],"context_oracle":record["context_oracle"],
        "method":record["method"],"original_success":record["outcome"]["success"],"task_steps":len(record["steps"])-n_probe,
        "probe_input_rank":frozen.rank,"probe_numerical_rank":frozen.numerical_rank,
        "frozen_probe_scope_gaps":gaps,"causal_prefix_scope_gaps":causal_gaps,
        "numerical_tolerance_near_misses":near_misses,"first_probe_scope_gap":first,
        "first_causal_scope_gap":first_causal,"maximum_frozen_projection_residual":max_distance,
        "final_causal_input_rank":len(independent.rows),"model_validity_qualified":False,"task_success_guarantee":False}


def summarize(rows,methods):
    if len(rows)!=176 or [r["episode_index"] for r in rows]!=list(range(1,177)):
        raise ValueError("complete diagnostic population mismatch")
    result={}
    for method in methods:
        selected=[row for row in rows if row["method"]==method]
        if len(selected)!=16: raise ValueError("method diagnostic population mismatch")
        steps=sum(row["task_steps"] for row in selected)
        gaps=sum(row["frozen_probe_scope_gaps"] for row in selected)
        result[method]={"episodes":16,"original_successes":sum(row["original_success"] for row in selected),
            "probe_ranks":sorted(set(row["probe_input_rank"] for row in selected)),"task_steps":steps,
            "frozen_probe_scope_gaps":gaps,"frozen_probe_scope_gap_fraction":gaps/steps if steps else None,
            "episodes_with_frozen_gap":sum(row["frozen_probe_scope_gaps"]>0 for row in selected),
            "causal_prefix_scope_gaps":sum(row["causal_prefix_scope_gaps"] for row in selected),
            "episodes_with_causal_gap":sum(row["causal_prefix_scope_gaps"]>0 for row in selected),
            "numerical_tolerance_near_misses":sum(row["numerical_tolerance_near_misses"] for row in selected),
            "all_final_prefixes_full_rank":all(row["final_causal_input_rank"]==3 for row in selected)}
    return result


def analyze(manifest_path,audit_path):
    manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    audit=json.loads(audit_path.read_text(encoding="utf-8"))
    for key in ("experiment_run_id","manifest_id","source_git_commit"):
        if manifest[key]!=audit[key]: raise ValueError("source audit provenance mismatch")
    if audit["integrity"]!="PASSED" or audit["episodes"]!=176:
        raise ValueError("requires the completed independent frame audit")
    for name,sha in audit["artifact_sha256"].items():
        if digest(manifest_path.parent/name)!=sha: raise ValueError("immutable source data changed")
    rows=[]
    with gzip.open(manifest_path.parent/"episodes.jsonl.gz","rt",encoding="utf-8") as handle:
        for line in handle: rows.append(episode(json.loads(line)))
    if sum(row["task_steps"] for row in rows)!=audit["verified_task_steps"]:
        raise ValueError("source task-step accounting mismatch")
    methods=summarize(rows,manifest["config"]["methods"])
    return {"source_experiment_run_id":manifest["experiment_run_id"],"source_manifest_id":manifest["manifest_id"],
        "source_git_commit":manifest["source_git_commit"],"source_audit_sha256":digest(audit_path),
        "analysis_tool_sha256":digest(Path(__file__)),"support_module_sha256":digest(ROOT/"src/probe/action_support.py"),
        "transfer_module_sha256":digest(ROOT/"src/probe/response_transfer.py"),
        "diagnosed_episodes":len(rows),"diagnosed_task_steps":sum(row["task_steps"] for row in rows),
        "independent_exact_rank_replay":"PASSED","methods":methods,"cases":rows,
        "api_calls_added":0,"physical_steps_added":0,"models_fitted":0,"source_results_changed":False,
        "scope":"Input informativity for an unrestricted static pre-clip planar affine actuator. Necessary input geometry only; finite rotation priors can identify additional directions. No model-validity, noise, safety, or task-success guarantee."}


def report(result):
    lines=["# 输入支持与模型作用域：只读诊断", "",f'源运行 `{result["source_experiment_run_id"]}`。',"",
        "此处的一般仿射作用域比原实验的已知两旋转作用域更宽。支持缺口是模型依赖诊断，不是原协议违规或新增任务失败。", "",
        "| 方法 | 原成功/16 | 探测输入秩 | 任务步 | 固定探测未覆盖步 | 比例 | 当前步前累积历史未覆盖步 |",
        "|---|---:|---|---:|---:|---:|---:|"]
    for name,row in result["methods"].items():
        fraction=f'{100*row["frozen_probe_scope_gap_fraction"]:.2f}%' if row["task_steps"] else "n/a"
        lines.append(f'| {name} | {row["original_successes"]} | {row["probe_ranks"]} | {row["task_steps"]} | {row["frozen_probe_scope_gaps"]} | {fraction} | {row["causal_prefix_scope_gaps"]} |')
    lines += ["",f'{result["diagnosed_episodes"]} 个案例、{result["diagnosed_task_steps"]} 个任务查询经独立精确秩方法复核。',"",
        "累积检查在加入当前命令之前进行；任务反馈很快补齐输入支持，不能把固定探测缺口当成整段任务始终没有信息。", "",
        "完整输入支持不证明模型正确、测量误差足够小或任务成功。低层机器人观察是否构成合格的执行器等价响应仍未验证。", "",
        "原框架/基线结果、模型和种子没有改变。零新仿真、零新 API、零拟合；本诊断不是新算法的表现对比。", ""]
    return "\n".join(lines)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest",type=Path,required=True);p.add_argument("--audit",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    args=p.parse_args();source,audit,output=args.manifest.resolve(),args.audit.resolve(),args.output.resolve()
    if output==source.parent or source.parent in output.parents: raise ValueError("diagnosis must be outside original collection")
    if subprocess.check_output(["git","status","--porcelain"],cwd=ROOT,text=True).strip():
        raise ValueError("commit the diagnostic implementation before running")
    commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    result=analyze(source,audit)
    result.update(analysis_source_git_commit=commit,analysis_utc=datetime.now(timezone.utc).isoformat())
    output.mkdir(parents=True,exist_ok=False)
    (output/"diagnostics.json").write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    (output/"report.md").write_text(report(result),encoding="utf-8");print(report(result))

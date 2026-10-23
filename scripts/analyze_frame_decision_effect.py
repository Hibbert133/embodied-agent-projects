"""Read-only exact controller equivalence and matched-choice effects."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def execution_hash(steps):
    # Remove only the decision hash: fixed and inferred choices have different
    # explanations. Every actual command, observation, counter and RNG stays.
    value = [{k:v for k,v in step.items() if k != "choice_hash"} for step in steps]
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()


def matched_effect(group):
    selected = group["MODEL_REVERSE8"]
    controller = selected["declaration"]["choice"]["controller"]["id"]
    method = {"FRAME_A":"FIXED_A_REVERSE8", "FRAME_B":"FIXED_B_REVERSE8"}.get(controller)
    if method is None:
        raise ValueError("selected controller is not registered")
    equivalent = group[method]
    a,b = execution_hash(selected["steps"]),execution_hash(equivalent["steps"])
    if a != b or selected["outcome"]["success"] != equivalent["outcome"]["success"]:
        raise ValueError("selected controller execution differs from matched fixed controller")
    effects = {}
    for fixed in ("FIXED_A_REVERSE8","FIXED_B_REVERSE8"):
        comparator = group[fixed]
        changed = controller != comparator["declaration"]["choice"]["controller"]["id"]
        difference = int(selected["outcome"]["success"])-int(comparator["outcome"]["success"])
        effects[fixed] = {"changed":changed,"difference":difference}
    return {"seed":selected["seed"],"context_oracle":selected["context_oracle"],
        "controller_id":controller,"matched_fixed_method":method,"complete_execution_sha256":a,
        "exact_execution_match":True,"task_steps":selected["outcome"]["task_steps"],"effects":effects}


def analyze(manifest_path,audit_path):
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    fields=("experiment_run_id","manifest_id","source_git_commit")
    if audit["integrity"] != "PASSED" or any(manifest[k] != audit[k] for k in fields):
        raise ValueError("requires a matching independent audit")
    for name,sha in audit["artifact_sha256"].items():
        if digest(manifest_path.parent/name) != sha:
            raise ValueError("audited raw data changed")
    rows=[]; group={}; current=None
    wanted={"MODEL_REVERSE8","FIXED_A_REVERSE8","FIXED_B_REVERSE8"}
    with gzip.open(manifest_path.parent/"episodes.jsonl.gz","rt",encoding="utf-8") as handle:
        for line in handle:
            record=json.loads(line); key=(record["seed"],record["context_oracle"])
            if current is not None and key != current:
                rows.append(matched_effect(group)); group={}
            current=key
            if record["method"] in wanted:
                if record["method"] in group: raise ValueError("duplicate matched method")
                group[record["method"]]=record
    if group: rows.append(matched_effect(group))
    if len(rows) != 16: raise ValueError("matched population incomplete")
    effects={}
    for fixed in ("FIXED_A_REVERSE8","FIXED_B_REVERSE8"):
        changed=[row["effects"][fixed] for row in rows if row["effects"][fixed]["changed"]]
        effects[fixed]={"changed":len(changed),"helpful":sum(e["difference"]>0 for e in changed),
                       "harmful":sum(e["difference"]<0 for e in changed),"tied":sum(e["difference"]==0 for e in changed)}
    return {**{k:manifest[k] for k in fields},"audit_sha256":digest(audit_path),
        "analysis_tool_sha256":digest(Path(__file__)),"exact_matched_executions":len(rows),"rows":rows,
        "matched_choice_effects":effects,"api_calls":0,"physical_steps_added":0,
        "scope":"Same reverse probe, same numerical controller and actuator stream. One realization per task/context; these contrasts are not stable action labels."}


def failures_markdown(audit):
    failures=audit["statistics"]["failures"]
    lines=["# 本轮全部失败案例", "", f'运行 `{audit["experiment_run_id"]}`；共 {len(failures)} 个失败方法执行。', "",
        "以下为一次噪声实现下的记录，不是稳定行动标签。标准反向/完整 ARX 本轮无失败。", "",
        "| 种子 | 评估上下文 | 方法 | 已保存控制器 | 探测步 | 任务步 | 停止 |",
        "|---|---|---|---|---:|---:|---|"]
    for row in failures:
        lines.append(f'| {row["seed"]} | {row["context_oracle"]} | {row["method"]} | {row["controller_id"]} | {row["probe_steps"]} | {row["task_steps"]} | {row["stopped"]} |')
    return "\n".join(lines)+"\n"


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest",type=Path,required=True); parser.add_argument("--audit",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True); args=parser.parse_args()
    manifest,audit,output=args.manifest.resolve(),args.audit.resolve(),args.output.resolve()
    if output == manifest.parent or manifest.parent in output.parents:
        raise ValueError("analysis must be outside immutable collection")
    result=analyze(manifest,audit); output.mkdir(parents=True,exist_ok=False)
    (output/"decision_effect.json").write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    (output/"failure_cases.md").write_text(failures_markdown(json.loads(audit.read_text(encoding="utf-8"))),encoding="utf-8")
    print(json.dumps({"exact_matched_executions":result["exact_matched_executions"],"effects":result["matched_choice_effects"]}))

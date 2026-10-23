"""Exploratory no-new-call diagnostics; never alter the registered gates."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np


def diagnostics(manifest_path, audit_path):
    m = json.loads(manifest_path.read_text(encoding="utf-8"))
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    identity = {k: m[k] for k in ("experiment_run_id", "manifest_id", "source_git_commit")}
    if any(audit.get(k) != v for k, v in identity.items()) or audit["integrity"] != "PASSED":
        raise ValueError("diagnostics require the matching completed primary audit")
    source = manifest_path.parent
    for name, expected in audit["artifact_sha256"].items():
        if hashlib.sha256((source/name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"raw artifact changed after primary audit: {name}")
    api = json.loads((source/"api_audit.json").read_text(encoding="utf-8"))
    requested = m["config"]["api"]["max_tokens"]
    exceeded = [r["attempt"] for r in api["attempts"] if r["usage"].get("output_tokens", 0) > requested]
    unknown = [r["attempt"] for r in api["attempts"] if "output_tokens" not in r["usage"]]
    per_attempt = [{"attempt": r["attempt"], "stage": r["stage"], "status": r["status"],
                    "reported_output_tokens": r["usage"].get("output_tokens"),
                    "visible_response_utf8_bytes": len(r["raw_response"].encode())} for r in api["attempts"]]
    choices = {}
    differences = {"different_effective_correction": 0, "helpful": 0, "harmful": 0, "tied": 0,
                   "same_effective_correction": 0, "no_matched_llm_execution": 0}
    episode_file = source/"episodes.jsonl.gz"
    if episode_file.exists():
        with gzip.open(episode_file, "rt", encoding="utf-8") as handle:
            records = [json.loads(line) for line in handle]
        indexed = {(r["seed"], r["condition_oracle"], r["method"]): r for r in records}
        for r in records:
            if r["method"] != "LLM_AGENT":
                continue
            operation = r["execution"]["selected_action"]
            choices[operation] = choices.get(operation, 0)+1
            baseline = indexed[r["seed"], r["condition_oracle"], "PRIOR_AFFINE"]
            if r["execution"]["aborted"] or r["probe"] != baseline["probe"]:
                differences["no_matched_llm_execution"] += 1
                continue
            a = np.asarray(r["execution"]["plan"]["correction"], dtype=np.float32)
            b = np.asarray(baseline["execution"]["plan"]["correction"], dtype=np.float32)
            if np.array_equal(a, b):
                differences["same_effective_correction"] += 1
            else:
                differences["different_effective_correction"] += 1
                delta = int(r["outcome"]["success"])-int(baseline["outcome"]["success"])
                differences["helpful" if delta > 0 else "harmful" if delta < 0 else "tied"] += 1
    return {**identity, "primary_audit_sha256": hashlib.sha256(audit_path.read_bytes()).hexdigest(),
            "analysis_tool_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "scope": "Exploratory reporting only; no new API calls, simulation, fitting or changes to registered gates.",
            "requested_max_tokens": requested, "attempts_above_requested_reported_output": exceeded,
            "attempts_without_output_usage": unknown,
            "all_reported_output_within_limit": False if exceeded else None if unknown else True,
            "per_attempt": per_attempt, "llm_final_choices": choices, "comparison_with_affine": differences,
            "token_limit_interpretation": "The SDK request sets max_tokens=512. Reported aggregate output usage is a different observable from returned text bytes. The saved worker does not retain a reasoning-token breakdown, so the cause of excess reported usage cannot be established from this run."}


def report(r):
    over = r["attempts_above_requested_reported_output"]
    return "\n".join([
        "# 在线 API 补充诊断（不改变预注册门槛）", "",
        f"运行标识：{r['experiment_run_id']}", f"清单标识：{r['manifest_id']}",
        f"冻结源代码：{r['source_git_commit']}", "",
        f"SDK 请求 max_tokens={r['requested_max_tokens']}；服务端报告输出用量超过该值的尝试：{over}。",
        f"输出用量未知的尝试：{r['attempts_without_output_usage']}；未知值不按零用量或限制通过处理。",
        "若该列表非空，本轮没有证明服务端总输出用量受到 512 的硬限制。可见返回字节与服务端 tokens 不是同一指标。",
        "保存的工作进程未记录内部推理用量拆分，因此不能把差异确定归因于隐藏推理，也不能声称总费用被该参数约束。",
        f"LLM 最终选择：{r['llm_final_choices']}。",
        f"与同轨迹仿射基线的有效 float32 纠正比较：{r['comparison_with_affine']}。",
        "方法名称不同与控制向量不同分别统计；有利/有害/相同只描述本轮配对结果，不构成稳定行动标签。",
        "这些是事后报告诊断，不替代冻结的接口门槛，不追加 API、仿真或拟合。", ""])


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--audit", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    result = diagnostics(a.manifest.resolve(), a.audit.resolve())
    a.output.mkdir(parents=True, exist_ok=False)
    (a.output/"diagnostics.json").write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    (a.output/"report.md").write_text(report(result), encoding="utf-8")
    print(report(result))

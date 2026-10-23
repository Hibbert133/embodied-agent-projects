"""Posthoc entry-condition decomposition; no simulation, fitting or new gate."""
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "outputs/integral_reprobe/qualification_v1/integral_reprobe_20261019T132410Z_8014d27d424a"
OUT = ROOT / "outputs/reproduction_reviews/integral_reprobe_qualification_v1/entry_diagnostics_v1"


def read(path):return json.loads(path.read_text(encoding="utf-8"))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    audit = read(RUN / "audit/record_audit.json")
    receipt = read(RUN / "audit/report_receipt.json")
    assert audit["integrity"] == "PASSED" and audit["executions"] == 36
    assert sha(RUN / "audit/record_audit.json") == receipt["record_audit_sha256"]
    raw = RUN / "collection/cases.jsonl.gz"
    assert sha(raw) == audit["collection_artifact_sha256"]["cases.jsonl.gz"]
    with gzip.open(raw, "rt", encoding="utf-8") as handle:rows = [json.loads(line) for line in handle]
    assert len(rows) == 36
    diagnostics = []
    for r in rows:
        start = r["approach"]["public"]["completed_steps"]
        h = [r["approach"]["public"]["final_observation"]["observation"]]
        h += [p["after"]["observation"] for p in r["physical_rows"][start:start+r["reposition_steps"]]]
        gates = []
        for j,obs in enumerate(h):
            position = max(abs(a-b) for a,b in zip(obs[:3], (0., .6, .25)))
            clearance = math.dist(obs[:3], obs[4:7])
            motion = None if j < 3 else max(max(abs(a-b) for a,b in zip(left[:3],right[:3]))
                for left,right in zip(h[j-3:j],h[j-2:j+1]))
            conditions = {"position":position <= .015, "three_actual_displacements":motion is not None,
                          "motion":motion is not None and motion <= .003, "clearance":clearance >= .10}
            gates.append({"step":start+j, "position_error_m":position, "motion_max_m":motion,
                          "clearance_m":clearance, "conditions":conditions, "ready":all(conditions.values())})
        first = next((g["step"] for g in gates if g["ready"]), None)
        if r["complete_window"]:
            entries = [e["payload"] for e in r["reacquisition"]["public"]["events"] if e["kind"] == "PROBE_ENTRY"]
            assert len(entries) == 1 and entries[0]["at_calls"] == first == start+r["reposition_steps"]
        if r["collection_stop_reason"] == "ANCHOR_NOT_REACHED":assert first is None
        diagnostics.append({"unit":r["unit"], "task":r["task"], "seed":r["seed"], "variant":r["variant"],
            "reason":r["collection_stop_reason"], "success":r["success"], "reposition_steps":r["reposition_steps"],
            "first_complete_entry_gate_step":first, "minimum_position_error_m":min(g["position_error_m"] for g in gates),
            "position_eligible_steps":sum(g["conditions"]["position"] for g in gates), "final_relocation_gate":gates[-1]})
    failed = [r for r in diagnostics if r["reason"] == "ANCHOR_NOT_REACHED"]
    counts = Counter(r["reason"] for r in diagnostics)
    failed_conditions = {key:sum(not r["final_relocation_gate"]["conditions"][key] for r in failed)
                         for key in ("position", "motion", "clearance")}
    assert sum(counts.values()) == 36
    OUT.mkdir(parents=True, exist_ok=False)
    payload = {"scope":"POSTHOC_DESCRIPTION_WITH_FROZEN_GATES_UNCHANGED", "cases":diagnostics,
        "stop_counts":dict(counts), "final_failed_conditions_overlapping":failed_conditions,
        "new_environment_steps":0, "new_api_calls":0, "new_parameter_fits":0}
    data = OUT / "diagnostics.json"
    with data.open("x",encoding="utf-8",newline="\n") as handle:
        json.dump(payload,handle,ensure_ascii=False,indent=2,allow_nan=False);handle.write("\n")
    labels = {"UNCHANGED_PD":"不变/PD", "UNCHANGED_PID":"不变/PID", "CHANGED_PD":"变化/PD", "CHANGED_PID":"变化/PID"}
    lines = ["# 重新探测失败的进入条件：事后只读分解", "",
        "本分解只读取已审计的全部36次执行，冻结的位置、稳定性、间距门槛及资格判定保持不变。它不是新的科学人口或重新执行。", "",
        f"13次取得完整窗口；8次在移动期间任务已成功，因此停止且不计探测成功；15次用完64步仍未到位。原始停止计数：{dict(counts)}。", "",
        f"15次未到位在最后一帧全部未满足最大坐标误差≤15毫米；其中{failed_conditions['motion']}次同时未满足最近3次最大坐标位移≤3毫米。没有案例在最后一帧因手与物体间距小于100毫米而被拒绝。条件重叠，不能将计数相加。", "",
        "|种子|条件/方法|最后位置误差/毫米|最近3次最大位移/毫米|最后物体间距/毫米|历史最低位置误差/毫米|",
        "|---:|---|---:|---:|---:|---:|"]
    for r in failed:
        g = r["final_relocation_gate"]
        lines.append(f"|{r['seed']}|{labels[r['variant']]}|{1000*g['position_error_m']:.3f}|{1000*g['motion_max_m']:.3f}|{1000*g['clearance_m']:.3f}|{1000*r['minimum_position_error_m']:.3f}|")
    lines += ["", "这些只是已保存轨迹的约束分解，不证明唯一动力学原因。一次位置误差进入门槛不代表三个条件同时满足，审计已逐步核对每个实际探测入口。临界接近15毫米的案例仍是失败，不能据本数据放宽门槛、延长轨迹或宣称再多走几步就一定成功。", "",
        "下一步应区分持续位置残差与尚未稳定的移动过程，评估在既定总成本内获取测量的方案。当前结果还不支持在这套操作上直接开展大批warm模型训练或宣称额外探测有任务价值。", ""]
    report = OUT / "report_zh.md"
    with report.open("x",encoding="utf-8",newline="\n") as handle:handle.write("\n".join(lines))
    with (OUT / "receipt.json").open("x",encoding="utf-8",newline="\n") as handle:
        json.dump({"source_sha256":sha(Path(__file__)),
            "input_sha256":{p.relative_to(ROOT).as_posix():sha(p) for p in (raw,RUN/"audit/record_audit.json",RUN/"audit/report_receipt.json")},
            "output_sha256":{p.relative_to(ROOT).as_posix():sha(p) for p in (data,report)},
            "new_environment_steps":0,"new_api_calls":0},handle,indent=2);handle.write("\n")
    print(json.dumps({"stop_counts":dict(counts),"final_failed_conditions":failed_conditions}))


if __name__ == "__main__":main()

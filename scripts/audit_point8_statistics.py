"""Independent complete-population aggregation/bootstrap; no robot replay."""
import argparse
import gzip
import json
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import run_point8_baseline as run


def audit(manifest_path, record_audit, output):
    if output.exists():
        raise FileExistsError("statistics audit already exists")
    manifest = run.load(manifest_path); base = manifest_path.parent
    passed = json.loads(record_audit.read_text(encoding="utf-8"))
    if passed["integrity"] != "PASSED" or passed["manifest_id"] != manifest["manifest_id"]:
        raise ValueError("qualified record audit required")
    for name, expected in passed["artifact_sha256"].items():
        if run.digest(base / name) != expected:
            raise ValueError("raw audited bytes changed")
    rows = []
    for stream in range(16):
        with gzip.open(base / f"episodes_{stream:02}.jsonl.gz", "rt", encoding="utf-8") as source:
            for line in source:
                record = json.loads(line)
                rows.append({**{k: record[k] for k in (*run.IDENTITY, "stream", "task", "replicate", "seed", "method", "operator_id_oracle")}, **record["outcome"]})
    summary = json.loads((base / "summary.json").read_text(encoding="utf-8"))
    if len(rows) != 672 or summary["cases"] != rows:
        raise ValueError("outcome population differs")
    expected_keys = {(s, t, f, m) for s in range(16) for t in run.TASKS for f in range(2) for m in run.METHODS}
    indexed = {(r["stream"], r["task"], r["replicate"], r["method"]): r for r in rows}
    if set(indexed) != expected_keys:
        raise ValueError("missing outcomes")
    checked = 0
    def number(actual, expected):
        nonlocal checked
        if abs(float(actual)-float(expected)) > 1e-10:
            raise ValueError("independent statistic differs")
        checked += 1
    for method in run.METHODS:
        part = [r for r in rows if r["method"] == method]
        saved = summary["statistics"]["methods"][method]
        number(len(part), saved["cases"]); number(sum(r["success"] for r in part), saved["successes"])
        number(sum(r["stopped"] for r in part), saved["stops"])
        for field in ("total_steps", "deadline_loss", "fixed_probe_steps", "policy_measure_steps"):
            number(sum(r[field] for r in part)/len(part), saved["mean_"+field])
        fee = method not in ("NO_PROBE", "IDENTITY_AFTER8")
        number(21010 if fee else 0, saved["nominal_offline_steps"]); number(288 if fee else 0, saved["nominal_offline_resets"])
        for task in run.TASKS:
            sub = [r for r in part if r["task"] == task]
            number(len(sub), saved["by_task"][task]["cases"])
            number(sum(r["success"] for r in sub), saved["by_task"][task]["successes"])
            number(sum(r["deadline_loss"] for r in sub)/len(sub), saved["by_task"][task]["mean_deadline_loss"])
    random = np.random.default_rng(20261015)
    even = random.choice([0, 2, 4, 6, 8, 10, 12, 14], (10000, 8), replace=True)
    odd = random.choice([1, 3, 5, 7, 9, 11, 13, 15], (10000, 8), replace=True)
    pairs = (("DIRECT_POINT8", "POINT16_CYCLE"), ("DIRECT_POINT8", "DIRECT_G8"),
             ("KEEP_POINT8_AFTER16", "POINT16_CYCLE"), ("UPDATE_G16", "POINT16_CYCLE"),
             ("DIRECT_POINT8", "KEEP_POINT8_AFTER16"))
    for i, (method, reference) in enumerate(pairs):
        saved = summary["statistics"]["registered_contrasts"][i]
        if saved["method"] != method or saved["reference"] != reference or saved["role"] != ("PRIMARY" if i == 0 else "SECONDARY_UNADJUSTED"):
            raise ValueError("registered comparison changed")
        matrix = []
        for stream in range(16):
            values = []
            for field in ("success", "deadline_loss", "total_steps"):
                total = 0.
                for task in run.TASKS:
                    for future in range(2):
                        total += float(indexed[(stream, task, future, method)][field])-float(indexed[(stream, task, future, reference)][field])
                values.append(total/6)
            matrix.append(values)
        matrix = np.asarray(matrix)
        for a, b in zip(matrix.ravel(), np.asarray(saved["stream_values"]).ravel()): number(a, b)
        samples = (matrix[even].sum(axis=1)+matrix[odd].sum(axis=1))/16
        for j, field in enumerate(("success_rate", "deadline_loss", "actual_steps")):
            number(matrix[:, j].sum()/16, saved["statistics"][field]["difference"])
            limits = np.percentile(samples[:, j], [2.5, 97.5])
            for a, b in zip(limits, saved["statistics"][field]["paired_stream_percentile_95"]): number(a, b)
        harmful = helpful = 0
        for stream in range(16):
            for task in run.TASKS:
                for future in range(2):
                    new = indexed[(stream, task, future, method)]["success"]
                    old = indexed[(stream, task, future, reference)]["success"]
                    harmful += old and not new; helpful += new and not old
        number(harmful, saved["success_to_failure"]); number(helpful, saved["failure_to_success"])
    result = {**{k: manifest[k] for k in run.IDENTITY}, "integrity": "PASSED", "episodes_checked": len(rows),
              "numeric_fields_checked": checked, "registered_contrasts_checked": 5,
              "record_audit_sha256": run.digest(record_audit), "summary_sha256": run.digest(base / "summary.json"),
              "scope": "Independent raw-outcome aggregation and paired bootstrap; NumPy RNG and percentile reused. No new simulation or model fit."}
    output.parent.mkdir(parents=True, exist_ok=True); run.write_json(output, result)
    print(json.dumps(result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); audit(args.manifest.resolve(), args.audit.resolve(), args.output.resolve())

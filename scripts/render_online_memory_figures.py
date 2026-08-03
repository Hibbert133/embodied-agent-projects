"""Render ProbeMem-Online development figures from real run artifacts."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
import sys

import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.analyze_online_memory import analyze  # noqa: E402


DISPLAY = {
    "ALWAYS_COMPENSATION": "Always compensation",
    "ALWAYS_RETRY": "Always retry",
    "FROZEN_VARIANCE_RULE": "Frozen variance rule",
    "STATELESS_GLM": "Stateless GLM",
    "GLM_FROZEN_BOOTSTRAP_MEMORY": "GLM + frozen memory",
    "GLM_ONLINE_ACTION_MEMORY": "GLM + online memory",
    "GLM_ONLINE_MEMORY_RESONANCE": "Full resonance Agent",
    "EVALUATOR_ONLY_ORACLE": "Oracle audit",
}


def render(run_dir: Path) -> list[Path]:
    figures = run_dir / "figures"
    figures.mkdir(exist_ok=True)
    decisions = _csv(run_dir / "decisions.csv")
    audit = _json(run_dir / "api_audit.json", [])
    summary = analyze(run_dir)
    paths = [
        _rolling(decisions, figures / "rolling_recovery.png"),
        _memory_changes(summary, figures / "memory_decision_changes.png"),
        _latency(audit, figures / "api_latency_by_method.png"),
    ]
    return paths


def _rolling(rows: list[dict[str, str]], path: Path) -> Path:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if row["method"] in DISPLAY:
            grouped[row["method"]].append(row)
    fig, axis = plt.subplots(figsize=(9, 5))
    for method, items in grouped.items():
        items.sort(key=lambda row: int(row["episode_id"]))
        accepted = np.asarray([row["verification_status"] == "ACCEPTED" for row in items], dtype=float)
        window = min(10, len(accepted))
        if not window:
            continue
        rolling = np.convolve(accepted, np.ones(window) / window, mode="valid")
        axis.plot(range(window, len(accepted) + 1), 100 * rolling, label=DISPLAY[method])
    axis.set(xlabel="Operational episode index", ylabel="Rolling accepted recovery (%)", ylim=(0, 105))
    axis.grid(alpha=0.25)
    axis.legend(fontsize=7, ncol=2)
    fig.tight_layout(); fig.savefig(path, dpi=180); plt.close(fig)
    return path


def _memory_changes(summary: dict, path: Path) -> Path:
    changes = summary["full_vs_stateless_changes"]
    names = ["Helpful", "Harmful", "Status tie"]
    values = [changes["helpful"], changes["harmful"], changes["tie"]]
    fig, axis = plt.subplots(figsize=(6, 4))
    axis.bar(names, values, color=["#2a9d8f", "#e76f51", "#8d99ae"])
    axis.set(ylabel="Changed-action cases", title=f"Full vs stateless decisions (n={summary['operational_cases']})")
    axis.grid(axis="y", alpha=0.25)
    fig.tight_layout(); fig.savefig(path, dpi=180); plt.close(fig)
    return path


def _latency(rows: list[dict], path: Path) -> Path:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        grouped[str(row["method"])].append(float(row["latency_ms"]) / 1000.0)
    methods = list(grouped)
    medians = [float(np.median(grouped[name])) for name in methods]
    p90 = [float(np.quantile(grouped[name], 0.9, method="higher")) for name in methods]
    fig, axis = plt.subplots(figsize=(8, 4.5))
    x = np.arange(len(methods))
    axis.bar(x, medians, label="Median", color="#457b9d")
    axis.scatter(x, p90, label="p90", color="#e63946", zorder=3)
    axis.set_xticks(x, [DISPLAY.get(name, name) for name in methods], rotation=20, ha="right")
    axis.set(ylabel="API latency (seconds)")
    axis.grid(axis="y", alpha=0.25); axis.legend()
    fig.tight_layout(); fig.savefig(path, dpi=180); plt.close(fig)
    return path


def _csv(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _json(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() and path.stat().st_size else default


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    for path in render(args.run_dir.resolve()):
        print(f"figure: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

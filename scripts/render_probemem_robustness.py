"""Render fixed-decision sensitivity; these are not independent online runs."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.audit.read_text(encoding="utf-8"))
    rows = {r["method"]: r for r in data["frozen_decision_sensitivity"]}
    evidence = rows["EVIDENCE_ACQUISITION_ENABLED"]["accepted_by_realization"]
    memory = rows["PROBE_MEMORY"]["accepted_by_realization"]
    baseline = rows["BASELINE"]["accepted_by_realization"]
    with plt.rc_context({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False}):
        fig, axes = plt.subplots(1, 2, figsize=(11, 4.8))
        x = range(4)
        for values, label, color in ((baseline, "Baseline", "#64748b"),
                                     (evidence, "Evidence acquisition", "#2563eb"),
                                     (memory, "Evidence + memory", "#d97706")):
            axes[0].plot(x, values, "o-", label=label, color=color, linewidth=2)
        axes[0].set(title="Recovery with original decisions fixed", ylabel="Accepted recoveries / 60 states",
                    xticks=list(x), xticklabels=["r0\n(primary)", "r1", "r2", "r3"], ylim=(49, 59))
        axes[0].legend(frameon=False, fontsize=10, loc="upper right")
        differences = [m - e for m, e in zip(memory, evidence)]
        axes[1].bar(x, differences, color=["#b45309" if d < 0 else "#0f766e" for d in differences], width=.55)
        axes[1].axhline(0, color="#475569", linewidth=1)
        for i, value in enumerate(differences):
            axes[1].text(i, value + (.2 if value > 0 else -.2), f"{value:+}", ha="center",
                         va="bottom" if value > 0 else "top")
        axes[1].set(title="Memory contrast changes sign", ylabel="Additional recoveries vs evidence acquisition",
                    xticks=list(x), xticklabels=["r0\n(primary)", "r1", "r2", "r3"], ylim=(-4.5, 4.5))
        fig.suptitle("ProbeMem: stochastic sensitivity of memory transfer", fontsize=15)
        fig.text(.5, .025, "Post-hoc evaluator audit: 60 states, fixed original memory history; not four independent online runs.",
                 ha="center", fontsize=10, color="#475569")
        fig.tight_layout(rect=(0, .07, 1, .94))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(args.output, dpi=180, metadata={k: data[k] for k in
                    ("experiment_run_id", "manifest_id", "source_git_commit")})
        plt.close(fig)


if __name__ == "__main__":
    main()

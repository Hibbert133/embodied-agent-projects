"""Plot frozen crossed-context results (optional Matplotlib environment)."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    audit = json.loads(args.audit.read_text())
    table = {(r["method"], r["coupling"]): r for r in audit["table"]}
    with plt.rc_context({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False}):
        fig, axes = plt.subplots(1, 2, figsize=(11, 4.8), gridspec_kw={"width_ratios": [1, 1.1]})
        for index, (method, label, color) in enumerate((
            ("PROBE_COMPENSATION", "Probe compensation", "#2563eb"),
            ("UNCORRECTED", "Uncorrected control", "#64748b"))):
            values = [table[method, c]["success_rate"] for c in ("aligned", "independent")]
            xs = [x + (index - .5) * .34 for x in range(2)]
            axes[0].bar(xs, values, width=.32, color=color, label=label)
            for x, value in zip(xs, values):
                axes[0].text(x, value + .025, f"{value:.1%}", ha="center", fontsize=10)
        axes[0].set(xticks=[0, 1], xticklabels=["Aligned context", "Independent contexts"],
                    ylim=(0, 1), ylabel="Task success", title="Same context marginals, different coupling")
        axes[0].yaxis.set_major_formatter(PercentFormatter(1))
        axes[0].legend(frameon=False, loc="upper right", fontsize=9)
        clusters = audit["statistics"]["per_seed"]
        xs = list(range(1, len(clusters) + 1))
        axes[1].scatter(xs, [100 * c["interaction"] for c in clusters], color="#0f766e", zorder=3)
        lo, hi = audit["statistics"]["interaction_cluster_bootstrap_95"]
        mean = audit["statistics"]["means"]["interaction"]
        axes[1].axhspan(100 * lo, 100 * hi, color="#0f766e", alpha=.12, label="95% cluster bootstrap CI")
        axes[1].axhline(100 * mean, color="#0f766e", label=f"Mean: {100*mean:.2f} pp")
        axes[1].axhline(0, color="#94a3b8", linewidth=1)
        axes[1].set(xlabel="Independent task seed index", ylabel="Coupling interaction (percentage points)",
                    title="Effect across 16 task seeds", ylim=(-3, 65), xticks=[1, 4, 8, 12, 16])
        axes[1].legend(frameon=False, fontsize=9, loc="lower right")
        fig.suptitle("Does diagnostic evidence remain valid at execution time?", fontsize=15)
        fig.text(.5, .025, "Development causal audit: 320 physical task rollouts; evaluator-only, all states included; no online policy claim.",
                 ha="center", color="#475569", fontsize=9)
        fig.tight_layout(rect=(0, .07, 1, .94))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(args.output, dpi=180, metadata={k: audit[k] for k in
                    ("experiment_run_id", "manifest_id", "source_git_commit")})
        plt.close(fig)


if __name__ == "__main__":
    main()

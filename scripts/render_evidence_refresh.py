"""Render the audited frozen study; requires matplotlib, not the simulator."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def render(audit, output):
    result = json.loads(audit.read_text())
    metrics = result["statistics"]["methods"]
    names = list(metrics)
    labels = [name.replace("_", " ").title() for name in names]
    colors = ["#d85a37" if name == "DECISION_STABILITY" else "#34749b" for name in names]
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.7), layout="constrained")
    for axis, key, title in zip(axes, ("successful", "mean_probe_steps"),
                                 ("Task success (out of 96)", "Mean charged probe steps")):
        values = [metrics[name][key] for name in names]
        axis.barh(labels, values, color=colors, height=.66)
        axis.invert_yaxis()
        axis.set_title(title, loc="left", fontweight="bold", pad=12)
        axis.set_xlim(0, 104 if key == "successful" else 73)
        for y, value in enumerate(values):
            axis.text(value + 1, y, f"{value:.0f}" if key == "successful" else f"{value:.1f}", va="center", fontsize=10)
        axis.spines[["top", "right", "left"]].set_visible(False)
        axis.tick_params(axis="y", length=0)
        axis.xaxis.grid(True, alpha=.18)
        axis.set_axisbelow(True)
    fig.suptitle("Evidence refresh: eight chronological streams", fontsize=17, fontweight="bold")
    contrast = result["statistics"]["candidate_minus_baseline"]["FIXED_64"]
    low, high = contrast["cluster_bootstrap_95"]
    fig.supxlabel(f"Candidate vs fixed 64: {100*contrast['difference']:+.1f} pp; stream-bootstrap 95% CI [{100*low:.1f}, {100*high:.1f}] pp.\n"
                  "Development task success; paired branches shared only for identical execution. No novelty or generalization claim.", fontsize=10)
    for suffix in (".png", ".pdf"):
        fig.savefig(output.with_suffix(suffix), dpi=180, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    render(args.audit, args.output)

"""Render the constructed identifiability witness from an audited result."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def render(audit, output):
    result = json.loads(audit.read_text())
    s = result["statistics"]
    counts = s["success_by_context_candidate"]
    contexts = list(counts)
    candidates = list(counts[contexts[0]])
    matrix = np.array([[counts[c][a] for a in candidates] for c in contexts])
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8), layout="constrained")
    axes[0].imshow(matrix, vmin=0, vmax=16, cmap="Blues", aspect="auto")
    axes[0].set_xticks(range(3), ["x - 0.2", "unchanged", "x + 0.2"])
    axes[0].set_yticks(range(3), contexts)
    axes[0].set_ylabel("Constructed context")
    axes[0].set_title("Task successes / 16 per cell", loc="left", fontweight="bold")
    for i in range(3):
        for j in range(3):
            axes[0].text(j, i, str(matrix[i,j]), ha="center", va="center", fontsize=20,
                         color="white" if matrix[i,j] > 9 else "#222222")
    blind = s["best_context_blind_successes_oracle"]
    aware = s["context_aware_successes_oracle"]
    axes[1].bar([0,1], [blind, aware], color=["#34749b", "#d85a37"], width=.55)
    axes[1].set_xticks([0,1], ["Best common action\nper seed", "Best action per\nseed and context"])
    axes[1].set_ylim(0, 53)
    axes[1].set_ylabel("Hindsight successes / 48")
    axes[1].set_title("Evaluator-only bounds", loc="left", fontweight="bold")
    for i, value in enumerate((blind, aware)):
        axes[1].text(i, value + 1, str(value), ha="center", fontsize=13)
    axes[1].spines[["top", "right"]].set_visible(False)
    fig.suptitle("Does an invisible actuator difference change the required action?", fontsize=15, fontweight="bold")
    fig.supxlabel(f"Disjoint successful-action witnesses: {s['witness_count']}/16 seeds. "
                  "Constructed noiseless stress test; bounds are not method performance.", fontsize=10)
    for suffix in (".png", ".pdf"):
        fig.savefig(output.with_suffix(suffix), dpi=180, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    render(args.audit, args.output)

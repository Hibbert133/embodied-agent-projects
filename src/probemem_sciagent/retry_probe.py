"""Independent nominal-prefix repeatability micro-probe."""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np

from src.probemem_sciagent.schemas import RetryProbeEvidence


def summarize_retry_repeatability(
    trials: Sequence[Sequence[dict[str, Any]]], *, positive_progress_threshold: float = 0.0,
    severe_failure_threshold: float = -0.02,
) -> RetryProbeEvidence:
    if len(trials) < 2 or any(not trial for trial in trials):
        raise ValueError("retry probe requires multiple non-empty trials")
    progress = np.asarray(
        [float(trial[-1]["task_progress_metrics"]["progress_to_goal"]) for trial in trials],
        dtype=float,
    )
    return RetryProbeEvidence(
        num_trials=len(trials),
        positive_progress_rate=float(np.mean(progress > positive_progress_threshold)),
        mean_progress=float(np.mean(progress)), progress_variance=float(np.var(progress)),
        severe_failure_rate=float(np.mean(progress <= severe_failure_threshold)),
    )

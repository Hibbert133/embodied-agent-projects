"""Leakage-safe planar correction decisions derived from active probes."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

import numpy as np


@dataclass(frozen=True)
class PlanarCorrectionEstimate:
    """A bounded x/y repair inferred from agent-visible probe evidence."""

    estimated_action_bias: tuple[float, float]
    simultaneous_correction: tuple[float, float, float, float]
    dominant_axis: str
    dominant_axis_correction: tuple[float, float, float, float]
    confidence: tuple[float, float]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _nearest_signed_level(value: float, levels: Sequence[float]) -> float:
    positive_levels = tuple(sorted({float(level) for level in levels if level >= 0.0}))
    if not positive_levels:
        raise ValueError("correction levels must contain at least one non-negative value")
    magnitude = min(positive_levels, key=lambda level: abs(level - abs(value)))
    if np.isclose(magnitude, 0.0) or np.isclose(value, 0.0):
        return 0.0
    return float(np.copysign(magnitude, value))


def estimate_planar_correction(
    diagnostic_context: Mapping[str, Any],
    *,
    allowed_magnitudes: Sequence[float],
    minimum_gain: float = 1e-6,
) -> PlanarCorrectionEstimate:
    """Convert visible drift/gain estimates into a quantized 2-D correction.

    The local probe model is ``observed_velocity = gain * command + drift``.
    Therefore inferred action bias is ``drift / gain`` and the repair opposes it.
    No injected perturbation fields are accepted or required.
    """

    if minimum_gain <= 0.0:
        raise ValueError("minimum_gain must be positive")
    inference = diagnostic_context.get("inference")
    if not isinstance(inference, Mapping):
        raise ValueError("planar correction requires probe inference")
    drift = np.asarray(inference.get("estimated_drift_per_step"), dtype=float)
    gain = np.asarray(inference.get("axis_response_gain"), dtype=float)
    if drift.shape != (2,) or gain.shape != (2,):
        raise ValueError("probe drift and gain must both be two-dimensional")
    if not np.all(np.isfinite(drift)) or not np.all(np.isfinite(gain)):
        raise ValueError("probe drift and gain must be finite")

    safe_gain = np.where(np.abs(gain) >= minimum_gain, gain, np.nan)
    inferred_bias = np.divide(drift, safe_gain)
    inferred_bias = np.nan_to_num(inferred_bias, nan=0.0, posinf=0.0, neginf=0.0)
    continuous_correction = -inferred_bias
    quantized = np.array(
        [_nearest_signed_level(value, allowed_magnitudes) for value in continuous_correction],
        dtype=np.float32,
    )
    dominant_index = int(np.argmax(np.abs(inferred_bias)))
    dominant = np.zeros(4, dtype=np.float32)
    simultaneous = np.zeros(4, dtype=np.float32)
    simultaneous[:2] = quantized
    dominant[dominant_index] = quantized[dominant_index]
    signal = np.abs(inferred_bias)
    confidence = signal / (signal.sum() + float(inference.get("residual", 0.0)) + 1e-12)
    return PlanarCorrectionEstimate(
        estimated_action_bias=(float(inferred_bias[0]), float(inferred_bias[1])),
        simultaneous_correction=tuple(float(value) for value in simultaneous),
        dominant_axis=("x", "y")[dominant_index],
        dominant_axis_correction=tuple(float(value) for value in dominant),
        confidence=(float(confidence[0]), float(confidence[1])),
    )

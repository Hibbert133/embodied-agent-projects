"""Reproducible action perturbations for controlled robustness experiments."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence

import numpy as np


class ActionPerturbation(ABC):
    """Base interface for one action perturbation configuration."""

    name: str

    def __init__(self) -> None:
        self._rng: np.random.Generator | None = None

    def reset(self, episode_seed: int) -> None:
        """Create an independent RNG stream for one episode."""

        self._rng = np.random.default_rng(int(episode_seed))

    @property
    @abstractmethod
    def level(self) -> float:
        """Scalar strength reported by sweep outputs."""

    @abstractmethod
    def apply(self, action: np.ndarray) -> np.ndarray:
        """Return a perturbed copy of an action without clipping it."""

    def _action_copy(self, action: np.ndarray) -> np.ndarray:
        result = np.asarray(action, dtype=np.float32).copy()
        if result.ndim != 1:
            raise ValueError(f"action must be one-dimensional, got shape={result.shape}")
        return result


class IdentityPerturbation(ActionPerturbation):
    name = "identity"

    @property
    def level(self) -> float:
        return 0.0

    def apply(self, action: np.ndarray) -> np.ndarray:
        return self._action_copy(action)


class ActionScalePerturbation(ActionPerturbation):
    name = "action_scale"

    def __init__(self, scale: float) -> None:
        super().__init__()
        if scale < 0:
            raise ValueError("action scale must be non-negative")
        self.scale = float(scale)

    @property
    def level(self) -> float:
        return self.scale

    def apply(self, action: np.ndarray) -> np.ndarray:
        return self._action_copy(action) * self.scale


class GaussianNoisePerturbation(ActionPerturbation):
    name = "gaussian_noise"

    def __init__(self, std: float) -> None:
        super().__init__()
        if std < 0:
            raise ValueError("noise standard deviation must be non-negative")
        self.std = float(std)

    @property
    def level(self) -> float:
        return self.std

    def apply(self, action: np.ndarray) -> np.ndarray:
        result = self._action_copy(action)
        if self._rng is None:
            raise RuntimeError("call reset(episode_seed) before applying noise")
        noise = self._rng.normal(loc=0.0, scale=self.std, size=result.shape)
        return result + noise.astype(np.float32)


class ActionBiasPerturbation(ActionPerturbation):
    name = "action_bias"

    def __init__(self, bias: float | Sequence[float]) -> None:
        super().__init__()
        bias_array = np.asarray(bias, dtype=np.float32)
        if bias_array.ndim > 1:
            raise ValueError("action bias must be a scalar or one-dimensional")
        self.bias = bias_array.copy()

    @property
    def level(self) -> float:
        if self.bias.ndim == 0:
            return abs(float(self.bias))
        return float(np.max(np.abs(self.bias), initial=0.0))

    def apply(self, action: np.ndarray) -> np.ndarray:
        result = self._action_copy(action)
        try:
            return result + self.bias
        except ValueError as exc:
            raise ValueError(
                f"bias shape {self.bias.shape} cannot broadcast to action {result.shape}"
            ) from exc


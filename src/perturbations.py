"""Reproducible, dimension-masked action perturbations."""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Sequence, Any
import numpy as np

DEFAULT_ACTION_MASK = (True, True, True, False)

class ActionPerturbation(ABC):
    name: str
    def __init__(self, action_mask: Sequence[bool] = DEFAULT_ACTION_MASK) -> None:
        self.action_mask = np.asarray(action_mask, dtype=bool)
        if self.action_mask.ndim != 1 or not self.action_mask.size:
            raise ValueError("action_mask must be a non-empty one-dimensional sequence")
        self._rng: np.random.Generator | None = None
    def reset(self, episode_seed: int) -> None:
        self._rng = np.random.default_rng(int(episode_seed))
    def _action_copy(self, action: np.ndarray) -> np.ndarray:
        result = np.asarray(action, dtype=np.float32).copy()
        if result.ndim != 1 or result.shape != self.action_mask.shape:
            raise ValueError(f"action shape {result.shape} does not match mask {self.action_mask.shape}")
        return result
    @property
    @abstractmethod
    def level(self) -> float: ...
    @abstractmethod
    def apply(self, action: np.ndarray) -> np.ndarray: ...
    def parameters(self) -> dict[str, Any]:
        return {"level": self.level, "action_mask": self.action_mask.tolist()}

class IdentityPerturbation(ActionPerturbation):
    name = "identity"
    @property
    def level(self) -> float: return 0.0
    def apply(self, action: np.ndarray) -> np.ndarray: return self._action_copy(action)

class ActionScalePerturbation(ActionPerturbation):
    name = "action_scale"
    def __init__(self, scale: float, action_mask: Sequence[bool] = DEFAULT_ACTION_MASK) -> None:
        super().__init__(action_mask)
        if scale < 0: raise ValueError("action scale must be non-negative")
        self.scale = float(scale)
    @property
    def level(self) -> float: return self.scale
    def apply(self, action: np.ndarray) -> np.ndarray:
        result = self._action_copy(action); result[self.action_mask] *= self.scale; return result

class GaussianNoisePerturbation(ActionPerturbation):
    name = "gaussian_noise"
    def __init__(self, std: float, action_mask: Sequence[bool] = DEFAULT_ACTION_MASK) -> None:
        super().__init__(action_mask)
        if std < 0: raise ValueError("noise standard deviation must be non-negative")
        self.std = float(std)
    @property
    def level(self) -> float: return self.std
    def apply(self, action: np.ndarray) -> np.ndarray:
        result = self._action_copy(action)
        if self._rng is None: raise RuntimeError("call reset(episode_seed) before applying noise")
        result[self.action_mask] += self._rng.normal(0, self.std, int(self.action_mask.sum())).astype(np.float32)
        return result

class ActionBiasPerturbation(ActionPerturbation):
    name = "action_bias"
    def __init__(self, bias: Sequence[float], action_mask: Sequence[bool] = DEFAULT_ACTION_MASK) -> None:
        super().__init__(action_mask)
        self.bias = np.asarray(bias, dtype=np.float32)
        if self.bias.ndim != 1 or self.bias.shape != self.action_mask.shape:
            raise ValueError("bias must be a full action vector matching action_mask")
        if np.any(self.bias[~self.action_mask] != 0):
            raise ValueError("bias must be zero outside action_mask")
    @property
    def level(self) -> float: return float(np.max(np.abs(self.bias), initial=0.0))
    def apply(self, action: np.ndarray) -> np.ndarray:
        result = self._action_copy(action); result[self.action_mask] += self.bias[self.action_mask]; return result
    def parameters(self) -> dict[str, Any]:
        result = super().parameters(); result["bias"] = self.bias.tolist(); return result

class BiasNoisePerturbation(ActionPerturbation):
    """Registered persistent bias plus independent per-step Gaussian execution noise."""
    name = "bias_plus_gaussian_noise"
    def __init__(self, bias: Sequence[float], std: float, action_mask: Sequence[bool] = DEFAULT_ACTION_MASK) -> None:
        super().__init__(action_mask)
        self.bias = np.asarray(bias, dtype=np.float32)
        self.std = float(std)
        if self.bias.ndim != 1 or self.bias.shape != self.action_mask.shape:
            raise ValueError("bias must be a full action vector matching action_mask")
        if np.any(self.bias[~self.action_mask] != 0):
            raise ValueError("bias must be zero outside action_mask")
        if self.std < 0:
            raise ValueError("noise standard deviation must be non-negative")
    @property
    def level(self) -> float: return max(float(np.max(np.abs(self.bias), initial=0.0)), self.std)
    def apply(self, action: np.ndarray) -> np.ndarray:
        result = self._action_copy(action)
        if self._rng is None: raise RuntimeError("call reset(episode_seed) before applying bias-plus-noise")
        result[self.action_mask] += self.bias[self.action_mask]
        result[self.action_mask] += self._rng.normal(0, self.std, int(self.action_mask.sum())).astype(np.float32)
        return result
    def parameters(self) -> dict[str, Any]:
        result = super().parameters(); result.update({"bias": self.bias.tolist(), "std": self.std}); return result

"""Evaluator-owned affine xy injection. Never pass this object to an estimator."""
import numpy as np
from src.perturbations import ActionPerturbation


class AffineNoisePerturbation(ActionPerturbation):
    name="affine_xy_plus_gaussian_noise_v1"
    def __init__(self,matrix_xy,bias_xy,std=.05):
        super().__init__();self.matrix=np.asarray(matrix_xy,dtype=np.float32);self.bias=np.asarray(bias_xy,dtype=np.float32);self.std=float(std)
        if self.matrix.shape!=(2,2) or self.bias.shape!=(2,) or not np.isfinite(self.matrix).all() or not np.isfinite(self.bias).all() or not np.isfinite(std) or std<0:
            raise ValueError("invalid evaluator affine injection")
    @property
    def level(self):return float(max(np.linalg.norm(self.matrix-np.eye(2)),np.linalg.norm(self.bias),self.std))
    def apply(self,action):
        result=self._action_copy(action)
        if self._rng is None:raise RuntimeError("reset actuator RNG before execution")
        result[:2]=self.matrix@result[:2]+self.bias
        result[:3]+=self._rng.normal(0,self.std,3).astype(np.float32)
        return result

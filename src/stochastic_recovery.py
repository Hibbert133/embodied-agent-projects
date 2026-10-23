"""Leakage-safe decisions and reproducible seeds for stochastic recovery."""
from __future__ import annotations
from dataclasses import asdict,dataclass
from typing import Any
import numpy as np
@dataclass(frozen=True)
class ValueAwareRecoveryDecision:
 strategy:str
 reason:str
 consistency_score:float
 consistency_threshold:float
 def to_dict(self)->dict[str,Any]:return asdict(self)
def derive_retry_seed(episode_seed:int,retry_index:int=1)->int:
 if retry_index<=0:raise ValueError("retry_index must be positive")
 return int(np.random.SeedSequence([int(episode_seed),int(retry_index),0x5EED]).generate_state(1)[0])
def choose_value_aware_recovery(consistency_score:float,consistency_threshold:float)->ValueAwareRecoveryDecision:
 if not np.isfinite(consistency_score) or consistency_score<0 or consistency_threshold<0:raise ValueError("finite non-negative consistency values required")
 if consistency_score>consistency_threshold:
  return ValueAwareRecoveryDecision("stochastic_retry","cross-repeat variability supports a new execution realization",float(consistency_score),float(consistency_threshold))
 return ValueAwareRecoveryDecision("bias_compensation","repeatable drift supports deterministic compensation",float(consistency_score),float(consistency_threshold))

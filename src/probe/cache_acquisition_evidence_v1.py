"""Decision-time data only; no evaluator identity, hidden state or future outcome."""
from dataclasses import asdict, dataclass, fields
import hashlib
import json
import numpy as np
from src.probe.cold_start_response import ColdPrefix, TASKS
from src.probe.chronological_cache_reference import BLOCK8


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CacheAcquisitionEvidenceV1:
    prefix: ColdPrefix
    old_parameters: tuple
    source_covariance: tuple
    source_task: str
    source_age: int
    source_active_parameter_bound: bool
    current_policy_command: tuple
    remaining_budget: int

    def __post_init__(self):
        if type(self.prefix) is not ColdPrefix or len(self.prefix.commands) != 4:
            raise ValueError("exactly four causally observed steps required")
        if list(map(list, self.prefix.commands)) != np.asarray(BLOCK8[:4], np.float32).astype(float).tolist():
            raise ValueError("frozen block-four sent commands required")
        parameters = np.asarray(self.old_parameters, float)
        covariance = np.asarray(self.source_covariance, float)
        raw = np.asarray(self.current_policy_command, float)
        if parameters.shape != (6,) or covariance.shape != (6, 6) or raw.shape != (4,):
            raise ValueError("registered point, covariance and current policy shapes required")
        if not all(np.isfinite(v).all() for v in (parameters, covariance, raw)):
            raise ValueError("finite visible evidence required")
        if not np.allclose(covariance, covariance.T, rtol=0, atol=1e-12):
            raise ValueError("symmetric working source covariance required")
        np.linalg.cholesky(covariance)
        singular = np.linalg.svd(parameters.reshape(2, 3)[:, :2], compute_uv=False)
        if singular[-1] < .25 or singular[0] > 4 or np.any(np.abs(parameters) > [2, 2, .3, 2, 2, .3]):
            raise ValueError("previously accepted point outside numerical domain")
        if self.source_task not in TASKS or type(self.source_age) is not int or not 1 <= self.source_age <= 11:
            raise ValueError("earlier source task and age required")
        if type(self.source_active_parameter_bound) is not bool or type(self.remaining_budget) is not int or self.remaining_budget != 496:
            raise ValueError("decision-time source flag and remaining budget required")
        object.__setattr__(self, "old_parameters", tuple(map(float, parameters)))
        object.__setattr__(self, "source_covariance", tuple(tuple(map(float, row)) for row in covariance))
        object.__setattr__(self, "current_policy_command", tuple(map(float, raw)))

    @classmethod
    def from_dict(cls, value):
        if type(value) is not dict or set(value) != {f.name for f in fields(cls)}:
            raise ValueError("unknown, evaluator-only or missing acquisition evidence field")
        value = dict(value)
        value["prefix"] = ColdPrefix.from_dict(value["prefix"])
        return cls(**value)

    def to_dict(self):
        return json.loads(canonical(asdict(self)))

    @property
    def evidence_sha256(self):
        return digest(self.to_dict())

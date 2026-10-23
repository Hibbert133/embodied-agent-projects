"""Owned past-policy query measure for a standard IVR reference.

This is an empirical task-query adaptation, not a reproduction of GAUGE's
planner or a task-return certificate. No current future rollout is queried.
"""
from dataclasses import asdict, dataclass, fields
import json
import numpy as np
from src.probe.cache_acquisition_evidence_v1 import canonical, digest
from src.probe.cold_start_response import TASKS, clipped_normal_mean
from src.probe.cold_cache_prediction import PredictionQuery, response
from src.probe.chronological_cache_reference import BLOCK8, VerifiedPoint, check_choice
from src.probe.forward_prediction import vector
from src.probe.operator_identification import encode_controller

MAX_QUERIES = 64
METHOD = "TASK_HISTORY_IVR4"


@dataclass(frozen=True)
class PastPolicyQueryV1:
    task: str
    source_episode: int
    host_calls: int
    raw_policy: tuple
    observation_sha256: str

    def __post_init__(self):
        if self.task not in TASKS or type(self.source_episode) is not int or self.source_episode < 0 or type(self.host_calls) is not int or not 1 <= self.host_calls <= 500:
            raise ValueError("completed earlier policy query required")
        h = self.observation_sha256
        if type(h) is not str or len(h) != 64 or any(c not in "0123456789abcdef" for c in h):
            raise ValueError("actual visible observation digest required")
        object.__setattr__(self, "raw_policy", vector(self.raw_policy, 4))

    @classmethod
    def from_dict(cls, value):
        if type(value) is not dict or set(value) != {f.name for f in fields(cls)}:
            raise ValueError("unknown or evaluator-only past query field")
        return cls(**value)


@dataclass(frozen=True)
class HistoryQueryMeasureV1:
    task: str
    episode: int
    past_queries: tuple
    current_policy_command: tuple

    def __post_init__(self):
        if self.task not in TASKS or type(self.episode) is not int or self.episode < 0 or len(self.past_queries) > MAX_QUERIES:
            raise ValueError("registered current task, episode and bounded history required")
        if any(type(q) is not PastPolicyQueryV1 or q.task != self.task or q.source_episode >= self.episode for q in self.past_queries):
            raise ValueError("future, foreign-task or untyped query rejected")
        keys = [(q.source_episode, q.host_calls) for q in self.past_queries]
        if keys != sorted(set(keys)):
            raise ValueError("unique chronological query history required")
        object.__setattr__(self, "past_queries", tuple(self.past_queries))
        object.__setattr__(self, "current_policy_command", vector(self.current_policy_command, 4))

    @classmethod
    def from_dict(cls, value):
        if type(value) is not dict or set(value) != {f.name for f in fields(cls)}:
            raise ValueError("unknown, hidden or future task-measure field")
        return cls(value["task"], value["episode"], tuple(PastPolicyQueryV1.from_dict(v) for v in value["past_queries"]), value["current_policy_command"])

    def to_dict(self): return json.loads(canonical(asdict(self)))


class OwnedQueryHistoryV1:
    """Host provenance store. Owner/labels never enter the numerical task measure."""
    def __init__(self, owner):
        if type(owner) is not str or not owner:
            raise ValueError("method owner required")
        self.owner, self.last_completed = owner, -1
        self.queries = {task: () for task in TASKS}

    def for_task(self, task, episode):
        if task not in TASKS or type(episode) is not int or episode != self.last_completed+1:
            raise ValueError("only the next actual episode can query history")
        return self.queries[task]

    def append_record(self, record):
        if record["method"] != self.owner or record["episode"] != self.last_completed+1 or "outcome" not in record:
            raise ValueError("foreign, incomplete, repeated or future episode history")
        task = record["task"]
        if task not in TASKS:
            raise ValueError("registered task history required")
        rows = record["trace"]
        if [r["host_calls"] for r in rows] != list(range(1, len(rows)+1)) or record["outcome"]["total_steps"] != len(rows):
            raise ValueError("actual continuous policy trace required")
        added = []
        for row in rows:
            if row["raw_policy"] is None:
                if row["phase"] != "FIXED_PROBE": raise ValueError("policy query omitted")
                continue
            if row["phase"] not in ("POLICY", "PASSIVE_PREFIX"):
                raise ValueError("nonexecuted check query cannot enter history")
            added.append(PastPolicyQueryV1(task, record["episode"], row["host_calls"], row["raw_policy"], digest(row["before"]["observation"])))
        self.queries[task] = tuple((*self.queries[task], *added)[-MAX_QUERIES:])
        self.last_completed = record["episode"]

    @property
    def sha256(self):
        return digest({"owner": self.owner, "last_completed": self.last_completed,
                       "queries": {task: [asdict(q) for q in values] for task, values in self.queries.items()}})


def history_ivr(model, prefix, cached, measure):
    if (type(cached) is not VerifiedPoint or cached.belief is None or type(measure) is not HistoryQueryMeasureV1 or
        measure.task != prefix.task or len(prefix.commands) != 4 or prefix.commands != BLOCK8[:4] or cached.source_episode >= measure.episode):
        raise ValueError("own earlier joint cache, current block four and visible query measure required")
    inverse_prior = np.linalg.inv(cached.belief.covariance)
    theta = np.asarray(cached.parameters).reshape(2, 3)
    moment = np.zeros((6, 6))
    commands = [q.raw_policy for q in measure.past_queries]+[measure.current_policy_command]
    for raw in commands:
        sent = encode_controller(cached.controller, raw)
        x = np.r_[sent[:2], 1.]
        _, slope = clipped_normal_mean(theta @ x)
        jac = np.zeros((2, 6)); jac[0, :3] = slope[0]*x; jac[1, 3:] = slope[1]*x
        moment += jac.T @ jac/len(commands)
    values = []
    for program in (prefix.commands, BLOCK8):
        query = PredictionQuery(prefix.task, prefix.initial_observation, program, True)
        _, jac, covariance = response(model, query, cached.parameters)
        posterior = np.linalg.inv(inverse_prior+jac.T @ np.linalg.solve(covariance, jac))
        values.append(float(np.trace(moment @ posterior)))
    relative = (values[0]-values[1])/max(values[0], 1e-12)
    if not np.isfinite(relative) or not -1e-8 <= relative <= 1+1e-8:
        raise ValueError("invalid nested history-query variance reduction")
    return {"variance_after4": values[0], "expected_variance_after8": values[1],
        "relative_variance_reduction": float(np.clip(relative, 0, 1)), "threshold": .25,
        "past_policy_queries": len(measure.past_queries), "total_measure_queries": len(commands),
        "measure_sha256": digest(measure.to_dict()), "physical_probability_qualified": False, "task_value_estimate": False}


def history_check(model, prefix, cached, measure):
    base = check_choice("UNCERTAINTY4", model, prefix, cached, 0., measure.current_policy_command)
    ivr = history_ivr(model, prefix, cached, measure)
    refresh = base["action"] == "REFRESH8" or ivr["relative_variance_reduction"] >= .25
    return {**base, "action": "REFRESH8" if refresh else "RUN_CACHED", "reason": "PREDICTIVE_OR_OWN_HISTORY_QUERY_VARIANCE",
            "ivr": ivr, "history_measure": measure.to_dict()}

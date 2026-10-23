"""Two-stage empirical branch-value learning on strictly visible histories.

RBF ridge regression and nested group cross-fitting are standard components.
This prototype confers no algorithm novelty, physical or probability guarantee.
Episode groups and realized targets are offline evaluator metadata, never inputs
to evidence features or a deployed decision.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import numpy as np
from src.probe.action_response_validity import CachedPoint

TASKS = ("push-v3", "reach-v3", "door-open-v3")
LENGTHS = (8, 16)
METHODS = ("CACHE_CONTINUE", "MID8_WIDE", "MID16_WIDE", "MID8_WIDE_KEEP", "MID16_WIDE_KEEP")
RIDGE = 1.0
SCALE_FLOOR = 1e-6
LOSS_SCALE = 500.0


def numbers(value, size):
    if not isinstance(value, (tuple, list)) or len(value) != size or any(type(x) not in (int, float) or not math.isfinite(x) for x in value):
        raise ValueError("finite visible numeric vector required")
    return tuple(float(x) for x in value)


@dataclass(frozen=True)
class ValueEvidence:
    task: str
    observations: tuple
    commands: tuple
    raw_policy: tuple
    old_parameters: tuple
    probe_steps: int
    remaining_steps: int
    fit_valid: object = None
    fit_parameters: object = None
    fit_rmse_m: object = None

    def __post_init__(self):
        if self.task not in TASKS or type(self.probe_steps) is not int or self.probe_steps not in (0, 8, 16):
            raise ValueError("registered task and evidence stage required")
        steps = 6 + self.probe_steps
        if type(self.remaining_steps) is not int or self.remaining_steps != 500 - steps:
            raise ValueError("causal registered budget required")
        if len(self.observations) != steps + 1 or len(self.commands) != steps or len(self.raw_policy) != steps:
            raise ValueError("evidence must end at its declared decision boundary")
        observations = tuple(numbers(v, 39) for v in self.observations)
        commands = tuple(numbers(v, 4) for v in self.commands)
        raw = tuple(None if v is None else numbers(v, 4) for v in self.raw_policy)
        if any(abs(x) > 1 for v in commands for x in v) or any(v is None for v in raw[:6]) or any(v is not None for v in raw[6:]):
            raise ValueError("prefix policy and actual probe commands differ")
        if self.probe_steps:
            direction_steps = self.probe_steps // 4
            expected = tuple(v for v in ((.4, 0., 0., 0.), (-.4, 0., 0., 0.), (0., .4, 0., 0.), (0., -.4, 0., 0.)) for _ in range(direction_steps))
            if not np.allclose(commands[6:], expected, atol=1e-8, rtol=0):
                raise ValueError("unregistered measurement evidence")
            if type(self.fit_valid) is not bool:
                raise ValueError("post-measurement fit validity required")
            if self.fit_valid and self.fit_parameters is None:
                raise ValueError("valid fit lacks executable parameters")
            if not self.fit_valid and self.fit_parameters is not None:
                raise ValueError("rejected fit cannot supply controller parameters")
        elif any(v is not None for v in (self.fit_valid, self.fit_parameters, self.fit_rmse_m)):
            raise ValueError("future fit provided before measurement")
        if self.fit_rmse_m is not None and (type(self.fit_rmse_m) not in (int, float) or not math.isfinite(self.fit_rmse_m) or self.fit_rmse_m < 0):
            raise ValueError("invalid visible fit diagnostic")
        object.__setattr__(self, "observations", observations)
        object.__setattr__(self, "commands", commands)
        object.__setattr__(self, "raw_policy", raw)
        object.__setattr__(self, "old_parameters", numbers(self.old_parameters, 6))
        old = self.old_parameters
        CachedPoint(((old[0], old[1]), (old[3], old[4])), (old[2], old[5]))
        if self.fit_parameters is not None:
            object.__setattr__(self, "fit_parameters", numbers(self.fit_parameters, 6))
            fitted = self.fit_parameters
            CachedPoint(((fitted[0], fitted[1]), (fitted[3], fitted[4])), (fitted[2], fitted[5]))

    @classmethod
    def from_dict(cls, value):
        if type(value) is not dict or set(value) != set(cls.__dataclass_fields__):
            raise ValueError("unknown or privileged evidence field")
        return cls(**value)

    def features(self):
        # All moments are computed from the available history, including its
        # state changes. Neither a model's future observation nor a label enters.
        obs = np.asarray(self.observations)
        command = np.asarray(self.commands)
        displacement = np.diff(obs[:, :3], axis=0)
        values = [*self.old_parameters, *obs[0], *obs[-1], *(obs[-1] - obs[0]),
                  *command[:, :2].mean(axis=0), *command[:, :2].std(axis=0),
                  *displacement.mean(axis=0), *displacement.std(axis=0), *displacement[-1]]
        if self.probe_steps:
            fitted = np.asarray(self.fit_parameters if self.fit_valid else self.old_parameters)
            values.extend([float(self.fit_valid), *fitted, *(fitted - np.asarray(self.old_parameters)),
                           1000 * (self.fit_rmse_m or 0.)])
        return np.asarray(values, dtype=float)

    @property
    def digest(self):
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class BranchRow:
    case_id: str
    group: int
    pre: ValueEvidence
    post: dict
    outcomes: dict

    def __post_init__(self):
        if type(self.group) is not int or not 0 <= self.group < 8 or type(self.case_id) is not str or not self.case_id:
            raise ValueError("offline source group required")
        if type(self.pre) is not ValueEvidence or self.pre.probe_steps != 0 or set(self.post) != set(LENGTHS) or set(self.outcomes) != set(METHODS):
            raise ValueError("complete registered branch row required")
        for length, evidence in self.post.items():
            if type(evidence) is not ValueEvidence or evidence.task != self.pre.task or evidence.probe_steps != length:
                raise ValueError("foreign post-measurement evidence")
            if evidence.observations[:7] != self.pre.observations or evidence.commands[:6] != self.pre.commands or evidence.raw_policy[:6] != self.pre.raw_policy or evidence.old_parameters != self.pre.old_parameters:
                raise ValueError("post evidence comes from a different prefix")
        for value in self.outcomes.values():
            if set(value) != {"success", "stopped", "steps", "loss"} or type(value["success"]) is not bool or type(value["stopped"]) is not bool or type(value["steps"]) is not int or not 0 <= value["steps"] <= 500:
                raise ValueError("registered realized outcome required")
            if (value["success"] and value["stopped"]) or value["loss"] != (value["steps"] if value["success"] else 500):
                raise ValueError("invalid deadline outcome")


@dataclass(frozen=True)
class KernelModel:
    mean: np.ndarray
    scale: np.ndarray
    support: np.ndarray
    bandwidth_squared: float
    target_mean: np.ndarray
    weights: np.ndarray

    @classmethod
    def fit(cls, features, targets):
        x, y = np.asarray(features, float), np.asarray(targets, float)
        if x.ndim != 2 or y.ndim != 2 or len(x) != len(y) or len(x) < 2 or not np.isfinite(x).all() or not np.isfinite(y).all():
            raise ValueError("finite matching offline training population required")
        mean, scale = x.mean(axis=0), np.maximum(x.std(axis=0), SCALE_FLOOR)
        support = (x - mean) / scale
        distance = ((support[:, None] - support[None, :]) ** 2).sum(axis=2)
        upper = distance[np.triu_indices(len(x), 1)]
        nonzero = upper[upper > 1e-12]
        bandwidth = float(np.median(nonzero)) if len(nonzero) else 1.
        kernel = np.exp(-distance / (2 * bandwidth))
        target_mean = y.mean(axis=0)
        weights = np.linalg.solve(kernel + RIDGE * np.eye(len(x)), y - target_mean)
        return cls(mean, scale, support, bandwidth, target_mean, weights)

    def predict(self, features):
        x = np.asarray(features, float)
        if x.shape != self.mean.shape or not np.isfinite(x).all():
            raise ValueError("visible query dimension differs")
        query = (x - self.mean) / self.scale
        kernel = np.exp(-((self.support - query) ** 2).sum(axis=1) / (2 * self.bandwidth_squared))
        return self.target_mean + kernel @ self.weights

    def saved(self):
        return {k: v.tolist() if isinstance(v, np.ndarray) else v for k, v in asdict(self).items()}

    @classmethod
    def from_saved(cls, value):
        if type(value) is not dict or set(value) != set(cls.__dataclass_fields__):
            raise ValueError("registered model artifact required")
        arrays = {k: np.asarray(value[k], float) for k in value if k != "bandwidth_squared"}
        mean, scale, support = arrays["mean"], arrays["scale"], arrays["support"]
        target, weights = arrays["target_mean"], arrays["weights"]
        width = value["bandwidth_squared"]
        if mean.ndim != 1 or scale.shape != mean.shape or support.ndim != 2 or support.shape[1:] != mean.shape or target.ndim != 1 or weights.shape != (len(support), len(target)):
            raise ValueError("model dimensions differ")
        if any(not np.isfinite(v).all() for v in arrays.values()) or np.any(scale < SCALE_FLOOR) or type(width) not in (int, float) or not math.isfinite(width) or width <= 0:
            raise ValueError("invalid numeric model artifact")
        return cls(**arrays, bandwidth_squared=float(width))


def training(rows, excluded=()):
    if len(rows) < 2 or any(type(r) is not BranchRow for r in rows) or len({r.case_id for r in rows}) != len(rows):
        raise ValueError("unique offline branch rows required")
    groups = {r.group for r in rows}
    if groups & set(excluded) or len(groups) < 2:
        raise ValueError("evaluation group entered training or training is ungrouped")
    if len({r.pre.task for r in rows}) != 1:
        raise ValueError("task-specific training required")
    return tuple(rows)


def post_model(rows, length, excluded=()):
    rows = training(rows, excluded)
    return KernelModel.fit([r.post[length].features() for r in rows],
                           [[(r.outcomes[f"MID{length}_WIDE"]["loss"] - r.outcomes[f"MID{length}_WIDE_KEEP"]["loss"]) / LOSS_SCALE] for r in rows])


def post_choice(evidence, model):
    if type(evidence) is not ValueEvidence or evidence.probe_steps not in LENGTHS:
        raise ValueError("post-measurement query required")
    predicted = float(model.predict(evidence.features())[0])
    action = "UPDATE" if evidence.fit_valid and predicted < 0 else "KEEP"
    return {"action": action, "update_minus_keep_loss_prediction": LOSS_SCALE * predicted,
            "evidence_digest": evidence.digest, "remaining_steps": evidence.remaining_steps}


def pre_choice(evidence, model):
    if type(evidence) is not ValueEvidence or evidence.probe_steps != 0:
        raise ValueError("pre-measurement query required")
    predicted = LOSS_SCALE * model.predict(evidence.features())
    if predicted.shape != (2,):
        raise ValueError("two registered acquisition values required")
    values = [0., *predicted.tolist()]
    index = min(range(3), key=lambda i: (values[i], i))
    action = ("CACHE_CONTINUE", "PROBE8_WIDE", "PROBE16_WIDE")[index]
    if index and evidence.remaining_steps < LENGTHS[index - 1] + 32:
        raise ValueError("insufficient acquisition/task budget")
    return {"action": action, "loss_difference_predictions": values, "evidence_digest": evidence.digest,
            "remaining_steps": evidence.remaining_steps}


def fit_policy(rows, excluded=()):
    """Inner predictions determine actual post-policy targets, not label minima."""
    rows = training(rows, excluded)
    if len({r.group for r in rows}) < 3:
        raise ValueError("nested cross-fitting needs three source groups")
    targets = np.zeros((len(rows), 2)); inner = []
    for group in sorted({r.group for r in rows}):
        train_rows = [r for r in rows if r.group != group]
        models = {n: post_model(train_rows, n, (*excluded, group)) for n in LENGTHS}
        decisions = []
        for index, row in enumerate(rows):
            if row.group != group:
                continue
            choices = {}
            for column, length in enumerate(LENGTHS):
                choice = post_choice(row.post[length], models[length])
                method = f"MID{length}_WIDE" + ("_KEEP" if choice["action"] == "KEEP" else "")
                targets[index, column] = (row.outcomes[method]["loss"] - row.outcomes["CACHE_CONTINUE"]["loss"]) / LOSS_SCALE
                choices[str(length)] = {**choice, "selected_method": method}
            decisions.append({"case_id": row.case_id, "choices": choices})
        inner.append({"excluded_group": group, "training_case_ids": [r.case_id for r in train_rows],
                      "models": {str(n): m.saved() for n, m in models.items()}, "decisions": decisions})
    pre = KernelModel.fit([r.pre.features() for r in rows], targets)
    post = {n: post_model(rows, n, excluded) for n in LENGTHS}
    direct_targets = [[(r.outcomes[f"MID{n}_WIDE"]["loss"] - r.outcomes["CACHE_CONTINUE"]["loss"]) / LOSS_SCALE for n in LENGTHS] for r in rows]
    direct = KernelModel.fit([r.pre.features() for r in rows], direct_targets)
    return {"pre": pre, "post": post, "direct": direct, "inner": inner,
            "training_case_ids": [r.case_id for r in rows]}

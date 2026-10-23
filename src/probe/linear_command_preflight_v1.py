"""Causal command comparisons for saved additive linear predictors, never a controller.

Every prediction is a model query, not an executed counterfactual or an assurance.
The four bounded XY offsets are fixed software/qualification queries only.
"""
from dataclasses import dataclass, asdict
import numbers
import numpy as np


TASKS = ("push-v3", "reach-v3", "door-open-v3")
FEATURES = ("H10", "F20", "F43")
DIRECTIONS = (("X_PLUS", (0.25, 0.)), ("X_MINUS", (-0.25, 0.)),
              ("Y_PLUS", (0., 0.25)), ("Y_MINUS", (0., -0.25)))
DIMENSIONS = {"H10": 10, "F20": 20, "F43": 43}
COMMAND_SLICES = {"H10": slice(6, 10), "F20": slice(9, 13), "F43": slice(39, 43)}


def require(value, message):
    if not value:
        raise ValueError(message)


def vector(values, size):
    require(isinstance(values, (tuple, list, np.ndarray)) and len(values) == size,
            "fixed numeric vector required")
    require(all(isinstance(v, numbers.Real) and not isinstance(v, (bool, np.bool_)) for v in values),
            "real numbers only")
    a = np.asarray(values, dtype=float)
    require(a.shape == (size,) and np.isfinite(a).all(), "finite vector required")
    return tuple(float(v) for v in a)


def command(values):
    result = vector(values, 4)
    require(max(map(abs, result)) <= 1., "bounded sent command required")
    return result


def fixed_candidates(baseline):
    baseline = command(baseline)
    result = []
    for name, delta in DIRECTIONS:
        xy = np.clip(np.asarray(baseline[:2]) + delta, -1., 1.)
        result.append(CommandCandidate(name, (*xy, *baseline[2:])))
    return tuple(result)


@dataclass(frozen=True)
class CommandCandidate:
    action_id: str
    command: tuple

    def __post_init__(self):
        require(type(self.action_id) is str and self.action_id in dict(DIRECTIONS), "registered query ID required")
        object.__setattr__(self, "command", command(self.command))

    @classmethod
    def from_dict(cls, value):
        require(type(value) is dict and set(value) == {"action_id", "command"}, "candidate fields rejected")
        return cls(**value)


@dataclass(frozen=True)
class CausalCommandQuery:
    task: str
    decision_step: int
    observation_steps: tuple
    observations: tuple
    baseline_command: tuple
    candidates: tuple

    def __post_init__(self):
        require(self.task in TASKS and type(self.decision_step) is int and 2 <= self.decision_step < 500,
                "matching task, real two-step history and budget required")
        require(isinstance(self.observation_steps, (tuple, list)) and isinstance(self.observations, (tuple, list, np.ndarray))
                and isinstance(self.candidates, (tuple, list)), "real history and candidate containers required")
        stamps = tuple(self.observation_steps)
        require(all(type(v) is int for v in stamps) and stamps == tuple(range(self.decision_step-2, self.decision_step+1)),
                "only the actual last three observations precede this command")
        require(len(self.observations) == 3, "do not fabricate missing history")
        observations = tuple(vector(v, 39) for v in self.observations)
        baseline = command(self.baseline_command)
        candidates = tuple(self.candidates)
        require(all(type(c) is CommandCandidate for c in candidates) and candidates == fixed_candidates(baseline),
                "consume all four fixed bounded XY queries in order; preserve Z and grip")
        object.__setattr__(self, "observation_steps", stamps)
        object.__setattr__(self, "observations", observations)
        object.__setattr__(self, "baseline_command", baseline)
        object.__setattr__(self, "candidates", candidates)

    @classmethod
    def from_dict(cls, value):
        keys = {"schema", "task", "decision_step", "observation_steps", "observations", "baseline_command", "candidates"}
        require(type(value) is dict and set(value) == keys and value["schema"] == "CAUSAL_COMMAND_QUERY_V1",
                "oracle/future/unknown query fields rejected")
        return cls(value["task"], value["decision_step"], value["observation_steps"], value["observations"],
                   value["baseline_command"], tuple(CommandCandidate.from_dict(c) for c in value["candidates"]))

    def to_dict(self):
        return {"schema": "CAUSAL_COMMAND_QUERY_V1", **asdict(self)}


def make_query(task, decision_step, observations, baseline):
    return CausalCommandQuery(task, decision_step, tuple(range(decision_step-2, decision_step+1)),
                              observations, baseline, fixed_candidates(baseline))


def feature_vector(query, feature, sent):
    require(type(query) is CausalCommandQuery and feature in FEATURES, "causal query and registered feature")
    sent = command(sent)
    a, b, current = np.asarray(query.observations)
    if feature == "F43":
        return np.r_[current, sent]
    displacement = np.r_[current[:3]-b[:3], b[:3]-a[:3]]
    if feature == "H10":
        return np.r_[displacement, sent]
    return np.r_[current[:3], displacement, sent, current[3],
                 current[4:7]-current[:3], current[-3:]-current[:3]]


@dataclass(frozen=True)
class LinearCommandModel:
    task: str
    feature: str
    mean: tuple
    scale: tuple
    coefficient: tuple

    def __post_init__(self):
        require(self.task in TASKS and self.feature in FEATURES, "registered saved linear model required")
        n = DIMENSIONS[self.feature]
        mean, scale = vector(self.mean, n), vector(self.scale, n)
        require(min(scale) > 0, "positive input scales required")
        require(len(self.coefficient) == n+1, "intercept plus all feature rows required")
        coefficient = tuple(vector(v, 2) for v in self.coefficient)
        object.__setattr__(self, "mean", mean)
        object.__setattr__(self, "scale", scale)
        object.__setattr__(self, "coefficient", coefficient)

    @classmethod
    def from_saved(cls, value):
        keys = {"schema", "task", "feature", "stats", "coefficient", "ridge", "weighted_design_rank", "parameter_count", "probability_guarantee"}
        require(type(value) is dict and set(value) == keys and value["schema"] == "TRAINING_CONTROL_LINEAR_V1",
                "only the versioned saved additive linear predictor is supported")
        stats = value["stats"]
        require(type(stats) is dict and set(stats) == {"feature", "loss", "input_mean", "input_scale", "target_mean", "target_scale", "training_trajectories", "training_responses"},
                "unknown saved-model statistics")
        require(value["feature"] in FEATURES and stats["feature"] == ("F20" if value["feature"] == "H10" else value["feature"])
                and stats["loss"] == "ISO" and value["ridge"] == .001 and value["probability_guarantee"] is False,
                "saved predictor semantics differ")
        require(value["parameter_count"] == 2*(DIMENSIONS[value["feature"]]+1), "parameter mapping differs")
        vector(stats["target_mean"], 2)
        require(min(vector(stats["target_scale"], 2)) > 0, "positive saved target scales")
        # Linear coefficients are already in physical metres: no target rescaling.
        return cls(value["task"], value["feature"], stats["input_mean"], stats["input_scale"], value["coefficient"])

    def predict(self, query, sent):
        require(type(query) is CausalCommandQuery and query.task == self.task, "matching causal task query")
        x = feature_vector(query, self.feature, sent)
        return np.r_[1., (x-self.mean)/self.scale] @ np.asarray(self.coefficient)

    def command_matrix(self):
        sl = COMMAND_SLICES[self.feature]
        return (np.asarray(self.coefficient)[1+sl.start:1+sl.stop] / np.asarray(self.scale)[sl, None]).T

    def compare(self, query):
        base = self.predict(query, query.baseline_command)
        matrix = self.command_matrix()
        output = []
        for c in query.candidates:
            prediction = self.predict(query, c.command)
            delta = matrix @ (np.asarray(c.command)-query.baseline_command)
            require(np.allclose(prediction-base, delta, rtol=1e-10, atol=1e-13), "command contrast identity failed")
            output.append({"action_id": c.action_id, "sent_command": c.command, "prediction_m": prediction.tolist(),
                           "predicted_difference_m": delta.tolist(), "same_as_baseline": c.command == query.baseline_command})
        return {"baseline_prediction_m": base.tolist(), "candidates": output, "state_independent_command_matrix_m": matrix.tolist(),
                "executed_counterfactuals": False, "physical_qualification": False, "probability_guarantee": False, "task_benefit": False}


def design_geometry(a, command_columns):
    """Unregularized weighted-design geometry; SVD projections do not fit outputs."""
    a = np.asarray(a, dtype=float)
    require(a.ndim == 2 and a.shape[0] > 0 and np.isfinite(a).all(), "finite nonempty weighted design")
    columns = tuple(command_columns)
    require(len(columns) in (2, 4) and len(set(columns)) == len(columns) and all(type(i) is int and 0 <= i < a.shape[1] for i in columns),
            "two XY or four distinct command columns")
    _, singular, right = np.linalg.svd(a, full_matrices=False)
    threshold = max(a.shape)*np.finfo(float).eps*singular[0]
    rank = int(np.sum(singular > threshold))
    nuisance = a[:, [i for i in range(a.shape[1]) if i not in columns]]
    left, ns, _ = np.linalg.svd(nuisance, full_matrices=False)
    nt = max(nuisance.shape)*np.finfo(float).eps*ns[0] if len(ns) else 0.
    nrank = int(np.sum(ns > nt))
    c = a[:, columns]
    residual = c-left[:, :nrank]@(left[:, :nrank].T@c)
    conditional = np.linalg.svd(residual, compute_uv=False)
    # Use the original design's absolute tolerance: cancellation is not excitation.
    conditional_rank = int(np.sum(conditional > threshold))
    return {"rows": len(a), "columns": a.shape[1], "rank": rank, "singular_values": singular,
            "rank_tolerance": threshold, "right_rows": right[:rank], "nuisance_rank": nrank,
            "conditional_command_singular_values": conditional, "conditional_command_rank": conditional_rank,
            "condition": None if rank < a.shape[1] else float(singular[0]/singular[-1])}


def query_geometry(geometry, difference):
    v = np.asarray(difference, dtype=float)
    require(v.shape == (geometry["columns"],) and np.isfinite(v).all(), "matching finite query difference")
    norm = float(np.linalg.norm(v))
    coordinates = geometry["right_rows"] @ v
    residual = float(np.linalg.norm(v-geometry["right_rows"].T@coordinates))
    singular = geometry["singular_values"][:geometry["rank"]]
    return {"zero_command_difference": norm == 0., "row_span_relative_residual": None if norm == 0. else residual/norm,
            "weighted_design_leverage": float(np.sum((coordinates/singular)**2)),
            "interpretation": "Numerical linear-design geometry only; neither conditional causal support nor physical validity nor confidence."}

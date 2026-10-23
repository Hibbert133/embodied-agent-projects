"""Causal, same-architecture feature/loss/history controls; no controller or selector."""
from dataclasses import asdict
import numpy as np

from src.probe.observable_history_model_v1 import HistoryTrajectory, inputs20, inputs43, targets, gru_cell

FEATURES = ("F20", "F43")
LOSSES = ("ISO", "AXIS")
WINDOWS = (1, 16)


def require(value, message):
    if not value:
        raise ValueError(message)


def feature_array(trajectory, feature):
    require(type(trajectory) is HistoryTrajectory and feature in FEATURES, "strict public trajectory and feature")
    return inputs20(trajectory) if feature == "F20" else inputs43(trajectory)[2:]


def training_data(trajectories, task):
    require(bool(trajectories) and all(type(t) is HistoryTrajectory and t.split == "TRAIN" and t.task == task for t in trajectories), "matching TRAIN only")
    require(len({t.trajectory_id for t in trajectories}) == len(trajectories), "duplicate trajectory")
    require(all(len(t.commands) >= 3 for t in trajectories), "real common targets required")


def statistics(trajectories, task, feature, loss):
    training_data(trajectories, task)
    require(feature in FEATURES and loss in LOSSES, "registered feature and loss")
    xs = [feature_array(t, feature) for t in trajectories]
    ys = [targets(t) for t in trajectories]
    xm = np.mean([x.mean(axis=0) for x in xs], axis=0)
    ym = np.mean([y.mean(axis=0) for y in ys], axis=0)
    xv = np.mean([np.mean((x-xm)**2, axis=0) for x in xs], axis=0)
    yv = np.mean([np.mean((y-ym)**2, axis=0) for y in ys], axis=0)
    xscl = np.where(np.sqrt(xv) > 1e-6, np.sqrt(xv), 1.)
    yscl = np.sqrt(yv) if loss == "AXIS" else np.repeat(np.sqrt(yv.mean()), 2)
    yscl = np.where(yscl > 1e-6, yscl, 1.)
    return {"feature": feature, "loss": loss, "input_mean": xm.tolist(), "input_scale": xscl.tolist(),
        "target_mean": ym.tolist(), "target_scale": yscl.tolist(), "training_trajectories": len(trajectories),
        "training_responses": sum(len(y) for y in ys)}


def frames(trajectory, stats):
    x = (feature_array(trajectory, stats["feature"]) - stats["input_mean"]) / stats["input_scale"]
    require(np.isfinite(x).all(), "nonfinite visible inputs")
    if stats["feature"] == "F20":
        x = np.pad(x, ((0, 0), (0, 23)))
    require(x.shape == (max(len(trajectory.commands)-2, 0), 43), "fixed 43-column network input")
    return x


def prepared(trajectory, stats, window):
    """Both feature families start at real t=2; padding is never consumed by GRU."""
    require(window in WINDOWS, "registered history")
    x = frames(trajectory, stats)
    n = len(x)
    array = np.zeros((n, window, 43), np.float32)
    lengths = np.minimum(np.arange(n)+1, window)
    for i in range(n):
        array[i, :lengths[i]] = x[max(0, i-window+1):i+1]
    y = (targets(trajectory)-stats["target_mean"]) / stats["target_scale"]
    return array, np.asarray(y, np.float32), lengths


def schedule(rng, trajectories, batch=32):
    chosen = rng.integers(0, len(trajectories), size=batch)
    positions = np.array([rng.integers(0, len(trajectories[i].commands)-2) for i in chosen])
    return chosen, positions


def minibatch(cache, chosen, positions):
    require(len(chosen) == len(positions) and len(chosen) > 0, "nonempty aligned batch")
    return (np.stack([cache[i][0][p] for i, p in zip(chosen, positions)]),
        np.stack([cache[i][1][p] for i, p in zip(chosen, positions)]),
        [int(cache[i][2][p]) for i, p in zip(chosen, positions)])


def fit_linear(trajectories, task, feature, ridge=.001):
    training_data(trajectories, task)
    require(feature in (*FEATURES, "H10") and ridge == .001, "frozen linear reference")
    stats = statistics(trajectories, task, "F20" if feature == "H10" else feature, "ISO")
    arrays = [feature_array(t, stats["feature"]) for t in trajectories]
    if feature == "H10":
        arrays = [a[:, 3:13] for a in arrays]
        stats["input_mean"] = stats["input_mean"][3:13]
        stats["input_scale"] = stats["input_scale"][3:13]
    x = np.concatenate([(a-stats["input_mean"])/stats["input_scale"] for a in arrays])
    a = np.column_stack((np.ones(len(x)), x))
    y = np.concatenate([targets(t) for t in trajectories])
    weights = np.concatenate([np.repeat(1/len(targets(t)), len(targets(t))) for t in trajectories])
    penalty = ridge*np.eye(a.shape[1]); penalty[0, 0] = 0
    coefficient = np.linalg.solve(a.T@(weights[:, None]*a)+penalty, a.T@(weights[:, None]*y))
    require(np.isfinite(coefficient).all(), "finite reference coefficients")
    return {"schema": "TRAINING_CONTROL_LINEAR_V1", "task": task, "feature": feature, "stats": stats,
        "coefficient": coefficient.tolist(), "ridge": ridge, "weighted_design_rank": int(np.linalg.matrix_rank(a*np.sqrt(weights[:, None]))),
        "parameter_count": coefficient.size, "probability_guarantee": False}


def predict(model, trajectory):
    require(type(trajectory) is HistoryTrajectory and trajectory.task == model["task"], "matching public trajectory")
    stats = model["stats"]
    if model["schema"] == "TRAINING_CONTROL_LINEAR_V1":
        x = feature_array(trajectory, "F20" if model["feature"] == "H10" else model["feature"])
        if model["feature"] == "H10":
            x = x[:, 3:13]
        a = np.column_stack((np.ones(len(x)), (x-stats["input_mean"])/stats["input_scale"]))
        out = a@np.asarray(model["coefficient"])
    else:
        require(model["schema"] == "TRAINING_CONTROL_GRU_V1" and model["window"] in WINDOWS, "versioned response model")
        x = frames(trajectory, stats)
        n = len(x)
        h = np.zeros((n, 32))
        starts = np.maximum(0, np.arange(n)-model["window"]+1)
        lengths = np.minimum(np.arange(n)+1, model["window"])
        for k in range(model["window"]):
            active = k < lengths
            if np.any(active):
                h[active] = gru_cell(x[starts[active]+k], h[active], model["gru"])
        out = (h@np.asarray(model["output_weight"]).T+model["output_bias"])*stats["target_scale"]+stats["target_mean"]
    require(out.shape == targets(trajectory).shape and np.isfinite(out).all(), "finite causal common-target prediction")
    return out


def public_dict(trajectory):
    require(type(trajectory) is HistoryTrajectory, "strict public trajectory")
    return asdict(trajectory)

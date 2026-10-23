"""Training-only helpers and evaluator-only parameter qualification statistics."""
import numpy as np
from src.probe.cold_start_response import ColdPrefix, NominalTrajectory, fit_response, TASKS, MODELS
from src.probe.forward_prediction import ForwardHistory, features, RIDGE
from src.probe.continuous import ContinuousTransition
from src.probe.operator_identification import OperatorSample, infer_operator


def visible_prefix(record):
    return ColdPrefix(record["task"], record["initial"]["observation"],
                      [r["command"] for r in record["trace"]],
                      [r["after"]["observation"] for r in record["trace"]], True)


def old_samples(prefix):
    history = ForwardHistory(prefix.initial_observation); samples = []
    for i, (sent, observation) in enumerate(zip(prefix.commands, prefix.observations), 1):
        query = history.request(sent)
        target = history.observe(ContinuousTransition(sent, history.current, observation))
        if query is not None: samples.append(OperatorSample(i, query, target))
    return samples


def fit_training(records):
    if len(records) != 384 or any(r["split"] != "TRAIN" or len(r["trace"]) != 8 for r in records):
        raise ValueError("complete 384-trajectory TRAIN source required")
    result = {"joint": {}, "same_data_arx": {}, "training_cases": [r["case_id"] for r in records]}
    for task in TASKS:
        samples = [NominalTrajectory(visible_prefix(r)) for r in records if r["task"] == task]
        result["joint"][task] = fit_response(samples, task)
        flat = [sample for record in records if record["task"] == task for sample in old_samples(visible_prefix(record))]
        inputs = np.array([features(s.query, "LINEAR_ARX") for s in flat]); y = np.array([s.displacement for s in flat])
        mean, scale = inputs.mean(axis=0), inputs.std(axis=0); scale = np.where(scale > 1e-6, scale, 1.)
        z = np.c_[np.ones(len(inputs)), (inputs-mean)/scale]
        penalty = RIDGE*np.eye(11); penalty[0, 0] = 0
        coefficient = np.linalg.solve(z.T @ z+penalty, z.T @ y)
        result["same_data_arx"][task] = {"method": "LINEAR_ARX", "training_samples": len(inputs), "mean": mean.tolist(),
            "scale": scale.tolist(), "coefficients": coefficient.tolist(), "ridge": RIDGE, "feature_count": 11,
            "training_rmse": float(np.sqrt(np.mean((z @ coefficient-y)**2))),
            "physical_response_qualified": False, "probability_guarantee": False}
    return result


def estimates(models, old, prefix):
    from src.probe.cold_start_response import infer_operator as infer_joint
    if len(prefix.commands) < 8:
        return {name: {"valid": False, "reason": "INCOMPLETE_EIGHT_STEP_PREFIX"} for name in MODELS}
    samples = tuple(old_samples(prefix))
    return {"JOINT_FULL8": infer_joint(models["joint"][prefix.task], prefix),
            "JOINT_DROP2": infer_joint(models["joint"][prefix.task], prefix, True),
            "SAME_DATA_ARX8": infer_operator(models["same_data_arx"][prefix.task], samples),
            "OLD_ARX8": infer_operator(old[prefix.task], samples)}


def statistics(rows, c):
    if len(rows) != 96 or {(r["stream"], r["task"], r["replicate"]) for r in rows} != {(s, t, f) for s in range(16) for t in TASKS for f in range(2)}:
        raise ValueError("all 96 qualification cases required")
    cells = {}
    for name in MODELS:
        values = []
        for record in rows:
            fit = record["estimates"][name]; truth = record["operator_oracle"]
            a = float(np.linalg.norm(np.asarray(fit["matrix_xy"])-truth["matrix_xy"])) if fit["valid"] else 8.
            b = float(np.linalg.norm(np.asarray(fit["bias_xy"])-truth["bias_xy"])) if fit["valid"] else 1.
            values.append({"stream": record["stream"], "task": record["task"], "replicate": record["replicate"],
                           "valid": fit["valid"], "matrix_error": a, "bias_error": b, "score": a+b/.4})
        cells[name] = {"cases": 96, "valid": sum(r["valid"] for r in values), "mean_matrix_error": float(np.mean([r["matrix_error"] for r in values])),
                       "mean_bias_error": float(np.mean([r["bias_error"] for r in values])), "mean_score": float(np.mean([r["score"] for r in values])),
                       "details": values}
    rng = np.random.default_rng(20261016); draws = rng.integers(0, 16, (10000, 16)); contrasts = []
    for base in ("SAME_DATA_ARX8", "JOINT_DROP2", "OLD_ARX8"):
        differences = [a["score"]-b["score"] for a, b in zip(cells["JOINT_FULL8"]["details"], cells[base]["details"])]
        streams = np.array([np.mean([value for value, row in zip(differences, rows) if row["stream"] == s]) for s in range(16)])
        interval = np.quantile(streams[draws].mean(axis=1), [.025, .975])
        contrasts.append({"method": "JOINT_FULL8", "reference": base, "mean_score_difference": float(streams.mean()),
                          "paired_stream_percentile_95": interval.tolist(), "stream_values": streams.tolist(),
                          "role": "PRIMARY" if base == "SAME_DATA_ARX8" else "SECONDARY_UNADJUSTED"})
    gate = {"valid_fraction": cells["JOINT_FULL8"]["valid"]/96 >= .95,
            "primary_upper_below_zero": contrasts[0]["paired_stream_percentile_95"][1] < 0,
            "full_better_than_drop_two_mean": contrasts[1]["mean_score_difference"] < 0}
    return {"models": cells, "contrasts": contrasts, "qualification": {"requirements": gate, "passed": all(gate.values())},
            "task_performance_established": False, "probability_qualification": False, "algorithm_novelty_established": False}

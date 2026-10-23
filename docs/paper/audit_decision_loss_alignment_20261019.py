"""Exact finite counterexamples for prediction metrics versus decision value.

No experiment inputs, simulator, model fitting, API calls or random numbers.
These are standard decision-theoretic identities, not a new robot method.
"""
import argparse
from fractions import Fraction as F
import hashlib
from itertools import product
import json
from pathlib import Path
from time import perf_counter_ns

ROOT = Path(__file__).resolve().parents[2]
ALLOWED = ROOT / "outputs/reproduction_reviews/decision_loss_alignment_v1"
ACTIONS = ("CURRENT", "ALTERNATIVE", "AUXILIARY")
ATOMS = (
    {"context": "A", "probability": F(9, 20), "losses": (F(100), F(99), F(100))},
    {"context": "A", "probability": F(1, 20), "losses": (F(100), F(200), F(200))},
    {"context": "B", "probability": F(1, 2), "losses": (F(100), F(96), F(100))},
)


def conditional(values):
    return {x: [sum(a["probability"] * v[j] for a, v in zip(ATOMS, values) if a["context"] == x)
            / sum(a["probability"] for a in ATOMS if a["context"] == x)
            for j in range(len(values[0]))] for x in ("A", "B")}


def policy_value(policy):
    return sum(a["probability"] * a["losses"][policy[a["context"]]] for a in ATOMS)


def evaluate(prediction, optimal_value):
    policy = {x: int(prediction[x] < 0) for x in ("A", "B")}
    error = sum(a["probability"] * abs((a["losses"][1] - a["losses"][0]) - prediction[a["context"]]) for a in ATOMS)
    winner_accuracy = sum(a["probability"] * (policy[a["context"]] == int(a["losses"][1] < a["losses"][0])) for a in ATOMS)
    binary_oracle = sum(a["probability"] * min(a["losses"][:2]) for a in ATOMS)
    weighted_mistakes = sum(a["probability"] * abs(a["losses"][1] - a["losses"][0])
        * (policy[a["context"]] != int(a["losses"][1] < a["losses"][0])) for a in ATOMS)
    value = policy_value(policy)
    assert value == binary_oracle + weighted_mistakes
    return {"predicted_difference": prediction, "selected_action": {x: ACTIONS[i] for x, i in policy.items()},
        "paired_difference_mae": error, "expected_task_loss": value, "observed_winner_accuracy": winner_accuracy,
        "excess_over_context_optimal": value - optimal_value,
        "future_clairvoyant_minimum": binary_oracle, "weighted_mistake_cost": weighted_mistakes}


def encode(value):
    if isinstance(value, F):
        return {"numerator": value.numerator, "denominator": value.denominator, "decimal": float(value)}
    if isinstance(value, dict): return {k: encode(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)): return [encode(v) for v in value]
    return value


def calculate():
    assert sum(a["probability"] for a in ATOMS) == 1
    mean_cost = conditional([a["losses"] for a in ATOMS])
    optimal_policy = {x: min(range(3), key=lambda i: (mean_cost[x][i], i)) for x in mean_cost}
    optimal_value = policy_value(optimal_policy)
    assert optimal_value == F(98)
    predictions = {"ZERO": {"A": F(0), "B": F(0)}, "CONDITIONAL_MEDIAN": {"A": F(-1), "B": F(-4)},
        "CONDITIONAL_MEAN": {x: mean_cost[x][1] - mean_cost[x][0] for x in mean_cost}}
    results = {name: evaluate(p, optimal_value) for name, p in predictions.items()}
    zero, median, mean = [results[k] for k in predictions]
    assert median["paired_difference_mae"] < zero["paired_difference_mae"] < mean["paired_difference_mae"]
    assert mean["expected_task_loss"] < zero["expected_task_loss"] < median["expected_task_loss"]
    assert median["observed_winner_accuracy"] > mean["observed_winner_accuracy"]
    assert [r["paired_difference_mae"] for r in (zero, median, mean)] == [F(149, 20), F(101, 20), F(909, 100)]
    assert [r["expected_task_loss"] for r in (zero, median, mean)] == [F(100), F(2051, 20), F(98)]

    weights = [tuple(max(a["losses"]) - v for v in a["losses"]) for a in ATOMS]
    expected_weights = conditional(weights)
    normalized = [tuple(v / sum(row) for v in row) for row in weights]
    expected_normalized = conditional(normalized)
    weighted_policy = {x: max(range(3), key=lambda i: (expected_weights[x][i], -i)) for x in mean_cost}
    normalized_policy = {x: max(range(3), key=lambda i: (expected_normalized[x][i], -i)) for x in mean_cost}
    assert weighted_policy == optimal_policy
    assert normalized_policy != optimal_policy
    assert policy_value(normalized_policy) == median["expected_task_loss"]
    for x in mean_cost:
        for i, j in product(range(3), repeat=2):
            assert expected_weights[x][i] - expected_weights[x][j] == mean_cost[x][j] - mean_cost[x][i]

    identities = 0
    for current, alternative, action in product(range(6), range(6), range(2)):
        delta = alternative - current
        selected = (current, alternative)[action]
        assert selected == min(current, alternative) + abs(delta) * (action != int(delta < 0))
        identities += 1
    all_policies = [{"A": a, "B": b} for a, b in product(range(3), repeat=2)]
    assert min(policy_value(p) for p in all_policies) == optimal_value
    return {"status": "PASSED", "atoms": ATOMS, "conditional_mean_costs": mean_cost,
        "context_optimal_actions": {x: ACTIONS[i] for x, i in optimal_policy.items()}, "context_optimal_value": optimal_value,
        "predictors": results, "multiclass_unnormalized_weights": weights,
        "conditional_expected_weights": expected_weights, "conditional_expected_normalized_weights": expected_normalized,
        "weighted_policy_value": policy_value(weighted_policy), "per_row_normalized_policy_value": policy_value(normalized_policy),
        "binary_identity_checks": identities, "enumerated_context_policies": len(all_policies),
        "new_environment_steps": 0, "new_resets": 0, "new_api_calls": 0, "model_fits": 0, "random_draws": 0,
        "scope": "Constructed exact finite distributions, no current or historical robot outcomes read; not algorithm novelty or empirical utility."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    target = parser.parse_args().receipt.resolve()
    if not target.is_relative_to(ALLOWED) or target == ALLOWED or target.exists():
        raise ValueError("fresh receipt in the dedicated mathematical review folder required")
    started = perf_counter_ns();result = encode(calculate())
    result.update(source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), wall_ns=perf_counter_ns() - started)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False);handle.write("\n")
    print(json.dumps({"status": result["status"], "binary_identity_checks": result["binary_identity_checks"],
        "new_environment_steps": 0, "wall_ns": result["wall_ns"]}))


if __name__ == "__main__": main()

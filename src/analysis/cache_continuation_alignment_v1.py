"""Evaluation-only alignment under the declared frozen-source reset contract.

Recorded witnesses are not complete hidden-state certificates. Realized paired
labels are restricted to actually reused states, never conditional expectations.
"""
from collections import Counter
from copy import deepcopy
import pickle
import random
import numpy as np
from src.probe.cache_acquisition_evidence_v1 import CacheAcquisitionEvidenceV1, canonical, digest
from src.probe.chronological_cache_reference import BLOCK8, VerifiedPoint
from src.probe.cold_start_response import ColdPrefix
from src.probe.operator_identification import affine_controller
from src.rollout.task_registry import create_task_policy

METHODS = ("CUSUM4", "PLUGIN4", "UNCERTAINTY4", "TASK_IVR4")
PHYSICAL_FIELDS = ("host_calls", "phase", "command", "raw_policy", "before", "after", "noise_before_hash",
                   "noise_after_hash", "target_xy", "executed_action_oracle", "simulation_time_before_oracle",
                   "simulation_time_after_oracle")
WITNESS_FIELDS = {"state_spec", "integration", "body_pos", "site_pos", "task_fields", "complete_hidden_state_qualification"}
SOURCE_IDENTITY = ("experiment_run_id", "manifest_id", "source_git_commit", "phase", "stream", "episode", "task", "seed")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def equal(a, b, message):
    require(canonical(a) == canonical(b), message)


def ended(observation):
    return any(observation[k] for k in ("success", "terminated", "truncated"))


def physical(row):
    return {name: row[name] for name in PHYSICAL_FIELDS}


def outcome(record):
    trace = record["trace"]
    require([r["host_calls"] for r in trace] == list(range(1, len(trace) + 1)), "noncontinuous physical step index")
    final = trace[-1]["after"] if trace else record["initial"]
    saved = record["outcome"]
    require(type(saved["success"]) is bool and saved["success"] == final["success"], "outcome not from final actual observation")
    require(saved["total_steps"] == len(trace) <= 500 and saved["environment_resets"] == 1 and saved["noise_rows_consumed"] == len(trace), "physical budget/reset/noise mismatch")
    require(saved["deadline_loss"] == (len(trace) if final["success"] else 500), "stopped or failed deadline loss changed")
    require(saved["stopped"] == (record["decisions"][-1]["controller"] is None and not ended(final)), "operational stop recoded")
    return saved


def reference_contract(record):
    require(record["method"] == "ALWAYS8", "fresh reference must be ALWAYS8")
    first = record["decisions"][0]
    require(first["action"] == "PROBE8" and first["at_host_calls"] == 0 and first["controller"] is None, "reference used history-dependent initial control")
    equal(first["program"], list(map(list, BLOCK8)), "reference probe declaration differs")
    result = outcome(record)
    length = min(8, len(record["trace"]))
    require(result["fixed_probe_steps"] == length, "reference physical prefix count differs")
    for row, command in zip(record["trace"][:length], BLOCK8):
        require(row["phase"] == "FIXED_PROBE", "reference prefix is not fixed probe")
        equal(row["command"], np.asarray(command, np.float32).astype(float).tolist(), "reference sent probe differs")
    if len(record["trace"]) >= 8 and not ended(record["trace"][7]["after"]):
        fits = [d for d in record["decisions"] if d["at_host_calls"] == 8]
        require(len(fits) == 1 and fits[0]["action"] in ("RUN_POINT", "STOP_POINT_FIT"), "reference continuation is not current-prefix fit")
        fit, decision = record["fit"], fits[0]
        require(fit is not None and fit["model"] == "JOINT_FULL8", "wrong reference estimator")
        equal(fit, decision["fit"], "reference ignored saved fit")
        require(decision["action"] == ("RUN_POINT" if fit["valid"] else "STOP_POINT_FIT"), "reference substituted invalid fit")
        if fit["valid"]:
            equal(decision["controller"], affine_controller(fit["matrix_xy"], fit["bias_xy"]), "reference controller depends on old cache")
        else:
            require(decision["controller"] is None, "invalid fresh fit executed a substitute")
        require(all(r["phase"] == "POLICY" and r["decision_sequence"] == decision["sequence"] for r in record["trace"][8:]), "reference future used another decision")
    else:
        require(ended(record["trace"][-1]["after"]) and record["fit"] is None, "incomplete reference without actual early ending")
    return result


def align_prefix(record, reference):
    for name in SOURCE_IDENTITY:
        equal(record[name], reference[name], "reference belongs to another actual unit")
    for name in ("initial", "initial_physics_witness_oracle", "initial_noise_hash", "noise_commitment_oracle", "clock_contract"):
        equal(record[name], reference[name], "initial state, noise or clock mismatch: " + name)
    require(len(record["trace"]) >= 4 and len(reference["trace"]) >= 4, "incomplete four-step prefix")
    for a, b in zip(record["trace"][:4], reference["trace"][:4]):
        equal(physical(a), physical(b), "recorded physical prefix differs")
    a = record["boundary_physics_witness_oracle"]["4"]
    b = reference["boundary_physics_witness_oracle"]["4"]
    require(set(a) == WITNESS_FIELDS and set(b) == WITNESS_FIELDS, "declared physical witness schema changed")
    equal(a, b, "recorded cutoff physical witness differs")
    require(a["complete_hidden_state_qualification"] is False, "source witness qualification changed")
    return a["complete_hidden_state_qualification"]


def visible_evidence(record, decision, past):
    saved = record["state_before"]["cache"]
    cache = VerifiedPoint.from_dict(saved)
    require(cache.belief is not None and cache.source_episode < record["episode"], "earlier accepted joint source required")
    origin = past[(record["method"], cache.source_episode)]
    require(origin["success"] and origin["new_fit"] and origin["task"] == cache.source_task, "source was not own actual successful new fit")
    equal(origin["cache"], saved, "source changed or was renewed without new evidence")
    require(decision["noise_hash"] == record["trace"][3]["noise_after_hash"], "cutoff decision used another noise time")
    prefix = ColdPrefix(record["task"], record["initial"]["observation"],
                        tuple(tuple(r["command"]) for r in record["trace"][:4]),
                        tuple(tuple(r["after"]["observation"]) for r in record["trace"][:4]), True)
    result = CacheAcquisitionEvidenceV1(prefix, cache.parameters, cache.belief.covariance, cache.source_task,
        record["episode"] - cache.source_episode, cache.belief.active_parameter_bound, decision["raw_policy_for_check"], 496)
    if decision["action"] == "RUN_CACHED":
        equal(decision["controller"], cache.controller, "actual reuse used a different cache controller")
        require(record["fit"] is None and record["outcome"]["online_parameter_fits"] == 0, "reuse replaced by an unobserved update")
    return result


def query_purity(task, observation, expected):
    """Actual source policy queries only, without constructing any environment."""
    policy = create_task_policy(task)
    before = pickle.dumps((policy.__dict__, random.getstate(), np.random.get_state()), protocol=5)
    first = np.asarray(policy.get_action(np.array(observation, dtype=float, copy=True)), np.float32).tolist()
    second = np.asarray(policy.get_action(np.array(observation, dtype=float, copy=True)), np.float32).tolist()
    after = pickle.dumps((policy.__dict__, random.getstate(), np.random.get_state()), protocol=5)
    equal(first, expected, "source cutoff policy query differs")
    equal(first, second, "repeated source policy query changes output")
    require(before == after, "source policy query has persistent state or consumes random state")
    return 2


def process_unit(records, past, check_policy=True):
    index = {r["method"]: r for r in records}
    require(len(index) == len(records) and "ALWAYS8" in index, "duplicate method or missing reference")
    reference = index["ALWAYS8"]
    fresh_outcome = reference_contract(reference)
    rows, pairs, controls, packets = [], [], [], {}
    policy_calls = 0
    for record in records:
        row = {"stream": record["stream"], "episode": record["episode"], "task": record["task"], "method": record["method"],
               "status": None, "decision_id": None, "public_evidence_sha256": None, "complete_hidden_state_qualified": False}
        first = record["decisions"][0]
        if record["method"] not in METHODS:
            row["status"] = "EXCLUDED_BALANCED_PROGRAM" if record["method"] == "BALANCED4" and first["action"] == "CHECK4" else "EXCLUDED_METHOD"
        elif first["action"] != "CHECK4":
            require(first["action"] == "PROBE8" and record["state_before"]["cache"] is None, "unexpected initial route in target family")
            row["status"] = "EXCLUDED_NO_WARM_CHECK"
        elif len(record["trace"]) < 4 or ended(record["trace"][3]["after"]):
            row["status"] = "EXCLUDED_ENDED_BY_CUTOFF"
        else:
            equal(first["program"], list(map(list, BLOCK8[:4])), "warm initial check program changed")
            require(first["at_host_calls"] == 0 and first["controller"] is None, "check executed a history-dependent prefix")
            decision = [d for d in record["decisions"] if d["at_host_calls"] == 4]
            require(len(decision) == 1, "missing or repeated cutoff decision")
            decision = decision[0]
            qualified = align_prefix(record, reference)
            if decision["action"] not in ("RUN_CACHED", "REFRESH8"):
                require(decision["action"].startswith("STOP_"), "unregistered cutoff choice")
                row["status"] = "EXCLUDED_CHECK_STOP"
            else:
                packet = visible_evidence(record, decision, past)
                public = packet.to_dict()
                require(CacheAcquisitionEvidenceV1.from_dict(public).to_dict() == public, "visible packet roundtrip changed")
                if check_policy:
                    policy_calls += query_purity(record["task"], record["trace"][3]["after"]["observation"], list(packet.current_policy_command))
                key = digest({"unit": [record["stream"], record["episode"]], "public_evidence_sha256": packet.evidence_sha256})
                row.update(decision_id=key, public_evidence_sha256=packet.evidence_sha256, complete_hidden_state_qualified=qualified)
                packets[key] = public
                own = outcome(record)
                if decision["action"] == "RUN_CACHED":
                    row["status"] = "CONDITIONAL_REALIZED_REUSE_PAIR"
                    pairs.append({**row, "source_age": packet.source_age, "source_task": packet.source_task,
                        "reuse_success": own["success"], "fresh_success": fresh_outcome["success"],
                        "reuse_deadline_loss": own["deadline_loss"], "fresh_deadline_loss": fresh_outcome["deadline_loss"],
                        "realized_loss_difference_under_source_contract": own["deadline_loss"] - fresh_outcome["deadline_loss"],
                        "realized_success_difference": int(own["success"]) - int(fresh_outcome["success"]),
                        "reuse_actual_steps": own["total_steps"], "fresh_actual_steps": fresh_outcome["total_steps"],
                        "source_episode_oracle": record["state_before"]["cache"]["source_episode"]})
                else:
                    equal(decision["program"], list(map(list, BLOCK8[4:])), "refresh does not complete frozen block eight")
                    require(decision["controller"] is None, "refresh used an old controller")
                    require(len(record["trace"]) == len(reference["trace"]), "actual fresh continuations have different lengths")
                    for a, b in zip(record["trace"][4:], reference["trace"][4:]):
                        equal(physical(a), physical(b), "actual fresh continuation differs")
                    equal(record["fit"], reference["fit"], "actual fresh fits differ")
                    equal(own, fresh_outcome, "actual fresh outcomes or physical fees differ")
                    row["status"] = "FACTUAL_REFRESH_NEGATIVE_CONTROL"
                    controls.append({**row, "actual_steps": own["total_steps"], "actual_loss_difference": 0,
                                     "continuation_physical_steps_checked": max(0, len(record["trace"]) - 4)})
        rows.append(row)
    # Deduplicate only within this actual unit, never across hidden worlds/futures.
    unique = {}
    for pair in pairs:
        key = pair["decision_id"]
        if key in unique:
            other = unique[key]
            for field in ("reuse_success", "fresh_success", "reuse_deadline_loss", "fresh_deadline_loss", "reuse_actual_steps", "fresh_actual_steps"):
                equal(pair[field], other[field], "same-unit identical evidence has inconsistent realized outcome")
            a, b = index[pair["method"]], index[other["method"]]
            require(len(a["trace"]) == len(b["trace"]), "identical reused controller has different actual length")
            for x, y in zip(a["trace"][4:], b["trace"][4:]):
                equal(physical(x), physical(y), "same-unit duplicate reuse physical continuation differs")
            other["behavior_methods"].append(pair["method"])
        else:
            unique[key] = {**pair, "behavior_methods": [pair["method"]]}
    for record in records:
        cache = record["state_after"]["cache"]
        past[record["method"], record["episode"]] = {"task": record["task"], "success": record["outcome"]["success"],
            "new_fit": record["fit"] is not None and record["fit"]["valid"], "cache": deepcopy(cache)}
    return {"dispositions": rows, "reuse_pairs": pairs, "unique_reuse_pairs": list(unique.values()),
            "refresh_controls": controls, "evidence": packets, "policy_queries": policy_calls}


def describe(dispositions, pairs, unique, controls, policy_queries):
    def count(part):
        values = [r["realized_loss_difference_under_source_contract"] for r in part]
        return {"cases": len(part), "fresh_lower_realized_loss": sum(x > 0 for x in values),
                "reuse_lower_realized_loss": sum(x < 0 for x in values), "equal_realized_loss": sum(x == 0 for x in values),
                "mean_realized_reuse_minus_fresh_loss": sum(values) / len(values) if values else None,
                "sum_realized_loss_difference": sum(values),
                "lost_success_with_reuse": sum(r["realized_success_difference"] < 0 for r in part),
                "rescued_success_with_reuse": sum(r["realized_success_difference"] > 0 for r in part)}
    return {"source_case_dispositions": len(dispositions), "disposition_counts": dict(Counter(r["status"] for r in dispositions)),
            "behavior_reuse_sites": len(pairs), "unique_same_unit_decisions": len(unique),
            "duplicate_reuse_sites": len(pairs) - len(unique), "by_behavior": {m: count([r for r in pairs if r["method"] == m]) for m in METHODS},
            "unique_decisions": count(unique), "factual_refresh_controls": len(controls),
            "factual_refresh_control_loss_difference_max_abs": max((abs(r["actual_loss_difference"]) for r in controls), default=0),
            "factual_refresh_continuation_steps_checked": sum(r["continuation_physical_steps_checked"] for r in controls),
            "source_policy_queries": policy_queries, "complete_hidden_state_qualified": all(r["complete_hidden_state_qualified"] for r in pairs + controls) and bool(pairs),
            "conditional_expectation_identified": False, "unconditional_causal_transport_qualified": False,
            "whole_stream_counterfactual_identified": False, "new_algorithm_established": False,
            "scope": "CONDITIONAL_EXISTING_TRACE_ALIGNMENT_AND_REALIZED_CURRENT_TASK_DESCRIPTION"}

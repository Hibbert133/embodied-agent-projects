"""Independent raw-row reconstruction; does not call extraction/statistics code."""
import argparse
from collections import Counter
from copy import deepcopy
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import run_cache_continuation_alignment_v1 as io
from src.probe.cache_acquisition_evidence_v1 import CacheAcquisitionEvidenceV1, canonical, digest

BEHAVIORS = ("CUSUM4", "PLUGIN4", "UNCERTAINTY4", "TASK_IVR4")
PHYSICAL = ("host_calls", "phase", "command", "raw_policy", "before", "after", "noise_before_hash",
            "noise_after_hash", "target_xy", "executed_action_oracle", "simulation_time_before_oracle", "simulation_time_after_oracle")
PROGRAM = np.array([[.4, 0., 0., 0.], [.4, 0., 0., 0.], [-.4, 0., 0., 0.], [-.4, 0., 0., 0.],
                    [0., .4, 0., 0.], [0., .4, 0., 0.], [0., -.4, 0., 0.], [0., -.4, 0., 0.]], np.float32).astype(float).tolist()


def same(left, right):
    if canonical(left) != canonical(right):
        raise ValueError("independent reconstruction differs")


def ensure(condition, message):
    if not condition:
        raise ValueError(message)


def done(observation):
    return observation["success"] or observation["terminated"] or observation["truncated"]


def controller(parameters):
    theta = np.array(parameters).reshape(2, 3)
    inverse = np.linalg.solve(theta[:, :2], np.eye(2))
    return {"source": "ESTIMATED_AFFINE", "matrix_xy": inverse.tolist(), "offset": [*(-inverse@theta[:, 2]).tolist(), 0., 0.]}


def same_controller(actual, expected):
    same(sorted(actual), sorted(expected))
    same(actual["source"], expected["source"])
    ensure(all(np.allclose(actual[k], expected[k], rtol=0, atol=1e-12) for k in ("matrix_xy", "offset")), "independent inverse differs")


def metrics(record):
    trace = record["trace"]
    last = trace[-1]["after"] if trace else record["initial"]
    result = record["outcome"]
    ensure([r["host_calls"] for r in trace] == list(range(1, len(trace)+1)), "source physical clock differs")
    ensure(result["success"] == last["success"] and result["total_steps"] == len(trace) <= 500, "source outcome differs")
    ensure(result["deadline_loss"] == (len(trace) if last["success"] else 500), "failed/stopped source loss changed")
    ensure(result["environment_resets"] == 1 and result["noise_rows_consumed"] == len(trace), "source physical fee differs")
    ensure(result["stopped"] == (record["decisions"][-1]["controller"] is None and not done(last)), "source stop changed")
    return result


def reconstruct(records, past):
    fresh = next(r for r in records if r["method"] == "ALWAYS8")
    fresh_result = metrics(fresh)
    first = fresh["decisions"][0]
    ensure(first["action"] == "PROBE8" and first["at_host_calls"] == 0 and first["controller"] is None, "nonfixed fresh reference")
    same(first["program"], PROGRAM)
    for index, row in enumerate(fresh["trace"][:8]):
        same(row["command"], np.array(PROGRAM[index], np.float32).astype(float).tolist())
        ensure(row["phase"] == "FIXED_PROBE", "fresh prefix not open loop")
    if len(fresh["trace"]) >= 8 and not done(fresh["trace"][7]["after"]):
        decisions = [d for d in fresh["decisions"] if d["at_host_calls"] == 8]
        ensure(len(decisions) == 1, "fresh fit missing or repeated")
        choice = decisions[0]
        fit = fresh["fit"]
        ensure(fit["model"] == "JOINT_FULL8", "wrong fresh model")
        same(choice["fit"], fit)
        ensure(choice["action"] == ("RUN_POINT" if fit["valid"] else "STOP_POINT_FIT"), "fresh invalidity hidden")
        if fit["valid"]:
            point = np.column_stack((fit["matrix_xy"], fit["bias_xy"])).ravel()
            same_controller(choice["controller"], controller(point))
        else:
            ensure(choice["controller"] is None, "fresh invalid fit executed")
        ensure(all(r["phase"] == "POLICY" and r["decision_sequence"] == choice["sequence"] for r in fresh["trace"][8:]), "fresh used another tail decision")
    else:
        ensure(done(fresh["trace"][-1]["after"]) and fresh["fit"] is None, "fresh prefix incomplete")
    dispositions, pairs, controls, packets = [], [], [], {}
    indexed = {r["method"]: r for r in records}
    for record in records:
        row = {"stream": record["stream"], "episode": record["episode"], "task": record["task"], "method": record["method"],
               "status": None, "decision_id": None, "public_evidence_sha256": None, "complete_hidden_state_qualified": False}
        initial = record["decisions"][0]
        if record["method"] not in BEHAVIORS:
            row["status"] = "EXCLUDED_BALANCED_PROGRAM" if record["method"] == "BALANCED4" and initial["action"] == "CHECK4" else "EXCLUDED_METHOD"
        elif initial["action"] == "PROBE8":
            ensure(record["state_before"]["cache"] is None, "cold source had a cache")
            row["status"] = "EXCLUDED_NO_WARM_CHECK"
        else:
            ensure(initial["action"] == "CHECK4", "unexpected warm route")
            if len(record["trace"]) < 4 or done(record["trace"][3]["after"]):
                row["status"] = "EXCLUDED_ENDED_BY_CUTOFF"
            else:
                same(initial["program"], PROGRAM[:4])
                ensure(initial["controller"] is None and initial["at_host_calls"] == 0, "warm prefix used old correction")
                for name in ("experiment_run_id", "manifest_id", "source_git_commit", "phase", "stream", "episode", "task", "seed",
                             "initial", "initial_physics_witness_oracle", "initial_noise_hash", "noise_commitment_oracle", "clock_contract"):
                    same(record[name], fresh[name])
                for left, right in zip(record["trace"][:4], fresh["trace"][:4]):
                    same({k: left[k] for k in PHYSICAL}, {k: right[k] for k in PHYSICAL})
                witness = record["boundary_physics_witness_oracle"]["4"]
                same(witness, fresh["boundary_physics_witness_oracle"]["4"])
                ensure(witness["complete_hidden_state_qualification"] is False, "incomplete witness promoted")
                cutoff = [d for d in record["decisions"] if d["at_host_calls"] == 4]
                ensure(len(cutoff) == 1, "missing/repeated cutoff decision")
                decision = cutoff[0]
                action = decision["action"]
                if action.startswith("STOP_"):
                    row["status"] = "EXCLUDED_CHECK_STOP"
                else:
                    ensure(action in ("RUN_CACHED", "REFRESH8"), "unregistered cutoff action")
                    cache = record["state_before"]["cache"]
                    ensure(cache["verification_success"] is True and cache["source_episode"] < record["episode"], "future or unverified source")
                    origin = past[record["method"], cache["source_episode"]]
                    ensure(origin["success"] and origin["new_fit"] and origin["task"] == cache["source_task"], "cache source not own accepted new fit")
                    same(origin["cache"], cache)
                    ensure(decision["noise_hash"] == record["trace"][3]["noise_after_hash"], "cutoff noise differs")
                    public = {"prefix": {"task": record["task"], "initial_observation": record["initial"]["observation"],
                        "commands": [r["command"] for r in record["trace"][:4]],
                        "observations": [r["after"]["observation"] for r in record["trace"][:4]], "controlled_reset_completed": True},
                        "old_parameters": cache["parameters"], "source_covariance": cache["belief"]["covariance"],
                        "source_task": cache["source_task"], "source_age": record["episode"]-cache["source_episode"],
                        "source_active_parameter_bound": cache["belief"]["active_parameter_bound"],
                        "current_policy_command": decision["raw_policy_for_check"], "remaining_budget": 496}
                    public = CacheAcquisitionEvidenceV1.from_dict(public).to_dict()
                    public_hash = digest(public)
                    key = digest({"unit": [record["stream"], record["episode"]], "public_evidence_sha256": public_hash})
                    row.update(decision_id=key, public_evidence_sha256=public_hash)
                    packets[key] = public
                    own = metrics(record)
                    if action == "RUN_CACHED":
                        same_controller(decision["controller"], controller(cache["parameters"]))
                        ensure(record["fit"] is None and own["online_parameter_fits"] == 0, "reuse actually refitted")
                        row["status"] = "CONDITIONAL_REALIZED_REUSE_PAIR"
                        pairs.append({**row, "source_age": public["source_age"], "source_task": public["source_task"],
                            "reuse_success": own["success"], "fresh_success": fresh_result["success"],
                            "reuse_deadline_loss": own["deadline_loss"], "fresh_deadline_loss": fresh_result["deadline_loss"],
                            "realized_loss_difference_under_source_contract": own["deadline_loss"]-fresh_result["deadline_loss"],
                            "realized_success_difference": int(own["success"])-int(fresh_result["success"]),
                            "reuse_actual_steps": own["total_steps"], "fresh_actual_steps": fresh_result["total_steps"],
                            "source_episode_oracle": cache["source_episode"]})
                    else:
                        same(decision["program"], PROGRAM[4:])
                        ensure(decision["controller"] is None, "refresh used old control")
                        same([{k: t[k] for k in PHYSICAL} for t in record["trace"][4:]],
                             [{k: t[k] for k in PHYSICAL} for t in fresh["trace"][4:]])
                        same(record["fit"], fresh["fit"])
                        same(own, fresh_result)
                        row["status"] = "FACTUAL_REFRESH_NEGATIVE_CONTROL"
                        controls.append({**row, "actual_steps": own["total_steps"], "actual_loss_difference": 0,
                            "continuation_physical_steps_checked": len(record["trace"])-4})
        dispositions.append(row)
    unique = {}
    for pair in pairs:
        key = pair["decision_id"]
        if key not in unique:
            unique[key] = {**pair, "behavior_methods": [pair["method"]]}
        else:
            other = unique[key]
            for field in ("reuse_success", "fresh_success", "reuse_deadline_loss", "fresh_deadline_loss", "reuse_actual_steps", "fresh_actual_steps"):
                same(pair[field], other[field])
            same([{k: t[k] for k in PHYSICAL} for t in indexed[pair["method"]]["trace"][4:]],
                 [{k: t[k] for k in PHYSICAL} for t in indexed[other["method"]]["trace"][4:]])
            other["behavior_methods"].append(pair["method"])
    for record in records:
        past[record["method"], record["episode"]] = {"task": record["task"], "success": record["outcome"]["success"],
            "new_fit": record["fit"] is not None and record["fit"]["valid"], "cache": deepcopy(record["state_after"]["cache"])}
    return dispositions, pairs, list(unique.values()), controls, packets


def counts(rows):
    values = [r["realized_loss_difference_under_source_contract"] for r in rows]
    return {"cases": len(rows), "fresh_lower_realized_loss": len([v for v in values if v > 0]),
        "reuse_lower_realized_loss": len([v for v in values if v < 0]), "equal_realized_loss": values.count(0),
        "mean_realized_reuse_minus_fresh_loss": sum(values)/len(values) if values else None,
        "sum_realized_loss_difference": sum(values),
        "lost_success_with_reuse": len([r for r in rows if r["reuse_success"] < r["fresh_success"]]),
        "rescued_success_with_reuse": len([r for r in rows if r["reuse_success"] > r["fresh_success"]])}


def audit(path):
    manifest, original, source_summary = io.load(path)
    folder = path.parent/"analysis_v1"
    completion = io.read(folder/"completion.json")
    ensure(set(completion["artifact_sha256"]) == set(io.OUTPUTS), "missing output artifact")
    for name, value in completion["artifact_sha256"].items():
        ensure(io.sha(folder/name) == value, "derived output bytes changed")
    ds, pairs, unique, controls, evidence = [], [], [], [], {}
    past, current = {}, None
    for stream, records in io.units(manifest, original):
        if stream != current:
            past, current = {}, stream
        d, p, u, c, e = reconstruct(records, past)
        ds.extend(d); pairs.extend(p); unique.extend(u); controls.extend(c)
        ensure(not (set(evidence) & set(e)), "actual unit key collided")
        evidence.update(e)
        if records[0]["episode"] == 11:
            print(f"independent stream={stream}: source_cases={len(ds)}", flush=True)
    exports = {"dispositions": ds, "reuse_pairs": pairs, "unique_reuse_pairs": unique, "refresh_controls": controls,
               "visible_evidence": [{"decision_id": k, "public_evidence": v} for k, v in evidence.items()]}
    for name, expected in exports.items():
        same(list(io.lines(folder/(name+".jsonl.gz"))), expected)
    summary = io.read(folder/"summary.json")
    expected = {"source_case_dispositions": len(ds), "disposition_counts": dict(Counter(r["status"] for r in ds)),
        "behavior_reuse_sites": len(pairs), "unique_same_unit_decisions": len(unique), "duplicate_reuse_sites": len(pairs)-len(unique),
        "by_behavior": {m: counts([r for r in pairs if r["method"] == m]) for m in BEHAVIORS}, "unique_decisions": counts(unique),
        "factual_refresh_controls": len(controls), "factual_refresh_control_loss_difference_max_abs": 0,
        "factual_refresh_continuation_steps_checked": sum(r["continuation_physical_steps_checked"] for r in controls),
        "source_policy_queries": 2*(len(pairs)+len(controls))}
    for key, value in expected.items():
        same(summary[key], value)
    for key in ("complete_hidden_state_qualified", "conditional_expectation_identified", "unconditional_causal_transport_qualified",
                "whole_stream_counterfactual_identified", "new_algorithm_established"):
        ensure(summary[key] is False, "qualification promoted")
    costs = io.read(folder/"costs.json")
    same(costs["source_cost_ledger"], io.read(ROOT/manifest["config"]["source_costs"]))
    same(costs["source_main_lifecycle"], source_summary["lifecycle"])
    ensure(costs["source_main_actual_environment_steps"] == source_summary["controlled_steps"], "source main cost lost")
    ensure(costs["local_policy_queries"] == expected["source_policy_queries"] and all(costs[k] == 0 for k in io.ZERO_RESOURCES), "new resource accounting differs")
    result = {**{k: manifest[k] for k in io.source.IDENTITY}, "integrity": "PASSED", "source_cases": len(ds),
        "derived_rows_checked": sum(len(v) for v in exports.values()), "unique_reuse_decisions": len(unique),
        "refresh_controls": len(controls), "summary_sha256": io.sha(folder/"summary.json"),
        "script_sha256": io.sha(Path(__file__)), "new_environment_steps": 0, "new_api_calls": 0,
        "scope": "Independent raw-row alignment, source lineage, feature packets, labels, deduplication and statistics; shares strict schema/hash/source loading only. No full hidden-state certificate."}
    io.write(path.parent/"audit_v1.json", result)
    print(result, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    audit(args.manifest.resolve())

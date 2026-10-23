"""Saved-action, own-cache, noise, clocks and lifecycle replay without resimulation."""
import argparse
from collections import Counter, deque
from copy import deepcopy
from dataclasses import asdict
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from scripts import run_chronological_cache_reference as run
from scripts.audit_acquisition_value_v3 import JournalAudit, compiled_clock_units
from scripts import audit_cross_task_cache_validity as predictive_reference
from scipy.special import gammaincc, gammainccinv
from src.rollout import chronological_cache_execution as execution
from src.probe.chronological_cache_reference import (METHODS, OLD_METHODS, CHECK_METHODS, BLOCK8, VerifiedPoint,
    initial_choice, check_choice, program, accepted_cache)
from src.probe.cold_start_response import ColdPrefix, infer_operator as infer_joint
from src.probe.cold_cache_prediction import digest
from src.probe.continuous import ContinuousTransition
from src.probe.forward_prediction import ForwardHistory
from src.probe.operator_identification import OperatorSample, infer_operator as infer_old, affine_controller, identity_controller, encode_controller
from src.rollout.task_registry import create_task_policy


def equal(a, b):
    if run.prior.normal(a) != run.prior.normal(b): raise ValueError("saved choice, evidence or state differs")


def lines(path):
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle: yield json.loads(line)


def verify_record(record, old_model, joint_model, fault, state, events, dt):
    for event in events:
        if any(event[k] != record[k] for k in (*run.IDENTITY, "stream", "episode", "task", "seed", "method")):
            raise ValueError("business event belongs to another case or method")
    equal(record["state_before"], execution.state_view(state))
    cache = state["cache"]; method = record["method"]; calls = 0; fit = None; fit_prefix = None; samples = []; last = None
    current = record["initial"]; history = ForwardHistory(tuple(current["observation"])); policy = create_task_policy(record["task"])
    pending_program = deque(); passive_left = 0; seen = set(); trace_position = 0; stopped = False
    random_seed = int(np.random.SeedSequence([record["seed"], 47001]).generate_state(1)[0])
    noise = np.random.default_rng(random_seed).normal(0, .05, (500, 3)).astype("<f4"); past = hashlib.sha256()
    if record["noise_commitment_oracle"] != {"full_sha256": hashlib.sha256(noise.tobytes()).hexdigest(), "rows": 500, "namespace": 47001, "dtype": "little-endian-float32"}:
        raise ValueError("private noise commitment differs")
    def ended(): return any(current[k] for k in ("success", "terminated", "truncated"))
    def prefix():
        trace = record["trace"][:calls]
        return ColdPrefix(record["task"], record["initial"]["observation"], tuple(tuple(r["command"]) for r in trace),
                          tuple(tuple(r["after"]["observation"]) for r in trace), True)
    for expected in ("FACTORY_INTENT", "FACTORY_COMPLETE", "CONTROLLED_INITIAL"):
        event = events.popleft()
        if event["event"] != expected: raise ValueError("initial lifecycle order differs")
        if expected == "FACTORY_INTENT":
            equal(event["ledger"], record["ledger_before"]); equal(event["noise_commitment_oracle"], record["noise_commitment_oracle"])
        if expected == "CONTROLLED_INITIAL":
            equal(event["initial"], current); equal(event["physics_witness_oracle"], record["initial_physics_witness_oracle"])
            if event["noise_hash"] != past.hexdigest() or record["initial_noise_hash"] != past.hexdigest(): raise ValueError("initial noise already consumed")
    previous_time = None
    while events and events[0]["event"] != "CACHE_STATE_AFTER_OUTCOME":
        event = events.popleft(); kind = event["event"]
        if kind == "DECISION":
            if ended() or pending_program or passive_left: raise ValueError("decision before requested trajectory completed")
            if event not in record["decisions"] or event["sequence"] in seen: raise ValueError("foreign or repeated decision")
            seen.add(event["sequence"])
            if event["at_host_calls"] != calls or event["observation_sha256"] != run.prior.state_hash(current["observation"]) or event["noise_hash"] != past.hexdigest() or event["cache_sha256"] != digest(execution.state_view(state)):
                raise ValueError("choice used future or foreign evidence/cache")
            action = event["action"]; expected_controller = None; expected_program = ()
            if last is None:
                if action != initial_choice(method, cache, record["episode"]): raise ValueError("initial selection differs")
                if action == "RUN_IDENTITY": expected_controller = identity_controller()
                elif action == "RUN_CACHED": expected_controller = cache.controller
                elif action == "PASSIVE8": expected_controller = cache.controller if cache else identity_controller(); passive_left = 8
                elif action == "PROBE16": expected_program = BLOCK8*2
                elif action == "PROBE8": expected_program = BLOCK8
                elif action == "CHECK4": expected_program = program(method)[:4]
                else: raise ValueError("unexpected initial route")
            elif calls == 4 and method in CHECK_METHODS and last["action"] == "CHECK4":
                raw = np.asarray(policy.get_action(np.asarray(current["observation"])), np.float32)
                try: result = check_choice(method, joint_model, prefix(), cache, state["cusum"], raw)
                except (ValueError, np.linalg.LinAlgError) as error:
                    if action != "STOP_CHECK_SCOPE_OR_NUMERICS" or event["reason"] != str(error): raise ValueError("invalid check stop")
                else:
                    equal(event["raw_policy_for_check"], raw.tolist())
                    equal(event["check"], result)
                    # Independent Gaussian moments and gamma-function score check.
                    p = prefix(); mu, jac, covariance = predictive_reference.response_reference(joint_model, p.commands, cache.parameters)
                    if method != "PLUGIN4": covariance = covariance+jac @ np.asarray(cache.belief.covariance) @ jac.T
                    residual = p.displacements.ravel()-mu; q = float(residual @ np.linalg.solve(covariance, residual))
                    if not np.isclose(q, result["score"]["statistic"], rtol=1e-8, atol=1e-8) or not np.allclose(covariance, result["prediction"]["covariance"], rtol=1e-8, atol=1e-10):
                        raise ValueError("independent predictive score differs")
                    if not np.isclose(gammaincc(4, q/2), result["score"]["nominal_tail_probability"], rtol=1e-8, atol=1e-10) or result["score"]["alarm_95"] != (q > 2*gammainccinv(4, .05)):
                        raise ValueError("nominal check classification differs")
                    if action != result["action"]: raise ValueError("saved revalidation choice substituted")
                    state["cusum"] = result["cusum_after_check"]
                    if action == "REFRESH8": expected_program = program(method)[4:]
                    else: expected_controller = cache.controller
            elif action in ("RUN_POINT", "STOP_POINT_FIT"):
                if calls != (16 if method == "ALWAYS16_OLD" else 8): raise ValueError("fit before requested evidence completed")
                if method in OLD_METHODS: fit = infer_old(old_model, tuple(samples))
                else: fit_prefix = prefix(); fit = infer_joint(joint_model, fit_prefix)
                equal(fit, event["fit"]); equal(record["fit"], fit)
                if action != ("RUN_POINT" if fit["valid"] else "STOP_POINT_FIT"): raise ValueError("failed fit replaced by another controller")
                if fit["valid"]: expected_controller = affine_controller(fit["matrix_xy"], fit["bias_xy"])
            else: raise ValueError("unknown, duplicate or late probe/choice")
            equal(event["controller"], expected_controller); equal(event["program"], expected_program)
            if expected_program and len(expected_program)+32 > 500-calls: raise ValueError("insufficient reserved task budget")
            pending_program = deque(expected_program); last = event; stopped = expected_controller is None and not pending_program
        elif kind == "STEP_INTENT":
            if ended() or calls >= 500 or last is None: raise ValueError("illegal physical step")
            row = record["trace"][trace_position]; trace_position += 1
            if event["decision_sequence"] != last["sequence"] or event["at_host_calls"] != calls or event["before"] != current or event["noise_before_hash"] != past.hexdigest():
                raise ValueError("step does not continue saved choice/state/noise")
            phase = event["phase"]
            if pending_program:
                expected = pending_program.popleft()
                if phase != "FIXED_PROBE" or event["raw_policy"] is not None: raise ValueError("probe mislabeled as policy")
            else:
                if last["controller"] is None: raise ValueError("step after stop")
                raw = np.asarray(policy.get_action(np.asarray(current["observation"])), np.float32)
                equal(raw.tolist(), event["raw_policy"]); expected = encode_controller(last["controller"], raw)
                if passive_left:
                    if phase != "PASSIVE_PREFIX": raise ValueError("passive measurement omitted")
                    passive_left -= 1
                elif phase != "POLICY": raise ValueError("unrequested repeated probe")
            equal(event["command"], np.asarray(expected, dtype=float).tolist())
            query = history.request(event["command"])
            equal(event["forward_query"], asdict(query) if query is not None else None)
            actual = np.asarray(event["command"], np.float32).copy()
            latent = np.asarray(fault["matrix_xy"], np.float32) @ actual[:2]+np.asarray(fault["bias_xy"], np.float32)
            zone = np.asarray(fault["deadzone_xy"], np.float32)
            actual[:2] = np.sign(latent)*np.maximum(np.abs(latent)-zone, 0)/(1-zone)
            actual[:3] += noise[calls]; actual = np.clip(actual, -1, 1); past.update(noise[calls].tobytes())
            equal(row["executed_action_oracle"], actual.tolist())
            if row["intent_saved_ns"] != event["saved_ns"] or not last["saved_ns"] < event["saved_ns"] < row["execution_started_ns"] < row["completed_ns"]:
                raise ValueError("execution before saved decision/intent")
            if not np.isclose(row["simulation_time_after_oracle"]-row["simulation_time_before_oracle"], dt, rtol=1e-10, atol=1e-10) or previous_time is not None and previous_time != row["simulation_time_before_oracle"]:
                raise ValueError("physical clock discontinuity")
            previous_time = row["simulation_time_after_oracle"]
            current = row["after"]; calls += 1
            displacement = history.observe(ContinuousTransition(tuple(event["command"]), tuple(event["before"]["observation"]), tuple(current["observation"])))
            if query is not None: samples.append(OperatorSample(calls, query, displacement))
            equal(row["target_xy"], list(displacement))
            if row["noise_after_hash"] != past.hexdigest() or row["noise_before_hash"] != event["noise_before_hash"]: raise ValueError("noise rewound or substituted")
            complete = events.popleft()
            if complete["event"] != "STEP_COMPLETE": raise ValueError("missing physical completion")
            for name, value in row.items(): equal(complete[name], value)
            if row["intent_sequence"] != event["sequence"] or row["decision_sequence"] != last["sequence"] or row["before"] != event["before"] or row["command"] != event["command"]: raise ValueError("trace/intent differs")
        else: raise ValueError("unexpected business event")
    if trace_position != len(record["trace"]) or seen != {d["sequence"] for d in record["decisions"]}: raise ValueError("incomplete execution transcript")
    if calls < 500 and not ended() and not stopped: raise ValueError("unfinished active task hidden")
    phase_counts = Counter(r["phase"] for r in record["trace"])
    resets = record["ledger_after"]["by_phase"].get("CONTROLLED_RESET", {}).get("reset_completed", 0)-record["ledger_before"]["by_phase"].get("CONTROLLED_RESET", {}).get("reset_completed", 0)
    expected_outcome = {"success": current["success"], "stopped": last["controller"] is None and not ended(), "total_steps": calls, "environment_resets": resets,
        "fixed_probe_steps": phase_counts["FIXED_PROBE"], "policy_measure_steps": phase_counts["PASSIVE_PREFIX"], "policy_steps": phase_counts["POLICY"]+phase_counts["PASSIVE_PREFIX"],
        "deadline_loss": calls if current["success"] else 500, "noise_rows_consumed": calls, "online_parameter_fits": int(fit is not None),
        "optimizer_nfev": int(fit.get("nfev", sum(t["nfev"] for t in fit.get("optimizer_trials", [])))) if fit else 0}
    equal(record["outcome"], expected_outcome)
    equal(record["fit"], fit)
    if resets != 1 or calls > 500 or phase_counts["FIXED_PROBE"] > 16: raise ValueError("budget or reset violation")
    expected_cache_error = None
    if not current["success"]: state.update(cache=None, cusum=0.)
    elif fit is not None:
        try:
            state["cache"] = accepted_cache(fit, fit_prefix, record["task"], record["episode"], success=True,
                joint_model=joint_model if method not in OLD_METHODS else None, evidence=[asdict(s) for s in samples])
        except (ValueError, np.linalg.LinAlgError) as error:
            state["cache"] = None
            expected_cache_error = str(error)
        state["cusum"] = 0.
    if record["cache_write_error"] != expected_cache_error: raise ValueError("cache-write error differs")
    equal(record["state_after"], execution.state_view(state))
    cache_event = events.popleft(); equal(cache_event, record["cache_event"])
    if cache_event["event"] != "CACHE_STATE_AFTER_OUTCOME" or cache_event["outcome"] != expected_outcome or cache_event["state_after"] != record["state_after"]:
        raise ValueError("cache transaction before actual own outcome")
    fit_sequence = next((d["sequence"] for d in reversed(record["decisions"]) if d.get("fit") is not None), None)
    if cache_event["selected_fit_decision_sequence"] != fit_sequence or cache_event["cache_write_error"] != expected_cache_error:
        raise ValueError("cache not bound to selected fit")
    if calls and cache_event["saved_ns"] <= record["trace"][-1]["completed_ns"]: raise ValueError("cache written before verification")
    if events: raise ValueError("extra case events")


def analyze(path, phase, output):
    if output.exists(): raise FileExistsError("preserve audit")
    m, old, joint = run.load(path); identity = {k: m[k] for k in run.IDENTITY}; folder = path.parent/phase.lower(); limits = m["config"][phase.lower()]
    completion = run.read(folder/"completion.json")
    for name, value in completion["artifact_sha256"].items():
        if run.sha(folder/name) != value: raise ValueError("completed raw artifact changed")
    for name, value in m["input_sha256"].items():
        blob = subprocess.check_output(["git", "show", m["source_git_commit"]+":"+name], cwd=ROOT)
        if hashlib.sha256(blob).hexdigest() != value: raise ValueError("frozen committed input differs")
    clocks = compiled_clock_units(m); journal = JournalAudit(identity); rows = []; coverage = {"cache_write": False, "reuse_after_check": False, "refresh_then_task": False}; prefix_checks = 0; prefix_steps = 0
    for stream in m["population_oracle"][phase]:
        number = stream["stream"]; events = iter(lines(folder/f"events_{number:02}.jsonl.gz")); states = {name: {"cache": None, "cusum": 0.} for name in METHODS}
        order = iter((case, method) for case in stream["cases"] for method in METHODS); references = {}; probe_references = {}
        for record in lines(folder/f"episodes_{number:02}.jsonl.gz"):
            expected = next(order, None)
            if expected is None: raise ValueError("extra case")
            case, method = expected
            if any(record[k] != v for k, v in {**identity, "phase": phase, "stream": number, "episode": case["episode"], "task": case["task"], "seed": case["seed"], "method": method}.items()): raise ValueError("foreign or reordered case")
            business = deque(); needed = 4+len(record["decisions"])+2*len(record["trace"])
            while len(business) < needed:
                item = journal.accept(next(events))
                if item is not None: business.append(item)
            equal(record["clock_contract"], {"model_timestep_s": clocks[case["task"]]["compiled_timestep_seconds"], "frame_skip": 5})
            verify_record(record, old[case["task"]], joint[case["task"]], case["fault_oracle"], states[method], business, clocks[case["task"]]["env_step_seconds"])
            if journal.ledger != record["ledger_after"]: raise ValueError("ledger not at case boundary")
            rows.append(run.compact_case(record, stream))
            prior_record = references.get(case["episode"])
            if prior_record is None: references[case["episode"]] = record
            else:
                equal(record["initial"], prior_record["initial"]); equal(record["initial_physics_witness_oracle"], prior_record["initial_physics_witness_oracle"])
            if method == "ALWAYS8": probe_references[case["episode"]] = record
            elif method != "NO_PROBE":
                base = probe_references[case["episode"]]; shared = 0
                for left, right in zip(record["trace"], base["trace"]):
                    if left["command"] != right["command"]: break
                    for key in ("before", "after", "noise_before_hash", "noise_after_hash", "executed_action_oracle", "simulation_time_before_oracle", "simulation_time_after_oracle"):
                        equal(left[key], right[key])
                    shared += 1
                first_action = record["decisions"][0]["action"]
                required = 8 if first_action in ("PROBE8", "PROBE16") else (1 if method == "BALANCED4" else 4) if first_action == "CHECK4" else 0
                if shared < min(required, len(record["trace"]), len(base["trace"])): raise ValueError("required matched probe prefix differs")
                for boundary in (4, 8, 16):
                    if shared >= boundary:
                        equal(record["boundary_physics_witness_oracle"][str(boundary)], base["boundary_physics_witness_oracle"][str(boundary)])
                prefix_checks += 1; prefix_steps += shared
            if record["method"] == "UNCERTAINTY4":
                coverage["cache_write"] |= bool(rows[-1]["cache_writes"])
                coverage["reuse_after_check"] |= any(d["action"] == "RUN_CACHED" and d["at_host_calls"] == 4 for d in record["decisions"]) and record["outcome"]["policy_steps"] > 0
                coverage["refresh_then_task"] |= any(d["action"] == "REFRESH8" for d in record["decisions"]) and record["fit"] is not None and record["fit"]["valid"] and record["outcome"]["policy_steps"] > 0
        if next(order, None) is not None or next(events, None) is not None: raise ValueError("missing case or trailing journal")
        journal.boundary(); print(f"Audited {phase} stream={number}: {len(rows)}/{limits['executions']}", flush=True)
    summary = run.read(folder/"summary.json"); status = run.read(folder/"status.json"); steps = sum(r["total_steps"] for r in rows)
    expected_status = {**identity, "phase": phase, "status": "COMPLETED_REFERENCE", "executions": len(rows), "controlled_steps": steps, "controlled_resets": len(rows), "lifecycle": journal.ledger}
    equal(status, expected_status); equal(summary["cases"], rows); equal(summary["statistics"], run.statistics(rows, phase))
    if len(rows) != limits["executions"] or steps > limits["maximum_environment_steps"]: raise ValueError("incomplete population or step budget")
    ledger = journal.ledger; counts = ledger["counts"]; parts = ledger["by_phase"]
    if any(counts.get(k, 0) for k in ("reset_errors", "simulation_errors", "uncertain_simulation_frames", "frame_budget_rejections")):
        raise ValueError("unresolved lifecycle failure")
    if parts["CONTROL"]["simulation_completed"] != steps or parts["CONTROL"].get("reset_attempts", 0) or parts["CONTROLLED_RESET"]["reset_completed"] != len(rows) or parts["GOAL_GENERATION"]["reset_completed"] != 50*len(rows):
        raise ValueError("reset or control cost mismatch")
    if counts["simulation_frames_completed"] != 500*counts["reset_completed"]+5*steps or counts["simulation_frames_completed"] > limits["maximum_simulation_frames"]:
        raise ValueError("full simulator frame budget mismatch")
    output.parent.mkdir(parents=True, exist_ok=True)
    result = {**identity, "phase": phase, "integrity": "PASSED", "executions": len(rows), "controlled_steps": steps, "controlled_resets": len(rows),
              "events_checked": journal.sequence, "frozen_inputs_checked": len(m["input_sha256"]), "chain_coverage": coverage,
              "matched_prefix_comparisons": prefix_checks, "matched_prefix_physical_steps": prefix_steps,
              "required_chain_coverage": bool(all(coverage.values())) if phase == "SMOKE" else True, "lifecycle": ledger,
              "summary_sha256": run.sha(folder/"summary.json"), "script_sha256": run.sha(Path(__file__)), "new_environment_steps": 0,
              "scope": "No resimulation. Shared deterministic actor, optimizer, cache math and ledger parser; independent private noise and predictive Gaussian/gamma checks. Separate statistics audit remains required."}
    run.write(output, result, exclusive=True); print(json.dumps({k: result[k] for k in ("phase", "integrity", "executions", "controlled_steps", "required_chain_coverage")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--manifest", required=True, type=Path); parser.add_argument("--phase", required=True, choices=("SMOKE", "MAIN")); parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(); analyze(args.manifest.resolve(), args.phase, args.output.resolve())

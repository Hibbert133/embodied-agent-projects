"""Independent saved-control replay and Woodbury/normal-CDF IVR reconstruction."""
from dataclasses import asdict
from pathlib import Path
import sys
import numpy as np
from scipy.special import ndtr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.audit_cross_task_cache_validity import response_reference
from src.probe.cache_acquisition_evidence_v1 import canonical, digest
from src.probe.chronological_cache_reference import BLOCK8, check_choice, accepted_cache
from src.probe.cold_start_response import ColdPrefix, infer_operator
from src.probe.continuous import StepObservation
from src.probe.history_query_reference_v1 import HistoryQueryMeasureV1
from src.probe.operator_identification import affine_controller, encode_controller


def equal(left, right):
    if canonical(left) != canonical(right): raise ValueError("history-reference saved evidence, command or outcome differs")


def independent_ivr(model, prefix, cache, measure):
    prior = np.asarray(cache.belief.covariance)
    posteriors = []
    for commands in (prefix.commands, BLOCK8):
        _, jac, covariance = response_reference(model, commands, cache.parameters)
        left = prior @ jac.T
        posteriors.append(prior-left @ np.linalg.solve(covariance+jac @ left, left.T))
    theta = np.asarray(cache.parameters).reshape(2, 3)
    values = [[], []]
    for raw in [q.raw_policy for q in measure.past_queries]+[measure.current_policy_command]:
        sent = encode_controller(cache.controller, raw)
        x = np.r_[sent[:2], 1.]; latent = theta @ x
        slope = ndtr((1-latent)/.05)-ndtr((-1-latent)/.05)
        for index, posterior in enumerate(posteriors):
            values[index].append(float(slope[0]**2*(x @ posterior[:3, :3] @ x)+slope[1]**2*(x @ posterior[3:, 3:] @ x)))
    a, b = map(np.mean, values)
    return float(a), float(b), float(np.clip((a-b)/max(a, 1e-12), 0, 1))


def verify(agent, model, previous, past_queries, policy):
    if set(agent) != {"mode", "task", "episode", "initial", "state_before", "events", "trace", "outcome", "fit", "state_after", "cache_write_error"} or agent["mode"] != "TASK_HISTORY_IVR4":
        raise ValueError("complete history-reference agent record required")
    equal(agent["state_before"], asdict(previous) if previous else None)
    current, calls, local_sequence, saved_ns = StepObservation(**agent["initial"]), 0, 0, -1
    events = iter(agent["events"]); trace = iter(agent["trace"])
    initial = current; observed = []; queries = 0; fit = None; fit_prefix = None; cache_error = None

    def ended(): return current.success or current.terminated or current.truncated

    def event(kind, payload):
        nonlocal local_sequence, saved_ns
        value = next(events); local_sequence += 1
        if (set(value) != {"event", "sequence", "saved_ns", "payload"} or value["event"] != kind or
            value["sequence"] != local_sequence or type(value["sequence"]) is not int or
            type(value["saved_ns"]) is not int or value["saved_ns"] < saved_ns): raise ValueError("history-reference journal order differs")
        equal(value["payload"], payload)
        saved_ns = value["saved_ns"]
        return value

    def choose(action, controller=None, program=(), **extra):
        return event("DECISION", {"at_host_calls": calls, "action": action, "controller": controller,
            "program": program, "remaining_budget": 500-calls, "observation_sha256": digest(asdict(current)), **extra})

    def consume(command, phase, raw=None):
        nonlocal current, calls
        before = current; sent = np.asarray(command, np.float32).astype(float).tolist()
        intent = event("STEP_INTENT", {"at_host_calls": calls, "decision_sequence": selected["sequence"], "phase": phase,
            "command": sent, "raw_policy": raw, "before": asdict(before)})
        actual = next(trace); current = StepObservation(**actual["after"]); calls += 1
        if len(current.observation) != 39: raise ValueError("actual observation shape differs")
        expected = {"host_calls": calls, "intent_sequence": intent["sequence"], "decision_sequence": selected["sequence"],
            "phase": phase, "command": sent, "raw_policy": raw, "before": asdict(before), "after": asdict(current)}
        equal(actual, expected); event("STEP_COMPLETE", expected); observed.append(actual)

    def probe():
        for command in selected["payload"]["program"]:
            if ended(): break
            consume(command, "FIXED_PROBE")

    def prefix():
        return ColdPrefix(agent["task"], initial.observation, tuple(tuple(r["command"]) for r in observed),
                          tuple(tuple(r["after"]["observation"]) for r in observed), True)

    selected = choose("CHECK4" if previous else "PROBE8", program=BLOCK8[:4] if previous else BLOCK8)
    probe()
    if previous and not ended():
        raw = np.asarray(policy(np.array(current.observation, float, copy=True)), np.float32).astype(float).tolist(); queries += 1
        measure = HistoryQueryMeasureV1(agent["task"], agent["episode"], past_queries, raw)
        try:
            base = check_choice("UNCERTAINTY4", model, prefix(), previous, 0., raw)
            a, b, relative = independent_ivr(model, prefix(), previous, measure)
        except (ValueError, np.linalg.LinAlgError) as error:
            selected = choose("STOP_CHECK_SCOPE_OR_NUMERICS", reason=str(error))
        else:
            # Obtain the saved numerical check, then validate all its fields
            # without calling the main history-IVR implementation or executor.
            position = local_sequence
            actual = agent["events"][position]["payload"]["check"]
            if set(actual) != set(base)|{"history_measure"}: raise ValueError("unknown check field")
            for key in set(base)-{"action", "reason", "ivr"}: equal(actual[key], base[key])
            equal(actual["history_measure"], measure.to_dict())
            ivr = actual["ivr"]
            if set(ivr) != {"variance_after4", "expected_variance_after8", "relative_variance_reduction", "threshold", "past_policy_queries", "total_measure_queries", "measure_sha256", "physical_probability_qualified", "task_value_estimate"}:
                raise ValueError("unknown task-IVR field")
            if not np.allclose([ivr["variance_after4"], ivr["expected_variance_after8"], ivr["relative_variance_reduction"]], [a, b, relative], rtol=1e-8, atol=1e-10):
                raise ValueError("independent history-query IVR differs")
            for key, value in {"threshold": .25, "past_policy_queries": len(past_queries), "total_measure_queries": len(past_queries)+1,
                               "measure_sha256": digest(measure.to_dict()), "physical_probability_qualified": False, "task_value_estimate": False}.items(): equal(ivr[key], value)
            action = "REFRESH8" if base["action"] == "REFRESH8" or relative >= .25 else "RUN_CACHED"
            equal(actual["action"], action); equal(actual["reason"], "PREDICTIVE_OR_OWN_HISTORY_QUERY_VARIANCE")
            selected = choose(action, previous.controller if action == "RUN_CACHED" else None,
                BLOCK8[4:] if action == "REFRESH8" else (), check=actual, raw_policy_for_check=raw)
            if action == "REFRESH8": probe()
    if not ended() and selected["payload"]["action"] in ("PROBE8", "REFRESH8"):
        fit_prefix = prefix(); fit = infer_operator(model, fit_prefix)
        selected = choose("RUN_POINT" if fit["valid"] else "STOP_POINT_FIT",
            affine_controller(fit["matrix_xy"], fit["bias_xy"]) if fit["valid"] else None, fit=fit)
    while not ended() and calls < 500 and selected["payload"]["controller"] is not None:
        raw = np.asarray(policy(np.array(current.observation, float, copy=True)), np.float32).astype(float).tolist(); queries += 1
        consume(encode_controller(selected["payload"]["controller"], raw), "POLICY", raw)
    if next(trace, None) is not None: raise ValueError("extra steps after end or budget")
    next_cache = None
    if current.success:
        if fit is None: next_cache = previous
        else:
            try: next_cache = accepted_cache(fit, fit_prefix, agent["task"], agent["episode"], success=True, joint_model=model)
            except (ValueError, np.linalg.LinAlgError) as error: cache_error = str(error)
    outcome = {"success": current.success, "stopped": selected["payload"]["controller"] is None and not ended(),
        "total_steps": calls, "deadline_loss": calls if current.success else 500,
        "fixed_probe_steps": sum(r["phase"] == "FIXED_PROBE" for r in observed), "fit_attempts": int(fit is not None),
        "optimizer_nfev": int(fit.get("nfev", 0)) if fit else 0, "policy_queries": queries, "physical_response_qualified": False, "probability_guarantee": False}
    equal(agent["outcome"], outcome); equal(agent["fit"], fit); equal(agent["cache_write_error"], cache_error)
    equal(agent["state_after"], asdict(next_cache) if next_cache else None)
    event("TASK_OUTCOME_AND_CACHE", {"outcome": outcome, "state_after": agent["state_after"], "cache_write_error": cache_error})
    if next(events, None) is not None: raise ValueError("extra agent events")
    return {"integrity": "PASSED", "events_checked": local_sequence, "audit_policy_queries": queries,
            "audit_fit_attempts": int(fit is not None), "audit_optimizer_nfev": outcome["optimizer_nfev"]}

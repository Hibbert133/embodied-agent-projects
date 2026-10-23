"""Independent control-flow replay; shares numerical fitter and strict cache schema.

This does not certify simulator state, resets, private noise or source costs.
Those require the separately frozen physical-host collector and journal audit.
"""
from dataclasses import asdict
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.probe.passive_supported_reference_v1 import OwnedPassiveCacheV1
from src.probe.chronological_cache_reference import VerifiedPoint
from src.probe.cache_acquisition_evidence_v1 import canonical, digest
from src.probe.cold_start_response import TASKS
from src.probe.continuous import ContinuousTransition, StepObservation
from src.probe.forward_prediction import ForwardHistory
from src.probe.operator_identification import infer_operator, OperatorSample, affine_controller, identity_controller, encode_controller


def equal(a, b):
    if canonical(a) != canonical(b):
        raise ValueError("passive saved controller, evidence, lineage or outcome differs")


def verify(record, model, policy):
    if set(record) != {"mode", "task", "episode", "initial", "state_before", "events", "trace", "outcome", "state_after"}:
        raise ValueError("complete unmodified passive agent record required")
    mode, task, episode = (record[k] for k in ("mode", "task", "episode"))
    if mode not in ("PASSIVE8_KEEP", "PASSIVE64_PERIODIC16_KEEP") or task not in TASKS or type(episode) is not int or episode < 0:
        raise ValueError("unregistered passive stream")
    old = OwnedPassiveCacheV1.from_dict(record["state_before"]) if record["state_before"] else None
    if old and (old.owner != mode or old.point.source_episode >= episode):
        raise ValueError("foreign or future cache")
    events = iter(record["events"])
    seen, saved_ns = 0, -1
    current = StepObservation(**record["initial"])
    if len(current.observation) != 39:
        raise ValueError("initial observation shape differs")
    history, samples = ForwardHistory(current.observation), []
    calls, fits, accepted, rejected, nfev = 0, 0, 0, 0, 0
    selected_fit, selected_fit_sequence = None, None

    def ended(): return any((current.success, current.terminated, current.truncated))

    def event(kind, payload):
        nonlocal seen, saved_ns
        item = next(events)
        seen += 1
        if (set(item) != {"event", "sequence", "saved_ns", "payload"} or item["event"] != kind or
            type(item["sequence"]) is not int or item["sequence"] != seen or
            type(item["saved_ns"]) is not int or item["saved_ns"] < saved_ns):
            raise ValueError("passive journal order differs")
        equal(item["payload"], payload)
        saved_ns = item["saved_ns"]
        return item

    def choose(action, controller, fit=None):
        return event("DECISION", {"at_host_calls": calls, "action": action, "controller": controller, "fit": fit,
            "observation_sha256": digest(asdict(current)), "remaining_budget": 500-calls})

    selected = choose("START_CACHED" if old else "START_IDENTITY", old.point.controller if old else identity_controller())
    while not ended() and calls < 500:
        if (mode == "PASSIVE8_KEEP" and calls == 8) or (mode == "PASSIVE64_PERIODIC16_KEEP" and calls and calls % 16 == 0):
            fit = infer_operator(model, tuple(samples[-64:]))
            fits += 1
            nfev += sum(t["nfev"] for t in fit.get("optimizer_trials", []))
            if fit["valid"]:
                selected = choose("ACCEPT_UPDATE", affine_controller(fit["matrix_xy"], fit["bias_xy"]), fit)
                selected_fit = fit
                selected_fit_sequence = selected["sequence"]
                accepted += 1
            else:
                selected = choose("REJECT_UPDATE_KEEP", selected["payload"]["controller"], fit)
                rejected += 1
        raw = np.asarray(policy(np.array(current.observation, dtype=float, copy=True)), np.float32)
        command = encode_controller(selected["payload"]["controller"], raw)
        before = current
        intent = event("STEP_INTENT", {"at_host_calls": calls, "decision_sequence": selected["sequence"],
            "before": asdict(before), "command": command.astype(float).tolist(), "raw_policy": raw.astype(float).tolist()})
        query = history.request(command)
        trace = record["trace"][calls]
        current = StepObservation(**trace["after"])
        if len(current.observation) != 39:
            raise ValueError("actual observation shape differs")
        calls += 1
        target = history.observe(ContinuousTransition(tuple(command), before.observation, current.observation))
        if query is not None:
            samples.append(OperatorSample(calls, query, target))
        expected = {"host_calls": calls, "intent_sequence": intent["sequence"], "decision_sequence": selected["sequence"],
            "command": command.astype(float).tolist(), "raw_policy": raw.astype(float).tolist(),
            "before": asdict(before), "after": asdict(current)}
        equal(trace, expected)
        event("STEP_COMPLETE", expected)
    equal(len(record["trace"]), calls)
    next_cache = None
    if current.success:
        if selected_fit is None:
            next_cache = old
        else:
            parameters = tuple(np.column_stack((selected_fit["matrix_xy"], selected_fit["bias_xy"])).ravel())
            next_cache = OwnedPassiveCacheV1(mode, VerifiedPoint(parameters, None, episode, task, selected_fit["sample_digest"], True))
    expected_outcome = {"success": current.success, "total_steps": calls, "deadline_loss": calls if current.success else 500,
        "step_attempts": calls, "fit_attempts": fits, "accepted_updates": accepted, "rejected_updates": rejected,
        "optimizer_nfev": nfev, "policy_queries": calls, "fixed_probe_steps": 0,
        "last_applied_fit_decision_sequence": selected_fit_sequence, "physical_response_qualified": False, "probability_guarantee": False}
    equal(record["outcome"], expected_outcome)
    expected_cache = next_cache.to_dict() if next_cache else None
    equal(record["state_after"], expected_cache)
    event("TASK_OUTCOME_AND_CACHE", {"outcome": expected_outcome, "state_after": expected_cache})
    if next(events, None) is not None:
        raise ValueError("extra journal events after outcome")
    return {"control_flow_integrity": "PASSED", "events_checked": seen, "physical_host_qualified": False,
            "shared_components": "numerical ARX fitter, encoder and strict cache schema"}

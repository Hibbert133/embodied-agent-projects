"""Visible-only saved-action execution of the owned-history IVR reference."""
from copy import deepcopy
from dataclasses import asdict
import json
from time import perf_counter_ns
import numpy as np
from src.probe.cache_acquisition_evidence_v1 import canonical, digest
from src.probe.chronological_cache_reference import BLOCK8, VerifiedPoint, accepted_cache
from src.probe.cold_start_response import ColdPrefix, TASKS, infer_operator
from src.probe.continuous import StepObservation
from src.probe.history_query_reference_v1 import HistoryQueryMeasureV1, history_check
from src.probe.operator_identification import affine_controller, encode_controller
from src.probe.passive_supported_reference_v1 import PassiveReferenceFailure


def run_history_query_reference(*, task, episode, initial, previous, past_queries, model, policy, step, persist):
    if task not in TASKS or type(episode) is not int or episode < 0 or type(initial) is not StepObservation or len(initial.observation) != 39:
        raise ValueError("current actual task and initial observation required")
    if previous is not None and (type(previous) is not VerifiedPoint or previous.belief is None or previous.source_episode >= episode):
        raise ValueError("own earlier joint-source cache required")
    HistoryQueryMeasureV1(task, episode, past_queries, (0.,)*4)
    record = {"mode": "TASK_HISTORY_IVR4", "task": task, "episode": episode, "initial": asdict(initial),
        "state_before": asdict(previous) if previous else None, "events": [], "trace": []}
    current, calls, sequence, saved_ns = initial, 0, 0, -1
    queries, fit, fit_prefix, cache_error = 0, None, None, None
    selected = None

    def ended(): return current.success or current.terminated or current.truncated

    def save(kind, payload):
        nonlocal sequence, saved_ns
        expected = canonical(payload)
        event = json.loads(canonical(persist(kind, deepcopy(payload))))
        if (set(event) != {"event", "sequence", "saved_ns", "payload"} or event["event"] != kind or canonical(event["payload"]) != expected or
            type(event["sequence"]) is not int or event["sequence"] != sequence+1 or type(event["saved_ns"]) is not int or not saved_ns <= event["saved_ns"] <= perf_counter_ns()):
            raise ValueError("saved history-reference acknowledgement changed")
        sequence, saved_ns = event["sequence"], event["saved_ns"]
        record["events"].append(event)
        return event

    def choose(action, controller=None, program=(), **extra):
        return save("DECISION", {"at_host_calls": calls, "action": action, "controller": controller,
            "program": program, "remaining_budget": 500-calls, "observation_sha256": digest(asdict(current)), **extra})

    def act(command, phase, raw=None):
        nonlocal calls, current
        if ended() or calls >= 500: raise ValueError("ended or exhausted history reference stepped")
        before = current
        command = np.asarray(command, np.float32)
        intent = save("STEP_INTENT", {"at_host_calls": calls, "decision_sequence": selected["sequence"], "phase": phase,
            "command": command.astype(float).tolist(), "raw_policy": raw, "before": asdict(before)})
        following = step(np.array(intent["payload"]["command"], np.float32))
        if type(following) is not StepObservation or len(following.observation) != 39:
            raise ValueError("actual step callback returned invalid observation")
        current, calls = following, calls+1
        completed = save("STEP_COMPLETE", {"host_calls": calls, "intent_sequence": intent["sequence"],
            "decision_sequence": selected["sequence"], "phase": phase, "command": intent["payload"]["command"],
            "raw_policy": raw, "before": asdict(before), "after": asdict(current)})
        record["trace"].append(completed["payload"])

    def consume_program():
        for command in selected["payload"]["program"]:
            if ended(): break
            act(command, "FIXED_PROBE")

    def prefix():
        return ColdPrefix(task, initial.observation, tuple(tuple(r["command"]) for r in record["trace"]),
            tuple(tuple(r["after"]["observation"]) for r in record["trace"]), True)

    try:
        selected = choose("CHECK4" if previous else "PROBE8", program=BLOCK8[:4] if previous else BLOCK8)
        consume_program()
        if previous and not ended():
            raw = np.asarray(policy(np.array(current.observation, float, copy=True)), np.float32).astype(float).tolist()
            queries += 1
            measure = HistoryQueryMeasureV1(task, episode, past_queries, raw)
            try:
                check = history_check(model, prefix(), previous, measure)
            except (ValueError, np.linalg.LinAlgError) as error:
                selected = choose("STOP_CHECK_SCOPE_OR_NUMERICS", reason=str(error))
            else:
                action = check["action"]
                selected = choose(action, previous.controller if action == "RUN_CACHED" else None,
                    BLOCK8[4:] if action == "REFRESH8" else (), check=check, raw_policy_for_check=raw)
                if action == "REFRESH8": consume_program()
        if not ended() and selected["payload"]["action"] in ("PROBE8", "REFRESH8"):
            fit_prefix = prefix()
            fit = infer_operator(model, fit_prefix)
            selected = choose("RUN_POINT" if fit["valid"] else "STOP_POINT_FIT",
                affine_controller(fit["matrix_xy"], fit["bias_xy"]) if fit["valid"] else None, fit=fit)
            fit = selected["payload"]["fit"]
        while not ended() and calls < 500 and selected["payload"]["controller"] is not None:
            raw = np.asarray(policy(np.array(current.observation, float, copy=True)), np.float32).astype(float).tolist()
            queries += 1
            act(encode_controller(selected["payload"]["controller"], raw), "POLICY", raw)
        next_cache = None
        if current.success:
            if fit is None:
                next_cache = previous
            else:
                try: next_cache = accepted_cache(fit, fit_prefix, task, episode, success=True, joint_model=model)
                except (ValueError, np.linalg.LinAlgError) as error: cache_error = str(error)
        outcome = {"success": current.success, "stopped": selected["payload"]["controller"] is None and not ended(),
            "total_steps": calls, "deadline_loss": calls if current.success else 500,
            "fixed_probe_steps": sum(r["phase"] == "FIXED_PROBE" for r in record["trace"]),
            "fit_attempts": int(fit is not None), "optimizer_nfev": int(fit.get("nfev", 0)) if fit else 0,
            "policy_queries": queries, "physical_response_qualified": False, "probability_guarantee": False}
        record.update(outcome=outcome, fit=fit, state_after=asdict(next_cache) if next_cache else None, cache_write_error=cache_error)
        save("TASK_OUTCOME_AND_CACHE", {"outcome": outcome, "state_after": record["state_after"], "cache_write_error": cache_error})
        return record
    except BaseException as error:
        record.update(error_type=type(error).__name__, error=str(error), completed_steps=calls, partial_current=asdict(current))
        raise PassiveReferenceFailure(record) from error

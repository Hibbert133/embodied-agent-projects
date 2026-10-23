"""Supported-update passive controls, with actual rejection and prior retention.

Standard references, not a novel acquisition algorithm. The host owns one live
environment and noise clock; this primitive has no reset or evaluator argument.
Numerical validity does not qualify a model's physical or task accuracy.
"""
from copy import deepcopy
from dataclasses import asdict, dataclass, fields
from time import perf_counter_ns
import json
import numpy as np
from src.probe.cache_acquisition_evidence_v1 import canonical, digest
from src.probe.chronological_cache_reference import VerifiedPoint
from src.probe.cold_start_response import TASKS
from src.probe.continuous import ContinuousTransition, StepObservation
from src.probe.forward_prediction import ForwardHistory
from src.probe.operator_identification import (OperatorSample, infer_operator, affine_controller,
                                              identity_controller, encode_controller)

MODES = ("PASSIVE8_KEEP", "PASSIVE64_PERIODIC16_KEEP")
BUDGET = 500


@dataclass(frozen=True)
class OwnedPassiveCacheV1:
    owner: str
    point: VerifiedPoint

    def __post_init__(self):
        if self.owner not in MODES or type(self.point) is not VerifiedPoint or self.point.belief is not None:
            raise ValueError("own actually verified ARX point required")

    @classmethod
    def from_dict(cls, value):
        if type(value) is not dict or set(value) != {f.name for f in fields(cls)}:
            raise ValueError("unknown or evaluator-only passive cache field")
        return cls(value["owner"], VerifiedPoint.from_dict(value["point"]))

    def to_dict(self): return json.loads(canonical(asdict(self)))


class PassiveReferenceFailure(RuntimeError):
    def __init__(self, record):
        self.record = record
        super().__init__(record["error"])


def run_passive_reference(*, mode, task, episode, initial, previous, model, policy, step, persist):
    """Drive policy commands using only acknowledged saved choices.

    step(command) must return the next actual StepObservation. persist(kind,
    payload) must durably save and return an envelope with exactly event,
    sequence, saved_ns, payload. No fault/seed/reset/other-method data is accepted.
    Source provenance is owned by the method and never renewed on mere reuse.
    """
    if mode not in MODES or task not in TASKS or type(episode) is not int or episode < 0:
        raise ValueError("registered method, task and visible episode clock required")
    if type(initial) is not StepObservation or len(initial.observation) != 39:
        raise ValueError("actual 39-dimensional initial observation required")
    if previous is not None and (type(previous) is not OwnedPassiveCacheV1 or previous.owner != mode or previous.point.source_episode >= episode):
        raise ValueError("foreign or future passive source rejected")
    # Validate the complete nominal model before execution, even if support will
    # be insufficient at the first fit. All coefficients are frozen host inputs.
    required = {"method", "training_samples", "mean", "scale", "physical_response_qualified", "probability_guarantee",
                "coefficients", "ridge", "feature_count", "training_rmse"}
    if type(model) is not dict or set(model) != required or model["method"] != "LINEAR_ARX" or model["physical_response_qualified"] is not False or model["probability_guarantee"] is not False:
        raise ValueError("frozen unqualified nominal linear ARX model required")
    if np.asarray(model["coefficients"]).shape != (11, 2) or np.asarray(model["mean"]).shape != (10,) or np.asarray(model["scale"]).shape != (10,):
        raise ValueError("nominal model shapes changed")
    if not all(np.isfinite(np.asarray(model[k], float)).all() for k in ("coefficients", "mean", "scale")) or np.any(np.asarray(model["scale"]) <= 0):
        raise ValueError("finite frozen nominal model required")
    record = {"mode": mode, "task": task, "episode": episode, "initial": asdict(initial),
              "state_before": previous.to_dict() if previous else None, "events": [], "trace": []}
    current, history, samples = initial, ForwardHistory(initial.observation), []
    calls, attempts, last_sequence, last_saved_ns = 0, 0, 0, -1
    selected, selected_fit, selected_fit_sequence = None, None, None
    fits, accepted, rejected, nfev = 0, 0, 0, 0

    def ended(): return current.success or current.terminated or current.truncated

    def save(kind, payload):
        nonlocal last_sequence, last_saved_ns
        expected = canonical(payload)
        envelope = json.loads(canonical(persist(kind, deepcopy(payload))))
        if (type(envelope) is not dict or set(envelope) != {"event", "sequence", "saved_ns", "payload"} or
            envelope["event"] != kind or canonical(envelope["payload"]) != expected or
            type(envelope["sequence"]) is not int or envelope["sequence"] != last_sequence+1 or
            type(envelope["saved_ns"]) is not int or not last_saved_ns <= envelope["saved_ns"] <= perf_counter_ns()):
            raise ValueError("saved acknowledgement differs, is unordered or has future time")
        last_sequence, last_saved_ns = envelope["sequence"], envelope["saved_ns"]
        record["events"].append(envelope)
        return envelope

    def choose(action, controller, fit=None):
        return save("DECISION", {"at_host_calls": calls, "action": action, "controller": controller,
            "fit": fit, "observation_sha256": digest(asdict(current)), "remaining_budget": BUDGET-calls})

    try:
        selected = choose("START_CACHED" if previous else "START_IDENTITY", previous.point.controller if previous else identity_controller())
        while not ended() and calls < BUDGET:
            due = calls == 8 if mode == "PASSIVE8_KEEP" else calls > 0 and calls % 16 == 0
            if due:
                # At most six samples for the single-eight reference; at most
                # 64 real response terms for the rolling reference. AR2 history
                # always comes from the actual continuous trajectory.
                available = tuple(samples[-64:])
                fit = infer_operator(model, available)
                fits += 1
                nfev += sum(trial["nfev"] for trial in fit.get("optimizer_trials", []))
                if fit["valid"]:
                    point = tuple(np.column_stack((fit["matrix_xy"], fit["bias_xy"])).ravel())
                    # Numerical domain check only. Verification is not claimed
                    # until the actual current task has succeeded.
                    p = np.asarray(point).reshape(2, 3)
                    singular = np.linalg.svd(p[:, :2], compute_uv=False)
                    if singular[-1] < .25 or singular[0] > 4 or np.any(np.abs(point) > [2, 2, .3, 2, 2, .3]):
                        raise ValueError("fitter marked an out-of-domain point valid")
                    selected = choose("ACCEPT_UPDATE", affine_controller(fit["matrix_xy"], fit["bias_xy"]), fit)
                    selected_fit = selected["payload"]["fit"]
                    selected_fit_sequence = selected["sequence"]
                    accepted += 1
                else:
                    selected = choose("REJECT_UPDATE_KEEP", selected["payload"]["controller"], fit)
                    rejected += 1
            raw = np.asarray(policy(np.array(current.observation, dtype=float, copy=True)), np.float32)
            sent = encode_controller(selected["payload"]["controller"], raw)
            before = current
            intent = save("STEP_INTENT", {"at_host_calls": calls, "decision_sequence": selected["sequence"],
                "before": asdict(before), "command": sent.astype(float).tolist(), "raw_policy": raw.astype(float).tolist()})
            # Consume the exact persisted command; do not reselect after save.
            command = np.asarray(intent["payload"]["command"], np.float32)
            query = history.request(command)
            attempts += 1
            following = step(command.copy())
            if type(following) is not StepObservation or len(following.observation) != 39:
                raise ValueError("actual step callback returned invalid observation")
            current = following
            calls += 1
            target = history.observe(ContinuousTransition(tuple(command), before.observation, current.observation))
            if query is not None:
                samples.append(OperatorSample(calls, query, target))
            completed = save("STEP_COMPLETE", {"host_calls": calls, "intent_sequence": intent["sequence"],
                "decision_sequence": selected["sequence"], "command": intent["payload"]["command"],
                "raw_policy": intent["payload"]["raw_policy"], "before": asdict(before), "after": asdict(current)})
            record["trace"].append(completed["payload"])
        # A rejected later update keeps the latest applied controller. It never
        # promotes the invalid fit, discards a prior valid update, or renews an
        # old episode's source merely because the current task succeeded.
        next_cache = None
        if current.success:
            if selected_fit is None:
                next_cache = previous
            else:
                parameters = tuple(np.column_stack((selected_fit["matrix_xy"], selected_fit["bias_xy"])).ravel())
                next_cache = OwnedPassiveCacheV1(mode, VerifiedPoint(parameters, None, episode, task,
                    selected_fit["sample_digest"], True))
        outcome = {"success": current.success, "total_steps": calls, "deadline_loss": calls if current.success else 500,
            "step_attempts": attempts, "fit_attempts": fits, "accepted_updates": accepted, "rejected_updates": rejected,
            "optimizer_nfev": nfev, "policy_queries": calls, "fixed_probe_steps": 0,
            "last_applied_fit_decision_sequence": selected_fit_sequence, "physical_response_qualified": False,
            "probability_guarantee": False}
        record["outcome"] = outcome
        record["state_after"] = next_cache.to_dict() if next_cache else None
        save("TASK_OUTCOME_AND_CACHE", {"outcome": outcome, "state_after": record["state_after"]})
        return record
    except BaseException as error:
        record.update(error_type=type(error).__name__, error=str(error), completed_steps=calls,
            step_attempts=attempts, partial_current=asdict(current))
        raise PassiveReferenceFailure(record) from error

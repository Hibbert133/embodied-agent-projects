"""Versioned, bounded API decisions for a live calibrated robot episode."""
from __future__ import annotations

import hashlib
import json
import os
import sys
from time import perf_counter
from typing import Callable

import numpy as np

from src.probemem_sciagent.api_envelope import extract_unique_certified_object
from src.probemem_sciagent.hard_deadline_transport import execute_subprocess_with_hard_deadline
from src.reasoning.evidence import validate_no_oracle_evidence

CONTRACT = "ONLINE_CALIBRATED_AGENT_V1"
RESPONSE_KEYS = {"action_id", "evidence_ids", "reason"}
SYSTEM = """You are a bounded online robot decision agent. Use only the supplied
current observations, calibration assumptions and candidates. Select whether to
collect the offered probe; after a probe select a supplied execution candidate
or abstain. Calibration estimates are not confidence certificates. Consider
evidence quality and interaction cost. Never invent a continuous action,
evidence ID, tool, hidden fault or outcome. Return one JSON object with exactly
action_id, evidence_ids, reason. Copy action_id from the current candidates.
Cite at least one supplied evidence ID. For a correction after probing include
the probe ID. Give a short reason (at most 240 characters), not a reasoning
transcript. For HEALTH select its sole candidate. No other fields."""
CARD = {
    "assumptions": ["known nominal actuator during calibration", "same robot, controller and initial robot pose",
                    "nominal continuous 16-step command program", "additive offsets within calibration support"],
    "limitations": ["not a confidence certificate", "no demonstrated calibration-shift or cross-task validity"],
    "training_trials": 72, "qualification_trials": 72,
    "offline_steps": 2304, "offline_resets": 144,
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def payload(stage, request_id, initial=None, evidence=None, plans=None, remaining_steps=500):
    """Build only from visible observations and host-computed candidate plans."""
    if stage == "HEALTH":
        visible = {"check": {"instruction": "Interface check only; select ABSTAIN."}}
        actions = [("ABSTAIN", None)]
        remaining_steps = 0
    else:
        if initial is None:
            raise ValueError("visible initial observation is required")
        visible = {"initial": {"observation": list(initial.observation)}, "calibration": CARD}
        if stage == "PRE_PROBE":
            if evidence is not None or plans is not None:
                raise ValueError("pre-probe payload cannot contain later evidence")
            actions = [("PROBE_16", None), ("RUN_UNCORRECTED", [0., 0., 0., 0.]), ("ABSTAIN", None)]
        elif stage == "POST_PROBE":
            if evidence is None or evidence.steps != 16 or evidence.stop_reason != "PROGRAM_COMPLETE":
                raise ValueError("post-probe requires the completed live probe")
            visible["probe"] = {
                "steps": evidence.steps,
                "trajectory": [{"command": list(row.command), "hand_after": list(row.after[:3]),
                                "object_after": list(row.after[4:7])} for row in evidence.transitions],
                "final_observation": list(evidence.final.observation),
            }
            actions = [("RUN_UNCORRECTED", [0., 0., 0., 0.])]
            for action in ("RUN_AFFINE", "RUN_NEAREST", "RUN_DYNAMIC"):
                plan = plans.get(action)
                if plan and plan["fit"]["valid"]:
                    actions.append((action, list(plan["correction"])))
                    visible["probe"][action] = {
                        "estimated_offset": list(plan["fit"]["bias_in_command_units"]),
                        "numerically_valid": True,
                    }
            actions.append(("ABSTAIN", None))
        else:
            raise ValueError("unknown API stage")
    candidates = [{"action_id": f"{request_id}.{i}", "operation": action, "correction": correction,
                   "probe_steps": 16 if action == "PROBE_16" else 0}
                  for i, (action, correction) in enumerate(actions)]
    result = {"contract": CONTRACT, "stage": stage, "request_id": request_id,
              "evidence": visible, "candidates": candidates,
              "budget": {"remaining_steps": remaining_steps, "probe_steps": 16,
                         "reserved_task_steps": 484 if stage == "PRE_PROBE" else remaining_steps},
              "response_fields": sorted(RESPONSE_KEYS)}
    validate_payload(result)
    return result


def validate_payload(p):
    validate_no_oracle_evidence(p)
    forbidden = {"seed", "noise_seed", "rng", "rng_state", "condition_oracle", "true_bias",
                 "executed_action", "future_outcome", "success_label"}
    def keys(x):
        if isinstance(x, dict):
            return set(x) | set().union(*(keys(v) for v in x.values()))
        if isinstance(x, list):
            return set().union(*(keys(v) for v in x))
        return set()
    if keys(p) & forbidden:
        raise ValueError("evaluator metadata cannot enter the API")
    if set(p) != {"contract", "stage", "request_id", "evidence", "candidates", "budget", "response_fields"}:
        raise ValueError("unexpected API payload fields")
    if p["contract"] != CONTRACT or p["stage"] not in ("HEALTH", "PRE_PROBE", "POST_PROBE"):
        raise ValueError("unknown API contract/stage")
    if not isinstance(p["request_id"], str) or not p["request_id"]:
        raise ValueError("request scope is required")
    visible = p["evidence"]
    expected_evidence = {"check"} if p["stage"] == "HEALTH" else {"initial", "calibration"} | ({"probe"} if p["stage"] == "POST_PROBE" else set())
    if not isinstance(visible, dict) or set(visible) != expected_evidence:
        raise ValueError("unknown or missing visible evidence fields")
    def finite_vector(vector, size):
        return isinstance(vector, list) and len(vector) == size and all(type(v) in (int, float) for v in vector) and np.isfinite(vector).all()
    if p["stage"] == "HEALTH":
        if visible != {"check": {"instruction": "Interface check only; select ABSTAIN."}}:
            raise ValueError("health check cannot include robot or evaluator data")
    else:
        if (set(visible["initial"]) != {"observation"} or not finite_vector(visible["initial"]["observation"], 39) or visible["calibration"] != CARD):
            raise ValueError("initial observation/model card schema mismatch")
        if p["stage"] == "POST_PROBE":
            probe = visible["probe"]
            fitted = {c["operation"] for c in p["candidates"]} & {"RUN_AFFINE", "RUN_NEAREST", "RUN_DYNAMIC"}
            if set(probe) != {"steps", "trajectory", "final_observation"} | fitted or probe["steps"] != 16 or len(probe["trajectory"]) != 16 or not finite_vector(probe["final_observation"], 39):
                raise ValueError("post-probe evidence schema mismatch")
            for row in probe["trajectory"]:
                if set(row) != {"command", "hand_after", "object_after"} or not finite_vector(row["command"], 4) or not finite_vector(row["hand_after"], 3) or not finite_vector(row["object_after"], 3):
                    raise ValueError("invalid visible probe trajectory")
            for operation in fitted:
                fit = probe[operation]
                if set(fit) != {"estimated_offset", "numerically_valid"} or not finite_vector(fit["estimated_offset"], 2) or fit["numerically_valid"] is not True:
                    raise ValueError("invalid current candidate estimate")
    allowed = ({"ABSTAIN"} if p["stage"] == "HEALTH" else
               {"PROBE_16", "RUN_UNCORRECTED", "ABSTAIN"} if p["stage"] == "PRE_PROBE" else
               {"RUN_UNCORRECTED", "RUN_AFFINE", "RUN_NEAREST", "RUN_DYNAMIC", "ABSTAIN"})
    budget = p["budget"]
    if set(budget) != {"remaining_steps", "probe_steps", "reserved_task_steps"} or any(type(v) is not int or v < 0 for v in budget.values()):
        raise ValueError("invalid environment budget")
    if budget["probe_steps"] != 16 or budget["remaining_steps"] > 500:
        raise ValueError("registered environment budget mismatch")
    seen = set()
    for i, candidate in enumerate(p["candidates"]):
        if set(candidate) != {"action_id", "operation", "correction", "probe_steps"}:
            raise ValueError("unexpected candidate fields")
        action = candidate["operation"]
        if action not in allowed or action in seen or candidate["action_id"] != f"{p['request_id']}.{i}":
            raise ValueError("invalid/request-external action")
        seen.add(action)
        if candidate["probe_steps"] != (16 if action == "PROBE_16" else 0):
            raise ValueError("candidate probe cost mismatch")
        if action == "PROBE_16" and budget["remaining_steps"] < 16 + budget["reserved_task_steps"]:
            raise ValueError("probe would consume task reserve")
        correction = candidate["correction"]
        if action in ("PROBE_16", "ABSTAIN"):
            if correction is not None:
                raise ValueError("non-task candidate cannot specify a correction")
        elif (not isinstance(correction, list) or len(correction) != 4 or
              any(type(v) not in (int, float) for v in correction) or
              not np.isfinite(correction).all() or max(abs(v) for v in correction) > .200001 or
              correction[2:] != [0., 0.]):
            raise ValueError("invalid bounded planar correction")
        elif action == "RUN_UNCORRECTED" and correction != [0., 0., 0., 0.]:
            raise ValueError("uncorrected execution cannot apply a correction")
    if not {"ABSTAIN"} <= seen or not p["evidence"] or p["response_fields"] != sorted(RESPONSE_KEYS):
        raise ValueError("incomplete decision contract")


def validate_response(value, p):
    validate_payload(p)
    if set(value) != RESPONSE_KEYS:
        raise ValueError("response must contain exactly action_id, evidence_ids, reason")
    candidate = next((c for c in p["candidates"] if c["action_id"] == value["action_id"]), None)
    if candidate is None:
        raise ValueError("unknown or stale action ID")
    refs = value["evidence_ids"]
    if (not isinstance(refs, list) or not refs or any(type(x) is not str for x in refs) or
            len(refs) != len(set(refs)) or not set(refs) <= set(p["evidence"])):
        raise ValueError("unknown or missing evidence ID")
    if candidate["operation"] in ("RUN_AFFINE", "RUN_NEAREST", "RUN_DYNAMIC") and "probe" not in refs:
        raise ValueError("correction requires the current probe reference")
    if not isinstance(value["reason"], str) or not value["reason"].strip() or len(value["reason"]) > 240:
        raise ValueError("reason must be a short nonempty string")
    return candidate


def worker_transport(p, config):
    base_url = os.environ.get("ANTHROPIC_BASE_URL")
    if not base_url or not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("local API configuration is unavailable")
    request = {"model": config["model"], "base_url": base_url,
               "timeout_seconds": config["hard_deadline_seconds"],
               "message_kwargs": {"model": config["model"], "temperature": 0.,
                                  "max_tokens": config["max_tokens"], "system": SYSTEM,
                                  "messages": [{"role": "user", "content": canonical(p)}]}}
    raw = execute_subprocess_with_hard_deadline(
        [sys.executable, "-m", "src.probemem_sciagent.hard_deadline_transport", "--worker"],
        input_text=json.dumps(request), deadline_seconds=config["hard_deadline_seconds"])
    result = json.loads(raw)
    if set(result) != {"raw", "usage"} or not isinstance(result["raw"], str) or not isinstance(result["usage"], dict):
        raise RuntimeError("invalid API worker response")
    return result


class OnlineClient:
    """No history in API messages; bounded attempts and explicit abstention."""
    def __init__(self, config, *, transport=worker_transport, emit: Callable | None = None):
        self.config = config
        self.transport = transport
        self.emit = emit or (lambda kind, row: None)
        self.attempts = []
        self.decisions = []
        self.primary_calls = 0
        self.repairs = 0
        self.health_calls = 0
        self.consecutive_failures = 0

    @property
    def next_request_id(self):
        return f"q{len(self.decisions):03d}"

    def decide(self, p):
        validate_payload(p)
        if p["request_id"] != self.next_request_id:
            raise ValueError("unexpected/stale logical request scope")
        health = p["stage"] == "HEALTH"
        if health and self.decisions:
            raise ValueError("health check must be the unique first logical call")
        numbers = []
        valid = False
        value = None
        action = "ABSTAIN"
        failure = None
        if not health and self.consecutive_failures >= 2:
            failure = "CIRCUIT_OPEN"
        elif len(self.attempts) >= 40 or (not health and self.primary_calls >= 32):
            failure = "CALL_BUDGET_EXHAUSTED"
        else:
            previous_error = None
            for repair in (False, True):
                if repair and (self.repairs >= 7 or len(self.attempts) >= 40):
                    failure = "REPAIR_BUDGET_EXHAUSTED"
                    break
                if repair:
                    self.repairs += 1
                elif health:
                    self.health_calls += 1
                else:
                    self.primary_calls += 1
                outgoing = dict(p)
                if repair:
                    outgoing["repair_feedback"] = {"error": previous_error,
                                                   "instruction": "Return the corrected three-field JSON only."}
                ordinal = len(self.attempts) + 1
                start = {"attempt": ordinal, "request_id": p["request_id"], "stage": p["stage"],
                         "repair": repair, "payload": outgoing, "request_sha256": sha(outgoing)}
                self.emit("API_REQUEST_STARTED", start)
                began = perf_counter()
                raw = ""
                usage = {}
                error = None
                extraction = None
                state = "TRANSPORT_ERROR"
                try:
                    result = self.transport(outgoing, self.config)
                    raw, usage = result["raw"], result["usage"]
                    state = "INVALID_RESPONSE"
                    value, extraction = extract_unique_certified_object(raw, expected_keys=RESPONSE_KEYS)
                    selected = validate_response(value, p)
                    action = selected["operation"]
                    valid = True
                    state = "VALID_RESPONSE"
                except Exception as exc:
                    state = "TIMEOUT" if isinstance(exc, TimeoutError) else state
                    error = f"{type(exc).__name__}: {exc}"
                    for secret_name in ("ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL"):
                        secret = os.environ.get(secret_name)
                        if secret:
                            error = error.replace(secret, "[REDACTED]")
                    error = error[:1000]
                    value = None
                row = {**start, "status": state, "raw_response": raw,
                       "response_sha256": hashlib.sha256(raw.encode()).hexdigest(),
                       "latency_ms": (perf_counter() - began) * 1000.,
                       "usage": usage, "extraction_mode": extraction, "error": error}
                self.attempts.append(row)
                numbers.append(ordinal)
                self.emit("API_ATTEMPT_COMPLETED", row)
                if valid:
                    break
                failure = state
                previous_error = error
                if state in ("TIMEOUT", "TRANSPORT_ERROR") or repair:
                    break
        if not health:
            self.consecutive_failures = 0 if valid else self.consecutive_failures + 1
        selected_candidate = next(c for c in p["candidates"] if c["operation"] == action)
        decision = {"request_id": p["request_id"], "stage": p["stage"], "payload": p,
                    "attempts": numbers, "valid": valid, "response": dict(value) if valid else None,
                    "selected_action": action, "candidate": selected_candidate,
                    "failure": None if valid else failure,
                    "consecutive_failures": self.consecutive_failures}
        self.decisions.append(decision)
        self.emit("API_DECISION_PERSISTED", decision)
        return decision

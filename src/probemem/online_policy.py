"""Anthropic-compatible ProbeMem reasoning policy with strict fail-closed audit."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Mapping, Sequence

from src.probemem.models import (
    InterventionSkill,
    MemorySnapshot,
    ProbeMemDecision,
    ProbeMemTool,
)
from src.reasoning.evidence import validate_no_oracle_evidence


PROMPT_VERSION = "probemem-tool-reasoning-v2-phase-b"
SYSTEM_PROMPT = """You are an attempt-level embodied research Agent above a
fixed robot policy. Use only the supplied Agent-visible evidence, empty or
verified memory snapshot, registered discrete tools, and registered skills.
Never infer or request injected fault truth. Never output continuous actions or
skill parameters. Return exactly one JSON object matching response_schema and
do not repeat fields listed in host_owned_envelope. If
evidence is inadequate and a valid probe is unavailable, choose abstain.
For predicted_outcome.verification_status use exactly one uppercase enum:
ACCEPTED, INCONCLUSIVE, or REJECTED. Never use pending, verified, success,
stable_bias_compensated, or another invented status. expected_progress must be
a JSON number, never a qualitative word."""

MODEL_DECISION_FIELDS = {
    "memory_used",
    "retrieved_principle_ids",
    "retrieved_episode_ids",
    "principle_applicable",
    "evidence_sufficient",
    "requested_tool",
    "mechanism_hypothesis",
    "selected_skill",
    "predicted_outcome",
    "reason",
    "confidence",
}


def _extract_single_json(text: str) -> Mapping[str, Any]:
    decoder = json.JSONDecoder()
    values: list[Mapping[str, Any]] = []
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, Mapping) and "requested_tool" in value and value not in values:
            values.append(value)
    if len(values) != 1:
        raise ValueError(f"expected exactly one ProbeMem decision object, found {len(values)}")
    return values[0]


@dataclass
class ApiCallBudget:
    maximum_calls: int
    calls_used: int = 0

    def consume(self) -> None:
        if self.calls_used >= self.maximum_calls:
            raise RuntimeError("ProbeMem API call budget exhausted")
        self.calls_used += 1


class AnthropicProbeMemPolicy:
    def __init__(
        self,
        *,
        model: str = "glm-5.2",
        base_url: str | None = None,
        timeout_seconds: float = 300.0,
        max_retries: int = 1,
        max_tokens: int = 900,
        client: Any | None = None,
    ) -> None:
        if not model.strip() or timeout_seconds <= 0 or max_retries < 0 or max_tokens <= 0:
            raise ValueError("valid model and bounded request limits are required")
        self.model = model
        self.base_url = base_url or os.environ.get("ANTHROPIC_BASE_URL")
        self.timeout_seconds = float(timeout_seconds)
        self.max_retries = int(max_retries)
        self.max_tokens = int(max_tokens)
        self._client = client
        self.prompt_hash = hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest()

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key or not self.base_url:
            raise RuntimeError("ANTHROPIC_API_KEY and ANTHROPIC_BASE_URL are required")
        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise RuntimeError("install dependencies from requirements.txt") from exc
        self._client = Anthropic(
            api_key=key,
            base_url=self.base_url,
            timeout=self.timeout_seconds,
            max_retries=self.max_retries,
        )
        return self._client

    @staticmethod
    def response_schema() -> dict[str, Any]:
        return {
            "memory_used": "boolean; true iff retrieved IDs are non-empty",
            "retrieved_principle_ids": ["only IDs present in memory snapshot"],
            "retrieved_episode_ids": ["only IDs present in memory snapshot"],
            "principle_applicable": "boolean",
            "evidence_sufficient": "boolean",
            "requested_tool": "request_diagnostic_probe | select_intervention_skill | abstain",
            "mechanism_hypothesis": "stable_bias | stochastic_or_unstable_response | insufficient_evidence",
            "selected_skill": "allowed skill only for select_intervention_skill; otherwise null",
            "predicted_outcome": (
                "object only for select_intervention_skill, with exactly: "
                "verification_status, expected_progress, expected_additional_steps; "
                "otherwise null"
            ),
            "reason": "brief evidence-grounded reason",
            "confidence": "low | medium | high",
        }

    def _request(self, payload: Mapping[str, Any], budget: ApiCallBudget) -> tuple[str, dict[str, Any]]:
        validate_no_oracle_evidence(payload)
        budget.consume()
        start = perf_counter()
        response = self._get_client().messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        )
        latency_ms = (perf_counter() - start) * 1000.0
        text = "".join(
            str(getattr(block, "text", ""))
            for block in getattr(response, "content", ())
            if getattr(block, "type", None) == "text"
        ).strip()
        if not text:
            raise RuntimeError("ProbeMem response did not contain text")
        usage = getattr(response, "usage", None)
        return text, {
            "provider": "anthropic-compatible",
            "response_id": str(getattr(response, "id", "")),
            "model": str(getattr(response, "model", self.model)),
            "prompt_version": PROMPT_VERSION,
            "prompt_hash": self.prompt_hash,
            "response_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "latency_ms": latency_ms,
            "usage": {
                key: int(getattr(usage, key))
                for key in ("input_tokens", "output_tokens")
                if usage is not None and hasattr(usage, key)
            },
        }

    def decide(
        self,
        *,
        decision_id: str,
        evidence: Mapping[str, Any],
        memory_snapshot: MemorySnapshot,
        allowed_tools: Sequence[ProbeMemTool],
        allowed_skills: Sequence[InterventionSkill],
        remaining_environment_steps: int,
        call_budget: ApiCallBudget,
        allow_schema_repair: bool = True,
    ) -> tuple[ProbeMemDecision, dict[str, Any]]:
        validate_no_oracle_evidence(evidence)
        payload = {
            "task": "select the next bounded ProbeMem tool at attempt level",
            "prompt_version": PROMPT_VERSION,
            "decision_id": decision_id,
            "evidence_id": str(evidence["evidence_id"]),
            "memory_snapshot_id": memory_snapshot.snapshot_id,
            "agent_visible_evidence": dict(evidence),
            "memory_snapshot": memory_snapshot.to_dict(),
            "remaining_environment_steps": int(remaining_environment_steps),
            "allowed_tools": [item.value for item in allowed_tools],
            "allowed_skills": [item.value for item in allowed_skills],
            "host_owned_envelope": {
                "schema_version": 1,
                "decision_id": decision_id,
                "evidence_id": str(evidence["evidence_id"]),
                "memory_snapshot_id": memory_snapshot.snapshot_id,
                "instruction": "These fields are added by the host. Do not return them.",
            },
            "response_schema": self.response_schema(),
            "conditional_rules": {
                "request_diagnostic_probe": {
                    "evidence_sufficient": False,
                    "selected_skill": None,
                    "predicted_outcome": None,
                },
                "select_intervention_skill": {
                    "evidence_sufficient": True,
                    "selected_skill": "one exact allowed_skills value",
                    "predicted_outcome": "required object",
                },
                "abstain": {
                    "selected_skill": "ABSTAIN or null",
                    "predicted_outcome": None,
                },
                "empty_memory_snapshot": {
                    "memory_used": False,
                    "retrieved_principle_ids": [],
                    "retrieved_episode_ids": [],
                    "principle_applicable": False,
                },
            },
            "valid_response_example": (
                {
                    "memory_used": False,
                    "retrieved_principle_ids": [],
                    "retrieved_episode_ids": [],
                    "principle_applicable": False,
                    "evidence_sufficient": False,
                    "requested_tool": "request_diagnostic_probe",
                    "mechanism_hypothesis": "insufficient_evidence",
                    "selected_skill": None,
                    "predicted_outcome": None,
                    "reason": "Current evidence does not distinguish a stable from unstable response.",
                    "confidence": "medium",
                }
                if ProbeMemTool.REQUEST_DIAGNOSTIC_PROBE in set(allowed_tools)
                else {
                    "memory_used": False,
                    "retrieved_principle_ids": [],
                    "retrieved_episode_ids": [],
                    "principle_applicable": False,
                    "evidence_sufficient": True,
                    "requested_tool": "select_intervention_skill",
                    "mechanism_hypothesis": "stable_bias",
                    "selected_skill": "BOUNDED_PLANAR_COMPENSATION",
                    "predicted_outcome": {
                        "verification_status": "ACCEPTED",
                        "expected_progress": 0.1,
                        "expected_additional_steps": 500,
                    },
                    "reason": "Repeated probe evidence supports a bounded compensation skill.",
                    "confidence": "medium",
                }
            ),
        }
        attempts: list[dict[str, Any]] = []
        maximum_attempts = 2 if allow_schema_repair else 1
        last_error = "unknown validation failure"
        for attempt_index in range(maximum_attempts):
            request_payload = payload
            if attempt_index:
                request_payload = {
                    **payload,
                    "schema_repair": {
                        "previous_error": last_error,
                        "instruction": "Return one corrected JSON object only.",
                    },
                }
            text = ""
            request_audit: dict[str, Any] = {}
            try:
                text, request_audit = self._request(request_payload, call_budget)
                model_body = dict(_extract_single_json(text))
                if set(model_body) != MODEL_DECISION_FIELDS:
                    raise ValueError(
                        f"model decision fields must be exactly {sorted(MODEL_DECISION_FIELDS)}"
                    )
                enveloped = {
                    "schema_version": 1,
                    "decision_id": decision_id,
                    "evidence_id": str(evidence["evidence_id"]),
                    "memory_snapshot_id": memory_snapshot.snapshot_id,
                    **model_body,
                }
                decision = ProbeMemDecision.from_mapping(enveloped)
                decision.validate_context(
                    evidence_id=str(evidence["evidence_id"]),
                    snapshot=memory_snapshot,
                    allowed_tools=allowed_tools,
                    allowed_skills=allowed_skills,
                )
                attempts.append({
                    **request_audit,
                    "attempt_index": attempt_index,
                    "valid": True,
                    "raw_response": text,
                    "structured_response": decision.to_dict(),
                })
                return decision, {
                    "status": "valid",
                    "schema_repair_used": bool(attempt_index),
                    "request_payload_hash": hashlib.sha256(
                        json.dumps(payload, sort_keys=True).encode("utf-8")
                    ).hexdigest(),
                    "request_payload": payload,
                    "attempts": attempts,
                }
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                attempts.append({
                    **request_audit,
                    "attempt_index": attempt_index,
                    "valid": False,
                    "error": last_error,
                    "raw_response": text,
                })
                if call_budget.calls_used >= call_budget.maximum_calls:
                    break
        decision = ProbeMemDecision.fail_closed(
            decision_id=decision_id,
            evidence_id=str(evidence["evidence_id"]),
            memory_snapshot_id=memory_snapshot.snapshot_id,
            reason=f"fail-closed after invalid or unavailable online reasoning: {last_error}",
        )
        return decision, {
            "status": "fail_closed",
            "schema_repair_used": len(attempts) > 1,
            "failure_reason": last_error,
            "request_payload_hash": hashlib.sha256(
                json.dumps(payload, sort_keys=True).encode("utf-8")
            ).hexdigest(),
            "request_payload": payload,
            "attempts": attempts,
        }

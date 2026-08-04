"""Optional GLM adapter that verifies candidates but never selects an action."""

from __future__ import annotations

import hashlib
import json
import os
from time import perf_counter
from typing import Any, Mapping

from src.probemem.compact_evidence import REGISTERED_SKILLS, SKILL_SEMANTICS
from src.probemem_verifier.candidate_verifier import CandidateMemorySummary, validate_glm_candidate_mapping
from src.probemem_verifier.schemas import CandidateVerification
from src.reasoning.evidence import validate_no_oracle_evidence


SYSTEM_PROMPT = """You are a candidate verifier, not an action selector.
Evaluate both registered recovery skills independently using only the supplied
Agent-visible memory summaries and skill semantics. Never infer perturbation
truth, Oracle outcomes, future records, continuous actions, or a final selected
skill. Return exactly one JSON object with one verification per skill."""


class HistoryAwareGlmVerifier:
    def __init__(
        self, *, model: str = "glm-5.2", base_url: str | None = None,
        timeout_seconds: float = 300.0, max_tokens: int = 1100,
        maximum_repairs: int = 1, client: Any | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url or os.environ.get("ANTHROPIC_BASE_URL")
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens
        self.maximum_repairs = maximum_repairs
        self._client = client
        self.audit: list[dict[str, Any]] = []
        self.prompt_hash = hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest()

    def verify_both(
        self, summaries: Mapping[str, CandidateMemorySummary],
    ) -> dict[str, CandidateVerification]:
        allowed = {
            record_id for summary in summaries.values()
            for record_id in summary.global_record_ids + summary.recent_record_ids
        }
        previous_error: str | None = None
        for attempt in range(self.maximum_repairs + 1):
            decision, audit = self.request_once(summaries, allowed_memory_ids=allowed, previous_error=previous_error)
            audit["repair"] = attempt > 0
            self.audit.append(audit)
            if decision is not None:
                return decision
            previous_error = str(audit.get("error", "invalid verifier output"))
        raise RuntimeError("GLM verifier failed closed after retry exhaustion")

    def request_once(
        self, summaries: Mapping[str, CandidateMemorySummary], *, allowed_memory_ids: set[str],
        previous_error: str | None = None,
    ) -> tuple[dict[str, CandidateVerification] | None, dict[str, Any]]:
        payload: dict[str, Any] = {
            "mode": "candidate_verification_only_no_action_selection",
            "registered_skill_semantics": {skill: SKILL_SEMANTICS[skill] for skill in REGISTERED_SKILLS},
            "candidate_memory_summaries": {skill: summaries[skill].to_dict() for skill in REGISTERED_SKILLS},
            "response_schema": {
                skill: {
                    "predicted_accept_probability": "0..1",
                    "predicted_status": "ACCEPTED | INCONCLUSIVE | REJECTED",
                    "confidence": "0..1",
                    "memory_applicable": "boolean",
                    "coverage_count": "non-negative integer matching supplied evidence",
                    "supporting_record_ids": "list of supplied record IDs",
                    "contradicting_record_ids": "list of supplied record IDs",
                }
                for skill in REGISTERED_SKILLS
            },
        }
        if previous_error is not None:
            payload["schema_repair"] = {"previous_error": previous_error, "instruction": "Return corrected JSON only."}
        validate_no_oracle_evidence(payload)
        started = perf_counter()
        raw = ""
        usage_payload: dict[str, int] = {}
        try:
            response = self._get_client().messages.create(
                model=self.model, max_tokens=self.max_tokens, temperature=0.0,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": json.dumps(payload)}],
            )
            raw = "".join(
                str(getattr(block, "text", "")) for block in getattr(response, "content", ())
                if getattr(block, "type", None) == "text"
            ).strip()
            usage = getattr(response, "usage", None)
            usage_payload = {
                name: int(getattr(usage, name)) for name in ("input_tokens", "output_tokens")
                if usage is not None and hasattr(usage, name)
            }
            mapping = _single_json(raw)
            decision = validate_glm_candidate_mapping(mapping, allowed_memory_ids=allowed_memory_ids)
            for skill, candidate in decision.items():
                if candidate.coverage_count != summaries[skill].coverage_count:
                    raise ValueError("GLM verifier changed host-owned coverage")
            return decision, {
                "valid": True, "latency_ms": (perf_counter() - started) * 1000.0,
                "usage": usage_payload, "response_hash": hashlib.sha256(raw.encode()).hexdigest(),
            }
        except Exception as exc:
            return None, {
                "valid": False, "latency_ms": (perf_counter() - started) * 1000.0,
                "usage": usage_payload, "error": f"{type(exc).__name__}: {exc}",
                "raw_response": raw,
            }

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key or not self.base_url:
            raise RuntimeError("ANTHROPIC_API_KEY and ANTHROPIC_BASE_URL are required")
        from anthropic import Anthropic
        self._client = Anthropic(
            api_key=key, base_url=self.base_url, timeout=self.timeout_seconds, max_retries=0,
        )
        return self._client


def _single_json(text: str) -> Mapping[str, Any]:
    decoder = json.JSONDecoder()
    candidates: list[Mapping[str, Any]] = []
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, Mapping) and set(REGISTERED_SKILLS) <= set(value) and value not in candidates:
            candidates.append(value)
    if len(candidates) != 1:
        raise ValueError(f"expected one candidate-verification object, found {len(candidates)}")
    return candidates[0]

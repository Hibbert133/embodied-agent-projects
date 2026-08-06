"""Three-stage structured-output GLM adapter for SciAgent."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from time import perf_counter
from typing import Any, Mapping

from src.probemem_sciagent.decision_validator import validate_decision_mapping
from src.probemem_sciagent.memory_retrieval import ScientificMemorySnapshot
from src.probemem_sciagent.schemas import KnowledgeUpdateProposal, SciAgentDecision, UPDATE_OPERATIONS


DECISION_SYSTEM_PROMPT = """You are an online scientific robot-recovery Agent.
Use only supplied Agent-visible evidence and bounded earlier memory. Generate
competing hypotheses for both registered skills. Choose ACT_DIRECTLY,
RUN_MICRO_PROBE, or ABSTAIN. Never emit continuous actions, fault truth, Oracle
claims, unknown memory IDs, or free-form tools. Return exactly one JSON object."""

POST_PROBE_SYSTEM_PROMPT = """You are making the single final recovery decision
after an authorized micro-probe. Explain how the new evidence changed the
hypotheses. Choose ACT_DIRECTLY or ABSTAIN only, using one registered skill when
acting. Return exactly one JSON object and never request another probe."""

UPDATE_SYSTEM_PROMPT = """You are proposing bounded scientific-memory updates
after selected-action Fresh Verification. You may create or update hypotheses
and suggest restricting knowledge, but you cannot promote principles. Never
infer or mention an unselected action outcome. Return {\"updates\": [...]} only."""


@dataclass
class SciAgentCallBudget:
    maximum_primary_calls: int = 45
    maximum_repairs: int = 15
    maximum_total_calls: int = 60
    primary_calls: int = 0
    repair_calls: int = 0

    @property
    def total_calls(self) -> int:
        return self.primary_calls + self.repair_calls

    def consume(self, *, repair: bool) -> None:
        if self.total_calls >= self.maximum_total_calls:
            raise RuntimeError("SciAgent total API-call budget exhausted")
        if repair:
            if self.repair_calls >= self.maximum_repairs:
                raise RuntimeError("SciAgent schema-repair budget exhausted")
            self.repair_calls += 1
        else:
            if self.primary_calls >= self.maximum_primary_calls:
                raise RuntimeError("SciAgent primary API-call budget exhausted")
            self.primary_calls += 1


class SciAgentGlmClient:
    def __init__(
        self, *, model: str = "glm-5.2", base_url: str | None = None,
        timeout_seconds: float = 300.0, max_tokens: int = 1400,
        call_budget: SciAgentCallBudget | None = None, client: Any | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url or os.environ.get("ANTHROPIC_BASE_URL")
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens
        self.call_budget = call_budget or SciAgentCallBudget()
        self._client = client
        self.audit: list[dict[str, Any]] = []

    def decide(
        self, payload: Mapping[str, Any], *, snapshot: ScientificMemorySnapshot, stage: str,
    ) -> SciAgentDecision:
        previous_error: str | None = None
        for attempt in range(2):
            try:
                mapping = self._request(
                    payload, phase=stage, system=POST_PROBE_SYSTEM_PROMPT if stage == "POST_PROBE" else DECISION_SYSTEM_PROMPT,
                    repair=attempt == 1, previous_error=previous_error,
                )
                return validate_decision_mapping(mapping, snapshot=snapshot, stage=stage)
            except Exception as exc:
                previous_error = f"{type(exc).__name__}: {exc}"
                if isinstance(exc, RuntimeError) and "budget exhausted" in str(exc):
                    return SciAgentDecision.fail_closed(previous_error)
                if attempt == 1:
                    return SciAgentDecision.fail_closed(previous_error)
        raise AssertionError("unreachable")

    def propose_updates(self, payload: Mapping[str, Any]) -> tuple[KnowledgeUpdateProposal, ...]:
        previous_error: str | None = None
        for attempt in range(2):
            try:
                mapping = self._request(
                    payload, phase="KNOWLEDGE_UPDATE", system=UPDATE_SYSTEM_PROMPT,
                    repair=attempt == 1, previous_error=previous_error,
                )
                if set(mapping) != {"updates"} or not isinstance(mapping["updates"], list):
                    raise ValueError("knowledge update response must contain only an updates list")
                return tuple(_update_from_mapping(item) for item in mapping["updates"])
            except Exception as exc:
                previous_error = f"{type(exc).__name__}: {exc}"
                if isinstance(exc, RuntimeError) and "budget exhausted" in str(exc):
                    return ()
                if attempt == 1:
                    return ()
        raise AssertionError("unreachable")

    def _request(
        self, payload: Mapping[str, Any], *, phase: str, system: str,
        repair: bool, previous_error: str | None,
    ) -> Mapping[str, Any]:
        self.call_budget.consume(repair=repair)
        request_payload = dict(payload)
        if repair:
            request_payload["schema_repair"] = {"previous_error": previous_error, "instruction": "Return corrected JSON only."}
        started = perf_counter()
        raw = ""
        usage_payload: dict[str, int] = {}
        try:
            response = self._get_client().messages.create(
                model=self.model, max_tokens=self.max_tokens, temperature=0.0,
                system=system, messages=[{"role": "user", "content": json.dumps(request_payload)}],
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
            self.audit.append({
                "phase": phase, "repair": repair, "valid_transport": True,
                "latency_ms": (perf_counter() - started) * 1000.0, "usage": usage_payload,
                "response_hash": hashlib.sha256(raw.encode()).hexdigest(),
            })
            return mapping
        except Exception as exc:
            self.audit.append({
                "phase": phase, "repair": repair, "valid_transport": False,
                "latency_ms": (perf_counter() - started) * 1000.0, "usage": usage_payload,
                "error": f"{type(exc).__name__}: {exc}",
                "response_hash": hashlib.sha256(raw.encode()).hexdigest(),
            })
            raise

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key or not self.base_url:
            raise RuntimeError("ANTHROPIC_API_KEY and ANTHROPIC_BASE_URL are required")
        from anthropic import Anthropic
        self._client = Anthropic(api_key=key, base_url=self.base_url, timeout=self.timeout_seconds, max_retries=0)
        return self._client


def _single_json(text: str) -> Mapping[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("response must be one bare JSON object") from exc
    if not isinstance(value, Mapping):
        raise ValueError("response must be one JSON object")
    return value


def _update_from_mapping(value: Mapping[str, Any]) -> KnowledgeUpdateProposal:
    expected = {"operation", "target_id", "statement", "applicability_conditions", "predicted_best_skill", "proposed_probe_type", "rationale"}
    if set(value) != expected or str(value["operation"]) not in UPDATE_OPERATIONS:
        raise ValueError("knowledge update has unexpected fields or operation")
    return KnowledgeUpdateProposal(
        operation=str(value["operation"]),
        target_id=None if value["target_id"] is None else str(value["target_id"]),
        statement=None if value["statement"] is None else str(value["statement"]),
        applicability_conditions=tuple(str(item) for item in value["applicability_conditions"]),
        predicted_best_skill=None if value["predicted_best_skill"] is None else str(value["predicted_best_skill"]),
        proposed_probe_type=None if value["proposed_probe_type"] is None else str(value["proposed_probe_type"]),
        rationale=str(value["rationale"]),
    )

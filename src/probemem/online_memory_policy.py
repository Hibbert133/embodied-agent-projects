"""Strict contracts for chronological ProbeMem-Online decisions.

The model selects one registered skill or abstains. Continuous skill
parameters, execution, verification, and memory writes remain host-owned.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from time import perf_counter
from typing import Any, Mapping

from src.probemem.compact_evidence import REGISTERED_SKILLS, SKILL_SEMANTICS
from src.probemem.memory_tools import validate_memory_ids
from src.probemem.online_glm_contract import EvidenceInterpretation, SkillPrediction
from src.probemem.regime_memory import RegimeActionMemory
from src.reasoning.evidence import validate_no_oracle_evidence


ONLINE_MEMORY_SCHEMA_VERSION = 1
ONLINE_MEMORY_SYSTEM_PROMPT = """You are a rollout-level embodied recovery agent.
Use only the supplied compact physical evidence, registered skill semantics, and
chronologically available action-outcome summaries. Predict both skills, then
select one registered skill or abstain. Do not infer fault truth, use Oracle or
counterfactual information, or output continuous actions or parameters. Memory
is evidence, not an action to copy. Return exactly one JSON object."""


@dataclass(frozen=True)
class OnlineMemoryDecision:
    evidence_interpretation: EvidenceInterpretation
    action_predictions: Mapping[str, SkillPrediction]
    memory_used: bool
    supporting_memory_ids: tuple[str, ...]
    contradicting_memory_ids: tuple[str, ...]
    memory_applicable: bool
    memory_conflict_detected: bool
    selected_skill: str | None
    abstain: bool
    reason: str

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
        *,
        allowed_memory_ids: set[str],
    ) -> "OnlineMemoryDecision":
        required = {
            "evidence_interpretation", "action_predictions", "memory_used",
            "supporting_memory_ids", "contradicting_memory_ids",
            "memory_applicable", "memory_conflict_detected", "selected_skill",
            "abstain", "reason",
        }
        if set(value) != required:
            raise ValueError("online-memory decision has unexpected or missing fields")
        predictions = value["action_predictions"]
        if not isinstance(predictions, Mapping) or set(predictions) != set(REGISTERED_SKILLS):
            raise ValueError("both and only registered skills must be predicted")
        boolean_fields = ("memory_used", "memory_applicable", "memory_conflict_detected", "abstain")
        if not all(type(value[name]) is bool for name in boolean_fields):
            raise ValueError("online-memory flags must be booleans")
        supporting = _record_ids(value["supporting_memory_ids"], "supporting_memory_ids")
        contradicting = _record_ids(value["contradicting_memory_ids"], "contradicting_memory_ids")
        cited = set(supporting) | set(contradicting)
        if not cited <= allowed_memory_ids:
            raise ValueError("decision cites unknown, current, or future memory IDs")
        if not value["memory_used"] and cited:
            raise ValueError("memory citations require memory_used=true")
        selected = None if value["selected_skill"] is None else str(value["selected_skill"])
        reason = str(value["reason"])
        interpretation = EvidenceInterpretation.from_mapping(value["evidence_interpretation"])
        if not reason.strip():
            raise ValueError("decision reason cannot be empty")
        if value["abstain"]:
            if selected is not None or interpretation.evidence_sufficient:
                raise ValueError("abstention requires null skill and insufficient evidence")
        elif selected not in REGISTERED_SKILLS or not interpretation.evidence_sufficient:
            raise ValueError("execution requires a registered skill and sufficient evidence")
        decision = cls(
            evidence_interpretation=interpretation,
            action_predictions={name: SkillPrediction.from_mapping(predictions[name]) for name in REGISTERED_SKILLS},
            memory_used=value["memory_used"],
            supporting_memory_ids=supporting,
            contradicting_memory_ids=contradicting,
            memory_applicable=value["memory_applicable"],
            memory_conflict_detected=value["memory_conflict_detected"],
            selected_skill=selected,
            abstain=value["abstain"],
            reason=reason,
        )
        validate_no_oracle_evidence(decision.to_dict())
        return decision

    @classmethod
    def fail_closed(cls, reason: str) -> "OnlineMemoryDecision":
        neutral = SkillPrediction("INCONCLUSIVE", 0.5, 0.0)
        return cls(
            EvidenceInterpretation(False, False, False),
            {name: neutral for name in REGISTERED_SKILLS},
            False, (), (), False, False, None, True, reason,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_interpretation": asdict(self.evidence_interpretation),
            "action_predictions": {name: asdict(prediction) for name, prediction in self.action_predictions.items()},
            "memory_used": self.memory_used,
            "supporting_memory_ids": list(self.supporting_memory_ids),
            "contradicting_memory_ids": list(self.contradicting_memory_ids),
            "memory_applicable": self.memory_applicable,
            "memory_conflict_detected": self.memory_conflict_detected,
            "selected_skill": self.selected_skill,
            "abstain": self.abstain,
            "reason": self.reason,
        }


def build_online_memory_payload(
    *,
    compact_evidence: Mapping[str, Any],
    memory_payload: Mapping[str, Any],
    memory: RegimeActionMemory,
    episode_id: int,
) -> dict[str, Any]:
    """Build the only payload permitted for a chronological online decision."""

    if episode_id <= 0:
        raise ValueError("episode_id must be positive")
    if int(memory_payload.get("memory_cutoff_episode_id", -1)) != episode_id:
        raise ValueError("memory cutoff must equal the current episode")
    normalized_memory = dict(memory_payload)
    validate_memory_ids(normalized_memory, memory, created_before_episode_id=episode_id)
    payload = {
        "schema_version": ONLINE_MEMORY_SCHEMA_VERSION,
        "episode_id": episode_id,
        "current_evidence": dict(compact_evidence),
        "available_registered_skills": list(REGISTERED_SKILLS),
        "registered_skill_semantics": SKILL_SEMANTICS,
        "action_conditioned_memory": normalized_memory,
        "host_constraints": {
            "continuous_parameters_host_owned": True,
            "fresh_verification_required_after_selection": True,
            "memory_write_allowed_only_after_verification": True,
            "abstain_executes_verification": False,
        },
    }
    validate_no_oracle_evidence(payload)
    return payload


class OnlineMemoryGlmPolicy:
    """Frozen GLM caller with one optional schema-repair attempt."""

    def __init__(self, *, model: str = "glm-5.2", base_url: str | None = None,
                 timeout_seconds: float = 300.0, max_tokens: int = 1100,
                 client: Any | None = None) -> None:
        self.model = model
        self.base_url = base_url or os.environ.get("ANTHROPIC_BASE_URL")
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens
        self._client = client
        self.prompt_hash = hashlib.sha256(ONLINE_MEMORY_SYSTEM_PROMPT.encode()).hexdigest()

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key or not self.base_url:
            raise RuntimeError("ANTHROPIC_API_KEY and ANTHROPIC_BASE_URL are required")
        from anthropic import Anthropic
        self._client = Anthropic(api_key=key, base_url=self.base_url, timeout=self.timeout_seconds, max_retries=0)
        return self._client

    def request_once(
        self, payload: Mapping[str, Any], *, allowed_memory_ids: set[str],
        previous_error: str | None = None,
    ) -> tuple[OnlineMemoryDecision | None, dict[str, Any]]:
        validate_no_oracle_evidence(payload)
        request = dict(payload)
        request["response_schema"] = {
            "evidence_interpretation": {"persistent_directional_drift": "boolean", "high_response_variance": "boolean", "evidence_sufficient": "boolean"},
            "action_predictions": {name: {"predicted_status": "ACCEPTED | INCONCLUSIVE | REJECTED", "accept_probability": "0..1", "confidence": "0..1"} for name in REGISTERED_SKILLS},
            "memory_used": "boolean", "supporting_memory_ids": "list of supplied record IDs",
            "contradicting_memory_ids": "list of supplied record IDs", "memory_applicable": "boolean",
            "memory_conflict_detected": "boolean", "selected_skill": "registered skill or null",
            "abstain": "boolean", "reason": "brief evidence-grounded reason",
        }
        if previous_error is not None:
            request["schema_repair"] = {"previous_error": previous_error, "instruction": "Return corrected JSON only."}
        start = perf_counter()
        raw = ""
        usage_payload: dict[str, int] = {}
        try:
            response = self._get_client().messages.create(
                model=self.model, max_tokens=self.max_tokens, temperature=0.0,
                system=ONLINE_MEMORY_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": json.dumps(request)}],
            )
            raw = "".join(str(getattr(block, "text", "")) for block in getattr(response, "content", ()) if getattr(block, "type", None) == "text").strip()
            usage = getattr(response, "usage", None)
            usage_payload = {name: int(getattr(usage, name)) for name in ("input_tokens", "output_tokens") if usage is not None and hasattr(usage, name)}
            decision = OnlineMemoryDecision.from_mapping(_single_decision(raw), allowed_memory_ids=allowed_memory_ids)
            return decision, {"valid": True, "latency_ms": (perf_counter() - start) * 1000.0,
                              "raw_response": raw, "usage": usage_payload,
                              "response_hash": hashlib.sha256(raw.encode()).hexdigest()}
        except Exception as exc:
            return None, {"valid": False, "error": f"{type(exc).__name__}: {exc}",
                          "latency_ms": (perf_counter() - start) * 1000.0,
                          "raw_response": raw, "usage": usage_payload}


def _record_ids(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"{field} must contain non-empty record IDs")
    if len(value) != len(set(value)):
        raise ValueError(f"{field} contains duplicate IDs")
    return tuple(value)


def _single_decision(text: str) -> Mapping[str, Any]:
    decoder = json.JSONDecoder()
    candidates: list[Mapping[str, Any]] = []
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, Mapping) and "action_predictions" in value and value not in candidates:
            candidates.append(value)
    if len(candidates) != 1:
        raise ValueError(f"expected one online-memory decision object, found {len(candidates)}")
    return candidates[0]

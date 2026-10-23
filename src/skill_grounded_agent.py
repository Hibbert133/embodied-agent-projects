"""Anthropic-compatible online Agent that selects grounded recovery skills."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from time import perf_counter
from typing import Any, Mapping, Sequence

from src.online_planar_agent import validate_agent_payload
from src.recovery_agent import CORRECTION_SCHEDULES
from src.recovery_skills import RecoverySkillContract, select_skill


SKILL_PROMPT_VERSION = "skill-grounded-planar-v1"
SKILL_DECISION_FIELDS = frozenset(
    {"skill_id", "correction_schedule", "hypothesis", "expected_effect",
     "verification_condition", "confidence", "stop"}
)
SKILL_SYSTEM_INSTRUCTIONS = """You are a high-level robotic recovery orchestrator.
Select exactly one supplied executable skill; never invent or modify correction
values and never output low-level actions. Use only agent-visible failure and
structured diagnostic evidence. Compare each skill's preconditions, cost, and
failure modes. With one rollout remaining, prefer a skill that addresses every
material inferred bias component. Return exactly one JSON object."""


@dataclass(frozen=True)
class SkillSelectionDecision:
    skill_id: str
    correction_schedule: str
    hypothesis: str
    expected_effect: str
    verification_condition: str
    confidence: float
    stop: bool = False

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "SkillSelectionDecision":
        try:
            return cls(
                skill_id=str(value["skill_id"]),
                correction_schedule=str(value["correction_schedule"]),
                hypothesis=str(value["hypothesis"]),
                expected_effect=str(value["expected_effect"]),
                verification_condition=str(value["verification_condition"]),
                confidence=float(value["confidence"]),
                stop=bool(value["stop"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid skill selection: {exc}") from exc

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def extract_skill_decision_json(text: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    candidates: list[dict[str, Any]] = []
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and SKILL_DECISION_FIELDS.issubset(value):
            if value not in candidates:
                candidates.append(value)
    if len(candidates) != 1:
        raise ValueError(f"expected one skill decision object, found {len(candidates)}")
    return candidates[0]


def validate_skill_decision(
    decision: SkillSelectionDecision,
    skills: Sequence[RecoverySkillContract],
) -> SkillSelectionDecision:
    if decision.correction_schedule not in CORRECTION_SCHEDULES:
        raise ValueError("unknown correction_schedule")
    if not 0.0 <= decision.confidence <= 1.0:
        raise ValueError("confidence must be between 0 and 1")
    text_fields = (
        decision.hypothesis, decision.expected_effect, decision.verification_condition
    )
    if any(not value.strip() for value in text_fields):
        raise ValueError("reasoning and verification fields must be non-empty")
    if decision.stop:
        if decision.skill_id != "stop":
            raise ValueError("stop decision must use skill_id=stop")
    else:
        select_skill(skills, decision.skill_id)
    return decision


class AnthropicSkillGroundedAgent:
    """One-call selector over precomputed, typed recovery skills."""

    def __init__(
        self, *, model: str = "glm-5.2", base_url: str | None = None,
        timeout_seconds: float = 180.0, max_retries: int = 2,
        max_tokens: int = 700, client: Any | None = None,
    ) -> None:
        if not model.strip() or timeout_seconds <= 0 or max_retries < 0 or max_tokens <= 0:
            raise ValueError("model and positive request limits are required")
        self.model = model
        self.base_url = base_url or os.environ.get("ANTHROPIC_BASE_URL")
        self.timeout_seconds = float(timeout_seconds)
        self.max_retries = int(max_retries)
        self.max_tokens = int(max_tokens)
        self._client = client
        self.prompt_hash = hashlib.sha256(SKILL_SYSTEM_INSTRUCTIONS.encode()).hexdigest()

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key or not self.base_url:
            raise RuntimeError("ANTHROPIC_API_KEY and ANTHROPIC_BASE_URL are required")
        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise RuntimeError("install dependencies with pip install -r requirements.txt") from exc
        self._client = Anthropic(
            api_key=key, base_url=self.base_url, timeout=self.timeout_seconds,
            max_retries=self.max_retries,
        )
        return self._client

    def decide(
        self, *, episode_evidence: Mapping[str, Any],
        structured_diagnosis: Mapping[str, Any],
        skills: Sequence[RecoverySkillContract], remaining_rollouts: int,
    ) -> tuple[SkillSelectionDecision, dict[str, Any]]:
        if remaining_rollouts <= 0 or not skills:
            raise ValueError("positive rollout budget and skills are required")
        skill_rows = [skill.to_dict() for skill in skills]
        validate_agent_payload(episode_evidence, structured_diagnosis, *skill_rows)
        schema = {
            "skill_id": [skill.skill_id for skill in skills] + ["stop"],
            "correction_schedule": sorted(CORRECTION_SCHEDULES),
            "hypothesis": "non-empty evidence-grounded string",
            "expected_effect": "non-empty measurable prediction",
            "verification_condition": "non-empty condition using verifier metrics",
            "confidence": "number from 0 to 1",
            "stop": "boolean",
        }
        payload = {
            "task": "MetaWorld push-v3 failure recovery",
            "prompt_version": SKILL_PROMPT_VERSION,
            "remaining_rollouts": remaining_rollouts,
            "failed_episode_evidence": dict(episode_evidence),
            "structured_diagnosis": dict(structured_diagnosis),
            "available_skills": skill_rows,
            "response_schema": schema,
        }
        start = perf_counter()
        try:
            response = self._get_client().messages.create(
                model=self.model, max_tokens=self.max_tokens,
                system=SKILL_SYSTEM_INSTRUCTIONS,
                messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            )
        except Exception as exc:
            raise RuntimeError(f"Anthropic-compatible skill request failed: {exc}") from exc
        latency_ms = (perf_counter() - start) * 1000.0
        text = "".join(
            str(getattr(block, "text", ""))
            for block in getattr(response, "content", ())
            if getattr(block, "type", None) == "text"
        ).strip()
        try:
            decision = validate_skill_decision(
                SkillSelectionDecision.from_mapping(extract_skill_decision_json(text)), skills
            )
        except ValueError as exc:
            raise RuntimeError(f"invalid skill-agent response: {exc}") from exc
        usage = getattr(response, "usage", None)
        audit = {
            "provider": "anthropic-compatible",
            "response_id": getattr(response, "id", ""),
            "model": getattr(response, "model", self.model),
            "base_url": self.base_url or "",
            "prompt_version": SKILL_PROMPT_VERSION,
            "prompt_hash": self.prompt_hash,
            "latency_ms": latency_ms,
            "usage": {
                key: getattr(usage, key) for key in ("input_tokens", "output_tokens")
                if usage is not None and hasattr(usage, key)
            },
        }
        return decision, audit

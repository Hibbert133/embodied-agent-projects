"""Strict Gate-A GLM contract for compact skill-grounding ablations."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from time import perf_counter
from typing import Any, Mapping

from src.probemem.compact_evidence import REGISTERED_SKILLS, SKILL_SEMANTICS
from src.reasoning.evidence import validate_no_oracle_evidence


INTERFACES = ("FULL_PAYLOAD", "COMPACT_EVIDENCE", "COMPACT_WITH_SKILL_SEMANTICS")
STATUSES = ("ACCEPTED", "INCONCLUSIVE", "REJECTED")
SYSTEM_PROMPT = """You are a shadow-mode rollout-level embodied action-selection agent.
Use only the supplied Agent-visible evidence and registered tool descriptions.
Predict both candidate skill outcomes and then select one registered skill or
abstain. Never infer injected fault truth, evaluator outcomes, host thresholds,
continuous actions, or skill parameters. Return exactly one JSON object matching
the schema. Your output is audited only and never controls the robot."""


def _single_json(text: str) -> Mapping[str, Any]:
    decoder = json.JSONDecoder()
    values: list[Mapping[str, Any]] = []
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, Mapping) and "selected_skill" in value and value not in values:
            values.append(value)
    if len(values) != 1:
        raise ValueError(f"expected one online decision object, found {len(values)}")
    return values[0]


@dataclass(frozen=True)
class EvidenceInterpretation:
    persistent_directional_drift: bool
    high_response_variance: bool
    evidence_sufficient: bool

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EvidenceInterpretation":
        if set(value) != {"persistent_directional_drift", "high_response_variance", "evidence_sufficient"}:
            raise ValueError("evidence interpretation has unexpected fields")
        if not all(type(value[name]) is bool for name in value):
            raise ValueError("evidence interpretation values must be booleans")
        return cls(**value)


@dataclass(frozen=True)
class SkillPrediction:
    predicted_status: str
    accept_probability: float
    confidence: float

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "SkillPrediction":
        if set(value) != {"predicted_status", "accept_probability", "confidence"}:
            raise ValueError("skill prediction has unexpected fields")
        result = cls(str(value["predicted_status"]), float(value["accept_probability"]), float(value["confidence"]))
        if result.predicted_status not in STATUSES:
            raise ValueError("unsupported predicted status")
        if not 0.0 <= result.accept_probability <= 1.0 or not 0.0 <= result.confidence <= 1.0:
            raise ValueError("probability and confidence must be in [0, 1]")
        return result


@dataclass(frozen=True)
class OnlineGroundingDecision:
    evidence_interpretation: EvidenceInterpretation
    action_predictions: Mapping[str, SkillPrediction]
    selected_skill: str | None
    abstain: bool
    reason: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "OnlineGroundingDecision":
        required = {"evidence_interpretation", "action_predictions", "selected_skill", "abstain", "reason"}
        if set(value) != required:
            raise ValueError("online grounding decision has unexpected fields")
        predictions = value["action_predictions"]
        if not isinstance(predictions, Mapping) or set(predictions) != set(REGISTERED_SKILLS):
            raise ValueError("both and only registered skills must be predicted")
        result = cls(
            EvidenceInterpretation.from_mapping(value["evidence_interpretation"]),
            {name: SkillPrediction.from_mapping(predictions[name]) for name in REGISTERED_SKILLS},
            None if value["selected_skill"] is None else str(value["selected_skill"]),
            bool(value["abstain"]),
            str(value["reason"]),
        )
        if type(value["abstain"]) is not bool or not result.reason.strip():
            raise ValueError("abstain and reason are invalid")
        if result.abstain:
            if result.selected_skill is not None or result.evidence_interpretation.evidence_sufficient:
                raise ValueError("abstention requires null skill and insufficient evidence")
        elif result.selected_skill not in REGISTERED_SKILLS or not result.evidence_interpretation.evidence_sufficient:
            raise ValueError("execution requires a registered skill and sufficient evidence")
        validate_no_oracle_evidence(result.to_dict())
        return result

    @classmethod
    def fail_closed(cls, reason: str) -> "OnlineGroundingDecision":
        neutral = SkillPrediction("INCONCLUSIVE", 0.5, 0.0)
        return cls(EvidenceInterpretation(False, False, False), {name: neutral for name in REGISTERED_SKILLS}, None, True, reason)

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_interpretation": asdict(self.evidence_interpretation),
            "action_predictions": {name: asdict(value) for name, value in self.action_predictions.items()},
            "selected_skill": self.selected_skill,
            "abstain": self.abstain,
            "reason": self.reason,
        }


class OnlineGroundingGlmPolicy:
    def __init__(self, *, model: str = "glm-5.2", base_url: str | None = None,
                 timeout_seconds: float = 300.0, max_tokens: int = 900,
                 client: Any | None = None) -> None:
        self.model = model
        self.base_url = base_url or os.environ.get("ANTHROPIC_BASE_URL")
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens
        self._client = client
        self.prompt_hash = hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest()

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key or not self.base_url:
            raise RuntimeError("ANTHROPIC_API_KEY and ANTHROPIC_BASE_URL are required")
        from anthropic import Anthropic
        self._client = Anthropic(api_key=key, base_url=self.base_url, timeout=self.timeout_seconds, max_retries=0)
        return self._client

    def request_once(self, evidence: Mapping[str, Any], *, interface: str,
                     previous_error: str | None = None) -> tuple[OnlineGroundingDecision | None, dict[str, Any]]:
        if interface not in INTERFACES:
            raise ValueError("unknown Gate-A interface")
        validate_no_oracle_evidence(evidence)
        payload: dict[str, Any] = {
            "mode": "shadow_only_no_action_execution",
            "interface": interface,
            "agent_visible_evidence": dict(evidence),
            "candidate_skills": list(REGISTERED_SKILLS),
            "allowed_outcomes": list(STATUSES),
            "response_schema": {
                "evidence_interpretation": {"persistent_directional_drift": "boolean", "high_response_variance": "boolean", "evidence_sufficient": "boolean"},
                "action_predictions": {name: {"predicted_status": "ACCEPTED | INCONCLUSIVE | REJECTED", "accept_probability": "0..1", "confidence": "0..1"} for name in REGISTERED_SKILLS},
                "selected_skill": "registered skill or null",
                "abstain": "boolean",
                "reason": "brief evidence-grounded reason",
            },
        }
        if interface == "COMPACT_WITH_SKILL_SEMANTICS":
            payload["registered_skill_semantics"] = SKILL_SEMANTICS
        if previous_error is not None:
            payload["schema_repair"] = {"previous_error": previous_error, "instruction": "Return corrected JSON only."}
        start = perf_counter()
        text = ""
        latency = 0.0
        usage_payload: dict[str, int] = {}
        try:
            response = self._get_client().messages.create(
                model=self.model, max_tokens=self.max_tokens, temperature=0.0,
                system=SYSTEM_PROMPT, messages=[{"role": "user", "content": json.dumps(payload)}],
            )
            latency = (perf_counter() - start) * 1000.0
            text = "".join(str(getattr(block, "text", "")) for block in getattr(response, "content", ()) if getattr(block, "type", None) == "text").strip()
            usage = getattr(response, "usage", None)
            usage_payload = {key: int(getattr(usage, key)) for key in ("input_tokens", "output_tokens") if usage is not None and hasattr(usage, key)}
            decision = OnlineGroundingDecision.from_mapping(_single_json(text))
            return decision, {
                "valid": True, "latency_ms": latency,
                "response_hash": hashlib.sha256(text.encode()).hexdigest(), "raw_response": text,
                "request_payload": payload,
                "usage": usage_payload,
            }
        except Exception as exc:
            if latency == 0.0:
                latency = (perf_counter() - start) * 1000.0
            return None, {
                "valid": False, "error": f"{type(exc).__name__}: {exc}",
                "latency_ms": latency, "raw_response": text,
                "request_payload": payload, "usage": usage_payload,
            }

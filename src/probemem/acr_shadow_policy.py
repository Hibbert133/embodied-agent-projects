"""Strict GLM shadow contract for action-conditional attempt reasoning."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from time import perf_counter
from typing import Any, Mapping

from src.reasoning.evidence import validate_no_oracle_evidence


CANDIDATES = ("BOUNDED_PLANAR_COMPENSATION", "INDEPENDENT_STOCHASTIC_RETRY")
DECISIONS = {"REPEAT_STOCHASTIC_RETRY", "SWITCH_TO_BOUNDED_COMPENSATION", "ABSTAIN"}
STATUSES = {"ACCEPTED", "INCONCLUSIVE", "REJECTED"}
PROMPT_VERSION = "probemem-acr-shadow-v1"
SYSTEM_PROMPT = """You are a shadow-mode attempt-level embodied reasoning agent.
Use only the supplied first-attempt Agent-visible evidence. Predict both bounded
candidate outcomes, then choose one registered discrete decision or abstain.
Never infer injected fault truth, future outcomes, thresholds, continuous robot
actions, or skill parameters. Return exactly one JSON object matching the schema.
Your decision is logged only and will not control the robot."""


def _single_json(text: str) -> Mapping[str, Any]:
    decoder = json.JSONDecoder()
    values = []
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, Mapping) and "selected_decision" in value and value not in values:
            values.append(value)
    if len(values) != 1:
        raise ValueError(f"expected one shadow decision object, found {len(values)}")
    return values[0]


@dataclass(frozen=True)
class CandidatePrediction:
    predicted_status: str
    accept_probability: float
    confidence: float

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CandidatePrediction":
        if set(value) != {"predicted_status", "accept_probability", "confidence"}:
            raise ValueError("candidate prediction has unexpected fields")
        result = cls(str(value["predicted_status"]), float(value["accept_probability"]), float(value["confidence"]))
        if result.predicted_status not in STATUSES:
            raise ValueError("invalid predicted status")
        if not 0.0 <= result.accept_probability <= 1.0 or not 0.0 <= result.confidence <= 1.0:
            raise ValueError("probability and confidence must be in [0, 1]")
        return result


@dataclass(frozen=True)
class AcrShadowDecision:
    evidence_sufficient: bool
    action_predictions: Mapping[str, CandidatePrediction]
    selected_decision: str
    reason: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "AcrShadowDecision":
        if set(value) != {"evidence_sufficient", "action_predictions", "selected_decision", "reason"}:
            raise ValueError("shadow decision has unexpected fields")
        predictions = value["action_predictions"]
        if not isinstance(predictions, Mapping) or set(predictions) != set(CANDIDATES):
            raise ValueError("both and only registered candidates must be predicted")
        result = cls(
            bool(value["evidence_sufficient"]),
            {name: CandidatePrediction.from_mapping(predictions[name]) for name in CANDIDATES},
            str(value["selected_decision"]), str(value["reason"]),
        )
        if result.selected_decision not in DECISIONS or not result.reason.strip():
            raise ValueError("invalid decision or empty reason")
        if result.selected_decision == "ABSTAIN" and result.evidence_sufficient:
            raise ValueError("abstention requires insufficient evidence")
        if result.selected_decision != "ABSTAIN" and not result.evidence_sufficient:
            raise ValueError("action selection requires sufficient evidence")
        validate_no_oracle_evidence(result.to_dict())
        return result

    @classmethod
    def fail_closed(cls, reason: str) -> "AcrShadowDecision":
        neutral = CandidatePrediction("INCONCLUSIVE", 0.5, 0.0)
        return cls(False, {name: neutral for name in CANDIDATES}, "ABSTAIN", reason)

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_sufficient": self.evidence_sufficient,
            "action_predictions": {name: asdict(value) for name, value in self.action_predictions.items()},
            "selected_decision": self.selected_decision, "reason": self.reason,
        }


class AcrGlmShadowPolicy:
    def __init__(self, *, model: str = "glm-5.2", base_url: str | None = None,
                 timeout_seconds: float = 300.0, max_tokens: int = 900, client: Any | None = None) -> None:
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
        self._client = Anthropic(api_key=key, base_url=self.base_url, timeout=self.timeout_seconds, max_retries=1)
        return self._client

    def decide(self, evidence: Mapping[str, Any], *, allow_repair: bool = True) -> tuple[AcrShadowDecision, dict[str, Any]]:
        validate_no_oracle_evidence(evidence)
        payload = {
            "mode": "shadow_only_no_action_execution", "prompt_version": PROMPT_VERSION,
            "agent_visible_evidence": dict(evidence), "candidate_actions": list(CANDIDATES),
            "allowed_decisions": sorted(DECISIONS),
            "response_schema": {
                "evidence_sufficient": "boolean",
                "action_predictions": {name: {"predicted_status": "ACCEPTED | INCONCLUSIVE | REJECTED", "accept_probability": "0..1", "confidence": "0..1"} for name in CANDIDATES},
                "selected_decision": "REPEAT_STOCHASTIC_RETRY | SWITCH_TO_BOUNDED_COMPENSATION | ABSTAIN",
                "reason": "brief evidence-grounded reason",
            },
        }
        attempts = []
        last_error = "unknown error"
        for attempt in range(2 if allow_repair else 1):
            request = payload if attempt == 0 else {**payload, "schema_repair": {"previous_error": last_error, "instruction": "Return corrected JSON only."}}
            start = perf_counter()
            text = ""
            try:
                response = self._get_client().messages.create(model=self.model, max_tokens=self.max_tokens, temperature=0.0, system=SYSTEM_PROMPT, messages=[{"role": "user", "content": json.dumps(request)}])
                latency = (perf_counter() - start) * 1000.0
                text = "".join(str(getattr(block, "text", "")) for block in getattr(response, "content", ()) if getattr(block, "type", None) == "text").strip()
                decision = AcrShadowDecision.from_mapping(_single_json(text))
                usage = getattr(response, "usage", None)
                attempts.append({"attempt_index": attempt, "valid": True, "latency_ms": latency, "response_hash": hashlib.sha256(text.encode()).hexdigest(), "raw_response": text, "usage": {key: int(getattr(usage, key)) for key in ("input_tokens", "output_tokens") if usage is not None and hasattr(usage, key)}})
                return decision, {"status": "valid", "prompt_hash": self.prompt_hash, "request_payload": payload, "attempts": attempts}
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                attempts.append({"attempt_index": attempt, "valid": False, "error": last_error, "raw_response": text})
        return AcrShadowDecision.fail_closed(f"fail-closed shadow decision: {last_error}"), {"status": "fail_closed", "prompt_hash": self.prompt_hash, "request_payload": payload, "attempts": attempts}

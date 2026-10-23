"""Bounded Anthropic-compatible policy for active evidence decisions."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from time import perf_counter
from typing import Any, Mapping

from src.reasoning import EvidencePacket
from src.uncertainty.models import EvidenceAction


PROMPT_VERSION = "active-evidence-decision-v1"
SYSTEM_PROMPT = """You are a diagnostic research agent for a robot, not a
low-level controller. Decide whether the supplied Agent-visible failed-rollout
evidence is sufficient or whether one bounded diagnostic probe is worth its
interaction cost. You never know injected fault type, axis, sign, magnitude,
perturbed action, or executed action. Do not invent such information. Return
exactly one JSON object matching the supplied schema, without Markdown or extra
text. Do not output robot actions or correction magnitudes."""


@dataclass(frozen=True)
class OnlineEvidenceDecision:
    action: EvidenceAction
    probe_kind: str
    target_uncertainty: str
    hypothesis_mechanism: str
    hypothesis_axis: str
    hypothesis_direction: str
    rationale: str
    confidence: float

    def __post_init__(self) -> None:
        if self.probe_kind not in {"symmetric_xy", "none"}:
            raise ValueError("unsupported probe_kind")
        if self.action is EvidenceAction.REQUEST_PROBE and self.probe_kind == "none":
            raise ValueError("request_probe requires a concrete probe_kind")
        if self.action is not EvidenceAction.REQUEST_PROBE and self.probe_kind != "none":
            raise ValueError("only request_probe may select a probe")
        if self.hypothesis_mechanism not in {
            "systematic_planar_bias", "stochastic_execution", "insufficient_evidence"
        }:
            raise ValueError("unsupported hypothesis mechanism")
        if self.hypothesis_axis not in {"x", "y", "unknown"}:
            raise ValueError("unsupported hypothesis axis")
        if self.hypothesis_direction not in {"positive", "negative", "unknown"}:
            raise ValueError("unsupported hypothesis direction")
        if not self.target_uncertainty.strip() or not self.rationale.strip():
            raise ValueError("decision requires target uncertainty and rationale")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("decision confidence must be in [0, 1]")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["action"] = self.action.value
        return payload

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "OnlineEvidenceDecision":
        required = {
            "action", "probe_kind", "target_uncertainty", "hypothesis_mechanism",
            "hypothesis_axis", "hypothesis_direction", "rationale", "confidence",
        }
        if set(value) != required:
            raise ValueError(
                f"decision fields must be exactly {sorted(required)}"
            )
        try:
            action = EvidenceAction(str(value["action"]))
            return cls(
                action=action,
                probe_kind=str(value["probe_kind"]),
                target_uncertainty=str(value["target_uncertainty"]),
                hypothesis_mechanism=str(value["hypothesis_mechanism"]),
                hypothesis_axis=str(value["hypothesis_axis"]),
                hypothesis_direction=str(value["hypothesis_direction"]),
                rationale=str(value["rationale"]),
                confidence=float(value["confidence"]),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid online evidence decision: {exc}") from exc


def extract_decision_json(text: str) -> Mapping[str, Any]:
    decoder = json.JSONDecoder()
    candidates = []
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and "action" in value and value not in candidates:
            candidates.append(value)
    if len(candidates) != 1:
        raise ValueError(f"expected one evidence decision object, found {len(candidates)}")
    return candidates[0]


class AnthropicEvidencePolicy:
    def __init__(
        self,
        *,
        model: str = "glm-5.2",
        base_url: str | None = None,
        timeout_seconds: float = 300.0,
        max_retries: int = 2,
        max_tokens: int = 700,
        client: Any | None = None,
    ) -> None:
        if not model.strip() or timeout_seconds <= 0 or max_retries < 0 or max_tokens <= 0:
            raise ValueError("valid model and request limits are required")
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

    def decide(
        self,
        evidence: EvidencePacket,
        *,
        available_probe_steps: int,
    ) -> tuple[OnlineEvidenceDecision, dict[str, Any]]:
        if available_probe_steps <= 0:
            raise ValueError("online evidence policy requires a positive probe budget")
        schema = {
            "action": "request_probe | update_hypothesis | abstain",
            "probe_kind": "symmetric_xy if requesting a probe, otherwise none",
            "target_uncertainty": "short string",
            "hypothesis_mechanism": (
                "systematic_planar_bias | stochastic_execution | insufficient_evidence"
            ),
            "hypothesis_axis": "x | y | unknown",
            "hypothesis_direction": "positive | negative | unknown",
            "rationale": "short evidence-grounded explanation",
            "confidence": "number in [0, 1]",
        }
        payload = {
            "task": "decide active evidence acquisition after a failed push-v3 rollout",
            "prompt_version": PROMPT_VERSION,
            "available_probe": {
                "probe_kind": "symmetric_xy",
                "cost_environment_steps": available_probe_steps,
                "purpose": "estimate common planar drift by paired directional actions",
            },
            "agent_visible_evidence": evidence.to_dict(),
            "response_schema": schema,
        }
        start = perf_counter()
        try:
            response = self._get_client().messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            )
        except Exception as exc:
            raise RuntimeError(f"online evidence API request failed: {exc}") from exc
        latency_ms = (perf_counter() - start) * 1000.0
        text = "".join(
            str(getattr(block, "text", ""))
            for block in getattr(response, "content", ())
            if getattr(block, "type", None) == "text"
        ).strip()
        if not text:
            raise RuntimeError("online evidence response did not contain text")
        try:
            decision = OnlineEvidenceDecision.from_mapping(extract_decision_json(text))
        except ValueError as exc:
            raise RuntimeError(f"invalid online evidence response: {exc}") from exc
        usage = getattr(response, "usage", None)
        audit = {
            "provider": "anthropic-compatible",
            "response_id": getattr(response, "id", ""),
            "model": getattr(response, "model", self.model),
            "base_url": self.base_url or "",
            "prompt_version": PROMPT_VERSION,
            "prompt_hash": self.prompt_hash,
            "response_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "latency_ms": latency_ms,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "usage": {
                key: getattr(usage, key)
                for key in ("input_tokens", "output_tokens")
                if usage is not None and hasattr(usage, key)
            },
        }
        return decision, audit

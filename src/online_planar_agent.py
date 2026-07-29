"""Bounded online-agent decisions for leakage-safe planar recovery."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from time import perf_counter
from typing import Any, Mapping, Sequence

import numpy as np

from src.recovery_agent import CORRECTION_SCHEDULES, DEFAULT_CORRECTION_MAGNITUDES
from src.trajectory_views import FORBIDDEN_AGENT_FIELDS


PLANAR_PROMPT_VERSION = "planar-recovery-v1"
PLANAR_DECISION_FIELDS = frozenset(
    {"repair_mode", "correction_x", "correction_y", "correction_schedule",
     "hypothesis", "expected_effect", "confidence", "stop"}
)
ONLINE_FORBIDDEN_FIELDS = FORBIDDEN_AGENT_FIELDS | frozenset(
    {"injected_bias", "injected_bias_axis", "injected_bias_sign",
     "injected_bias_magnitude", "fault_axis", "fault_sign", "fault_magnitude"}
)

PLANAR_SYSTEM_INSTRUCTIONS = """You are a bounded robotic recovery planner.
Use only the supplied agent-visible state-transition and active-probe evidence.
Never assume access to injected fault type, axis, direction, magnitude, executed
action, clipping audit, or Oracle labels. Choose one high-level planar repair;
do not produce low-level actions. Prefer the smallest evidence-supported repair
and account for the remaining rollout budget. Return exactly one JSON object."""


@dataclass(frozen=True)
class PlanarAgentDecision:
    repair_mode: str
    correction_x: float
    correction_y: float
    correction_schedule: str
    hypothesis: str
    expected_effect: str
    confidence: float
    stop: bool = False

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "PlanarAgentDecision":
        try:
            return cls(
                repair_mode=str(value["repair_mode"]),
                correction_x=float(value["correction_x"]),
                correction_y=float(value["correction_y"]),
                correction_schedule=str(value["correction_schedule"]),
                hypothesis=str(value["hypothesis"]),
                expected_effect=str(value["expected_effect"]),
                confidence=float(value["confidence"]),
                stop=bool(value["stop"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid planar decision: {exc}") from exc

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def correction(self) -> np.ndarray:
        return np.array([self.correction_x, self.correction_y, 0.0, 0.0], dtype=np.float32)


def _nested_keys(value: Any) -> set[str]:
    if isinstance(value, Mapping):
        return set(value) | set().union(*(_nested_keys(item) for item in value.values()))
    if isinstance(value, (list, tuple)):
        return set().union(*(_nested_keys(item) for item in value))
    return set()


def validate_agent_payload(*values: Mapping[str, Any]) -> None:
    leaked = ONLINE_FORBIDDEN_FIELDS & set().union(*(_nested_keys(value) for value in values))
    if leaked:
        raise ValueError(f"online Agent payload contains forbidden fields: {sorted(leaked)}")


def planar_decision_schema(levels: Sequence[float]) -> dict[str, Any]:
    signed = sorted({0.0, *(float(x) for x in levels), *(-float(x) for x in levels)})
    return {
        "repair_mode": ["dominant_only", "simultaneous", "stop"],
        "correction_x": signed,
        "correction_y": signed,
        "correction_schedule": sorted(CORRECTION_SCHEDULES),
        "hypothesis": "non-empty string grounded in visible evidence",
        "expected_effect": "non-empty string with a measurable prediction",
        "confidence": "number from 0 to 1",
        "stop": "boolean",
    }


def validate_planar_decision(
    decision: PlanarAgentDecision,
    levels: Sequence[float] = DEFAULT_CORRECTION_MAGNITUDES,
) -> PlanarAgentDecision:
    if decision.repair_mode not in {"dominant_only", "simultaneous", "stop"}:
        raise ValueError("repair_mode must be dominant_only, simultaneous, or stop")
    if decision.correction_schedule not in CORRECTION_SCHEDULES:
        raise ValueError("unknown correction_schedule")
    if not 0.0 <= decision.confidence <= 1.0:
        raise ValueError("confidence must be between 0 and 1")
    if not decision.hypothesis.strip() or not decision.expected_effect.strip():
        raise ValueError("hypothesis and expected_effect must be non-empty")
    allowed_signed = np.array(
        sorted({0.0, *(float(x) for x in levels), *(-float(x) for x in levels)}),
        dtype=float,
    )
    correction = np.array([decision.correction_x, decision.correction_y], dtype=float)
    if not all(np.any(np.isclose(value, allowed_signed, atol=1e-9)) for value in correction):
        raise ValueError("correction components must use the allowed signed grid")
    nonzero = int(np.count_nonzero(~np.isclose(correction, 0.0)))
    if decision.stop or decision.repair_mode == "stop":
        if not decision.stop or decision.repair_mode != "stop" or nonzero:
            raise ValueError("stop requires mode=stop and zero correction")
    elif decision.repair_mode == "dominant_only" and nonzero != 1:
        raise ValueError("dominant_only requires exactly one nonzero component")
    elif decision.repair_mode == "simultaneous" and nonzero != 2:
        raise ValueError("simultaneous requires two nonzero components")
    return decision


def extract_planar_decision_json(text: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    candidates: list[dict[str, Any]] = []
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and PLANAR_DECISION_FIELDS.issubset(value):
            if value not in candidates:
                candidates.append(value)
    if len(candidates) != 1:
        raise ValueError(f"expected one planar decision object, found {len(candidates)}")
    return candidates[0]


class AnthropicPlanarRecoveryAgent:
    """One-call Anthropic-compatible high-level decision adapter."""

    name = "anthropic_planar"

    def __init__(
        self, *, model: str = "glm-5.1", base_url: str | None = None,
        allowed_magnitudes: Sequence[float] = DEFAULT_CORRECTION_MAGNITUDES,
        timeout_seconds: float = 180.0, max_retries: int = 2,
        max_tokens: int = 900, client: Any | None = None,
    ) -> None:
        if not model.strip() or timeout_seconds <= 0 or max_retries < 0 or max_tokens <= 0:
            raise ValueError("model and positive request limits are required")
        self.model = model
        self.base_url = base_url or os.environ.get("ANTHROPIC_BASE_URL")
        self.allowed_magnitudes = tuple(float(x) for x in allowed_magnitudes)
        self.timeout_seconds = float(timeout_seconds)
        self.max_retries = int(max_retries)
        self.max_tokens = int(max_tokens)
        self._client = client
        prompt_material = PLANAR_SYSTEM_INSTRUCTIONS + json.dumps(
            planar_decision_schema(self.allowed_magnitudes), sort_keys=True
        )
        self.prompt_hash = hashlib.sha256(prompt_material.encode()).hexdigest()

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
        diagnostic_context: Mapping[str, Any], remaining_rollouts: int,
    ) -> tuple[PlanarAgentDecision, dict[str, Any]]:
        if remaining_rollouts <= 0:
            raise ValueError("remaining_rollouts must be positive")
        validate_agent_payload(episode_evidence, diagnostic_context)
        payload = {
            "task": "MetaWorld push-v3 planar recovery",
            "prompt_version": PLANAR_PROMPT_VERSION,
            "remaining_rollouts": remaining_rollouts,
            "decision_schema": planar_decision_schema(self.allowed_magnitudes),
            "failed_episode_evidence": dict(episode_evidence),
            "active_probe_evidence": dict(diagnostic_context),
        }
        start = perf_counter()
        try:
            response = self._get_client().messages.create(
                model=self.model, max_tokens=self.max_tokens,
                system=PLANAR_SYSTEM_INSTRUCTIONS,
                messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            )
        except Exception as exc:
            raise RuntimeError(f"Anthropic-compatible planar request failed: {exc}") from exc
        latency_ms = (perf_counter() - start) * 1000.0
        text = "".join(
            str(getattr(block, "text", ""))
            for block in getattr(response, "content", ())
            if getattr(block, "type", None) == "text"
        ).strip()
        try:
            decision = validate_planar_decision(
                PlanarAgentDecision.from_mapping(extract_planar_decision_json(text)),
                self.allowed_magnitudes,
            )
        except ValueError as exc:
            raise RuntimeError(f"invalid planar-agent response: {exc}") from exc
        usage = getattr(response, "usage", None)
        audit = {
            "provider": "anthropic-compatible",
            "response_id": getattr(response, "id", ""),
            "model": getattr(response, "model", self.model),
            "base_url": self.base_url or "",
            "prompt_version": PLANAR_PROMPT_VERSION,
            "prompt_hash": self.prompt_hash,
            "latency_ms": latency_ms,
            "usage": {
                key: getattr(usage, key) for key in ("input_tokens", "output_tokens")
                if usage is not None and hasattr(usage, key)
            },
        }
        return decision, audit

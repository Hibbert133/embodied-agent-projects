"""Leakage-safe online selector over action-conditioned recovery evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from time import perf_counter
from typing import Any, Mapping, Sequence

from src.online_planar_agent import validate_agent_payload


PROMPT_VERSION = "candidate-utility-agent-v1"
SYSTEM_PROMPT = """You are a high-level robotic recovery decision agent.
Select exactly one supplied candidate using only agent-visible initial evidence
and action-conditioned probe outcomes. Compare predicted recovery success first
and interaction cost second. Candidate probes use independent execution
realizations, so do not assume their full trajectories will repeat. Never invent
actions, corrections, schedules, fault labels, or candidates. Return exactly one
JSON object."""
DECISION_FIELDS = frozenset(
    {
        "candidate_id",
        "hypothesis",
        "expected_effect",
        "verification_condition",
        "confidence",
    }
)


@dataclass(frozen=True)
class UtilityDecision:
    """A bounded choice among supplied, executable recovery candidates."""

    candidate_id: str
    hypothesis: str
    expected_effect: str
    verification_condition: str
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def extract_decision_object(text: str) -> Mapping[str, Any]:
    """Extract exactly one schema-shaped JSON object from a model response."""

    decoder = json.JSONDecoder()
    found: list[Mapping[str, Any]] = []
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and DECISION_FIELDS.issubset(value) and value not in found:
            found.append(value)
    if len(found) != 1:
        raise ValueError(f"expected one utility decision, found {len(found)}")
    return found[0]


def validate_decision(
    value: Mapping[str, Any], candidate_ids: Sequence[str]
) -> UtilityDecision:
    """Fail closed unless the response selects one supplied candidate."""

    try:
        decision = UtilityDecision(
            candidate_id=str(value["candidate_id"]),
            hypothesis=str(value["hypothesis"]),
            expected_effect=str(value["expected_effect"]),
            verification_condition=str(value["verification_condition"]),
            confidence=float(value["confidence"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"invalid utility decision: {exc}") from exc
    if candidate_ids.count(decision.candidate_id) != 1:
        raise ValueError("candidate_id must select exactly one supplied candidate")
    reasoning = (
        decision.hypothesis,
        decision.expected_effect,
        decision.verification_condition,
    )
    if not 0.0 <= decision.confidence <= 1.0 or any(
        not field.strip() for field in reasoning
    ):
        raise ValueError("non-empty reasoning and confidence in [0, 1] required")
    return decision


class AnthropicUtilityAgent:
    """Anthropic-compatible client for one bounded candidate-selection call."""

    def __init__(
        self,
        *,
        model: str = "glm-5.2",
        base_url: str | None = None,
        timeout_seconds: float = 300,
        max_retries: int = 2,
        max_tokens: int = 900,
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
        *,
        episode_evidence: Mapping[str, Any],
        structured_diagnosis: Mapping[str, Any],
        candidates: Sequence[Mapping[str, Any]],
        candidate_probe_evidence: Sequence[Mapping[str, Any]],
        remaining_rollouts: int = 1,
    ) -> tuple[UtilityDecision, dict[str, Any]]:
        if remaining_rollouts != 1:
            raise ValueError("the protocol requires exactly one remaining rollout")
        if len(candidates) < 2 or len(candidates) != len(candidate_probe_evidence):
            raise ValueError("at least two candidates with aligned evidence are required")
        validate_agent_payload(
            episode_evidence,
            structured_diagnosis,
            *candidates,
            *candidate_probe_evidence,
        )
        candidate_ids = [str(candidate["candidate_id"]) for candidate in candidates]
        evidence_ids = {
            str(evidence["candidate_id"]) for evidence in candidate_probe_evidence
        }
        if len(set(candidate_ids)) != len(candidate_ids) or evidence_ids != set(candidate_ids):
            raise ValueError("candidate IDs must be unique and evidence-aligned")

        payload = {
            "task": "select one bounded push-v3 recovery candidate",
            "prompt_version": PROMPT_VERSION,
            "remaining_rollouts": 1,
            "failed_episode_evidence": dict(episode_evidence),
            "structured_diagnosis": dict(structured_diagnosis),
            "candidates": list(candidates),
            "action_conditioned_probe_evidence": list(candidate_probe_evidence),
            "response_schema": {
                "candidate_id": candidate_ids,
                "hypothesis": "evidence-grounded string",
                "expected_effect": "measurable prediction",
                "verification_condition": "post-rollout metric condition",
                "confidence": "number from 0 to 1",
            },
        }
        started = perf_counter()
        try:
            response = self._get_client().messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": json.dumps(payload, ensure_ascii=False),
                    }
                ],
            )
        except Exception as exc:
            raise RuntimeError(f"Anthropic-compatible utility request failed: {exc}") from exc
        latency_ms = (perf_counter() - started) * 1000.0
        text = "".join(
            str(getattr(block, "text", ""))
            for block in getattr(response, "content", ())
            if getattr(block, "type", None) == "text"
        ).strip()
        try:
            decision = validate_decision(
                extract_decision_object(text), candidate_ids
            )
        except ValueError as exc:
            raise RuntimeError(f"invalid utility-agent response: {exc}") from exc

        usage = getattr(response, "usage", None)
        audit = {
            "provider": "anthropic-compatible",
            "response_id": getattr(response, "id", ""),
            "model": getattr(response, "model", self.model),
            "base_url": self.base_url or "",
            "prompt_version": PROMPT_VERSION,
            "prompt_hash": self.prompt_hash,
            "latency_ms": latency_ms,
            "usage": {
                key: getattr(usage, key)
                for key in ("input_tokens", "output_tokens")
                if usage is not None and hasattr(usage, key)
            },
        }
        return decision, audit

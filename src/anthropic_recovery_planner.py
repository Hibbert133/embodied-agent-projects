"""Anthropic-protocol adapter for bounded recovery planning."""

from __future__ import annotations

import hashlib
import json
import os
from time import perf_counter
from typing import Any, Mapping, Sequence

from src.openai_recovery_planner import PROMPT_VERSION, SYSTEM_INSTRUCTIONS, proposal_json_schema
from src.recovery_agent import (
    DEFAULT_CORRECTION_MAGNITUDES,
    ExperimentProposal,
    PlannerHistoryItem,
    PlannerOutput,
    validate_proposal,
)


PROPOSAL_FIELDS = frozenset(
    {
        "correction_axis",
        "correction_direction",
        "correction_magnitude",
        "hypothesis",
        "expected_effect",
        "confidence",
        "stop",
    }
)


def extract_proposal_json(text: str) -> dict[str, Any]:
    """Extract one unambiguous proposal object from compatibility-model prose."""

    decoder = json.JSONDecoder()
    candidates: list[dict[str, Any]] = []
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and PROPOSAL_FIELDS.issubset(value):
            if value not in candidates:
                candidates.append(value)
    if not candidates:
        preview = text[:240].replace("\r", " ").replace("\n", " ")
        raise ValueError(f"no proposal JSON object found; response starts with {preview!r}")
    if len(candidates) != 1:
        raise ValueError(f"response contains {len(candidates)} ambiguous proposal objects")
    return candidates[0]


class AnthropicRecoveryPlanner:
    """Use an Anthropic-compatible Messages endpoint without provider truth leakage."""

    name = "anthropic"

    def __init__(
        self,
        *,
        model: str = "glm-5.1",
        base_url: str | None = None,
        allowed_magnitudes: Sequence[float] = DEFAULT_CORRECTION_MAGNITUDES,
        client: Any | None = None,
        timeout_seconds: float = 180.0,
        max_retries: int = 2,
        max_tokens: int = 800,
        diagnostic_context: Mapping[str, Any] | None = None,
    ) -> None:
        if not model.strip():
            raise ValueError("model must be non-empty")
        if max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        self.model = model
        self.base_url = base_url or os.environ.get("ANTHROPIC_BASE_URL")
        self.allowed_magnitudes = tuple(float(value) for value in allowed_magnitudes)
        self._client = client
        self.timeout_seconds = float(timeout_seconds)
        self.max_tokens = int(max_tokens)
        self.max_retries = int(max_retries)
        self.diagnostic_context = dict(diagnostic_context or {})
        prompt_material = SYSTEM_INSTRUCTIONS + json.dumps(
            proposal_json_schema(self.allowed_magnitudes), sort_keys=True
        )
        self.prompt_hash = hashlib.sha256(prompt_material.encode("utf-8")).hexdigest()

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required for the Anthropic planner")
        if not self.base_url:
            raise RuntimeError("ANTHROPIC_BASE_URL is required for a compatible endpoint")
        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise RuntimeError("install dependencies with pip install -r requirements.txt") from exc
        self._client = Anthropic(
            api_key=api_key,
            base_url=self.base_url,
            timeout=self.timeout_seconds,
            max_retries=self.max_retries,
        )
        return self._client

    @staticmethod
    def _response_text(response: Any) -> str:
        parts: list[str] = []
        for block in getattr(response, "content", ()):
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(str(block.get("text", "")))
            elif getattr(block, "type", None) == "text":
                parts.append(str(getattr(block, "text", "")))
        text = "".join(parts).strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        return text

    def propose(
        self, history: Sequence[PlannerHistoryItem], remaining_budget: int
    ) -> PlannerOutput:
        if not history or remaining_budget <= 0:
            raise ValueError("Anthropic planner requires evidence and positive remaining budget")
        payload = {
            "task": "push-v3 failure recovery",
            "prompt_version": PROMPT_VERSION,
            "remaining_rollout_budget": remaining_budget,
            "allowed_correction_magnitudes": self.allowed_magnitudes,
            "trial_history": [item.to_dict() for item in history],
            "active_probe_evidence": self.diagnostic_context or None,
        }
        schema = proposal_json_schema(self.allowed_magnitudes)
        user_prompt = (
            "Return only one JSON object matching this schema, without Markdown fences:\n"
            + json.dumps(schema, ensure_ascii=False, sort_keys=True)
            + "\nAgent-visible experiment evidence:\n"
            + json.dumps(payload, ensure_ascii=False)
        )
        start = perf_counter()
        try:
            response = self._get_client().messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=SYSTEM_INSTRUCTIONS,
                messages=[{"role": "user", "content": user_prompt}],
            )
        except Exception as exc:
            raise RuntimeError(f"Anthropic-compatible API request failed: {exc}") from exc
        latency_ms = (perf_counter() - start) * 1000.0
        text = self._response_text(response)
        if not text:
            raise RuntimeError("Anthropic-compatible response did not contain text")
        try:
            proposal = validate_proposal(
                ExperimentProposal.from_mapping(extract_proposal_json(text)),
                self.allowed_magnitudes,
            )
        except ValueError as exc:
            raise RuntimeError(
                f"Anthropic-compatible response contained an invalid proposal: {exc}"
            ) from exc

        usage = getattr(response, "usage", None)
        audit_usage = {
            key: getattr(usage, key)
            for key in ("input_tokens", "output_tokens")
            if usage is not None and hasattr(usage, key)
        }
        audit = {
            "provider": "anthropic-compatible",
            "response_id": getattr(response, "id", ""),
            "model": getattr(response, "model", self.model),
            "base_url": self.base_url or "",
            "prompt_version": PROMPT_VERSION,
            "prompt_hash": self.prompt_hash,
            "latency_ms": latency_ms,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "usage": audit_usage,
        }
        return PlannerOutput(proposal=proposal, audit=audit)

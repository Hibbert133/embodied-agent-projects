"""Optional OpenAI Responses API adapter for the bounded recovery agent."""

from __future__ import annotations

import hashlib
import json
import os
from time import perf_counter
from typing import Any, Sequence

from src.recovery_agent import (
    DEFAULT_CORRECTION_MAGNITUDES,
    EpisodeEvidence,
    ExperimentProposal,
    PlannerHistoryItem,
    PlannerOutput,
    validate_proposal,
)


PROMPT_VERSION = "push-recovery-v1"
SYSTEM_INSTRUCTIONS = """You are a high-level robotic experiment planner for MetaWorld push-v3.
You receive only agent-visible rollout evidence; the injected control bias is hidden.
Propose exactly one bounded x/y command correction for the next full rollout, or stop.
Use trajectory evidence rather than episode return alone. Never claim knowledge of the
hidden perturbation. The executor, not you, controls the robot and validates the proposal."""


def proposal_json_schema(allowed_magnitudes: Sequence[float]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "correction_axis": {"type": "string", "enum": ["x", "y", "none"]},
            "correction_direction": {
                "type": "string",
                "enum": ["positive", "negative", "none"],
            },
            "correction_magnitude": {
                "type": "number",
                "enum": [float(value) for value in allowed_magnitudes],
            },
            "hypothesis": {"type": "string", "minLength": 1},
            "expected_effect": {"type": "string", "minLength": 1},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "stop": {"type": "boolean"},
        },
        "required": [
            "correction_axis",
            "correction_direction",
            "correction_magnitude",
            "hypothesis",
            "expected_effect",
            "confidence",
            "stop",
        ],
        "additionalProperties": False,
    }


class OpenAIRecoveryPlanner:
    name = "openai"

    def __init__(
        self,
        *,
        model: str = "gpt-5.6-luna",
        reasoning_effort: str = "medium",
        allowed_magnitudes: Sequence[float] = DEFAULT_CORRECTION_MAGNITUDES,
        client: Any | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        if not model.strip():
            raise ValueError("model must be non-empty")
        if reasoning_effort not in {"none", "low", "medium", "high", "xhigh", "max"}:
            raise ValueError("unsupported reasoning effort")
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.allowed_magnitudes = tuple(float(value) for value in allowed_magnitudes)
        self._client = client
        self.timeout_seconds = float(timeout_seconds)
        self.prompt_hash = hashlib.sha256(SYSTEM_INSTRUCTIONS.encode("utf-8")).hexdigest()

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is required for the OpenAI planner")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("install dependencies with pip install -r requirements.txt") from exc
        self._client = OpenAI(timeout=self.timeout_seconds)
        return self._client

    def propose(
        self, history: Sequence[PlannerHistoryItem], remaining_budget: int
    ) -> PlannerOutput:
        if not history or remaining_budget <= 0:
            raise ValueError("OpenAI planner requires evidence and positive remaining budget")
        payload = {
            "task": "push-v3 failure recovery",
            "prompt_version": PROMPT_VERSION,
            "remaining_rollout_budget": remaining_budget,
            "allowed_correction_magnitudes": self.allowed_magnitudes,
            "trial_history": [item.to_dict() for item in history],
        }
        start = perf_counter()
        try:
            response = self._get_client().responses.create(
                model=self.model,
                instructions=SYSTEM_INSTRUCTIONS,
                input=json.dumps(payload, ensure_ascii=False),
                reasoning={"effort": self.reasoning_effort},
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "experiment_proposal",
                        "strict": True,
                        "schema": proposal_json_schema(self.allowed_magnitudes),
                    }
                },
            )
        except Exception as exc:
            raise RuntimeError(f"OpenAI Responses API request failed: {exc}") from exc
        latency_ms = (perf_counter() - start) * 1000.0
        output_text = getattr(response, "output_text", "")
        if not output_text:
            raise RuntimeError("OpenAI response did not contain output_text")
        try:
            proposal = validate_proposal(
                ExperimentProposal.from_mapping(json.loads(output_text)),
                self.allowed_magnitudes,
            )
        except (json.JSONDecodeError, ValueError) as exc:
            raise RuntimeError(f"OpenAI response contained an invalid proposal: {exc}") from exc

        usage = getattr(response, "usage", None)
        if hasattr(usage, "model_dump"):
            usage = usage.model_dump()
        elif usage is not None and not isinstance(usage, dict):
            usage = {
                key: getattr(usage, key)
                for key in ("input_tokens", "output_tokens", "total_tokens")
                if hasattr(usage, key)
            }
        audit = {
            "provider": "openai",
            "response_id": getattr(response, "id", ""),
            "model": getattr(response, "model", self.model),
            "prompt_version": PROMPT_VERSION,
            "prompt_hash": self.prompt_hash,
            "reasoning_effort": self.reasoning_effort,
            "latency_ms": latency_ms,
            "usage": usage or {},
        }
        return PlannerOutput(proposal=proposal, audit=audit)

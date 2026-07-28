"""Optional OpenAI Responses API adapter for the bounded recovery agent."""

from __future__ import annotations

import hashlib
import json
import os
from time import perf_counter
from typing import Any, Mapping, Sequence

from src.recovery_agent import (
    DEFAULT_CORRECTION_MAGNITUDES,
    EpisodeEvidence,
    ExperimentProposal,
    PlannerHistoryItem,
    PlannerOutput,
    validate_proposal,
)


PROMPT_VERSION = "push-recovery-v2-causal"
SYSTEM_INSTRUCTIONS = """You are a high-level robotic experiment planner for MetaWorld push-v3.

Semantics and coordinate system:
- commanded_action=[dx,dy,dz,gripper] is the policy command, not the hidden executed action.
- positive/negative x and y are MuJoCo world-frame command directions.
- each transition is state_t + commanded_action_t -> state_t+1.
- task metrics are computed from state_t+1 and distances are metres.

Evidence boundary:
- You receive only causally available Agent View summaries and optional active-probe evidence.
- The injected control bias, perturbed action, executed action, and clipping audit are hidden.
- Treat a bias axis/sign as a hypothesis inferred from observed motion; never claim it as fact.

Decision procedure:
1. Prioritize object-goal distance, signed object/goal geometry, contact distance, progress,
   lateral drift, state displacement, and active-probe transitions. Return is auxiliary.
2. Distinguish failure before contact, wrong pushing direction, overshoot/lateral drift, and
   near-success. Do not infer control error solely from final reward.
3. Under an additive-bias hypothesis, a compensating correction should oppose the inferred
   drift direction. State the observed evidence and causal assumption in `hypothesis`.
4. Review earlier proposals and outcomes. Do not repeat an ineffective setting unless the
   evidence explicitly supports replication.
5. Propose exactly one allowed x/y correction for the next full rollout, or stop when evidence
   is insufficient or the remaining budget should not be spent.

Output only the schema-conforming proposal. The executor validates and applies it; you never
control the robot directly."""


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
        diagnostic_context: Mapping[str, Any] | None = None,
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
        self.diagnostic_context = dict(diagnostic_context or {})
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
            "active_probe_evidence": self.diagnostic_context or None,
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

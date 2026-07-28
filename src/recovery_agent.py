"""Leakage-safe, budgeted high-level recovery agents for push-v3."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable, Mapping, Protocol, Sequence

import numpy as np

from src.rollout import EpisodeResult
from src.trajectory_views import build_agent_view


DEFAULT_CORRECTION_MAGNITUDES = (0.0, 0.02, 0.04, 0.06, 0.08, 0.10, 0.12, 0.145, 0.16)


@dataclass(frozen=True)
class EpisodeEvidence:
    """Compact evidence derived only from validated schema-v2 Agent Views."""

    seed: int
    success: bool
    steps: int
    episode_return: float
    final_object_goal_distance: float
    minimum_gripper_object_distance: float
    object_displacement: float
    progress_to_goal: float
    lateral_drift: float
    mean_commanded_action: tuple[float, float, float, float]
    net_gripper_displacement: tuple[float, float, float]
    final_object_position: tuple[float, float, float]
    goal_position: tuple[float, float, float]
    temporal_summary: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExperimentProposal:
    correction_axis: str
    correction_direction: str
    correction_magnitude: float
    hypothesis: str
    expected_effect: str
    confidence: float
    stop: bool = False

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ExperimentProposal":
        try:
            return cls(
                correction_axis=str(value["correction_axis"]),
                correction_direction=str(value["correction_direction"]),
                correction_magnitude=float(value["correction_magnitude"]),
                hypothesis=str(value["hypothesis"]),
                expected_effect=str(value["expected_effect"]),
                confidence=float(value["confidence"]),
                stop=bool(value["stop"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid experiment proposal: {exc}") from exc

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PlannerOutput:
    proposal: ExperimentProposal
    audit: dict[str, Any]


@dataclass(frozen=True)
class PlannerHistoryItem:
    """What the agent tried and subsequently observed; contains no Oracle fields."""

    trial: int
    proposal: ExperimentProposal
    evidence: EpisodeEvidence

    def to_dict(self) -> dict[str, Any]:
        return {
            "trial": self.trial,
            "proposal": self.proposal.to_dict(),
            "evidence": self.evidence.to_dict(),
        }


class RecoveryPlanner(Protocol):
    name: str

    def propose(
        self, history: Sequence[PlannerHistoryItem], remaining_budget: int
    ) -> PlannerOutput: ...


@dataclass(frozen=True)
class TrialOutcome:
    result: EpisodeResult
    agent_records: tuple[dict[str, Any], ...]
    trajectory_path: str = ""
    video_path: str = ""


@dataclass(frozen=True)
class RecoveryTrial:
    trial: int
    proposal: ExperimentProposal
    correction: tuple[float, float, float, float]
    evidence: EpisodeEvidence
    episode_result: EpisodeResult
    trajectory_path: str
    video_path: str
    planner_audit: dict[str, Any]


@dataclass(frozen=True)
class RecoveryResult:
    success: bool
    trials_used: int
    environment_steps: int
    trials: tuple[RecoveryTrial, ...]


TrialRunner = Callable[[int, np.ndarray], TrialOutcome]
TrialObserver = Callable[[RecoveryTrial], None]


def build_episode_evidence(records: Sequence[Mapping[str, Any]]) -> EpisodeEvidence:
    """Validate and summarize a trajectory without exposing Oracle-only fields."""

    if not records:
        raise ValueError("cannot build evidence from an empty trajectory")
    views = [build_agent_view(record) for record in records]
    expected_steps = list(range(1, len(views) + 1))
    if [int(view["step"]) for view in views] != expected_steps:
        raise ValueError("trajectory steps must be consecutive and start at 1")
    for previous, current in zip(views, views[1:]):
        if not np.allclose(previous["next_observation"], current["observation"]):
            raise ValueError("trajectory state transitions are not continuous")

    final_metrics = views[-1]["task_progress_metrics"]
    first_metrics = views[0]["task_progress_metrics"]
    required_metrics = {
        "object_goal_distance",
        "gripper_object_distance",
        "object_displacement_from_start",
        "progress_to_goal",
        "lateral_drift",
        "object_position",
        "goal_position",
    }
    missing = required_metrics - set(final_metrics)
    if missing:
        raise ValueError(f"task progress metrics missing fields: {sorted(missing)}")

    indices = sorted({0, len(views) // 2, len(views) - 1})
    temporal_summary = tuple(
        {
            "step": int(views[index]["step"]),
            "success": bool(views[index]["success"]),
            "task_progress_metrics": views[index]["task_progress_metrics"],
        }
        for index in indices
    )
    return EpisodeEvidence(
        seed=int(views[0]["seed"]),
        success=bool(views[-1]["success"]),
        steps=len(views),
        episode_return=sum(float(view["reward"]) for view in views),
        final_object_goal_distance=float(final_metrics["object_goal_distance"]),
        minimum_gripper_object_distance=min(
            float(view["task_progress_metrics"]["gripper_object_distance"])
            for view in views
        ),
        object_displacement=float(final_metrics["object_displacement_from_start"]),
        progress_to_goal=float(final_metrics["progress_to_goal"]),
        lateral_drift=float(final_metrics["lateral_drift"]),
        mean_commanded_action=tuple(
            float(x)
            for x in np.mean(
                np.asarray([view["commanded_action"] for view in views], dtype=float),
                axis=0,
            )
        ),
        net_gripper_displacement=tuple(
            float(x)
            for x in (
                np.asarray(final_metrics["gripper_position"], dtype=float)
                - np.asarray(first_metrics["gripper_position"], dtype=float)
            )
        ),
        final_object_position=tuple(float(x) for x in final_metrics["object_position"]),
        goal_position=tuple(float(x) for x in final_metrics["goal_position"]),
        temporal_summary=temporal_summary,
    )


def validate_proposal(
    proposal: ExperimentProposal,
    allowed_magnitudes: Sequence[float] = DEFAULT_CORRECTION_MAGNITUDES,
) -> ExperimentProposal:
    if proposal.correction_axis not in {"x", "y", "none"}:
        raise ValueError("correction_axis must be x, y, or none")
    if proposal.correction_direction not in {"positive", "negative", "none"}:
        raise ValueError("correction_direction must be positive, negative, or none")
    if not 0.0 <= proposal.confidence <= 1.0:
        raise ValueError("confidence must be between 0 and 1")
    if not proposal.hypothesis.strip() or not proposal.expected_effect.strip():
        raise ValueError("hypothesis and expected_effect must be non-empty")
    if proposal.stop:
        if (
            proposal.correction_axis != "none"
            or proposal.correction_direction != "none"
            or proposal.correction_magnitude != 0.0
        ):
            raise ValueError("a stop proposal must use none/none/0 correction")
        return proposal
    if proposal.correction_axis == "none" or proposal.correction_direction == "none":
        raise ValueError("non-stop proposals require an axis and direction")
    matches = [
        float(level)
        for level in allowed_magnitudes
        if np.isclose(proposal.correction_magnitude, level, atol=1e-9)
    ]
    if not matches or matches[0] <= 0.0:
        raise ValueError(
            f"correction_magnitude must be a positive allowed value: {tuple(allowed_magnitudes)}"
        )
    return ExperimentProposal(
        **{**proposal.to_dict(), "correction_magnitude": matches[0]}
    )


def proposal_to_correction(proposal: ExperimentProposal) -> np.ndarray:
    correction = np.zeros(4, dtype=np.float32)
    if proposal.stop or proposal.correction_axis == "none":
        return correction
    axis = 0 if proposal.correction_axis == "x" else 1
    sign = 1.0 if proposal.correction_direction == "positive" else -1.0
    correction[axis] = sign * proposal.correction_magnitude
    return correction


class CompensatedPolicy:
    """Make a fixed high-level correction part of the policy command."""

    def __init__(self, base_policy: Any, correction: Sequence[float]) -> None:
        self.base_policy = base_policy
        self.correction = np.asarray(correction, dtype=np.float32)
        if self.correction.shape != (4,):
            raise ValueError("correction must be a four-dimensional action vector")
        if self.correction[2] != 0.0 or self.correction[3] != 0.0:
            raise ValueError("recovery corrections may only affect x or y")

    def get_action(self, observation: np.ndarray) -> np.ndarray:
        action = np.asarray(self.base_policy.get_action(observation), dtype=np.float32)
        if action.shape != (4,):
            raise ValueError("base policy must return a four-dimensional action")
        return action + self.correction


class RandomRecoveryPlanner:
    name = "random"

    def __init__(
        self,
        seed: int,
        allowed_magnitudes: Sequence[float] = DEFAULT_CORRECTION_MAGNITUDES,
    ) -> None:
        self._rng = np.random.default_rng(int(seed))
        self.allowed_magnitudes = tuple(float(x) for x in allowed_magnitudes if x > 0)
        if not self.allowed_magnitudes:
            raise ValueError("random planner requires positive correction magnitudes")

    def propose(
        self, history: Sequence[PlannerHistoryItem], remaining_budget: int
    ) -> PlannerOutput:
        del history
        if remaining_budget <= 0:
            raise ValueError("remaining_budget must be positive")
        proposal = ExperimentProposal(
            correction_axis=("x", "y")[int(self._rng.integers(0, 2))],
            correction_direction=("positive", "negative")[int(self._rng.integers(0, 2))],
            correction_magnitude=float(self._rng.choice(self.allowed_magnitudes)),
            hypothesis="Random-search control proposal.",
            expected_effect="Establish an unbiased search baseline.",
            confidence=0.0,
        )
        return PlannerOutput(validate_proposal(proposal, self.allowed_magnitudes), {})


class NoRecoveryPlanner:
    """Ablation that stops after observing the initial failed rollout."""

    name = "none"

    def propose(
        self, history: Sequence[PlannerHistoryItem], remaining_budget: int
    ) -> PlannerOutput:
        if not history or remaining_budget <= 0:
            raise ValueError("no-recovery planner requires evidence and positive remaining budget")
        proposal = ExperimentProposal(
            correction_axis="none",
            correction_direction="none",
            correction_magnitude=0.0,
            hypothesis="No-recovery ablation stops after the initial rollout.",
            expected_effect="Measure performance without adaptation.",
            confidence=1.0,
            stop=True,
        )
        return PlannerOutput(validate_proposal(proposal), {})


class RuleBasedRecoveryPlanner:
    name = "rule_based"

    def __init__(
        self,
        allowed_magnitudes: Sequence[float] = DEFAULT_CORRECTION_MAGNITUDES,
    ) -> None:
        self.allowed_magnitudes = tuple(float(x) for x in allowed_magnitudes if x > 0)
        if not self.allowed_magnitudes:
            raise ValueError("rule planner requires positive correction magnitudes")

    def propose(
        self, history: Sequence[PlannerHistoryItem], remaining_budget: int
    ) -> PlannerOutput:
        if not history or remaining_budget <= 0:
            raise ValueError("rule planner requires evidence and positive remaining budget")
        latest = history[-1].evidence
        error = np.asarray(latest.goal_position[:2]) - np.asarray(
            latest.final_object_position[:2]
        )
        axis_index = int(np.argmax(np.abs(error)))
        target = min(self.allowed_magnitudes, key=lambda value: abs(value - abs(error[axis_index])))
        axis = ("x", "y")[axis_index]
        direction = "positive" if error[axis_index] >= 0 else "negative"
        proposal = ExperimentProposal(
            correction_axis=axis,
            correction_direction=direction,
            correction_magnitude=target,
            hypothesis=f"The final object position has its largest planar goal error on {axis}.",
            expected_effect=f"Reduce the signed {axis}-axis goal error on the next rollout.",
            confidence=min(1.0, abs(float(error[axis_index])) / 0.15),
        )
        attempted = {
            (
                item.proposal.correction_axis,
                item.proposal.correction_direction,
                item.proposal.correction_magnitude,
            )
            for item in history
        }
        if (
            proposal.correction_axis,
            proposal.correction_direction,
            proposal.correction_magnitude,
        ) in attempted:
            alternatives = [
                value for value in self.allowed_magnitudes
                if (axis, direction, value) not in attempted
            ]
            if alternatives:
                proposal = ExperimentProposal(
                    **{**proposal.to_dict(), "correction_magnitude": min(
                        alternatives, key=lambda value: abs(value - abs(error[axis_index]))
                    ), "hypothesis": proposal.hypothesis + " The previous setting did not recover, so try the nearest untested magnitude."}
                )
        return PlannerOutput(validate_proposal(proposal, self.allowed_magnitudes), {})


class OracleRecoveryPlanner:
    """Audit-only upper bound that receives the hidden injected bias."""

    name = "oracle"

    def __init__(
        self,
        hidden_bias: Sequence[float],
        allowed_magnitudes: Sequence[float] = DEFAULT_CORRECTION_MAGNITUDES,
    ) -> None:
        self.hidden_bias = np.asarray(hidden_bias, dtype=float)
        if self.hidden_bias.shape != (4,) or np.count_nonzero(self.hidden_bias[:2]) != 1:
            raise ValueError("oracle expects a single-axis x/y hidden bias")
        self.allowed_magnitudes = tuple(float(x) for x in allowed_magnitudes if x > 0)

    def propose(
        self, history: Sequence[PlannerHistoryItem], remaining_budget: int
    ) -> PlannerOutput:
        del history
        if remaining_budget <= 0:
            raise ValueError("remaining_budget must be positive")
        axis_index = int(np.flatnonzero(self.hidden_bias[:2])[0])
        correction = -float(self.hidden_bias[axis_index])
        magnitude = min(self.allowed_magnitudes, key=lambda value: abs(value - abs(correction)))
        proposal = ExperimentProposal(
            correction_axis=("x", "y")[axis_index],
            correction_direction="positive" if correction > 0 else "negative",
            correction_magnitude=magnitude,
            hypothesis="Oracle upper bound uses the hidden injected bias.",
            expected_effect="Cancel the known control bias.",
            confidence=1.0,
        )
        return PlannerOutput(validate_proposal(proposal, self.allowed_magnitudes), {"oracle": True})


def run_budgeted_recovery(
    planner: RecoveryPlanner,
    trial_runner: TrialRunner,
    *,
    max_trials: int = 5,
    allowed_magnitudes: Sequence[float] = DEFAULT_CORRECTION_MAGNITUDES,
    trial_observer: TrialObserver | None = None,
) -> RecoveryResult:
    """Run an initial uncorrected trial followed by bounded recovery trials."""

    if max_trials <= 0:
        raise ValueError("max_trials must be positive")
    history: list[PlannerHistoryItem] = []
    trials: list[RecoveryTrial] = []
    proposal = ExperimentProposal(
        correction_axis="none",
        correction_direction="none",
        correction_magnitude=0.0,
        hypothesis="Initial uncorrected rollout.",
        expected_effect="Measure the failure before recovery.",
        confidence=1.0,
    )
    correction = np.zeros(4, dtype=np.float32)
    audit: dict[str, Any] = {"initial_trial": True}

    for trial_index in range(1, max_trials + 1):
        outcome = trial_runner(trial_index, correction.copy())
        evidence = build_episode_evidence(outcome.agent_records)
        history.append(PlannerHistoryItem(trial_index, proposal, evidence))
        completed_trial = RecoveryTrial(
                trial=trial_index,
                proposal=proposal,
                correction=tuple(float(x) for x in correction),
                evidence=evidence,
                episode_result=outcome.result,
                trajectory_path=outcome.trajectory_path,
                video_path=outcome.video_path,
                planner_audit=audit,
            )
        trials.append(completed_trial)
        if trial_observer is not None:
            trial_observer(completed_trial)
        if outcome.result.success or trial_index == max_trials:
            break
        output = planner.propose(history, max_trials - trial_index)
        proposal = validate_proposal(output.proposal, allowed_magnitudes)
        audit = dict(output.audit)
        if proposal.stop:
            break
        correction = proposal_to_correction(proposal)

    return RecoveryResult(
        success=trials[-1].evidence.success,
        trials_used=len(trials),
        environment_steps=sum(trial.evidence.steps for trial in trials),
        trials=tuple(trials),
    )

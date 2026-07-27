"""Execute complete MetaWorld push episodes with optional artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

import imageio.v2 as imageio
import numpy as np

from src.trajectory import TrajectoryRecorder
from src.perturbations import ActionPerturbation, IdentityPerturbation


@dataclass(frozen=True)
class EpisodeResult:
    success: bool
    steps: int
    episode_return: float
    elapsed_time_ms: float
    clip_count: int
    clip_fraction: float


def create_push_environment(seed: int, render_mode: str | None = None) -> Any:
    try:
        import gymnasium as gym
        import metaworld  # noqa: F401 - registers MetaWorld environments
    except ImportError as exc:
        raise RuntimeError(
            "Dependencies are missing; run pip install -r requirements.txt"
        ) from exc
    return gym.make(
        "Meta-World/MT1",
        env_name="push-v3",
        render_mode=render_mode,
        seed=seed,
    )


def create_push_policy() -> Any:
    try:
        from metaworld.policies import SawyerPushV3Policy
    except ImportError as exc:
        raise RuntimeError(
            "Dependencies are missing; run pip install -r requirements.txt"
        ) from exc
    return SawyerPushV3Policy()


def _validate_frame(frame: Any) -> np.ndarray:
    if not isinstance(frame, np.ndarray):
        raise RuntimeError(
            f"env.render() did not return a numpy array: {type(frame).__name__}"
        )
    if frame.ndim != 3 or frame.shape[2] != 3:
        raise RuntimeError(f"expected an HxWx3 RGB frame, got shape={frame.shape}")
    if frame.dtype != np.uint8:
        frame = np.clip(frame, 0, 255).astype(np.uint8)
    return frame


def run_episode(
    env: Any,
    policy: Any,
    *,
    seed: int,
    max_steps: int,
    episode_id: int = 1,
    trajectory_path: Path | None = None,
    video_path: Path | None = None,
    fps: int = 30,
    stop_on_success: bool = True,
    perturbation: ActionPerturbation | None = None,
) -> EpisodeResult:
    """Run one episode, stopping at first success by default.

    Elapsed time covers ``reset`` and the episode loop. Final JSONL/video file
    replacement happens after the measurement. Baseline evaluation has no video.
    """

    if max_steps <= 0 or fps <= 0:
        raise ValueError("max_steps and fps must be positive integers")

    recorder = TrajectoryRecorder(episode_id=episode_id, seed=seed)
    writer: Any | None = None
    temporary_video: Path | None = None
    output_video: Path | None = None
    success = False
    steps_run = 0
    episode_return = 0.0
    clip_count = 0
    active_perturbation = perturbation or IdentityPerturbation()

    try:
        if video_path is not None:
            output_video = video_path.expanduser().resolve()
            output_video.parent.mkdir(parents=True, exist_ok=True)
            temporary_video = output_video.with_name(
                f".{output_video.stem}.tmp{output_video.suffix}"
            )
            writer = imageio.get_writer(
                temporary_video,
                format="FFMPEG",
                mode="I",
                fps=fps,
                codec="libx264",
                pixelformat="yuv420p",
                macro_block_size=1,
            )

        start_time = perf_counter()
        observation, _ = env.reset(seed=seed)
        active_perturbation.reset(seed)
        if writer is not None:
            writer.append_data(_validate_frame(env.render()))

        for step in range(1, max_steps + 1):
            observation_before_action = np.asarray(observation).copy()
            raw_action = np.asarray(
                policy.get_action(observation), dtype=np.float32
            )
            perturbed_action = np.asarray(
                active_perturbation.apply(raw_action), dtype=np.float32
            )
            if perturbed_action.shape != raw_action.shape:
                raise ValueError(
                    "perturbation changed action shape from "
                    f"{raw_action.shape} to {perturbed_action.shape}"
                )
            executed_action = np.clip(
                perturbed_action, env.action_space.low, env.action_space.high
            )
            was_clipped = bool(np.any(perturbed_action != executed_action))
            clip_count += int(was_clipped)
            observation, reward, terminated, truncated, info = env.step(
                executed_action
            )
            step_success = bool(info.get("success", False))
            success = success or step_success
            episode_return += float(reward)
            steps_run = step

            recorder.record_transition(
                step=step,
                observation=observation_before_action,
                action=executed_action,
                raw_action=raw_action,
                perturbed_action=perturbed_action,
                executed_action=executed_action,
                was_clipped=was_clipped,
                reward=reward,
                success=success,
                terminated=terminated,
                truncated=truncated,
            )
            if writer is not None:
                writer.append_data(_validate_frame(env.render()))

            if (stop_on_success and success) or terminated or truncated:
                break

        elapsed_time_ms = (perf_counter() - start_time) * 1000.0

        if writer is not None:
            writer.close()
            writer = None
            assert temporary_video is not None and output_video is not None
            if not temporary_video.is_file() or temporary_video.stat().st_size == 0:
                raise RuntimeError("the video encoder did not create a valid file")
            temporary_video.replace(output_video)

        if trajectory_path is not None:
            recorder.save_jsonl(trajectory_path)
    finally:
        if writer is not None:
            writer.close()
        if temporary_video is not None and temporary_video.exists():
            temporary_video.unlink()

    return EpisodeResult(
        success=success,
        steps=steps_run,
        episode_return=episode_return,
        elapsed_time_ms=elapsed_time_ms,
        clip_count=clip_count,
        clip_fraction=clip_count / steps_run if steps_run else 0.0,
    )

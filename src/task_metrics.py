"""Push-v3 progress metrics derived from MetaWorld 3.1.1 observations.

SawyerXYZEnv._get_obs constructs 39 values: current 18, previous 18, goal 3.
Current hand is [0:3], current object is [4:7], and goal is [-3:].
SawyerPushEnvV3.compute_reward independently confirms object = obs[4:7].
Distances are in MuJoCo metres.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Sequence, Any
import numpy as np

@dataclass(frozen=True)
class PushStepMetrics:
    gripper_position: list[float]; object_position: list[float]; goal_position: list[float]
    gripper_object_distance: float; object_goal_distance: float
    object_displacement_from_start: float; progress_to_goal: float; lateral_drift: float
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class PushEpisodeMetrics:
    final_object_goal_distance: float; minimum_gripper_object_distance: float
    object_displacement: float; progress_to_goal: float

def extract_push_positions(observation: Sequence[float]) -> tuple[np.ndarray,np.ndarray,np.ndarray]:
    obs=np.asarray(observation,dtype=float).reshape(-1)
    if obs.size != 39: raise ValueError(f"push-v3 observation must have 39 values, got {obs.size}")
    return obs[0:3].copy(), obs[4:7].copy(), obs[-3:].copy()

def compute_push_step_metrics(observation: Sequence[float], initial_observation: Sequence[float]) -> PushStepMetrics:
    grip,obj,goal=extract_push_positions(observation); _,initial_obj,initial_goal=extract_push_positions(initial_observation)
    if not np.allclose(goal, initial_goal): raise ValueError("goal changed within episode")
    initial_distance=float(np.linalg.norm(initial_obj-goal)); current=float(np.linalg.norm(obj-goal))
    line=goal[:2]-initial_obj[:2]; denom=float(np.linalg.norm(line))
    lateral=0.0 if denom == 0 else abs(float(line[0]*(initial_obj[1]-obj[1])-line[1]*(initial_obj[0]-obj[0])))/denom
    return PushStepMetrics(grip.tolist(),obj.tolist(),goal.tolist(),float(np.linalg.norm(grip-obj)),current,float(np.linalg.norm(obj-initial_obj)),initial_distance-current,lateral)

def summarize_push_episode(records: Sequence[PushStepMetrics]) -> PushEpisodeMetrics:
    if not records: raise ValueError("cannot summarize empty metrics")
    last=records[-1]
    return PushEpisodeMetrics(last.object_goal_distance,min(x.gripper_object_distance for x in records),last.object_displacement_from_start,last.progress_to_goal)

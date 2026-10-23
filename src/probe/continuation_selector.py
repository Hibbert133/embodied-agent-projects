"""Standard empirical continuation-cost selection on a strict eight-step Agent View.

RBF ridge and nearest-neighbour regression are reference algorithms, not novel
methods. Training outcomes are separately labelled offline supervision. Neither
fitted means nor the local covariance confers a physical/probability guarantee.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import numpy as np

from src.probe.task_value_learner import KernelModel

TASKS = ("push-v3", "reach-v3", "door-open-v3")
BRANCHES = ("DIRECT_G8", "PASSIVE_G16", "POINT16_CYCLE", "UPDATE_G16", "KEEP_G8_AFTER16")
SELECTORS = ("MEAN_COST_RBF", "MEAN_COST_NEAREST", "TASK_MEAN", "SINGLE_FUTURE_RBF")
INITIAL_SELECTOR = "TASK_FULL_PORTFOLIO"
LEARNED_METHODS = SELECTORS + (INITIAL_SELECTOR,)
FULL_BRANCHES = ("NO_PROBE", *BRANCHES, "POINT16_WIDE")
FEATURE_COUNT = 28


def finite(value, shape):
    array = np.asarray(value, float)
    if array.shape != shape or not np.isfinite(array).all():
        raise ValueError("finite registered visible shape required")
    return array


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class ContinuationEvidence:
    task: str
    observations: tuple
    commands: tuple
    reference_mean: tuple
    reference_covariance: tuple
    current_raw_policy: tuple
    remaining_steps: int

    def __post_init__(self):
        if self.task not in TASKS or type(self.remaining_steps) is not int or not 0 <= self.remaining_steps <= 492:
            raise ValueError("registered task and causal budget required")
        observations = finite(self.observations, (9, 39))
        commands = finite(self.commands, (8, 4))
        expected = np.asarray([v for v in ((.4,0,0,0),(-.4,0,0,0),(0,.4,0,0),(0,-.4,0,0)) for _ in range(2)], np.float32)
        if not np.array_equal(commands, expected.astype(float)):
            raise ValueError("exact actual eight-step probe required")
        mean = finite(self.reference_mean, (6,))
        covariance = finite(self.reference_covariance, (6, 6))
        if not np.allclose(covariance, covariance.T, atol=1e-12, rtol=0) or np.linalg.eigvalsh(covariance)[0] <= 0:
            raise ValueError("positive definite visible reference required")
        raw = finite(self.current_raw_policy, (4,))
        for name, value in (("observations", observations), ("commands", commands), ("reference_covariance", covariance)):
            object.__setattr__(self, name, tuple(tuple(float(x) for x in row) for row in value))
        object.__setattr__(self, "reference_mean", tuple(mean.tolist()))
        object.__setattr__(self, "current_raw_policy", tuple(raw.tolist()))

    @classmethod
    def from_dict(cls, value):
        if type(value) is not dict or set(value) != set(cls.__dataclass_fields__):
            raise ValueError("unknown or privileged evidence field")
        return cls(**value)

    def features(self):
        obs = np.asarray(self.observations)
        scale = np.array((1.,1.,.3,1.,1.,.3))
        hand, obj, goal = obs[-1,:3], obs[-1,4:7], obs[-1,-3:]
        result = np.concatenate((np.asarray(self.reference_mean)/scale,
                                 np.log1p(np.diag(self.reference_covariance)/(scale*scale)),
                                 (goal-hand)/.1, (goal-obj)/.1, (obj-hand)/.1,
                                 (obs[-1,:3]-obs[-2,:3])/.01, np.clip(self.current_raw_policy,-1,1)))
        return finite(result, (FEATURE_COUNT,))

    @property
    def sha256(self):
        return digest(asdict(self))


@dataclass(frozen=True)
class TrainingCase:
    case_id: str
    source_group: int
    evidence: ContinuationEvidence
    branch_future_losses: tuple

    def __post_init__(self):
        if type(self.case_id) is not str or not self.case_id or type(self.source_group) is not int or self.source_group not in range(8) or type(self.evidence) is not ContinuationEvidence:
            raise ValueError("offline source identity and strict visible evidence required")
        losses = finite(self.branch_future_losses, (7,4))
        if np.any(losses < 0) or np.any(losses > 500):
            raise ValueError("seven branches and four bounded offline outcomes required")
        object.__setattr__(self, "branch_future_losses", tuple(tuple(row) for row in losses.tolist()))


def train(cases):
    if len(cases) != 24 or any(type(c) is not TrainingCase for c in cases) or len({c.case_id for c in cases}) != 24:
        raise ValueError("complete fixed twenty-four-context source required")
    expected = {(s,t) for s in range(8) for t in TASKS}
    if {(c.source_group,c.evidence.task) for c in cases} != expected:
        raise ValueError("complete eight-source-group/task design required")
    tasks = {}
    for task in TASKS:
        rows = sorted((c for c in cases if c.evidence.task == task), key=lambda c:c.source_group)
        x = np.array([c.evidence.features() for c in rows])
        losses = np.array([c.branch_future_losses for c in rows])
        feasible = losses[:,[FULL_BRANCHES.index(m) for m in BRANCHES],:]
        paired = feasible[:,1:,:] - feasible[:,:1,:]
        averaged, single = paired.mean(axis=2)/500., paired[:,:,0]/500.
        rbf, single_rbf = KernelModel.fit(x,averaged), KernelModel.fit(x,single)
        tasks[task] = {"mean_rbf": rbf.saved(), "single_rbf": single_rbf.saved(),
                       "source_targets": averaged.tolist(), "task_mean": averaged.mean(axis=0).tolist(),
                       "source_case_ids": [c.case_id for c in rows],
                       "initial_mean_losses": losses.mean(axis=(0,2)).tolist()}
    return {"schema":"causal-continuation-model-v1", "branches":list(BRANCHES), "initial_branches":list(FULL_BRANCHES), "feature_count":FEATURE_COUNT,
            "source_contexts":24, "source_groups":8, "source_futures":4,
            "ridge":1., "hyperparameter_searches":0, "tasks":tasks,
            "algorithm_novelty":False, "physical_response_qualified":False, "probability_guarantee":False}


def validate_model(artifact):
    allowed = {"schema","branches","initial_branches","feature_count","source_contexts","source_groups","source_futures","ridge",
               "hyperparameter_searches","tasks","algorithm_novelty","physical_response_qualified","probability_guarantee"}
    if type(artifact) is not dict or set(artifact) != allowed or artifact["schema"] != "causal-continuation-model-v1":
        raise ValueError("registered learned-model schema required")
    expected = {"branches":list(BRANCHES),"initial_branches":list(FULL_BRANCHES),"feature_count":28,"source_contexts":24,"source_groups":8,
                "source_futures":4,"ridge":1.,"hyperparameter_searches":0,"algorithm_novelty":False,
                "physical_response_qualified":False,"probability_guarantee":False}
    if any(artifact[k] != v for k,v in expected.items()) or set(artifact["tasks"]) != set(TASKS):
        raise ValueError("registered empirical learner scope required")
    for value in artifact["tasks"].values():
        if set(value) != {"mean_rbf","single_rbf","source_targets","task_mean","source_case_ids","initial_mean_losses"}:
            raise ValueError("unknown model field")
        for key in ("mean_rbf","single_rbf"):
            model = KernelModel.from_saved(value[key])
            if model.support.shape != (8,28) or model.target_mean.shape != (4,):
                raise ValueError("complete task-specific reference model required")
        finite(value["source_targets"], (8,4)); finite(value["task_mean"], (4,))
        initial = finite(value["initial_mean_losses"], (7,))
        if np.any(initial<0) or np.any(initial>500): raise ValueError("bounded initial-source losses required")
        if len(value["source_case_ids"]) != 8 or len(set(value["source_case_ids"])) != 8:
            raise ValueError("unique offline model provenance required")
    return artifact


def choose_initial(task, artifact):
    if task not in TASKS: raise ValueError("registered known task required")
    validate_model(artifact)
    losses = artifact["tasks"][task]["initial_mean_losses"]
    index = min(range(7),key=lambda i:(losses[i],i))
    return {"selector":INITIAL_SELECTOR,"selected_branch":FULL_BRANCHES[index],
            "source_mean_losses":dict(zip(FULL_BRANCHES,losses)),"task_evidence":{"task":task},
            "remaining_steps":500,"model_sha256":digest(artifact),
            "physical_response_qualified":False,"probability_guarantee":False}


def choose(evidence, artifact, selector):
    if type(evidence) is not ContinuationEvidence or selector not in SELECTORS:
        raise ValueError("strict visible evidence and registered selector required")
    validate_model(artifact)
    value = artifact["tasks"][evidence.task]
    model = KernelModel.from_saved(value["single_rbf" if selector == "SINGLE_FUTURE_RBF" else "mean_rbf"])
    x = evidence.features(); nearest = None
    if selector == "TASK_MEAN":
        predicted = np.asarray(value["task_mean"])
    elif selector == "MEAN_COST_NEAREST":
        distance = ((model.support-(x-model.mean)/model.scale)**2).sum(axis=1)
        nearest = int(np.argmin(distance)); predicted = np.asarray(value["source_targets"])[nearest]
    else:
        predicted = model.predict(x)
    losses = [0., *(500.*finite(predicted,(4,))).tolist()]
    index = min(range(5), key=lambda i:(losses[i],i))
    if index and evidence.remaining_steps < 8+32:
        raise ValueError("insufficient continuation/task budget")
    return {"selected_branch":BRANCHES[index], "loss_minus_direct_predictions":dict(zip(BRANCHES,losses)),
            "selector":selector, "evidence_sha256":evidence.sha256, "model_sha256":digest(artifact),
            "remaining_steps":evidence.remaining_steps, "nearest_training_index":nearest,
            "physical_response_qualified":False, "probability_guarantee":False}

"""Separate MetaWorld task-factory overhead from registered control interactions.

Source inspection and a simulator-free factory spy identify initialization work.
Historical totals are structural inferences, not measured constructor traces;
the original registered trajectory/reset counters and all results remain intact.
"""
import argparse
import hashlib
import importlib.metadata
import inspect
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
from scripts.report_action_response import IDENTITY,load,matching_audit,sha


class GoalFactorySpy:
    created=0;resets=0;closed=0;steps=0
    def __init__(self):
        type(self).created+=1;self._last_rand_vec=None
    def _set_task_inner(self,**kwargs):pass
    def reset(self):
        type(self).resets+=1;self._last_rand_vec=np.array([float(type(self).resets)])
    def step(self,*args):
        type(self).steps+=1;raise AssertionError("factory spy never executes robot steps")
    def close(self):type(self).closed+=1


def factory_spy(metaworld_module):
    for name in ("created","resets","closed","steps"):setattr(GoalFactorySpy,name,0)
    tasks=metaworld_module._make_tasks({"INITIALIZATION_SPY":GoalFactorySpy},
        {"INITIALIZATION_SPY":{"args":[],"kwargs":{"task_id":0}}},{},seed=0)
    result={"temporary_environments_created":GoalFactorySpy.created,"temporary_reset_calls":GoalFactorySpy.resets,
            "temporary_environments_closed":GoalFactorySpy.closed,"env_step_calls":GoalFactorySpy.steps,"tasks_generated":len(tasks)}
    if result!={"temporary_environments_created":1,"temporary_reset_calls":50,"temporary_environments_closed":1,"env_step_calls":0,"tasks_generated":50}:
        raise ValueError("installed task-generation semantics differ from the inspected v3.1.1 source")
    return result


def infer_counts(controlled_episodes,source_episodes,temporary_per_factory):
    for n in (controlled_episodes,source_episodes,temporary_per_factory):
        if type(n) is not int or n<0:raise ValueError("nonnegative integer factory counts required")
    return {"registered_controlled_resets":controlled_episodes,
        "inferred_temporary_task_factory_resets":controlled_episodes*temporary_per_factory,
        "inferred_total_reset_entry_calls":controlled_episodes*(1+temporary_per_factory),
        "registered_prior_controlled_resets":source_episodes,
        "inferred_prior_temporary_task_factory_resets":source_episodes*temporary_per_factory,
        "inferred_prior_total_reset_entry_calls":source_episodes*(1+temporary_per_factory),
        "historical_initialization_calls_runtime_measured":False}


def analyze(manifest,audit_path):
    import metaworld
    from src.rollout import task_registry
    m=load(manifest);a=load(audit_path);matching_audit(m,a)
    if m["versions"]["metaworld"]!="3.1.1" or importlib.metadata.version("metaworld")!="3.1.1":raise ValueError("bound installed version required")
    if sha(ROOT/"src/rollout/task_registry.py")!=m["input_sha256"]["src/rollout/task_registry.py"]:
        raise ValueError("registered task factory changed")
    for name,expected in a["artifact_sha256"].items():
        if sha(manifest.parent/name)!=expected:raise ValueError("audited trajectory bytes changed")
    old_path=ROOT/m["config"]["forward_audit_path"];old=load(old_path)
    if old["integrity"]!="PASSED" or old["environment_resets"]!=288:raise ValueError("audited source population required")
    old_manifest_path=(ROOT/m["config"]["forward_model_path"]).parent/"manifest.json"
    old_manifest=load(old_manifest_path)
    if old_manifest["versions"]["metaworld"]!="3.1.1" or old_manifest["input_sha256"]["src/rollout/task_registry.py"]!=sha(ROOT/"src/rollout/task_registry.py"):
        raise ValueError("same source-factory evidence required")
    source=inspect.getsource(task_registry.create_task_environment)
    if 'gym.make("Meta-World/MT1",env_name=task,seed=seed)' not in source or "num_goals" in source:
        raise ValueError("registered default MT1 creation semantics differ")
    spy=factory_spy(metaworld)
    package=Path(metaworld.__file__).parent
    source_files={"metaworld/__init__.py":package/"__init__.py","metaworld/sawyer_xyz_env.py":package/"sawyer_xyz_env.py",
                  "metaworld/wrappers.py":package/"wrappers.py"}
    for name in ("sawyer_push_v3.py","sawyer_reach_v3.py","sawyer_door_v3.py"):source_files["metaworld/envs/"+name]=package/"envs"/name
    return {**{k:m[k] for k in IDENTITY},"primary_audit_sha256":sha(audit_path),"source_audit_sha256":sha(old_path),"source_manifest_sha256":sha(old_manifest_path),
        "analysis_source_sha256":sha(Path(__file__)),"installed_metaworld_version":"3.1.1",
        "installed_source_sha256":{name:sha(path) for name,path in source_files.items()},"simulator_free_factory_spy":spy,
        "counts":infer_counts(a["episodes"],old["episodes"],spy["temporary_reset_calls"]),
        "registered_control_500_step_budget_reinterpreted":False,"registered_probe_handoff_reinterpreted":False,
        "factory_goal_resets_use_separate_temporary_environment":True,"reset_hand_internal_physics_not_counted_as_env_step_calls":True,
        "historical_internal_physics_frames_not_measured":True,"new_robot_env_steps":0,"new_api_calls":0,"physical_response_qualified":False,
        "scope":"Current installed-source and simulator-free call-count check. Historical factory-reset totals inferred from completed factory-instance counts, same registered factory source and package version, not lifetime instrumentation. Registered host steps/resets remain unchanged; full process overhead was outside the original replay audit."}


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("manifest","audit","output"):p.add_argument("--"+name,type=Path,required=True)
    a=p.parse_args();manifest=a.manifest.resolve();output=a.output.resolve()
    if output.exists() or output==manifest.parent or manifest.parent in output.parents:raise FileExistsError("new external setup audit directory required")
    result=analyze(manifest,a.audit.resolve());output.mkdir(parents=True,exist_ok=False)
    (output/"setup_cost.json").write_bytes((json.dumps(result,indent=2,ensure_ascii=False)+"\n").encode("utf-8"))
    print(json.dumps(result["counts"]))

"""Frozen end-to-end validation of consistency-gated recovery and controls."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from statistics import mean
from typing import Any
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts.build_autoresearch_benchmark import get_conditions,rollout,save_csv  # noqa:E402
from src.autoresearch import RecoveryPolicyConfig,choose_runtime_skill  # noqa:E402
from src.diagnostic_probes import (build_agent_probe_context,build_repeated_agent_probe_context,
 estimate_planar_bias,run_repeated_symmetric_probes,run_symmetric_probes)  # noqa:E402
from src.recovery_skills import build_planar_recovery_skills,select_skill  # noqa:E402
from src.rollout import create_push_environment  # noqa:E402
def parse()->argparse.Namespace:
 p=argparse.ArgumentParser(description=__doc__);p.add_argument("--seed-start",type=int,default=310);p.add_argument("--num-seeds",type=int,default=10)
 p.add_argument("--research-config",type=Path,required=True);p.add_argument("--random-config",type=Path,required=True)
 p.add_argument("--noise-selection",type=Path,default=ROOT/"outputs/autoresearch/noise_calibration/selected.json")
 p.add_argument("--consistency-threshold",type=float,required=True);p.add_argument("--repeats",type=int,default=4)
 p.add_argument("--consistency-probe-steps",type=int,default=4);p.add_argument("--max-steps",type=int,default=500)
 p.add_argument("--output-dir",type=Path,default=ROOT/"outputs/autoresearch/gated_recovery_validation");return p.parse_args()
def repair(seed:int,fault:Any,config:RecoveryPolicyConfig,max_steps:int)->tuple[bool,int,float,str,str]:
 probes=run_symmetric_probes(lambda:create_push_environment(seed),seed=seed,perturbation_factory=fault.build,
  magnitude=config.probe_magnitude,steps=config.probe_steps_per_direction)
 context=build_agent_probe_context(probes,estimate_planar_bias(probes));diagnosis,skills=build_planar_recovery_skills(context)
 decision=choose_runtime_skill(config,diagnosis);probe_steps=int(context["probe_environment_steps"])
 if decision.skill_id=="abstain_and_escalate":return False,probe_steps,float("nan"),decision.skill_id,decision.schedule
 skill=select_skill(skills,decision.skill_id);result=rollout(seed,fault,skill.correction,decision.schedule,max_steps)
 return result.success,probe_steps+result.steps,result.final_object_goal_distance,decision.skill_id,decision.schedule
def gated_repair(seed:int,fault:Any,config:RecoveryPolicyConfig,threshold:float,repeats:int,steps:int,max_steps:int)->tuple[bool,int,float,str,str,float]:
 groups=run_repeated_symmetric_probes(lambda:create_push_environment(seed),seed=seed,perturbation_factory=fault.build,
  repeats=repeats,magnitude=config.probe_magnitude,steps=steps)
 estimates=tuple(estimate_planar_bias(group) for group in groups);repeated=build_repeated_agent_probe_context(groups,estimates)
 score=float(repeated["consistency"]["estimated_bias_std_norm"]);probe_steps=int(repeated["probe_environment_steps"])
 if score>threshold:return False,probe_steps,float("nan"),"abstain_and_escalate","none",score
 context=build_agent_probe_context(groups[0],estimates[0]);diagnosis,skills=build_planar_recovery_skills(context)
 decision=choose_runtime_skill(config,diagnosis)
 if decision.skill_id=="abstain_and_escalate":return False,probe_steps,float("nan"),decision.skill_id,decision.schedule,score
 skill=select_skill(skills,decision.skill_id);result=rollout(seed,fault,skill.correction,decision.schedule,max_steps)
 return result.success,probe_steps+result.steps,result.final_object_goal_distance,decision.skill_id,decision.schedule,score
def main()->int:
 a=parse()
 try:
  if min(a.num_seeds,a.repeats,a.consistency_probe_steps,a.max_steps)<=0 or a.consistency_threshold<0:raise ValueError("valid positive budgets required")
  research=RecoveryPolicyConfig.from_mapping(json.loads(a.research_config.read_text(encoding="utf-8")))
  random=RecoveryPolicyConfig.from_mapping(json.loads(a.random_config.read_text(encoding="utf-8")))
  noise=float(json.loads(a.noise_selection.read_text(encoding="utf-8"))["noise_std"]);out=a.output_dir.resolve()
  baselines=[];rows=[]
  for fault in get_conditions(noise):
   for seed in range(a.seed_start,a.seed_start+a.num_seeds):
    initial=rollout(seed,fault,(0,0,0,0),"whole",a.max_steps)
    baselines.append({"condition_id":fault.condition_id,"seed":seed,"success":initial.success,"steps":initial.steps,
     "final_object_goal_distance":initial.final_object_goal_distance});save_csv(out/"baselines.csv",baselines)
    if initial.success:continue
    rows.append({"method":"no_recovery","condition_id":fault.condition_id,"seed":seed,"recovery_success":False,
     "skill_id":"none","schedule":"none","consistency_score":"","recovery_environment_steps":0,
     "final_object_goal_distance":initial.final_object_goal_distance})
    for method,config in (("research_r1_c1",research),("random_03",random)):
     success,cost,distance,skill,schedule=repair(seed,fault,config,a.max_steps)
     rows.append({"method":method,"condition_id":fault.condition_id,"seed":seed,"recovery_success":success,
      "skill_id":skill,"schedule":schedule,"consistency_score":"","recovery_environment_steps":cost,
      "final_object_goal_distance":initial.final_object_goal_distance if distance!=distance else distance})
    success,cost,distance,skill,schedule,score=gated_repair(seed,fault,research,a.consistency_threshold,a.repeats,a.consistency_probe_steps,a.max_steps)
    rows.append({"method":"consistency_gated_r1_c1","condition_id":fault.condition_id,"seed":seed,"recovery_success":success,
     "skill_id":skill,"schedule":schedule,"consistency_score":score,"recovery_environment_steps":cost,
     "final_object_goal_distance":initial.final_object_goal_distance if distance!=distance else distance})
    save_csv(out/"results.csv",rows);print(f"condition={fault.condition_id} seed={seed} gated={skill} success={success}")
  failed=len(rows)//4;summary=[]
  for method in ("no_recovery","research_r1_c1","random_03","consistency_gated_r1_c1"):
   selected=[r for r in rows if r["method"]==method];recovered=sum(bool(r["recovery_success"]) for r in selected)
   summary.append({"method":method,"initial_failures":failed,"recovered":recovered,
    "conditional_recovery_rate":recovered/failed if failed else 0,"abstentions":sum(r["skill_id"]=="abstain_and_escalate" for r in selected),
    "mean_recovery_environment_steps":mean(float(r["recovery_environment_steps"]) for r in selected) if selected else 0,
    "mean_final_object_goal_distance":mean(float(r["final_object_goal_distance"]) for r in selected) if selected else 0})
  save_csv(out/"summary.csv",summary);print(f"summary: {(out/'summary.csv').resolve()}");return 0
 except Exception as e:print(f"[FAIL] {type(e).__name__}: {e}",file=sys.stderr);return 1
if __name__=="__main__":raise SystemExit(main())

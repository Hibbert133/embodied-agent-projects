"""Evaluate compensation, retry, and value-aware recovery on fixed tuning seeds."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from statistics import mean
from typing import Any
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts.build_autoresearch_benchmark import get_conditions,rollout,save_csv  # noqa:E402
from src.autoresearch import RecoveryPolicyConfig,choose_runtime_skill  # noqa:E402
from src.diagnostic_probes import build_agent_probe_context,build_repeated_agent_probe_context,estimate_planar_bias,run_repeated_symmetric_probes,run_symmetric_probes  # noqa:E402
from src.recovery_skills import build_planar_recovery_skills,select_skill  # noqa:E402
from src.rollout import create_push_environment  # noqa:E402
from src.stochastic_recovery import choose_value_aware_recovery,derive_retry_seed  # noqa:E402
def parse()->argparse.Namespace:
 p=argparse.ArgumentParser(description=__doc__);p.add_argument("--seed-start",type=int,default=300);p.add_argument("--num-seeds",type=int,default=10)
 p.add_argument("--research-config",type=Path,required=True);p.add_argument("--noise-selection",type=Path,default=ROOT/"outputs/autoresearch/noise_calibration/selected.json")
 p.add_argument("--consistency-threshold",type=float,required=True);p.add_argument("--repeats",type=int,default=4);p.add_argument("--probe-steps",type=int,default=4)
 p.add_argument("--max-steps",type=int,default=500);p.add_argument("--output-dir",type=Path,default=ROOT/"outputs/autoresearch/stochastic_retry_tuning");return p.parse_args()
def compensate(seed:int,fault:Any,config:RecoveryPolicyConfig,max_steps:int,probes:Any|None=None,estimate:Any|None=None)->tuple[bool,int,float,str]:
 if probes is None:
  probes=run_symmetric_probes(lambda:create_push_environment(seed),seed=seed,perturbation_factory=fault.build,magnitude=config.probe_magnitude,steps=config.probe_steps_per_direction);estimate=estimate_planar_bias(probes)
 context=build_agent_probe_context(probes,estimate);diagnosis,skills=build_planar_recovery_skills(context);decision=choose_runtime_skill(config,diagnosis);probe_cost=sum(r.steps for r in probes)
 if decision.skill_id=="abstain_and_escalate":return False,probe_cost,float("nan"),decision.skill_id
 skill=select_skill(skills,decision.skill_id);result=rollout(seed,fault,skill.correction,decision.schedule,max_steps);return result.success,probe_cost+result.steps,result.final_object_goal_distance,decision.skill_id
def row(method:str,fault:Any,seed:int,success:bool,cost:int,distance:float,strategy:str,retry_seed:Any="",score:Any="")->dict[str,Any]:
 return {"method":method,"condition_id":fault.condition_id,"seed":seed,"recovery_success":success,"strategy":strategy,"retry_seed":retry_seed,
  "consistency_score":score,"recovery_environment_steps":cost,"final_object_goal_distance":distance}
def main()->int:
 a=parse()
 try:
  config=RecoveryPolicyConfig.from_mapping(json.loads(a.research_config.read_text(encoding="utf-8")));noise=float(json.loads(a.noise_selection.read_text(encoding="utf-8"))["noise_std"]);out=a.output_dir.resolve();baselines=[];rows=[]
  for fault in get_conditions(noise):
   for seed in range(a.seed_start,a.seed_start+a.num_seeds):
    initial=rollout(seed,fault,(0,0,0,0),"whole",a.max_steps);baselines.append({"condition_id":fault.condition_id,"seed":seed,"success":initial.success,"steps":initial.steps,"final_object_goal_distance":initial.final_object_goal_distance});save_csv(out/"baselines.csv",baselines)
    if initial.success:continue
    rows.append(row("no_recovery",fault,seed,False,0,initial.final_object_goal_distance,"none"))
    success,cost,distance,skill=compensate(seed,fault,config,a.max_steps);rows.append(row("bias_compensation",fault,seed,success,cost,distance,skill))
    same=rollout(seed,fault,(0,0,0,0),"whole",a.max_steps,perturbation_seed=seed);rows.append(row("same_seed_retry",fault,seed,same.success,same.steps,same.final_object_goal_distance,"identity_retry",seed))
    retry_seed=derive_retry_seed(seed);retry=rollout(seed,fault,(0,0,0,0),"whole",a.max_steps,perturbation_seed=retry_seed);rows.append(row("independent_retry",fault,seed,retry.success,retry.steps,retry.final_object_goal_distance,"identity_retry",retry_seed))
    groups=run_repeated_symmetric_probes(lambda:create_push_environment(seed),seed=seed,perturbation_factory=fault.build,repeats=a.repeats,magnitude=config.probe_magnitude,steps=a.probe_steps)
    estimates=tuple(estimate_planar_bias(group) for group in groups);context=build_repeated_agent_probe_context(groups,estimates);score=float(context["consistency"]["estimated_bias_std_norm"]);decision=choose_value_aware_recovery(score,a.consistency_threshold);probe_cost=int(context["probe_environment_steps"])
    if decision.strategy=="stochastic_retry":result=rollout(seed,fault,(0,0,0,0),"whole",a.max_steps,perturbation_seed=retry_seed);success=result.success;cost=probe_cost+result.steps;distance=result.final_object_goal_distance;strategy="stochastic_retry"
    else:success,repair_cost,distance,skill=compensate(seed,fault,config,a.max_steps,groups[0],estimates[0]);cost=probe_cost+(repair_cost-sum(r.steps for r in groups[0]));strategy=skill
    rows.append(row("value_aware",fault,seed,success,cost,distance,strategy,retry_seed if decision.strategy=="stochastic_retry" else "",score));save_csv(out/"results.csv",rows);print(f"condition={fault.condition_id} seed={seed} value={decision.strategy} success={success}")
  failures=len(rows)//5;summary=[]
  for method in ("no_recovery","bias_compensation","same_seed_retry","independent_retry","value_aware"):
   selected=[r for r in rows if r["method"]==method];recovered=sum(bool(r["recovery_success"]) for r in selected)
   summary.append({"method":method,"initial_failures":failures,"recovered":recovered,"conditional_recovery_rate":recovered/failures,
    "mean_recovery_environment_steps":mean(float(r["recovery_environment_steps"]) for r in selected),"mean_final_object_goal_distance":mean(float(r["final_object_goal_distance"]) for r in selected)})
  save_csv(out/"summary.csv",summary);print(f"summary: {(out/'summary.csv').resolve()}");return 0
 except Exception as e:print(f"[FAIL] {type(e).__name__}: {e}",file=sys.stderr);return 1
if __name__=="__main__":raise SystemExit(main())

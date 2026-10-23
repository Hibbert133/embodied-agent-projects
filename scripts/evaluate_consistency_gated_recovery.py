"""Run recovery with a frozen Agent-visible probe-consistency abstention gate."""
from __future__ import annotations
import argparse,csv,json,sys
from pathlib import Path
from statistics import mean
from typing import Any
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts.build_autoresearch_benchmark import FaultCondition,rollout,save_csv  # noqa:E402
from src.autoresearch import RecoveryPolicyConfig,choose_runtime_skill  # noqa:E402
from src.diagnostic_probes import (build_agent_probe_context,build_repeated_agent_probe_context,
 estimate_planar_bias,run_repeated_symmetric_probes)  # noqa:E402
from src.recovery_skills import build_planar_recovery_skills,select_skill  # noqa:E402
from src.rollout import create_push_environment  # noqa:E402
def parse()->argparse.Namespace:
 p=argparse.ArgumentParser(description=__doc__);p.add_argument("--config",type=Path,required=True)
 p.add_argument("--agent-cases",type=Path,required=True);p.add_argument("--oracle-audit",type=Path,required=True)
 p.add_argument("--case-ids",nargs="+",required=True);p.add_argument("--consistency-threshold",type=float,required=True)
 p.add_argument("--repeats",type=int,default=4);p.add_argument("--probe-steps",type=int,default=4)
 p.add_argument("--probe-magnitude",type=float,default=.2);p.add_argument("--max-steps",type=int,default=500)
 p.add_argument("--reference-summary",type=Path);p.add_argument("--output-dir",type=Path,required=True);return p.parse_args()
def load(path:Path)->dict[str,dict[str,Any]]:
 return {row["case_id"]:row for row in (json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip())}
def main()->int:
 a=parse()
 try:
  if a.consistency_threshold<0:raise ValueError("consistency threshold must be non-negative")
  config=RecoveryPolicyConfig.from_mapping(json.loads(a.config.read_text(encoding="utf-8")))
  agent=load(a.agent_cases);oracle=load(a.oracle_audit);rows=[]
  for case_id in a.case_ids:
   visible=agent[case_id];audit=oracle[case_id];initial=visible["initial_rollout"]
   if initial["success"]:continue
   seed=int(visible["seed"]);fault=FaultCondition(audit["condition_id"],audit["perturbation_type"],audit["perturbation_parameters"])
   groups=run_repeated_symmetric_probes(lambda:create_push_environment(seed),seed=seed,perturbation_factory=fault.build,
    repeats=a.repeats,magnitude=a.probe_magnitude,steps=a.probe_steps)
   estimates=tuple(estimate_planar_bias(group) for group in groups);repeated=build_repeated_agent_probe_context(groups,estimates)
   score=float(repeated["consistency"]["estimated_bias_std_norm"]);probe_steps=int(repeated["probe_environment_steps"])
   if score>a.consistency_threshold:
    skill_id="abstain_and_escalate";schedule="none";success=False;repair_steps=0;distance=float(initial["final_object_goal_distance"])
   else:
    context=build_agent_probe_context(groups[0],estimates[0]);diagnosis,skills=build_planar_recovery_skills(context)
    decision=choose_runtime_skill(config,diagnosis);skill_id=decision.skill_id;schedule=decision.schedule
    if skill_id=="abstain_and_escalate":success=False;repair_steps=0;distance=float(initial["final_object_goal_distance"])
    else:
     skill=select_skill(skills,skill_id);result=rollout(seed,fault,skill.correction,schedule,a.max_steps)
     success=result.success;repair_steps=result.steps;distance=result.final_object_goal_distance
   rows.append({"config_id":config.config_id,"case_id":case_id,"seed":seed,"condition_id":audit["condition_id"],
    "is_stochastic_ood":audit["perturbation_type"]=="gaussian_noise","consistency_score":score,
    "consistency_threshold":a.consistency_threshold,"skill_id":skill_id,"schedule":schedule,"recovery_success":success,
    "probe_environment_steps":probe_steps,"recovery_rollout_steps":repair_steps,
    "total_recovery_environment_steps":probe_steps+repair_steps,"final_object_goal_distance":distance})
   print(f"case={case_id} score={score:.6f} skill={skill_id}:{schedule} success={success}")
  recovered=sum(bool(r["recovery_success"]) for r in rows);abstained=[r for r in rows if r["skill_id"]=="abstain_and_escalate"]
  summary={"method":"consistency_gated_recovery","cases":len(rows),"recovered":recovered,
   "conditional_recovery_rate":recovered/len(rows),"abstentions":len(abstained),
   "ood_abstentions":sum(bool(r["is_stochastic_ood"]) for r in abstained),
   "mean_recovery_environment_steps":mean(float(r["total_recovery_environment_steps"]) for r in rows),
   "mean_final_object_goal_distance":mean(float(r["final_object_goal_distance"]) for r in rows)}
  if a.reference_summary:
   with a.reference_summary.open(encoding="utf-8") as f:reference=next(csv.DictReader(f))
   summary["step_difference_vs_reference"]=summary["mean_recovery_environment_steps"]-float(reference["mean_recovery_environment_steps"])
  out=a.output_dir.resolve();save_csv(out/"results.csv",rows);save_csv(out/"summary.csv",[summary]);print(json.dumps(summary,indent=2));return 0
 except Exception as e:print(f"[FAIL] {type(e).__name__}: {e}",file=sys.stderr);return 1
if __name__=="__main__":raise SystemExit(main())

"""Evaluate one bounded recovery-system config on anonymous benchmark cases."""
from __future__ import annotations
import argparse,csv,json,sys
from pathlib import Path
from statistics import mean
from typing import Any
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from scripts.build_autoresearch_benchmark import FaultCondition, rollout, save_csv  # noqa: E402
from src.autoresearch import RecoveryPolicyConfig, choose_runtime_skill  # noqa: E402
from src.diagnostic_probes import build_agent_probe_context,estimate_planar_bias,run_symmetric_probes  # noqa: E402
from src.recovery_skills import build_planar_recovery_skills,select_skill  # noqa: E402
from src.rollout import create_push_environment  # noqa: E402

def args()->argparse.Namespace:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--config",type=Path,required=True)
    p.add_argument("--agent-cases",type=Path,required=True); p.add_argument("--oracle-audit",type=Path,required=True)
    p.add_argument("--case-ids",nargs="+"); p.add_argument("--max-steps",type=int,default=500); p.add_argument("--output-dir",type=Path,required=True)
    return p.parse_args()
def jsonl(path:Path)->list[dict[str,Any]]: return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
def main()->int:
    a=args()
    try:
        config=RecoveryPolicyConfig.from_mapping(json.loads(a.config.read_text(encoding="utf-8")))
        agent={x["case_id"]:x for x in jsonl(a.agent_cases)}; oracle={x["case_id"]:x for x in jsonl(a.oracle_audit)}
        selected=a.case_ids or list(agent); unknown=set(selected)-set(agent)
        if unknown or set(selected)-set(oracle): raise ValueError(f"unknown cases: {sorted(unknown)}")
        rows=[]
        for case_id in selected:
            visible=agent[case_id]; audit=oracle[case_id]; initial=visible["initial_rollout"]
            if initial["success"]:
                rows.append({"config_id":config.config_id,"case_id":case_id,"seed":visible["seed"],"initial_success":True,
                    "skill_id":"not_needed","schedule":"none","recovery_success":True,"probe_environment_steps":0,
                    "recovery_rollout_steps":0,"total_recovery_environment_steps":0,"final_object_goal_distance":initial["final_object_goal_distance"]})
                continue
            fault=FaultCondition(audit["condition_id"],audit["perturbation_type"],audit["perturbation_parameters"]); seed=int(visible["seed"])
            probes=run_symmetric_probes(lambda:create_push_environment(seed),seed=seed,perturbation_factory=fault.build,
                magnitude=config.probe_magnitude,steps=config.probe_steps_per_direction)
            context=build_agent_probe_context(probes,estimate_planar_bias(probes)); diagnosis,skills=build_planar_recovery_skills(context)
            decision=choose_runtime_skill(config,diagnosis); probe_steps=int(context["probe_environment_steps"])
            if decision.skill_id=="abstain_and_escalate": result=None; success=False; recovery_steps=0; distance=float(initial["final_object_goal_distance"])
            else:
                skill=select_skill(skills,decision.skill_id); result=rollout(seed,fault,skill.correction,decision.schedule,a.max_steps)
                success=result.success; recovery_steps=result.steps; distance=result.final_object_goal_distance
            rows.append({"config_id":config.config_id,"case_id":case_id,"seed":seed,"initial_success":False,
                "skill_id":decision.skill_id,"schedule":decision.schedule,"recovery_success":success,
                "probe_environment_steps":probe_steps,"recovery_rollout_steps":recovery_steps,
                "total_recovery_environment_steps":probe_steps+recovery_steps,"final_object_goal_distance":distance})
            print(f"config={config.config_id} case={case_id} skill={decision.skill_id}:{decision.schedule} success={success}")
        failures=[r for r in rows if not r["initial_success"]]; recovered=sum(bool(r["recovery_success"]) for r in failures)
        summary=[{"config_id":config.config_id,"cases":len(rows),"initial_failures":len(failures),"recovered":recovered,
            "conditional_recovery_rate":recovered/len(failures) if failures else 0.0,
            "mean_recovery_environment_steps":mean(float(r["total_recovery_environment_steps"]) for r in failures) if failures else 0.0,
            "mean_final_object_goal_distance":mean(float(r["final_object_goal_distance"]) for r in failures) if failures else 0.0}]
        out=a.output_dir.resolve(); save_csv(out/"results.csv",rows); save_csv(out/"summary.csv",summary)
        (out/"config.json").write_text(json.dumps(config.to_dict(),indent=2),encoding="utf-8")
        print(f"summary: {(out/'summary.csv').resolve()}"); return 0
    except Exception as e: print(f"[FAIL] {type(e).__name__}: {e}",file=sys.stderr); return 1
if __name__=="__main__": raise SystemExit(main())

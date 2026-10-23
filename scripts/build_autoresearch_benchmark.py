"""Build heterogeneous push-v3 recovery cases with counterfactual labels."""
from __future__ import annotations
import argparse, csv, json, sys
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from src.autoresearch import SkillOutcome, select_counterfactual_skill  # noqa: E402
from src.diagnostic_probes import build_agent_probe_context, estimate_planar_bias, run_symmetric_probes  # noqa: E402
from src.perturbations import ActionBiasPerturbation, GaussianNoisePerturbation  # noqa: E402
from src.recovery_agent import PhaseGatedCompensatedPolicy  # noqa: E402
from src.recovery_skills import build_planar_recovery_skills  # noqa: E402
from src.rollout import create_push_environment, create_push_policy, run_episode  # noqa: E402

@dataclass(frozen=True)
class FaultCondition:
    condition_id: str
    kind: str
    parameters: dict[str, Any]
    def build(self) -> Any:
        if self.kind == "action_bias": return ActionBiasPerturbation(self.parameters["bias"])
        if self.kind == "gaussian_noise": return GaussianNoisePerturbation(float(self.parameters["std"]))
        raise ValueError(f"unsupported perturbation: {self.kind}")

def get_conditions(noise_std: float) -> tuple[FaultCondition, ...]:
    return (
        FaultCondition("fault_01", "action_bias", {"bias": [0.145, 0, 0, 0]}),
        FaultCondition("fault_02", "action_bias", {"bias": [-0.18, 0, 0, 0]}),
        FaultCondition("fault_03", "action_bias", {"bias": [0, -0.198, 0, 0]}),
        FaultCondition("fault_04", "action_bias", {"bias": [0.14, -0.14, 0, 0]}),
        FaultCondition("fault_05", "gaussian_noise", {"std": noise_std}),
    )

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seed-start", type=int, default=300); p.add_argument("--num-seeds", type=int, default=10)
    p.add_argument("--max-steps", type=int, default=500); p.add_argument("--probe-magnitude", type=float, default=.2)
    p.add_argument("--probe-steps", type=int, default=8)
    p.add_argument("--noise-selection", type=Path, default=ROOT/"outputs/autoresearch/noise_calibration/selected.json")
    p.add_argument("--output-dir", type=Path, default=ROOT/"outputs/autoresearch/benchmark_tuning")
    return p.parse_args()

def save_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows: return
    path.parent.mkdir(parents=True, exist_ok=True); tmp = path.with_name(f".{path.name}.tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w=csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    tmp.replace(path)

def save_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); tmp=path.with_name(f".{path.name}.tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False)+"\n" for r in rows), encoding="utf-8"); tmp.replace(path)

def rollout(seed: int, fault: FaultCondition, correction: tuple[float, ...], schedule: str, max_steps: int,
            perturbation_seed: int | None = None) -> Any:
    env=create_push_environment(seed); policy=PhaseGatedCompensatedPolicy(create_push_policy(), correction, schedule=schedule)
    try: return run_episode(env, policy, seed=seed, max_steps=max_steps, perturbation=fault.build(),perturbation_seed=perturbation_seed)
    finally: env.close()

def result_view(r: Any) -> dict[str, Any]:
    return {"success":r.success,"steps":r.steps,"episode_return":r.episode_return,
            "final_object_goal_distance":r.final_object_goal_distance,"progress_to_goal":r.progress_to_goal}

def main() -> int:
    a=parse_args()
    if min(a.num_seeds,a.max_steps,a.probe_steps)<=0: print("[FAIL] positive budgets required",file=sys.stderr); return 1
    try:
        noise=float(json.loads(a.noise_selection.read_text(encoding="utf-8"))["noise_std"]); out=a.output_dir.resolve()
        cases:list[dict[str,Any]]=[]; outcomes:list[dict[str,Any]]=[]; agent:list[dict[str,Any]]=[]; oracle:list[dict[str,Any]]=[]; number=0
        for fault in get_conditions(noise):
            for seed in range(a.seed_start,a.seed_start+a.num_seeds):
                number+=1; case_id=f"case_{number:04d}"; base=rollout(seed,fault,(0,0,0,0),"whole",a.max_steps)
                audit={"case_id":case_id,"seed":seed,"condition_id":fault.condition_id,"perturbation_type":fault.kind,
                       "perturbation_parameters":fault.parameters,"baseline":result_view(base)}
                if base.success:
                    cases.append({"case_id":case_id,"seed":seed,"condition_id":fault.condition_id,"initial_success":True,
                                  "counterfactual_label":"not_needed","probe_environment_steps":0})
                    agent.append({"case_id":case_id,"seed":seed,"initial_rollout":result_view(base),"decision_required":False}); oracle.append(audit); continue
                probes=run_symmetric_probes(lambda:create_push_environment(seed),seed=seed,perturbation_factory=fault.build,
                                             magnitude=a.probe_magnitude,steps=a.probe_steps)
                context=build_agent_probe_context(probes,estimate_planar_bias(probes)); diagnosis,skills=build_planar_recovery_skills(context)
                probe_steps=int(context["probe_environment_steps"]); trials:list[SkillOutcome]=[]
                for skill in skills:
                    if skill.skill_id=="abstain_and_escalate":
                        trials.append(SkillOutcome(
                            case_id, skill.skill_id, "none", False, probe_steps,
                            base.final_object_goal_distance, 0,
                        )); continue
                    axes=sum(abs(x)>1e-9 for x in skill.correction[:2])
                    for schedule in ("whole","phase_aware"):
                        r=rollout(seed,fault,skill.correction,schedule,a.max_steps)
                        trials.append(SkillOutcome(
                            case_id, skill.skill_id, schedule, r.success,
                            probe_steps+r.steps, r.final_object_goal_distance, axes,
                        ))
                chosen=select_counterfactual_skill(trials)
                outcomes.extend({"case_id":case_id,**asdict(x)} for x in trials)
                cases.append({"case_id":case_id,"seed":seed,"condition_id":fault.condition_id,"initial_success":False,
                              "counterfactual_label":f"{chosen.skill_id}:{chosen.schedule}","probe_environment_steps":probe_steps})
                agent.append({"case_id":case_id,"seed":seed,"initial_rollout":result_view(base),"decision_required":True,
                              "probe_evidence":context,"structured_diagnosis":diagnosis,"available_skills":[s.to_dict() for s in skills]})
                audit.update({"counterfactual_outcomes":[asdict(x) for x in trials],"selected_label":asdict(chosen)}); oracle.append(audit)
                print(f"{case_id} condition={fault.condition_id} seed={seed} label={chosen.skill_id}:{chosen.schedule}")
                save_csv(out/"cases.csv",cases); save_csv(out/"skill_outcomes.csv",outcomes); save_jsonl(out/"agent_cases.jsonl",agent); save_jsonl(out/"oracle_audit.jsonl",oracle)
        summary=[]
        for fault in get_conditions(noise):
            rows=[r for r in cases if r["condition_id"]==fault.condition_id]; failed=[r for r in rows if not r["initial_success"]]
            summary.append({"condition_id":fault.condition_id,"episodes":len(rows),"initial_failures":len(failed),
                            "initial_failure_rate":len(failed)/len(rows),"repairable_failures":sum(not r["counterfactual_label"].startswith("abstain") for r in failed),
                            "mean_probe_environment_steps":mean(float(r["probe_environment_steps"]) for r in failed) if failed else 0})
        save_csv(out/"cases.csv",cases); save_csv(out/"skill_outcomes.csv",outcomes); save_csv(out/"summary.csv",summary)
        save_jsonl(out/"agent_cases.jsonl",agent); save_jsonl(out/"oracle_audit.jsonl",oracle)
        print(f"cases: {(out/'cases.csv').resolve()}"); print(f"summary: {(out/'summary.csv').resolve()}"); return 0
    except Exception as e: print(f"[FAIL] {type(e).__name__}: {e}",file=sys.stderr); return 1

if __name__=="__main__": raise SystemExit(main())

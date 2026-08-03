"""Run the development-only mixed persistent-regime tuning campaign."""

from __future__ import annotations

import argparse, json, subprocess, sys, time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts.run_probemem_acr_utility_stability import _compensation_is_constructible,_sha256,_write_csv,_write_json  # noqa:E402
from scripts.run_probemem_v2_smoke import _probe_context,_read_jsonl,_run_verification  # noqa:E402
from src.perturbations import BiasNoisePerturbation  # noqa:E402
from src.probemem.models import InterventionSkill  # noqa:E402
from src.recovery_agent import RecoveryPolicyConfig  # noqa:E402
from src.reasoning import EvidenceSource,build_structured_evidence_state,validate_no_oracle_evidence  # noqa:E402
from src.rollout import create_push_environment,create_push_policy,run_episode  # noqa:E402

COMP=InterventionSkill.BOUNDED_PLANAR_COMPENSATION; RETRY=InterventionSkill.INDEPENDENT_STOCHASTIC_RETRY

@dataclass(frozen=True)
class MixedRegime:
    regime_id:str; bias:tuple[float,...]; noise_std:float
    def build(self)->BiasNoisePerturbation:return BiasNoisePerturbation(self.bias,self.noise_std)

def _git(*args:str)->str:return subprocess.run(["git","-c",f"safe.directory={ROOT.as_posix()}",*args],cwd=ROOT,check=True,capture_output=True,text=True).stdout.strip()
def _validate(path:Path)->tuple[dict[str,Any],dict[str,Any]]:
    manifest=json.loads(path.read_text(encoding="utf-8"))
    if path.parent.name!=manifest["experiment_run_id"] or _git("rev-parse","HEAD")!=manifest["source_git_commit"]:raise RuntimeError("mixed tuning manifest identity mismatch")
    if _git("status","--porcelain","--untracked-files=no"):raise RuntimeError("mixed tuning requires clean tracked worktree")
    config_path=ROOT/manifest["config_path"]
    if _sha256(config_path)!=manifest["config_sha256"]:raise RuntimeError("mixed tuning config changed")
    for group in ("implementation_sha256","input_sha256"):
        for relative,expected in manifest[group].items():
            if _sha256(ROOT/relative)!=expected:raise RuntimeError(f"mixed tuning source changed: {relative}")
    return manifest,json.loads(config_path.read_text(encoding="utf-8"))

def main()->int:
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--manifest",type=Path,required=True);args=parser.parse_args();manifest=None;status_path=None
    try:
        manifest,config=_validate(args.manifest.resolve());run_dir=args.manifest.resolve().parent;status_path=run_dir/"run_status.json"
        if status_path.exists():raise FileExistsError("mixed tuning cannot restart or overwrite")
        _write_json(status_path,{"status":"RUNNING","manifest_id":manifest["manifest_id"]})
        regimes={row["regime_id"]:MixedRegime(row["regime_id"],tuple(float(v) for v in row["bias"]),float(row["noise_std"])) for row in config["regimes"]}
        recovery=RecoveryPolicyConfig.from_mapping(json.loads((ROOT/config["recovery_policy_config"]).read_text(encoding="utf-8")))
        cases:list[dict[str,Any]]=[];candidates:list[dict[str,Any]]=[];evidence:list[dict[str,Any]]=[];integrity={"chronology_violations":0,"oracle_leakage_events":0,"budget_violations":0,"random_namespace_violations":0}
        episode_id=0
        for unit in manifest["population_units"]:
            regime=regimes[str(unit["regime_id_oracle"])];seed=int(unit["environment_seed"]);unit_id=int(unit["unit_id"])
            streams={int(unit["initial_perturbation_seed"]),int(unit["diagnostic_probe_seed"]),int(unit["paired_verification_seed"])}
            if len(streams)!=3:integrity["random_namespace_violations"]+=1;raise RuntimeError("mixed tuning random namespace overlap")
            trajectory=run_dir/"initial_trajectories"/f"unit{unit_id:03d}_seed{seed}_{regime.regime_id}.jsonl";trajectory.parent.mkdir(parents=True,exist_ok=True)
            env=create_push_environment(seed)
            try:initial=run_episode(env,create_push_policy(),seed=seed,episode_id=unit_id,max_steps=int(config["budget"]["initial_max_steps"]),perturbation=regime.build(),perturbation_seed=int(unit["initial_perturbation_seed"]),agent_trajectory_path=trajectory)
            finally:env.close()
            base={"unit_id":unit_id,"seed":seed,"regime_id_oracle":regime.regime_id,"initial_success":initial.success,"initial_steps":initial.steps,"operational":False,"episode_id":None,"ineligibility_reason":"","probe_steps":0,"outcome_class":"not_operational"}
            state=build_structured_evidence_state(_read_jsonl(trajectory),evidence_id=f"mixed_tuning_unit{unit_id:03d}_attempt0",source=EvidenceSource.FAILED_ROLLOUT,attempt_id=0)
            if not state.decision_required:cases.append({**base,"ineligibility_reason":"initial_success"});_write_csv(run_dir/"case_results.csv",cases);continue
            probe=_probe_context(regime,seed,config,int(unit["diagnostic_probe_seed"]));probe_steps=int(probe["probe_environment_steps"])
            if probe_steps>int(config["budget"]["probe_max_steps"]):integrity["budget_violations"]+=1;raise RuntimeError("mixed tuning probe budget exceeded")
            if not _compensation_is_constructible(seed=seed,probe_context=probe,recovery_config=recovery):cases.append({**base,"ineligibility_reason":"compensation_not_constructible","probe_steps":probe_steps});_write_csv(run_dir/"case_results.csv",cases);continue
            episode_id+=1;agent={"evidence_id":f"mixed_tuning_episode{episode_id:03d}_attempt1","episode_id":episode_id,"initial_evidence":{**state.to_dict(),"episode_id":episode_id,"evidence_id":f"mixed_tuning_episode{episode_id:03d}_attempt0"},"registered_probe_evidence":probe,"remaining_verification_budget":int(config["budget"]["verification_max_steps_per_candidate"])};validate_no_oracle_evidence(agent);timestamp=time.perf_counter_ns();evidence.append({"episode_id":episode_id,"unit_id":unit_id,"agent_visible_evidence":agent,"candidate_outcomes_available":False,"decision_timestamp_ns":timestamp});_write_json(run_dir/"agent_evidence.json",evidence)
            statuses=[];total=initial.steps+probe_steps
            for skill in (COMP,RETRY):
                result,execution=_run_verification(seed=seed,fault=regime,skill=skill,probe_context=probe,recovery_config=recovery,perturbation_seed=int(unit["paired_verification_seed"]),max_steps=int(config["budget"]["verification_max_steps_per_candidate"]),initial_distance=initial.final_object_goal_distance)
                if time.perf_counter_ns()<=timestamp:integrity["chronology_violations"]+=1;raise RuntimeError("mixed tuning outcome preceded evidence")
                total+=result.steps;status=str(execution["verification_status"]);statuses.append(status);candidates.append({"episode_id":episode_id,"unit_id":unit_id,"seed":seed,"regime_id_oracle":regime.regime_id,"candidate_skill":skill.value,"verification_status":status,"verification_steps":result.steps,"final_object_goal_distance":result.final_object_goal_distance,"observed_progress":initial.final_object_goal_distance-result.final_object_goal_distance,"paired_verification_seed":int(unit["paired_verification_seed"])})
            if total>int(config["budget"]["evaluator_max_steps_per_case"]):integrity["budget_violations"]+=1;raise RuntimeError("mixed tuning evaluator budget exceeded")
            accepted=statuses.count("ACCEPTED");outcome="both_recover" if accepted==2 else "exclusive_recovery" if accepted==1 else "neither_recovers"
            cases.append({**base,"operational":True,"episode_id":episode_id,"probe_steps":probe_steps,"outcome_class":outcome})
            _write_csv(run_dir/"case_results.csv",cases);_write_csv(run_dir/"candidate_results.csv",candidates);print(f"episode={episode_id} seed={seed} regime={regime.regime_id} outcome={outcome}",flush=True)
        counts=Counter(row["outcome_class"] for row in cases if row["operational"]);by_regime={regime_id:dict(Counter(row["outcome_class"] for row in cases if row["operational"] and row["regime_id_oracle"]==regime_id)) for regime_id in regimes}
        summary={"experiment_run_id":manifest["experiment_run_id"],"manifest_id":manifest["manifest_id"],"source_git_commit":manifest["source_git_commit"],"population_units":len(manifest["population_units"]),"operational_cases":episode_id,"outcome_classes":dict(counts),"outcomes_by_regime":by_regime,**integrity,"api_calls":0,"operational_memory_writes":0}
        _write_json(run_dir/"summary.json",summary);_write_json(status_path,{"status":"COMPLETED",**summary});print(f"run: {run_dir}");return 0
    except Exception as exc:
        if manifest is not None and status_path is not None:_write_json(status_path,{"status":"FAILED","manifest_id":manifest["manifest_id"],"error_type":type(exc).__name__,"error":str(exc)})
        print(f"[FAIL] {type(exc).__name__}: {exc}",file=sys.stderr);return 1
if __name__=="__main__":raise SystemExit(main())

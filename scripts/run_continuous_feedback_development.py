"""Run the immutable prospective continuous-feedback development collection."""
from __future__ import annotations
import argparse, json, sys, time
from pathlib import Path
from typing import Any
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from scripts.run_probemem_acr_utility_stability import COMPENSATION, RETRY, _compensation_is_constructible, _git, _load_inputs, _sha256, _write_csv, _write_json  # noqa: E402
from scripts.run_probemem_v2_smoke import _probe_context, _read_jsonl, _run_verification  # noqa: E402
from src.probemem import InterventionApplicabilitySignature  # noqa: E402
from src.reasoning import EvidenceSource, build_structured_evidence_state, validate_no_oracle_evidence  # noqa: E402
from src.rollout import create_push_environment, create_push_policy, run_episode  # noqa: E402

def _validate(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    m=json.loads(path.read_text(encoding="utf-8")); cp=ROOT/m["config_path"]
    if path.name!="immutable_manifest.json" or path.parent.name!=m["experiment_run_id"]: raise ValueError("manifest path mismatch")
    if _git("rev-parse","HEAD")!=m["source_git_commit"]: raise RuntimeError("HEAD differs from manifest")
    if _git("status","--porcelain","--untracked-files=no"): raise RuntimeError("tracked worktree must be clean")
    if _sha256(cp)!=m["config_sha256"]: raise RuntimeError("config hash mismatch")
    for group in ("implementation_sha256","input_sha256"):
        for rel, expected in m[group].items():
            if _sha256(ROOT/rel)!=expected: raise RuntimeError(f"immutable input changed: {rel}")
    return m,json.loads(cp.read_text(encoding="utf-8"))

def main() -> int:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--manifest",type=Path,required=True); args=p.parse_args()
    manifest=None; status_path=None
    try:
        manifest,cfg=_validate(args.manifest.resolve()); rd=args.manifest.resolve().parent; status_path=rd/"run_status.json"
        if status_path.exists(): raise FileExistsError("run already started")
        _write_json(status_path,{"status":"RUNNING","manifest_id":manifest["manifest_id"]})
        fault,recovery=_load_inputs(cfg); b=cfg["budget"]; target=cfg["population"]["target_second_decision_cases"]
        cases=[]; candidates=[]; eligible=0; second=0; integrity={"chronology_violations":0,"oracle_leakage_events":0,"budget_violations":0,"random_namespace_violations":0,"reset_violations":0}
        for u in manifest["population_units"]:
            if second>=target: break
            eid,seed=u["episode_id"],u["environment_seed"]
            if len({u["initial_perturbation_seed"],u["diagnostic_probe_seed"],u["first_verification_seed"],u["paired_second_verification_seed"]})!=4: raise RuntimeError("namespace collision")
            traj=rd/"initial_trajectories"/f"episode{eid:03d}_seed{seed}.jsonl"; traj.parent.mkdir(parents=True,exist_ok=True)
            env=create_push_environment(seed)
            try: initial=run_episode(env,create_push_policy(),seed=seed,episode_id=eid,max_steps=b["initial_rollout_max_steps"],perturbation=fault.build(),perturbation_seed=u["initial_perturbation_seed"],agent_trajectory_path=traj)
            finally: env.close()
            state=build_structured_evidence_state(_read_jsonl(traj),evidence_id=f"continuous_episode{eid:03d}_attempt0",source=EvidenceSource.FAILED_ROLLOUT,attempt_id=0)
            base={"experiment_run_id":manifest["experiment_run_id"],"manifest_id":manifest["manifest_id"],"source_git_commit":manifest["source_git_commit"],"episode_id":eid,"seed":seed,"condition_id_oracle":"fault_05","initial_success":initial.success,"initial_steps":initial.steps,"initial_final_object_goal_distance":initial.final_object_goal_distance,"probe_steps":0,"eligible_first_attempt":False,"first_verification_status":"NOT_EXECUTED","first_verification_steps":0,"first_final_object_goal_distance":"","first_observed_progress":"","second_decision_required":False,"second_decision_index":0,"ineligibility_reason":"initial_success" if initial.success else "not_yet_evaluated","online_steps_before_optional_second":initial.steps}
            if not state.decision_required: cases.append(base); _write_csv(rd/"case_results.csv",cases); continue
            probe=_probe_context(fault,seed,cfg,u["diagnostic_probe_seed"]); ps=int(probe["probe_environment_steps"])
            if ps>b["registered_probe_max_steps"]: raise RuntimeError("probe budget exceeded")
            if not _compensation_is_constructible(seed=seed,probe_context=probe,recovery_config=recovery):
                cases.append({**base,"probe_steps":ps,"ineligibility_reason":"bounded_compensation_not_constructible","online_steps_before_optional_second":initial.steps+ps}); _write_csv(rd/"case_results.csv",cases); continue
            eligible+=1; evidence={**state.to_dict(),"evidence_id":f"continuous_episode{eid:03d}_attempt1","attempt_id":1,"source":EvidenceSource.DIAGNOSTIC_PROBE.value,"parent_evidence_ids":[state.evidence_id],"registered_probe_evidence":probe}; validate_no_oracle_evidence(evidence); InterventionApplicabilitySignature.from_agent_evidence(evidence); t0=time.perf_counter_ns()
            first,fx=_run_verification(seed=seed,fault=fault,skill=RETRY,probe_context=probe,recovery_config=recovery,perturbation_seed=u["first_verification_seed"],max_steps=b["first_verification_max_steps"],initial_distance=initial.final_object_goal_distance); t1=time.perf_counter_ns()
            status=str(fx["verification_status"]); progress=initial.final_object_goal_distance-first.final_object_goal_distance; before=initial.steps+ps+first.steps
            row={**base,"probe_steps":ps,"eligible_first_attempt":True,"first_verification_status":status,"first_verification_steps":first.steps,"first_final_object_goal_distance":first.final_object_goal_distance,"first_observed_progress":progress,"ineligibility_reason":"","online_steps_before_optional_second":before}
            if t1<=t0: raise RuntimeError("chronology violation")
            if status=="ACCEPTED": cases.append(row); _write_csv(rd/"case_results.csv",cases); continue
            second+=1; pair_seed=u["paired_second_verification_seed"]
            for skill in (COMPENSATION,RETRY):
                result,execution=_run_verification(seed=seed,fault=fault,skill=skill,probe_context=probe,recovery_config=recovery,perturbation_seed=pair_seed,max_steps=b["second_verification_max_steps"],initial_distance=initial.final_object_goal_distance)
                candidates.append({**row,"second_decision_required":True,"second_decision_index":second,"candidate_id":skill.value,"paired_second_verification_seed":pair_seed,"verification_status":execution["verification_status"],"verification_steps":result.steps,"final_object_goal_distance":result.final_object_goal_distance,"observed_progress":initial.final_object_goal_distance-result.final_object_goal_distance})
            cases.append({**row,"second_decision_required":True,"second_decision_index":second}); _write_csv(rd/"case_results.csv",cases); _write_csv(rd/"second_candidate_results.csv",candidates); print(f"seed={seed} first={status} second={second}/{target}",flush=True)
        summary={"experiment_run_id":manifest["experiment_run_id"],"manifest_id":manifest["manifest_id"],"initial_units_scanned":len(cases),"eligible_first_attempts":eligible,"second_decision_cases":second,"second_candidate_rollouts":len(candidates),**integrity,"api_calls":0,"heldout_seeds_executed":0}
        complete=second>=target; _write_json(rd/"collection_summary.json",summary); _write_json(status_path,{"status":"COMPLETED" if complete else "INCOMPLETE_POPULATION",**summary}); print(f"run: {rd}"); return 0 if complete else 2
    except Exception as exc:
        if status_path and manifest: _write_json(status_path,{"status":"FAILED","manifest_id":manifest["manifest_id"],"error_type":type(exc).__name__,"error":str(exc)})
        print(f"[FAIL] {type(exc).__name__}: {exc}",file=sys.stderr); return 1
if __name__=="__main__": raise SystemExit(main())

"""Analyze prospective zero-progress feedback against matched baselines."""
from __future__ import annotations
import argparse,csv,json,statistics,sys
from collections import defaultdict
from pathlib import Path
from typing import Any
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from scripts.analyze_resonance_validation import _paired_bootstrap_difference  # noqa: E402
from scripts.run_probemem_acr_utility_stability import _write_csv,_write_json  # noqa: E402
from src.probemem.continuous_feedback_policy import decide_from_progress  # noqa: E402
from src.probemem.resonance_policy import decide_second_attempt  # noqa: E402

C="BOUNDED_PLANAR_COMPENSATION"; R="INDEPENDENT_STOCHASTIC_RETRY"
def _csv(path:Path)->list[dict[str,str]]:
    with path.open("r",encoding="utf-8",newline="") as h:return list(csv.DictReader(h))
def _truth(v:str)->bool:return v.lower()=="true"
def analyze(rd:Path)->dict[str,Any]:
    m=json.loads((rd/"immutable_manifest.json").read_text()); cfg=json.loads((ROOT/m["config_path"]).read_text()); status=json.loads((rd/"run_status.json").read_text())
    if status["status"] not in {"COMPLETED","INCOMPLETE_POPULATION"}:raise RuntimeError("collection not analyzable")
    cases=[r for r in _csv(rd/"case_results.csv") if _truth(r["eligible_first_attempt"])]
    pairs:dict[int,dict[str,dict[str,str]]]=defaultdict(dict)
    for r in _csv(rd/"second_candidate_results.csv"):pairs[int(r["episode_id"])][r["candidate_id"]]=r
    methods=cfg["methods"]; rows=[]
    for case in cases:
        eid=int(case["episode_id"]); first=case["first_verification_status"]; pair=pairs.get(eid)
        for method in methods:
            selected=None
            if first!="ACCEPTED":
                if set(pair or {})!={C,R}:raise ValueError("incomplete pair")
                if method=="always_repeat":selected=R
                elif method=="always_switch":selected=C
                elif method=="frozen_status_rule":selected=decide_second_attempt(method="status_conditioned",first_verification_status=first,remaining_budget=500,reserved_second_verification_budget=500).selected_skill.value
                elif method=="zero_progress_rule":selected=decide_from_progress(first_status=first,first_observed_progress=float(case["first_observed_progress"])).selected_skill.value
                elif method=="oracle_second":
                    selected=max((C,R),key=lambda a:(pair[a]["verification_status"]=="ACCEPTED",float(pair[a]["observed_progress"]),-int(pair[a]["verification_steps"])))
            chosen=pair[selected] if pair and selected else None; alt=pair[R if selected==C else C] if pair and selected else None
            accepted=first=="ACCEPTED" or bool(chosen and chosen["verification_status"]=="ACCEPTED")
            harmful=bool(chosen and chosen["verification_status"]!="ACCEPTED" and alt and alt["verification_status"]=="ACCEPTED")
            steps=int(case["online_steps_before_optional_second"])+(int(chosen["verification_steps"]) if chosen else 0)
            rows.append({"method":method,"episode_id":eid,"seed":int(case["seed"]),"first_status":first,"first_observed_progress":float(case["first_observed_progress"]),"selected_second_skill":selected or "STOP","final_accepted":accepted,"harmful_selection":harmful,"second_attempt":chosen is not None,"total_environment_steps":steps})
    _write_csv(rd/"method_results.csv",rows); summaries={}
    for method in methods:
        rr=[x for x in rows if x["method"]==method]; summaries[method]={"cases":len(rr),"accepted":sum(x["final_accepted"] for x in rr),"accepted_rate":statistics.fmean(x["final_accepted"] for x in rr),"harmful_selections":sum(x["harmful_selection"] for x in rr),"second_attempts":sum(x["second_attempt"] for x in rr),"total_environment_steps":sum(x["total_environment_steps"] for x in rr),"mean_environment_steps":statistics.fmean(x["total_environment_steps"] for x in rr)}
    fixed=min(("always_repeat","always_switch"),key=lambda x:(-summaries[x]["accepted"],summaries[x]["harmful_selections"],summaries[x]["total_environment_steps"]))
    def vals(method:str,field:str)->list[float]:return [float(x[field]) for x in rows if x["method"]==method]
    z=summaries["zero_progress_rule"]; f=summaries[fixed]; complete=status["status"]=="COMPLETED" and len(pairs)>=cfg["completion_gate"]["second_decision_cases_minimum"]
    not_below=z["accepted"]>=f["accepted"]; harm_ok=z["harmful_selections"]<=f["harmful_selections"]; tied=z["accepted"]==f["accepted"]; efficient=z["total_environment_steps"]<f["total_environment_steps"] or z["harmful_selections"]<f["harmful_selections"]
    seed=cfg["random_namespaces"]["paired_bootstrap"]
    report={"experiment_run_id":m["experiment_run_id"],"manifest_id":m["manifest_id"],"source_git_commit":m["source_git_commit"],"initial_units_scanned":status["initial_units_scanned"],"eligible_first_attempts":len(cases),"second_decision_cases":len(pairs),"strongest_fixed":fixed,"method_summaries":summaries,"paired_bootstrap_zero_vs_strongest_fixed":{"accepted_rate":_paired_bootstrap_difference(vals("zero_progress_rule","final_accepted"),vals(fixed,"final_accepted"),seed=seed,resamples=cfg["bootstrap"]["resamples"]),"harmful_rate":_paired_bootstrap_difference(vals("zero_progress_rule","harmful_selection"),vals(fixed,"harmful_selection"),seed=seed+1,resamples=cfg["bootstrap"]["resamples"]),"steps":_paired_bootstrap_difference(vals("zero_progress_rule","total_environment_steps"),vals(fixed,"total_environment_steps"),seed=seed+2,resamples=cfg["bootstrap"]["resamples"])},"promotion_checks":{"population_complete":complete,"recovery_not_below":not_below,"harm_not_above":harm_ok,"recovery_tied":tied,"tie_has_efficiency_improvement":efficient},"promotion_gate_passed":complete and not_below and harm_ok and (not tied or efficient),"glm_authorized":False,"memory_authorized":False,"validation_authorized":False,"heldout_authorized":False,"api_calls":0}
    _write_json(rd/"analysis_summary.json",report);return report
def main()->int:
    p=argparse.ArgumentParser();p.add_argument("--run-dir",type=Path,required=True);a=p.parse_args()
    try:print(json.dumps(analyze(a.run_dir.resolve()),indent=2));return 0
    except Exception as e:print(f"[FAIL] {type(e).__name__}: {e}",file=sys.stderr);return 1
if __name__=="__main__":raise SystemExit(main())

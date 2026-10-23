"""Guarded, exclusive posthoc analysis of the completed 270-run population."""
import argparse
import gzip
import json
from pathlib import Path
import sys
from time import perf_counter_ns

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
import numpy.testing
from src.analysis import response_qualification_io_v1 as io
from src.analysis import response_qualification_failure_v1 as analysis
from src.analysis.movement_diagnostic_guard_v1 import read_only_analysis_guard

SOURCE=ROOT/"outputs/response_model_qualification/development_v1/response_qualification_20261020T092011Z_636d6b1f9e39"
OUTPUT=ROOT/"outputs/response_qualification_failure/analysis_v1"
CONFIG=ROOT/"configs/movement_task/response_qualification_failure_analysis_v1.json"


def compact(case):
    return {**{k:v for k,v in case.items() if k not in ("physical_rows","behavior","state_witnesses","partial_public_events")},
        "physical_rows":[{k:r[k] for k in ("logical_step","noise_cursor_after","command","after","phase","executed_action_oracle")} for r in case["physical_rows"]],
        "behavior":{"events":[e for e in case["behavior"]["events"] if e["kind"]=="ACQUISITION_ENTRY"]}}


def expected_config():
    return {"version":"response_qualification_failure_analysis_v1","scope":"POSTHOC_DESCRIPTIVE_ONLY",
        "source":SOURCE.relative_to(ROOT).as_posix(),"source_manifest_id":"b3bd767f35c0720e8fa148097ba8f1b909da5c3d61c8a3c4398f58ae76a536e6",
        "populations":{"TRAIN":108,"CAL":54,"QUAL":108},"stages":list(analysis.STAGES),
        "training_geometry":"FROZEN_QUADRATIC_NORMALIZATION; TRAIN_RANGES; WEIGHTED_PHI_GRAM_PLUS_ORIGINAL_RIDGE; NO_TARGETS_OR_NEW_RESPONSE_FIT",
        "terms":list(analysis.TERMS),"correlation_lags":[0,1,2],"within_trajectory_quantiles":[.9],
        "aggregation":"TRAJECTORY_FIRST_THEN_EQUAL_GROUP; NULL_NOT_ZERO; ALL_TASKS_CONDITIONS_STAGES_RETAINED",
        "new_collection":0,"new_api_calls":0,"new_response_fits":0,"threshold_or_model_search":False,"arx_selector_changes":False}


def source_catalog():
    manifest=io.load(SOURCE/"manifest.json")
    io.require(manifest["manifest_id"]==expected_config()["source_manifest_id"],"wrong frozen population")
    catalogue={n:io.sha(ROOT/n) for n in io.read(SOURCE/"artifact_provenance.json")["source_sha256"]}
    catalogue[(SOURCE/"artifact_provenance.json").relative_to(ROOT).as_posix()]=io.sha(SOURCE/"artifact_provenance.json")
    for n,h in io.read(SOURCE/"artifact_provenance.json")["source_sha256"].items():io.require(catalogue[n]==h,"prior result artifact changed: "+n)
    return manifest,catalogue


def run(output=OUTPUT):
    start=perf_counter_ns();config=io.read(CONFIG);io.require(config==expected_config(),"posthoc scope changed")
    with read_only_analysis_guard():
        manifest,catalogue=source_catalog();bank=io.read(SOURCE/"training/models.json")["models"];output.mkdir(parents=True)
        training=[compact(c) for c in io.rows(SOURCE/"train/cases.jsonl.gz")]
        geometries={t:analysis.geometry([c for c in training if c["task"]==t],bank[t][analysis.MODELS[2]]) for t in io.TASKS}
        io.write(output/"training_geometry.json",{t:g["summary"] for t,g in geometries.items()});del training
        all_cells=[];registry=[];steps=responses=qual_predictions_checked=0
        original=iter(io.rows(SOURCE/"evaluation/step_predictions.jsonl.gz"))
        with gzip.open(output/"step_diagnostics.jsonl.gz","xt",encoding="utf-8") as target:
            for split in io.SPLITS:
                count=0
                for raw in io.rows(SOURCE/split.lower()/"cases.jsonl.gz"):
                    case=compact(raw);n=len(case["physical_rows"]);noise=io.noise(case["seed"],case["noise_namespace"])[:n]
                    rows,cells=analysis.analyze_case(case,bank[case["task"]],geometries[case["task"]],noise)
                    for row in rows:
                        if split=="QUAL" and row["eligible"]:
                            for mode in analysis.MODES:
                                for name in analysis.MODELS:
                                    saved=next(original)
                                    io.require((saved["case_id"],saved["step"],saved["method"],saved["input_mode"])==(case["case_id"],row["step"],name,mode),"QUAL source chronology changed")
                                    io.require(np.allclose(saved["prediction"],row["predictions"][mode][name],atol=1e-12,rtol=1e-8) and np.allclose(saved["target"],row["target"],atol=1e-14),"frozen QUAL prediction changed")
                                    qual_predictions_checked+=1
                        target.write(json.dumps(row,separators=(",",":"),allow_nan=False)+"\n")
                    all_cells.extend(cells);steps+=n;responses+=max(n-2,0);count+=1
                    registry.append({**{k:case[k] for k in ("case_id","split","task","group","variant","planned_boundary","success","stop_reason")},
                        "actual_steps":n,"responses":max(n-2,0),"missing_history_steps":min(n,2),"actual_task_steps":case["task_steps"],"missing_post_task":not any(c["responses"] for c in cells if c["stage"]=="POST_TASK")})
                io.require(count==config["populations"][split],"missing/extra allocated trajectory")
        io.require(next(original,None) is None,"extra QUAL source predictions")
        metric_index={(c["case_id"],c["stage"]):c for c in all_cells};checked=0
        for old in io.read(SOURCE/"evaluation/trajectory_metrics.json"):
            cell=metric_index[old["case_id"],old["stage"]];value=cell["rmse"][old["input_mode"]][old["method"]]
            io.require(cell["responses"]==old["n"] and (value is None and old["rmse"] is None or value is not None and np.isclose(value,old["rmse"],atol=1e-12,rtol=1e-8)),"original QUAL metric changed");checked+=1
        summary=analysis.grouped_summary(all_cells)
        io.write(output/"trajectory_stages.json",all_cells);io.write(output/"group_summaries.json",summary);io.write(output/"case_registry.json",registry)
        io.require(all(io.sha(ROOT/n)==h for n,h in catalogue.items()),"read-only analysis mutated its source")
        io.write(output/"source_hashes.json",catalogue)
        source_files=["src/analysis/response_qualification_failure_v1.py","scripts/analyze_response_qualification_failure_v1.py",
            "scripts/audit_response_qualification_failure_v1.py","scripts/report_response_qualification_failure_v1.py","tests/test_response_qualification_failure_v1.py",
            CONFIG.relative_to(ROOT).as_posix(),"docs/protocols/response_qualification_failure_analysis_v1.md"]
        completion={"scope":"POSTHOC_DESCRIPTIVE_ONLY","status":"COMPLETE_FOR_INDEPENDENT_AUDIT","source_experiment_run_id":manifest["experiment_run_id"],
            "source_manifest_id":manifest["manifest_id"],"source_git_commit":manifest["source_git_commit"],"source_result_commit":"a1cdb48",
            "executions":len(registry),"actual_source_steps":steps,"eligible_real_history_responses":responses,"first_two_history_missing":steps-responses,
            "trajectory_stage_cells":len(all_cells),"group_summary_cells":len(summary),"frozen_qual_predictions_checked":qual_predictions_checked,"original_qual_metrics_unchanged":checked,
            "wall_ns":perf_counter_ns()-start,"new_environment_creations":0,"new_environment_steps":0,"new_all_resets":0,"new_simulation_frames":0,
            "new_api_calls":0,"new_model_fits":0,"diagnostic_training_geometry_constructions":3,"threshold_searches":0,"new_selectors":0,
            "analysis_sha256":{n:io.sha(ROOT/n) for n in source_files},"artifact_sha256":{p.name:io.sha(p) for p in output.iterdir() if p.is_file()}}
        io.write(output/"completion.json",completion)
    print(json.dumps({k:completion[k] for k in ("status","executions","actual_source_steps","original_qual_metrics_unchanged","new_environment_steps","new_api_calls","new_model_fits")}))


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--output",type=Path,default=OUTPUT);run(p.parse_args().output.resolve())

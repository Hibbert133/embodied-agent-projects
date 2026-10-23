"""One exclusive, zero-interaction descriptive analysis of all 756 saved executions."""
import argparse
import gzip
import json
from pathlib import Path
import sys
from time import perf_counter_ns
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
from src.analysis import observable_history_io_v1 as io
from src.analysis import history_response_failure_v1 as analysis

SOURCE=ROOT/"outputs/observable_history_transfer/development_v1/observable_history_20261021T154956Z_d256a0cf6753"
OUTPUT=ROOT/"outputs/history_response_failure/analysis_v1"
CONFIG=ROOT/"configs/movement_task/history_response_failure_analysis_v1.json"
PROTOCOL="docs/protocols/history_response_failure_analysis_v1_zh.md"


def expected_config():
    return {"version":"history_response_failure_analysis_v1","scope":"POSTHOC_DESCRIPTIVE_ONLY","source":SOURCE.relative_to(ROOT).as_posix(),
        "source_manifest_id":"210833e32b9ae18d9ad6f08eab55a4a2db9adebb00fc000686ea3e20a776ae5e","source_result_commit":"ab3f7a85b285b4bc8c07044a0d3b727613509c27",
        "models_sha256":"b168a7b11e53ae20d014361fdf132f52fda1b57e8ed3eb23277946cb271411d3","statistics_sha256":"6dbafa7e75bf0ab806d15e568ea90e27bd34d5bf2a02a5be037d8b57c400119c",
        "populations":{"TRAIN":216,"CAL":108,"TEST":432},"models":list(analysis.MODELS),"stages":list(analysis.STAGES),"correlation_lags":[0,1,2],
        "range_scope":"SOURCE_MATCHED_TRAIN_CURRENT_INPUTS_T_GE_2; PREFIX_FRAMES0_1_NOT_TRAIN_RANGE_REFERENCES","z_descriptors":[3,5,10],"gate_descriptors":[.01,.99],
        "feature_quantile":.95,"aggregation":"WITHIN_TRAJECTORY_THEN_EQUAL_GROUP; SOURCES_NOT_REPLICATES; EMPTY_PREDICTION_NULL; EMPTY_ADDITIVE_OBJECTIVE_MASS_ZERO",
        "target_population":"UNCHANGED_REAL_T_GE_2","new_environment_steps":0,"new_api_calls":0,"new_model_fits":0,"new_parameter_variants":0,"online_thresholds_fitted":False}


def compact(case):
    return {**{k:case[k] for k in ("case_id","split","group","task","context","measurement_program","seed","noise_namespace","planned_boundary","success","stop_reason","total_steps","task_steps")},
        "initial":case["initial"],"physical_rows":[{k:r[k] for k in ("logical_step","noise_cursor_after","command","after","phase")} for r in case["physical_rows"]],
        "behavior":{"events":[e for e in case["behavior"]["events"] if e["kind"]=="ACQUISITION_ENTRY"]}}


def source_catalog():
    m=io.load(SOURCE/"manifest.json");cfg=expected_config();io.require(m["manifest_id"]==cfg["source_manifest_id"],"wrong source population")
    io.require(io.sha(SOURCE/"training/models.json")==cfg["models_sha256"] and io.sha(SOURCE/"evaluation/statistics.json")==cfg["statistics_sha256"],"frozen models/statistics changed")
    io.require(io.read(SOURCE/"pipeline_completion.json")["status"]=="COMPLETE","completed source required")
    catalog={}
    closure=SOURCE/"delivery_v1/final_index_closure.json"
    for name,h in io.read(closure)["indexed_files_sha256"].items():
        io.require(io.sha(ROOT/name)==h,"committed result changed: "+name);catalog[name]=h
    catalog[closure.relative_to(ROOT).as_posix()]=io.sha(closure)
    for split in (*io.SPLITS,"training","calibration","evaluation"):
        folder=SOURCE/split.lower();completion=io.read(folder/"completion.json")
        for n,h in completion["artifact_sha256"].items():
            p=folder/n;io.require(io.sha(p)==h,"source artifact changed: "+str(p));catalog[p.relative_to(ROOT).as_posix()]=h
    for n in ("manifest.json","report_receipt.json","evaluation/numeric_audit.json","training/audit.json","calibration/audit.json","test_lock.json","delivery_v1/final_report_receipt.json"):
        catalog[(SOURCE/n).relative_to(ROOT).as_posix()]=io.sha(SOURCE/n)
    for n in ("train/audit.json","cal/audit.json","test/audit.json","training/audit.json","calibration/audit.json","evaluation/numeric_audit.json"):
        io.require(io.read(SOURCE/n)["integrity"]=="PASSED","source independent audit required")
    return m,catalog


def run(output=OUTPUT):
    started=perf_counter_ns();config=io.read(CONFIG);io.require(config==expected_config(),"analysis scope changed")
    commit=io.git("rev-parse","HEAD");manifest,catalog=source_catalog();output.mkdir(parents=True)
    with analysis.diagnostic_guard():
        bank=io.read(SOURCE/"training/models.json")["models"];bank_digest=io.digest(bank)
        ranges=analysis.training_ranges((compact(c) for c in io.rows(SOURCE/"train/cases.jsonl.gz")),io.PROGRAMS,io.TASKS)
        io.require(all(ranges[b][t]["trajectories"]==36 for b in io.PROGRAMS for t in io.TASKS),"complete TRAIN range population")
        io.write(output/"training_ranges.json",ranges);registry=[];all_rows=[];feature_rows=[];steps=responses=checked_predictions=checked_metrics=0
        original=iter(io.rows(SOURCE/"evaluation/step_predictions.jsonl.gz"));metric_index={(r["case_id"],r["source_bank"],r["method"],r["stage"]):r for r in io.read(SOURCE/"evaluation/trajectory_metrics.json")}
        with gzip.open(output/"trajectory_stage_diagnostics.jsonl.gz","xt",encoding="utf-8") as log:
            for split in io.SPLITS:
                count=0;specs=manifest["config"]["population"][split]
                for raw in io.rows(SOURCE/split.lower()/"cases.jsonl.gz"):
                    case=compact(raw);io.require(count<len(specs) and all(case[k]==specs[count][k] for k in ("case_id","split","group","task","context","measurement_program","seed")),"source population/order mismatch")
                    n=len(case["physical_rows"]);io.require(all(r["logical_step"]==j and r["noise_cursor_after"]==j+1 for j,r in enumerate(case["physical_rows"])),"noise cursor mismatch")
                    noise=io.noise(case["seed"],case["noise_namespace"])[:n]
                    task_bank={b:bank[b][case["task"]] for b in io.PROGRAMS}
                    rows=analysis.analyze_case(case,task_bank,ranges,noise,original if split=="TEST" else None)
                    for row in rows:
                        if split=="TEST" and row["method"] in io.MODELS:
                            old=metric_index[row["case_id"],row["source_bank"],row["method"],row["stage"]]
                            io.require(row["responses"]==old["n"] and (row["rmse"] is None and old["rmse"] is None or row["rmse"] is not None and np.isclose(row["rmse"],old["rmse"],atol=1e-12,rtol=1e-8)),"original TEST stage metric changed");checked_metrics+=1
                        log.write(json.dumps(row,separators=(",",":"),allow_nan=False)+"\n")
                        all_rows.append({k:v for k,v in row.items() if k!="gru"})
                        # Preserve scalar gate descriptors for grouped tables, while
                        # the complete 43-feature diagnostics remain in the log.
                        if "gru" in row:all_rows[-1]["gru"]={k:v for k,v in row["gru"].items() if not k.startswith("feature_")}
                        if name_for_features(row):feature_rows.append(row)
                    steps+=n;responses+=max(n-2,0);count+=1
                    checked_predictions+=(max(n-2,0)*10 if split=="TEST" else 0)
                    registry.append({k:case[k] for k in ("case_id","split","group","task","context","measurement_program","planned_boundary","success","stop_reason","total_steps","task_steps")}|{"common_responses":max(n-2,0)})
                io.require(count==config["populations"][split],"incomplete source split")
        io.require(next(original,None) is None and checked_metrics==34560 and checked_predictions==411440,"source TEST prediction/metric population changed")
        io.require(io.digest(bank)==bank_digest,"frozen models mutated in memory")
        tables={"overall":analysis.grouped(all_rows,("split","method","stage")),
            "matched_training":analysis.grouped([r for r in all_rows if r["split"]=="TRAIN" and r["same_training_source"]],("task","source_bank","method","stage")),
            "task_context_program":analysis.grouped(all_rows,("split","task","context","measurement_program","method","stage")),
            "source_program_transfer":analysis.grouped(all_rows,("split","source_bank","measurement_program","method","stage"))}
        io.write(output/"grouped_tables.json",tables);io.write(output/"feature_tables.json",analysis.feature_tables(feature_rows));io.write(output/"case_registry.json",registry);io.write(output/"source_hashes.json",catalog)
        io.require(all(io.sha(ROOT/n)==h for n,h in catalog.items()),"source bytes changed during read-only analysis")
        io.require(steps==71773 and responses==70261 and len(registry)==756,"all source physical steps/history required")
        files=("src/analysis/history_response_failure_v1.py","scripts/analyze_history_response_failure_v1.py","scripts/audit_history_response_failure_v1.py","scripts/report_history_response_failure_v1.py","tests/test_history_response_failure_v1.py",PROTOCOL,CONFIG.relative_to(ROOT).as_posix())
        io.write(output/"completion.json",{"scope":"POSTHOC_DESCRIPTIVE_ONLY","status":"COMPLETE_FOR_INDEPENDENT_AUDIT","source_run_id":manifest["experiment_run_id"],"source_manifest_id":manifest["manifest_id"],
            "source_result_commit":config["source_result_commit"],"analysis_git_commit":commit,"executions":756,"source_physical_steps":steps,"common_real_responses":responses,"trajectory_stage_model_cells":len(all_rows),
            "source_TEST_predictions_unchanged":checked_predictions,"source_TEST_stage_metrics_unchanged":checked_metrics,"diagnostic_range_summaries":6,"new_model_fits":0,"new_parameter_variants":0,
            "new_environment_creations":0,"new_environment_steps":0,"new_all_resets":0,"new_physical_frames":0,"new_api_calls":0,"wall_ns":perf_counter_ns()-started,
            "analysis_sha256":{n:io.sha(ROOT/n) for n in files},"artifact_sha256":{p.name:io.sha(p) for p in output.iterdir() if p.is_file()}})
    print({"status":"COMPLETE_FOR_INDEPENDENT_AUDIT","executions":756,"new_environment_steps":0,"new_api_calls":0,"new_model_fits":0})


def name_for_features(row):return row["method"]=="GRU_WINDOW16" and row["stage"] in ("ALL_RESPONSE","POST_TASK")


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--output",type=Path,default=OUTPUT);run(parser.parse_args().output.resolve())

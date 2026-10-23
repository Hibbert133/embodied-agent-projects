"""Identification-only evaluator; never drives the robot or a task controller."""
import argparse
from collections import Counter
from copy import deepcopy
import gzip
import json
from pathlib import Path
import sys
from time import perf_counter_ns
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.analysis import selected_response_io_v1 as io
from src.probe.local_reprobe_v1 import SelectedAnchorWindow
from src.probe.selected_response_reference_v1 import METHODS, infer_operator

REFERENCES = ("SAVED_C8","RELOCATION_INTEGRAL")
ALL_METHODS = (*METHODS,*REFERENCES)


def lines(path):
    with gzip.open(path,"rt",encoding="utf-8") as handle:
        for line in handle:yield json.loads(line)


def estimates(row, models):
    """Send only a strict visible window to the learned estimator."""
    if not row["boundary_ready"]:
        return {m:{"valid":False,"reason":"PLANNED_BOUNDARY_UNAVAILABLE","nfev":0} for m in ALL_METHODS}
    public = row["reacquisition"]["public"]
    fits = {}
    for method in METHODS:
        if public["window"] is None:
            fits[method] = {"valid":False,"reason":"NO_COMPLETE_WINDOW:"+public["reason"],"nfev":0}
        else:
            fits[method] = infer_operator(models[row["task"]][method],SelectedAnchorWindow.from_mapping(public["window"]))
    saved = [e["payload"]["fit"] for e in row["prefix"]["public"]["events"]
             if e["kind"] == "FIT_RESULT" and e["payload"]["at_calls"] == 8]
    if len(saved) != 1 or saved[0]["valid"] is not True:raise ValueError("audited saved C8 fit required")
    fits[REFERENCES[0]] = {"valid":True,"reason":"SAVED_PRECHANGE_C8","nfev":0,
        "matrix_xy":deepcopy(saved[0]["matrix_xy"]),"bias_xy":deepcopy(saved[0]["bias_xy"])}
    evidence = public["relocation_evidence"]
    if evidence is None:
        fits[REFERENCES[1]] = {"valid":False,"reason":"NO_RELOCATION_EVIDENCE","nfev":0}
    else:
        # Invert the saved command correction. This heuristic cannot learn a new
        # matrix: its matrix is inherited from C8, only its offset was integrated.
        controller = evidence["controller"];matrix = np.linalg.inv(controller["matrix_xy"])
        bias = -matrix@np.asarray(controller["offset"][:2])
        fits[REFERENCES[1]] = {"valid":True,"reason":"SAVED_PREPROBE_INTEGRAL","nfev":0,
            "matrix_xy":matrix.tolist(),"bias_xy":bias.tolist()}
    return fits


def score(fit, truth, config):
    if fit["valid"]:
        matrix_error = float(np.linalg.norm(np.array(fit["matrix_xy"])-truth["matrix_xy"]))
        bias_error = float(np.linalg.norm(np.array(fit["bias_xy"])-truth["bias_xy"]))
    else:
        matrix_error,bias_error = config["invalid_matrix_error"],config["invalid_bias_error"]
    return {"matrix_error":matrix_error,"bias_error":bias_error,
            "score":matrix_error+bias_error/config["bias_score_scale"],"penalty_applied":not fit["valid"]}


def evaluate_case(row, models, config):
    started = perf_counter_ns();fits = estimates(row,models);truth = io.destination(row)
    return {**{k:row[k] for k in ("unit","task","seed","variant","planned_boundary","boundary_ready","complete_window",
        "collection_stop_reason","success","total_steps","reposition_steps","probe_steps")},
        "group":row["unit"]//9,"fits":fits,
        "errors":{m:score(fits[m],truth,config) for m in ALL_METHODS},
        "evaluation_wall_ns":perf_counter_ns()-started}


def summarize(rows,config):
    if not rows:raise ValueError("full independent population required")
    summaries = []
    for method in ALL_METHODS:
        valid_rows = [r for r in rows if r["fits"][method]["valid"]]
        summaries.append({"method":method,"attempts":len(rows),"valid":sum(r["fits"][method]["valid"] for r in rows),
            **{key:float(np.mean([r["errors"][method][key] for r in rows])) for key in ("score","matrix_error","bias_error")},
            "valid_only_means":{key:float(np.mean([r["errors"][method][key] for r in valid_rows])) if valid_rows else None for key in ("score","matrix_error","bias_error")},
            "reasons":dict(sorted(Counter(r["fits"][method]["reason"] for r in rows).items()))})
    strata = []
    for task in io.TASKS:
        for condition in ("UNCHANGED","CHANGED"):
            subset = [r for r in rows if r["task"] == task and r["variant"] == condition]
            complete = sum(r["complete_window"] for r in subset)
            valid = sum(r["complete_window"] and r["fits"][config["candidate"]]["valid"] for r in subset)
            strata.append({"task":task,"condition":condition,"attempts":len(subset),"complete":complete,
                "candidate_valid_complete":valid,"complete_fraction":complete/len(subset) if subset else 0.,
                "candidate_valid_fraction_complete":valid/complete if complete else 0.,
                "candidate_valid_fraction_all":valid/len(subset) if subset else 0.})
    group_ids = sorted({r["group"] for r in rows});contrasts = []
    # The same resampled groups are used for both registered comparisons.
    indices = np.random.default_rng(config["bootstrap_seed"]).integers(0,len(group_ids),
        (config["bootstrap_replicates"],len(group_ids)))
    for reference in ("SELECTED_HISTORY","RELOCATION_INTEGRAL"):
        values = np.array([np.mean([r["errors"][config["candidate"]]["score"]-r["errors"][reference]["score"]
                                   for r in rows if r["group"] == group]) for group in group_ids])
        low,high = np.quantile(values[indices].mean(axis=1),[.025,.975])
        contrasts.append({"candidate":config["candidate"],"reference":reference,"groups":len(values),
            "group_differences":values.tolist(),"mean_difference":float(values.mean()),"ci95":[float(low),float(high)]})
    gates = {"complete_each_task_condition":all(s["complete_fraction"] >= config["minimum_complete_fraction_each_task_condition"] for s in strata),
        "valid_among_complete_each_task_condition":all(s["candidate_valid_fraction_complete"] >= config["minimum_valid_fraction_complete"] for s in strata),
        "better_than_both_references":all(c["ci95"][1] < 0 for c in contrasts)}
    return {"methods":summaries,"strata":strata,"contrasts":contrasts,"gates":gates,
        "qualification":"QUALIFIED_IDENTIFICATION_ONLY" if all(gates.values()) else "NOT_QUALIFIED",
        "failure_reasons":dict(sorted(Counter(r["collection_stop_reason"] for r in rows).items())),
        "planned_boundary_unavailable":sum(not r["boundary_ready"] for r in rows),
        "early_task_successes":sum(r["success"] for r in rows),"task_utility_demonstrated":False,"probability_guarantee":False}


def costs(rows,bank,audit,config):
    units = len({r["unit"] for r in rows});training = bank["training_costs"]
    prior = config["historical_nominal_cost"];n = len(rows)
    result = []
    for method in ALL_METHODS:
        online = sum(r["total_steps"] if method in METHODS else
                     r["total_steps"]-r["probe_steps"]-(r["reposition_steps"] if method == "SAVED_C8" else 0) for r in rows)
        nominal = training["total_steps"] if method in METHODS else 0
        resets = training["lifecycle"]["counts"]["reset_completed"] if method in METHODS else 0
        frames = training["lifecycle"]["counts"]["simulation_frames_completed"] if method in METHODS else 0
        controlled = training["lifecycle"]["by_phase"]["CONTROLLED_RESET"]["reset_completed"] if method in METHODS else 0
        result.append({"method":method,"online_steps":online,"new_nominal_steps":nominal,"historical_steps":prior["environment_steps"],
            "total_steps":online+nominal+prior["environment_steps"],"steps_per_paired_unit":(online+nominal+prior["environment_steps"])/units,
            "controlled_resets":n+controlled+prior["controlled_resets"],"all_reset_calls":51*n+resets+prior["all_reset_calls"],
            "simulation_frames":25500*n+5*online+frames+prior["simulation_frames"],
            "new_response_model_fits":3 if method in METHODS else 0,
            "new_causal_output_regressions":24 if method in METHODS else 0,
            "online_inference_attempts":sum(r["complete_window"] for r in rows) if method in METHODS else 0,
            "online_optimizer_nfev":sum(r["fits"][method]["nfev"] for r in rows)})
    return {"actual_training_collection":training,"actual_qualification_collection":audit["costs"],
        "method_accounting":result,"amortization_paired_units":units,"new_api_calls":0,
        "shared_collection_not_sum_of_method_accounts":True,
        "baseline_accounts_end_at_saved_evidence_without_replaying_counterfactual_tasks":True}


def evaluate(path):
    manifest,_ = io.load(path);bank,done = io.bank(path);folder = path.parent
    audit = io.read(folder/"qualify_audit/record_audit.json")
    if audit["integrity"] != "PASSED" or audit["stage"] != "qualify":raise ValueError("passed independent record audit required")
    if any(audit[k] != manifest[k] for k in io.IDENTITY):raise ValueError("qualification identity changed")
    for name,value in audit["collection_artifact_sha256"].items():
        if io.sha(folder/"qualify"/name) != value:raise ValueError("qualification source changed")
    output = folder/"evaluation";output.mkdir();started = perf_counter_ns();identity = {k:manifest[k] for k in io.IDENTITY}
    try:
        rows = []
        with (output/"estimates.jsonl").open("x",encoding="utf-8") as handle:
            for row in lines(folder/"qualify/cases.jsonl.gz"):
                result = evaluate_case(row,bank["models"],manifest["config"]);rows.append(result)
                handle.write(json.dumps(result,allow_nan=False)+"\n");handle.flush()
        if len(rows) != len(manifest["config"]["qualify_cases"]):raise ValueError("incomplete evaluation population")
        result = {**identity,**summarize(rows,manifest["config"]),"costs":costs(rows,bank,audit,manifest["config"]),
            "models_sha256":done["models_sha256"],"qualification_audit_sha256":io.sha(folder/"qualify_audit/record_audit.json"),
            "estimates_sha256":io.sha(output/"estimates.jsonl"),"wall_ns":perf_counter_ns()-started}
        io.write(output/"summary.json",result)
        return result
    except BaseException as error:
        io.write(output/"failed_evaluation.json",{**identity,"error":type(error).__name__,"message":str(error),"wall_ns":perf_counter_ns()-started})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__);parser.add_argument("--manifest",required=True,type=Path)
    result = evaluate(parser.parse_args().manifest.resolve());print(json.dumps({"qualification":result["qualification"],"gates":result["gates"]}))

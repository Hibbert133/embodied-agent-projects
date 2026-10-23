"""Whole-group task statistics for the fixed, prospective four-method bridge."""
from collections import Counter

import numpy as np

from src.analysis import movement_task_io_v1 as io


def require(ok, message):
    if not ok:raise ValueError(message)


def validate_rows(rows, config):
    io.validate(config)
    require(len(rows) == config["executions"], "all registered executions remain in the denominator")
    index = {(r["unit"],r["variant"]):r for r in rows}
    require(len(index) == len(rows), "duplicated task execution")
    counters = ("total_steps","deadline_loss","reposition_steps","task_steps","policy_queries","parameter_fit_attempts",
                "parameter_fit_results","optimizer_nfev","movement_fit_attempts","movement_fit_results","movement_optimizer_nfev")
    for spec in config["cases"]:
        row = index.get((spec["unit"],spec["variant"]));require(type(row) is dict and set(row) == set(io.COMPACT), "unknown or missing task summary")
        require(all(type(row[k]) is type(v) and row[k] == v for k,v in spec.items()), "task population changed")
        require(all(type(row[k]) is bool for k in ("completed","success","boundary_ready","stopped")) and row["completed"], "unfinished task cannot be silently dropped")
        require(all(type(row[k]) is int and row[k] >= 0 for k in counters), "strict nonnegative task counters required")
        require(row["total_steps"] <= 500 and row["deadline_loss"] == (row["total_steps"] if row["success"] else 500)
                and not (row["stopped"] and row["success"]), "task loss or success denominator differs")
        require(row["reposition_steps"] <= 64 and row["reposition_steps"]+row["task_steps"] <= row["total_steps"], "movement/task budget differs")
        require(row["parameter_fit_attempts"] == row["parameter_fit_results"] and row["movement_fit_attempts"] == row["movement_fit_results"] <= 1
                and row["optimizer_nfev"] >= row["movement_optimizer_nfev"], "incomplete computation counts")
        method = io.method(spec["variant"])
        actions = {"DIRECT_C8":{"RUN_SAVED_C8"},"MOVE_KEEP_C8":{"RUN_SAVED_C8","ENDED_NO_UPDATE"},
            "MOVE_INTEGRAL":{"RUN_SAVED_INTEGRAL","ENDED_NO_UPDATE"},
            "MOVE_ARX_KEEP":{"RUN_SAVED_ARX","REJECT_ARX_KEEP_SAVED_C8","ENDED_NO_UPDATE"}}[method] | {"NO_LIVE_BOUNDARY"}
        require(row["action"] in actions, "task action does not belong to its method")
        if method == "DIRECT_C8":require(row["reposition_steps"] == 0, "direct control moved first")
        if method != "MOVE_ARX_KEEP":require(row["movement_fit_attempts"] == row["movement_optimizer_nfev"] == 0, "unregistered movement fit")
        if not row["boundary_ready"]:
            require(row["action"] == "NO_LIVE_BOUNDARY" and row["reposition_steps"] == row["task_steps"] == row["movement_fit_attempts"] == 0,
                    "unavailable boundary was replaced with another execution")
    return index


def statistics(rows, config, arx_costs):
    index = validate_rows(rows, config);cases = 6*io.GROUPS
    require(arx_costs["known_full_source_environment_steps"] == 23314 and arx_costs["known_full_source_controlled_resets"] == 432
            and arx_costs["direct_source_collection"]["all_reset_calls"] is None
            and arx_costs["direct_source_collection"]["simulation_frames"] is None, "source fee scope changed")
    cells = {}
    for method in io.METHODS:
        part = [r for r in rows if io.method(r["variant"]) == method]
        fee = config["historical_c8_cost"]["environment_steps"]+(23314 if method == "MOVE_ARX_KEEP" else 0)
        resets = config["historical_c8_cost"]["controlled_resets"]+(432 if method == "MOVE_ARX_KEEP" else 0)
        cells[method] = {"cases":len(part),"successes":sum(r["success"] for r in part),"stops":sum(r["stopped"] for r in part),
            "actions":dict(sorted(Counter(r["action"] for r in part).items())),
            **{"mean_"+k:sum(r[k] for r in part)/cases for k in ("deadline_loss","total_steps","reposition_steps","task_steps")},
            **{"total_"+k:sum(r[k] for r in part) for k in ("policy_queries","parameter_fit_attempts","optimizer_nfev","movement_optimizer_nfev")},
            "historical_source_environment_steps":fee,"historical_source_controlled_resets":resets,
            "mean_amortized_actual_steps":(sum(r["total_steps"] for r in part)+fee)/cases,
            "by_condition_task":[{"condition":c,"task":t,"cases":io.GROUPS,
                "successes":sum(r["success"] for r in part if r["variant"] == c+"_"+method and r["task"] == t),
                "mean_deadline_loss":sum(r["deadline_loss"] for r in part if r["variant"] == c+"_"+method and r["task"] == t)/io.GROUPS}
                for c in io.CONDITIONS for t in io.TASKS]}
    rng = np.random.default_rng(config["bootstrap_seed"])
    draws = np.concatenate([rng.choice(np.arange(s,io.GROUPS,3),(config["bootstrap_replicates"],18)) for s in range(3)],axis=1)
    contrasts = []
    for number,(method,base) in enumerate(io.CONTRASTS):
        totals = np.array([[sum(int(index[3*g+i,c+"_"+method][field])-int(index[3*g+i,c+"_"+base][field])
            for i in range(3) for c in io.CONDITIONS) for field in ("success","deadline_loss","total_steps")]
            for g in range(io.GROUPS)],dtype=np.int64)
        intervals = np.quantile(totals[draws].sum(axis=1)/cases,[.025,.975],axis=0)
        contrasts.append({"method":method,"reference":base,"role":"PRIMARY" if number == 0 else "SECONDARY_UNADJUSTED",
            "group_values":(totals/6).tolist(),"metrics":{name:{"difference":float(totals[:,j].sum()/cases),
                "paired_group_percentile_95":intervals[:,j].tolist()}
                for j,name in enumerate(("success_rate","deadline_loss","actual_steps"))},
            "success_to_failure":sum(index[u,c+"_"+base]["success"] and not index[u,c+"_"+method]["success"] for u in range(162) for c in io.CONDITIONS),
            "failure_to_success":sum(not index[u,c+"_"+base]["success"] and index[u,c+"_"+method]["success"] for u in range(162) for c in io.CONDITIONS)})
    return {"methods":cells,"contrasts":contrasts,"independent_groups":54,"boundary_strata_groups":[18,18,18],
        "primary_loss_upper_below_zero":bool(contrasts[0]["metrics"]["deadline_loss"]["paired_group_percentile_95"][1] < 0),
        "primary_successes_not_lower":cells["MOVE_ARX_KEEP"]["successes"] >= cells["MOVE_INTEGRAL"]["successes"],
        "study_actual_control_steps":sum(r["total_steps"] for r in rows),
        "shared_historical_known_steps_once":27154,"shared_historical_controlled_resets_once":912,
        "historical_native_and_all_reset_total_unknown":True,"new_api_calls":0,
        "algorithm_novelty_demonstrated":False,"physical_model_transfer_qualified":False,
        "scope":"Fixed-method task comparisons; early successes and all failures retained; secondary intervals unadjusted; no adaptive acquisition claim."}

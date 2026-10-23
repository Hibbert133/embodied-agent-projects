"""Frozen-prefix, train-only model and independent parameter-score audit.

Public response-fit/optimizer helpers and lifecycle parser are explicitly reused.
Noise/action arithmetic, source memberships, normal equations and statistics are
reconstructed; no robot environment is created or advanced.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from scripts import run_cold_start_evidence as run
from scripts.audit_acquisition_value_v3 import JournalAudit, compiled_clock_units
from src.probe.cold_start_response import clipped_normal_mean, TASKS, MODELS, validate_model
from src.analysis.cold_start_evidence import visible_prefix, fit_training, estimates, old_samples
from src.probe.forward_prediction import features


def read(path):
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle: yield json.loads(line)


def same(a, b):
    if run.normal(a) != run.normal(b): raise ValueError("recorded business value differs")


def verify_terminal(summary, status, identity, lifecycle, steps, model_hash):
    for record in (summary, status):
        if any(record[k] != v for k, v in identity.items()): raise ValueError("foreign terminal identity")
        same(record["lifecycle"], lifecycle)
        if record["training_episodes"] != 384 or record["qualification_episodes"] != 96 or record["controlled_steps"] != steps or record["controlled_resets"] != 480:
            raise ValueError("terminal population or resource count differs")
        if any(record[k] != 0 for k in ("api_calls", "task_policy_executions", "memory_writes")):
            raise ValueError("unregistered task, API or memory cost")
    for k, v in status.items(): same(summary[k], v)
    if summary["models_sha256"] != model_hash: raise ValueError("terminal model digest differs")
    stats = summary["statistics"]
    if any(stats[k] is not False for k in ("task_performance_established", "probability_qualification", "algorithm_novelty_established")):
        raise ValueError("qualification scope changed")
    expected = "COMPLETED_COMPONENT_PASSED" if stats["qualification"]["passed"] else "COMPLETED_COMPONENT_FAILED"
    if status["status"] != expected: raise ValueError("terminal gate status differs")
    counts = lifecycle["counts"]; control = lifecycle["by_phase"].get("CONTROL", {})
    if steps > 3840 or lifecycle["by_phase"].get("CONTROLLED_RESET", {}).get("reset_completed") != 480 or control.get("simulation_completed") != steps:
        raise ValueError("physical control count differs")
    frames = counts["simulation_frames_completed"]
    if frames > 13000000 or frames != 500*counts["reset_completed"]+5*steps:
        raise ValueError("full cost arithmetic or frame cap differs")
    if any(counts.get(k, 0) for k in ("reset_errors", "simulation_errors", "uncertain_simulation_frames", "frame_budget_rejections")):
        raise ValueError("unresolved lifecycle error")


def audit(path, output):
    if output.exists(): raise FileExistsError("external audit already exists")
    m = run.load(path); base = path.parent; identity = {k: m[k] for k in run.IDENTITY}
    for name, expected in m["input_sha256"].items():
        content = subprocess.check_output(["git", "show", m["source_git_commit"]+":"+name], cwd=ROOT)
        if hashlib.sha256(content).hexdigest() != expected: raise ValueError("frozen Git input differs")
    clocks = compiled_clock_units(m); journal = JournalAudit(identity); events = iter(read(base / "events.jsonl.gz"))
    def business():
        while True:
            item = journal.accept(next(events))
            if item is not None: return item
    training = list(read(base / "TRAIN.jsonl.gz")); qualification = list(read(base / "QUALIFY.jsonl.gz"))
    saved_models = json.loads((base / "models.json").read_text(encoding="utf-8")); old, _, _ = run.load_bank(m["config"])
    rebuilt = fit_training(training)
    same(saved_models, {**identity, **rebuilt}); model_hash = run.digest(base / "models.json")
    max_normal_residual = 0.; mean_models_checked = 0
    for task in TASKS:
        part = [r for r in training if r["task"] == task]
        inputs = np.array([clipped_normal_mean(np.array(r["program"]["commands"])[:, :2])[0].ravel() for r in part])
        targets = np.array([visible_prefix(r).displacements.ravel() for r in part])
        model = saved_models["joint"][task]; offset, impulse, covariance = validate_model(model)
        prediction = offset+inputs @ impulse.T
        for t in range(1, 9):
            z = np.c_[np.ones(128), inputs[:, :2*t]]; coefficient = np.vstack((offset[2*t-2:2*t], impulse[2*t-2:2*t, :2*t].T))
            left = z.T @ z+np.diag(np.r_[0., np.full(2*t, 1e-6)])
            residual = float(np.max(np.abs(left @ coefficient-z.T @ targets[:, 2*t-2:2*t])))
            max_normal_residual = max(max_normal_residual, residual)
            if residual > 1e-10: raise ValueError("joint response normal equations differ")
            mean_models_checked += 1
        errors = targets-prediction; expected = errors.T @ errors/111
        expected = .95*expected+.05*np.diag(np.diag(expected))+1e-12*np.eye(16)
        np.testing.assert_allclose(covariance, expected, atol=1e-14, rtol=1e-12)
        flat = [s for record in part for s in old_samples(visible_prefix(record))]
        x = np.array([features(s.query, "LINEAR_ARX") for s in flat]); y = np.array([s.displacement for s in flat])
        arx = saved_models["same_data_arx"][task]; z = np.c_[np.ones(len(x)), (x-arx["mean"])/arx["scale"]]
        penalty = np.diag(np.r_[0., np.full(10, .001)])
        residual = float(np.max(np.abs((z.T @ z+penalty) @ np.array(arx["coefficients"])-z.T @ y)))
        max_normal_residual = max(max_normal_residual, residual)
        if residual > 1e-9: raise ValueError("same-data ARX normal equations differ")
        mean_models_checked += 1
    if len(training) != 384 or len(qualification) != 96: raise ValueError("incomplete registered population")
    expected_train = run.population(m["config"], "TRAIN"); expected_qual = run.population(m["config"], "QUALIFY")
    count = 0; steps = 0; frozen_sequence = None
    for split, records, specs in (("TRAIN", training, expected_train), ("QUALIFY", qualification, expected_qual)):
        if split == "QUALIFY":
            frozen = business()
            if frozen["event"] != "MODELS_FROZEN" or frozen["models_sha256"] != model_hash or frozen["training_case_ids"] != [r["case_id"] for r in training]:
                raise ValueError("model not frozen from train before qualification")
            frozen_sequence = frozen["sequence"]
        for record, spec in zip(records, specs):
            same({k: record[k] for k in spec}, spec)
            if any(record[k] != v for k, v in identity.items()): raise ValueError("foreign record identity")
            declared = business(); same(declared, record["program"])
            if declared["event"] != "PROGRAM_SAVED": raise ValueError("program not saved before execution")
            same(declared["ledger"], record["ledger_before"])
            if split == "QUALIFY" and declared["sequence"] <= frozen_sequence: raise ValueError("qualification before model freeze")
            tindex = TASKS.index(spec["task"])
            if split == "TRAIN":
                rng = np.random.default_rng(np.random.SeedSequence([spec["seed"], tindex, 54001]))
                commands = np.zeros((8, 4), np.float32); commands[:, :2] = rng.uniform(-.9, .9, (8, 2)).astype(np.float32)
            else:
                commands = np.repeat(np.array([[.4, 0, 0, 0], [-.4, 0, 0, 0], [0, .4, 0, 0], [0, -.4, 0, 0]], np.float32), 2, axis=0)
            same(commands.tolist(), declared["commands"])
            rng = np.random.default_rng(np.random.SeedSequence([spec["seed"], tindex, 54002, 0 if split == "TRAIN" else 1, spec["replicate"]+1]))
            noise = rng.normal(0, .05, (8, 3)).astype("<f4")
            if hashlib.sha256(noise.tobytes()).hexdigest() != declared["noise_commitment_oracle"]: raise ValueError("noise source commitment differs")
            start, factory, initial = business(), business(), business()
            if (start["event"], factory["event"], initial["event"]) != ("FACTORY_INTENT", "FACTORY_COMPLETE", "CONTROLLED_INITIAL"):
                raise ValueError("factory/reset ordering differs")
            same(initial["initial"], record["initial"]); same(initial["physics_witness_oracle"], record["initial_physics_witness_oracle"])
            operator = {"matrix_xy": np.eye(2).tolist(), "bias_xy": [0., 0.]} if split == "TRAIN" else next(o for o in m["operators_oracle"][spec["stream"]]["states_oracle"] if o["id"] == "A")
            current = record["initial"]; past = hashlib.sha256(); previous_clock = None
            for i, row in enumerate(record["trace"]):
                intent = business()
                if intent["event"] != "STEP_INTENT" or row["step"] != i+1 or intent["sequence"] != row["intent_sequence"] or row["program_sequence"] != declared["sequence"]:
                    raise ValueError("command timeline differs")
                for name in ("command", "before", "noise_before_hash", "ledger_before"): same(intent[name], row[name])
                same(row["before"], current); same(row["command"], commands[i].tolist())
                if any(current[k] for k in ("success", "terminated", "truncated")) or row["noise_before_hash"] != past.copy().hexdigest(): raise ValueError("ended or rewound prefix")
                actual = commands[i].copy(); actual[:2] = np.asarray(operator["matrix_xy"], np.float32) @ actual[:2]+np.asarray(operator["bias_xy"], np.float32)
                actual[:3] += noise[i]; actual = np.clip(actual, -1, 1); past.update(noise[i].tobytes())
                same(actual.tolist(), row["executed_action_oracle"])
                if past.copy().hexdigest() != row["noise_after_hash"]: raise ValueError("noise consumption differs")
                if not declared["saved_ns"] < row["intent_saved_ns"] == intent["saved_ns"] < row["execution_started_ns"] <= row["completed_ns"]: raise ValueError("execution before saved intent")
                if not np.isclose(row["simulation_time_after_oracle"]-row["simulation_time_before_oracle"], clocks[spec["task"]]["env_step_seconds"], atol=1e-10, rtol=1e-10): raise ValueError("step clock differs")
                if previous_clock is not None and previous_clock != row["simulation_time_before_oracle"]: raise ValueError("reset during live prefix")
                previous_clock = row["simulation_time_after_oracle"]; current = row["after"]
                complete = business()
                if complete["event"] != "STEP_COMPLETE": raise ValueError("missing executed command")
                for name, value in row.items(): same(complete[name], value)
            if len(record["trace"]) != record["total_steps"] or len(record["trace"]) > 8 or record["environment_resets"] != 1 or record["completed_eight"] != (len(record["trace"]) == 8):
                raise ValueError("prefix completeness or resource count differs")
            if record["task_success_during_probe"] != current["success"]:
                raise ValueError("probe success flag differs")
            if len(record["trace"]) < 8 and not any(current[k] for k in ("success", "terminated", "truncated")):
                raise ValueError("unexplained incomplete prefix")
            before_phases, after_phases = record["ledger_before"]["by_phase"], record["ledger_after"]["by_phase"]
            if after_phases["CONTROLLED_RESET"]["reset_completed"]-before_phases.get("CONTROLLED_RESET", {}).get("reset_completed", 0) != 1:
                raise ValueError("per-prefix controlled reset count differs")
            if after_phases.get("CONTROL", {}).get("simulation_completed", 0)-before_phases.get("CONTROL", {}).get("simulation_completed", 0) != len(record["trace"]):
                raise ValueError("per-prefix physical step count differs")
            same(journal.ledger, record["ledger_after"])
            if split == "QUALIFY":
                saved = business()
                if saved["event"] != "ESTIMATES_SAVED" or saved["models_sha256"] != model_hash or saved["sequence"] != record["estimates_sequence"] or record["models_sha256"] != model_hash: raise ValueError("estimate chronology differs")
                same(record["estimates"], estimates(saved_models, old, visible_prefix(record))); same(saved["estimates"], record["estimates"])
                same(record["operator_oracle"], operator)
            count += 1; steps += len(record["trace"])
            if count % 48 == 0: print(f"audited {count}/480 prefixes", flush=True)
    if next(events, None) is not None: raise ValueError("trailing business events")
    journal.boundary(); summary = json.loads((base / "summary.json").read_text(encoding="utf-8")); status = json.loads((base / "status.json").read_text(encoding="utf-8"))
    verify_terminal(summary, status, identity, journal.ledger, steps, model_hash)
    # Independent parameter errors and clustered bootstrap, not runner.statistics.
    details = {}; numeric = 0
    for name in MODELS:
        values = []
        for record in qualification:
            fit = record["estimates"][name]; truth = record["operator_oracle"]
            a = sum((fit["matrix_xy"][i][j]-truth["matrix_xy"][i][j])**2 for i in range(2) for j in range(2))**.5 if fit["valid"] else 8.
            b = sum((fit["bias_xy"][i]-truth["bias_xy"][i])**2 for i in range(2))**.5 if fit["valid"] else 1.
            values.append((a, b, a+b/.4)); numeric += 3
        details[name] = np.asarray(values)
        cell = summary["statistics"]["models"][name]
        for j, field in enumerate(("mean_matrix_error", "mean_bias_error", "mean_score")):
            if abs(details[name][:, j].mean()-cell[field]) > 1e-10: raise ValueError("mean parameter statistic differs")
        if cell["valid"] != sum(r["estimates"][name]["valid"] for r in qualification): raise ValueError("invalid cases dropped")
    rng = np.random.default_rng(20261016); draws = rng.integers(0, 16, (10000, 16))
    rebuilt_contrasts = []
    for i, name in enumerate(("SAME_DATA_ARX8", "JOINT_DROP2", "OLD_ARX8")):
        delta = details["JOINT_FULL8"][:, 2]-details[name][:, 2]
        stream_values = np.array([sum(delta[k] for k, row in enumerate(qualification) if row["stream"] == s)/6 for s in range(16)])
        ci = np.percentile(np.sum(stream_values[draws], axis=1)/16, [2.5, 97.5]); saved = summary["statistics"]["contrasts"][i]
        np.testing.assert_allclose(stream_values, saved["stream_values"], atol=1e-12, rtol=0)
        np.testing.assert_allclose(ci, saved["paired_stream_percentile_95"], atol=1e-12, rtol=0)
        if abs(stream_values.mean()-saved["mean_score_difference"]) > 1e-12: raise ValueError("contrast differs")
        rebuilt_contrasts.append((stream_values.mean(), ci)); numeric += 19
    requirements = {"valid_fraction": summary["statistics"]["models"]["JOINT_FULL8"]["valid"]/96 >= .95,
                    "primary_upper_below_zero": rebuilt_contrasts[0][1][1] < 0,
                    "full_better_than_drop_two_mean": rebuilt_contrasts[1][0] < 0}
    same(requirements, summary["statistics"]["qualification"]["requirements"])
    if all(requirements.values()) != summary["statistics"]["qualification"]["passed"]: raise ValueError("qualification gate changed")
    result = {**identity, "integrity": "PASSED", "prefixes_checked": count, "environment_steps_checked": steps,
              "events_checked": journal.sequence, "frozen_git_inputs_checked": len(m["input_sha256"]), "training_mean_models_checked": mean_models_checked,
              "max_normal_equation_residual": max_normal_residual, "parameter_numbers_checked": numeric, "models_sha256": model_hash,
              "lifecycle": journal.ledger, "artifact_sha256": {p.name: run.digest(p) for p in base.iterdir() if p.is_file()},
              "new_environment_steps": 0, "shared_helpers": ["visible prefix schema", "clipped working mean", "response fitting/point optimizers", "lifecycle parser", "NumPy"]}
    output.mkdir(parents=True, exist_ok=False); run.write_json(output / "audit.json", result); print(json.dumps({k: result[k] for k in ("integrity", "prefixes_checked", "events_checked", "parameter_numbers_checked")}))


if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("--manifest", type=Path, required=True); p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(); audit(args.manifest.resolve(), args.output.resolve())

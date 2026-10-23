"""Recorded-action, RNG, program and lifecycle replay; no robot resimulation."""
import argparse
from collections import Counter, deque
from dataclasses import asdict
import gzip
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import run_early_evidence as run
from scripts.audit_acquisition_value_v3 import JournalAudit, compiled_clock_units
from src.probe.acquisition_value import paired_sign, repeat_consistency
from src.probe.continuous import ContinuousTransition, symmetric_program
from src.probe.forward_prediction import ForwardHistory
from src.probe.operator_identification import OperatorSample, infer_operator, affine_controller, identity_controller
from src.probe.gaussian_response_reference import GaussianReference, PRIMITIVES


def equal(a, b):
    if run.normal(a) != run.normal(b): raise ValueError("saved observation/decision differs")


def statistics(manifest, rows, pairs):
    c = manifest["config"]; methods = {}; contexts = []; indexed = {(r["stream"], r["task"], r["replicate"], r["method"]): r for r in rows}
    expected = {(s, t, v, p) for s in range(8) for t in run.TASKS for v in range(4) for p in run.METHODS}
    if len(rows) != 768 or set(indexed) != expected or len(pairs) != 96: raise ValueError("complete registered early population required")
    for method in run.METHODS:
        part = [r for r in rows if r["method"] == method]; n = len(part)
        methods[method] = {"cases": n, "successes": sum(r["success"] for r in part), "stops": sum(r["stopped"] for r in part),
                           "total_steps": sum(r["total_steps"] for r in part), "mean_steps": sum(r["total_steps"] for r in part) / n,
                           "mean_deadline_loss": sum(r["deadline_loss"] for r in part) / n,
                           "mean_probe_steps": sum(r["fixed_probe_steps"] + r["ivr_probe_steps"] for r in part) / n,
                           "point_fit_failures": sum(r["point_fit_failures"] for r in part),
                           "offline_steps": 0 if method == "NO_PROBE" else 21010, "offline_resets": 0 if method == "NO_PROBE" else 288,
                           "mean_amortized_steps": (sum(r["total_steps"] for r in part) + (0 if method == "NO_PROBE" else 21010)) / n}
    paired = {(r["stream"], r["task"], r["replicate"]): r["reason"] for r in pairs}
    if len(paired) != 96: raise ValueError("duplicate continuation pair")
    for stream in range(8):
        for task in run.TASKS:
            reasons = [paired[(stream, task, v)] for v in range(4)]; complete = all(r == "MATCHED_CONTINUATION" for r in reasons)
            signs = []
            for v, reason in enumerate(reasons):
                if reason != "MATCHED_CONTINUATION": signs.append(None); continue
                target, reference = indexed[(stream, task, v, "POINT16_CYCLE")], indexed[(stream, task, v, "POINT8")]
                signs.append(paired_sign({k: target[k] for k in ("success", "stopped", "total_steps")}, {k: reference[k] for k in ("success", "stopped", "total_steps")}))
            detail = repeat_consistency(signs) if complete else {}
            contexts.append({"stream": stream, "task": task, "complete": complete, "reasons": reasons, "signs": signs, **detail})
    usable = [r for r in contexts if r["complete"]]; nonzero = sum(r["has_non_tie"] for r in usable); reversal = sum(r["sign_reversal"] for r in usable)
    checked = sum(r["leave_one_out_checked"] for r in usable); correct = sum(r["leave_one_out_correct"] for r in usable); abstained = sum(r["leave_one_out_abstained"] for r in usable)
    fraction = reversal / nonzero if nonzero else None; agreement = correct / checked if checked else None; coverage = checked / (checked + abstained) if checked + abstained else None
    passed = len(usable) == 24 and nonzero >= c["minimum_non_tie_contexts"] and fraction <= c["maximum_sign_reversal_fraction"] and agreement is not None and agreement >= c["minimum_leave_one_out_agreement"] and coverage >= c["minimum_leave_one_out_coverage"]
    return {"methods": methods, "primary_contexts": contexts, "repeat_gate": {"contexts": 24, "fully_matched_contexts": len(usable), "non_tie_contexts": nonzero,
            "sign_reversal_contexts": reversal, "sign_reversal_fraction": fraction, "leave_one_out_checked": checked, "leave_one_out_correct": correct,
            "leave_one_out_abstained": abstained, "leave_one_out_agreement": agreement, "leave_one_out_coverage": coverage, "passed": passed}}


def verify_record(record, model, sigma, measures, operator, events, env_dt):
    fields = (*run.IDENTITY, "stream", "task", "replicate", "seed", "method", "operator_id_oracle")
    def event():
        value = events.popleft()
        if any(value[k] != record[k] for k in fields): raise ValueError("foreign branch event")
        return value
    start, factory, initial = event(), event(), event()
    if start["event"] != "FACTORY_INTENT" or factory["event"] != "FACTORY_COMPLETE" or initial["event"] != "CONTROLLED_INITIAL": raise ValueError("initialization order differs")
    equal(start["ledger"], record["ledger_before"]); equal(initial["initial"], record["initial"]); equal(initial["physics_witness_oracle"], record["initial_physics_witness_oracle"])
    method = record["method"]; trace = record["trace"]; decisions = {d["sequence"]: d for d in record["decisions"]}
    if method not in run.METHODS or len(trace) > 500 or [r["host_calls"] for r in trace] != list(range(1, len(trace) + 1)): raise ValueError("registered method/timeline differs")
    if len(decisions) != len(record["decisions"]): raise ValueError("duplicate decision")
    rng = np.random.default_rng(run.noise_seed(record["seed"], record["task"], record["replicate"]))
    def rng_hash(): return hashlib.sha256(json.dumps(rng.bit_generator.state, sort_keys=True).encode()).hexdigest()
    if record["initial_rng_hash"] != rng_hash() or initial["rng_hash"] != rng_hash(): raise ValueError("initial actuator RNG differs")
    current = record["initial"]; history = ForwardHistory(current["observation"]); samples = []; calls = 0; selected = None; last_sequence = None
    program = (); position = 0; fixed_batches = 0; ivr_batches = 0; reference = None; built_at = None; seen_decisions = set(); previous_clock = None
    policy = run.create_task_policy(record["task"])
    while events:
        item = event(); kind = item["event"]
        if kind == "DECISION":
            if any(current[k] for k in ("success", "terminated", "truncated")): raise ValueError("decision after task ended")
            if item["sequence"] not in decisions or item["sequence"] in seen_decisions: raise ValueError("unrecorded/duplicate choice")
            equal(item, decisions[item["sequence"]]); seen_decisions.add(item["sequence"])
            if item["at_host_calls"] != calls or item["observation_sha256"] != run.state_hash(current["observation"]) or item["rng_hash"] != rng_hash(): raise ValueError("future evidence at choice")
            action = item["action"]; expected = None
            if position != len(program): raise ValueError("decision before selected measurement completed")
            if action == "RUN_UNCORRECTED":
                if method != "NO_PROBE" or calls or seen_decisions != {item["sequence"]}: raise ValueError("uncorrected method changed")
                expected = identity_controller()
            elif action == "REQUEST_FIXED_PROBE":
                batches = (16,) if method == "POINT16_WIDE" else (8, 8) if method in ("POINT16_CYCLE", "GAUSS16_CYCLE") else (8,)
                if method == "NO_PROBE" or fixed_batches >= len(batches) or calls != sum(batches[:fixed_batches]) or item["probe_steps"] != batches[fixed_batches] or calls + item["probe_steps"] + 32 > 500: raise ValueError("fixed/repeated measurement budget differs")
                program = symmetric_program(.4, steps_per_direction=item["probe_steps"] // 4); position = 0; fixed_batches += 1
            elif action in ("RUN_POINT", "STOP_POINT_FIT"):
                boundary = 8 if method == "POINT8" else 16
                if method not in ("POINT8", "POINT16_CYCLE", "POINT16_WIDE") or calls != boundary: raise ValueError("unregistered point decision")
                fit = infer_operator(model, tuple(samples)); equal(fit, item["fit"])
                if action == "RUN_POINT" and fit["valid"]: expected = affine_controller(fit["matrix_xy"], fit["bias_xy"])
                elif action != "STOP_POINT_FIT" or fit["valid"]: raise ValueError("point validity substituted")
            elif action in ("BUILD_GAUSSIAN", "STOP_NO_GAUSSIAN_POINT"):
                allowed = (8, 12, 16) if method.startswith("IVR_") else (8,) if method == "GAUSS8" else (16,) if method == "GAUSS16_CYCLE" else ()
                if calls not in allowed or built_at == calls or method.startswith("IVR_") and calls != 8 + 4 * ivr_batches: raise ValueError("Gaussian boundary changed")
                try:
                    reference, fit = GaussianReference.from_visible(model, tuple(samples), sigma)
                except ValueError as exc:
                    if action != "STOP_NO_GAUSSIAN_POINT" or item["reason"] != str(exc): raise ValueError("Gaussian failure replaced")
                    equal(item["fit"], infer_operator(model, tuple(samples)))
                else:
                    if action != "BUILD_GAUSSIAN": raise ValueError("valid Gaussian construction stopped")
                    equal(fit, item["fit"]); expected = reference.controller()
                built_at = calls
            elif action == "REQUEST_IVR_PROBE":
                if not method.startswith("IVR_") or calls not in (8, 12) or reference is None or built_at != calls or ivr_batches >= 2: raise ValueError("unregistered IVR or repeated probe")
                queries, weights = run.query_measure(method, record["task"], measures)
                choice = reference.choose(queries, weights, 500 - calls, calls); equal(choice, item["validation"])
                program = PRIMITIVES[item["validation"]["action"]]; position = 0; ivr_batches += 1
            else: raise ValueError("unexpected or budget-stop action")
            equal(expected, item["controller"]); selected = item["controller"]; last_sequence = item["sequence"]
        elif kind == "STEP_INTENT":
            if calls >= len(trace) or last_sequence is None or item["decision_sequence"] != last_sequence or any(current[k] for k in ("success", "terminated", "truncated")): raise ValueError("unselected or ended branch stepped")
            row = trace[calls]; phase = row["phase"]
            for name in ("command", "before", "rng_before", "phase", "raw_policy", "decision_sequence", "ledger_before"): equal(item[name], row[name])
            if row["before"] != current or item["at_host_calls"] != calls or row["rng_before"] != rng_hash() or row["intent_sequence"] != item["sequence"]: raise ValueError("step chronology/RNG differs")
            if not (last_sequence < item["sequence"] and decisions[last_sequence]["saved_ns"] <= item["saved_ns"] == row["intent_saved_ns"] < row["execution_started_ns"] <= row["completed_ns"]): raise ValueError("choice or intent did not precede execution")
            if phase in ("FIXED_PROBE", "IVR_PROBE"):
                if position >= len(program) or row["raw_policy"] is not None or phase == "IVR_PROBE" and not method.startswith("IVR_"): raise ValueError("extra or changed measurement")
                if np.asarray(program[position], np.float32).tolist() != row["command"]: raise ValueError("saved program not executed")
                position += 1
            elif phase == "POLICY":
                if selected is None or position != len(program) or method.startswith("IVR_") and (ivr_batches != 2 or built_at != 16): raise ValueError("policy before selected estimate/measurements")
                raw = np.asarray(policy.get_action(np.asarray(current["observation"])), np.float32)
                if raw.tolist() != row["raw_policy"] or run.command(selected, raw).tolist() != row["command"]: raise ValueError("saved controller not consumed")
            else: raise ValueError("unknown physical phase")
            query = history.request(row["command"]); equal(asdict(query) if query else None, item["forward_query"])
            actual = np.asarray(row["command"], np.float32).copy()
            actual[:2] = np.asarray(operator["matrix_xy"], np.float32) @ actual[:2] + np.asarray(operator["bias_xy"], np.float32)
            actual[:3] += rng.normal(0, .05, 3).astype(np.float32); actual = np.clip(actual, -1, 1)
            if actual.tolist() != row["executed_action_oracle"] or rng_hash() != row["rng_after"]: raise ValueError("injection or continuous noise differs")
            target = history.observe(ContinuousTransition(tuple(row["command"]), current["observation"], row["after"]["observation"])); calls += 1
            if query is not None: samples.append(OperatorSample(calls, query, target))
            equal(list(target), row["target_xy"]); current = row["after"]
            if not np.isclose(row["simulation_time_after_oracle"] - row["simulation_time_before_oracle"], env_dt, atol=1e-10, rtol=1e-10) or previous_clock is not None and row["simulation_time_before_oracle"] != previous_clock: raise ValueError("clock or reset discontinuity")
            previous_clock = row["simulation_time_after_oracle"]
            complete = event()
            if complete["event"] != "STEP_COMPLETE": raise ValueError("missing completed execution")
            for name, value in row.items(): equal(value, complete[name])
        else: raise ValueError("unexpected business event")
    if calls != len(trace) or seen_decisions != set(decisions): raise ValueError("incomplete decision/trace replay")
    ended = any(current[k] for k in ("success", "terminated", "truncated"))
    if selected is not None and calls < 500 and not ended: raise ValueError("policy branch truncated early")
    phase = Counter(r["phase"] for r in trace)
    expected = {"success": current["success"], "stopped": selected is None and not ended, "total_steps": calls, "environment_resets": 1,
                "fixed_probe_steps": phase["FIXED_PROBE"], "ivr_probe_steps": phase["IVR_PROBE"], "policy_steps": phase["POLICY"],
                "point_fit_failures": sum(d.get("fit") is not None and not d["fit"]["valid"] for d in decisions.values()), "deadline_loss": calls if current["success"] else 500}
    if record["outcome"] != expected or record["ledger_after"] != (trace[-1]["ledger_after"] if trace else initial["ledger"]): raise ValueError("branch outcome or cost substituted")
    if phase["FIXED_PROBE"] + phase["IVR_PROBE"] > 16: raise ValueError("probe cap exceeded")


def read_lines(path):
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle: yield json.loads(line)


def analyze(path):
    m = run.load(path); output = path.parent; c = m["config"]; identity = {k: m[k] for k in run.IDENTITY}
    for name, expected in m["input_sha256"].items():
        content = __import__("subprocess").check_output(["git", "show", m["source_git_commit"] + ":" + name], cwd=ROOT)
        if hashlib.sha256(content).hexdigest() != expected: raise ValueError("frozen Git bytes differ")
    clocks = compiled_clock_units(m); models, _, _ = run.load_bank(c)
    profile = json.loads((ROOT / c["nominal_profile_path"]).read_text(encoding="utf-8")); journal = JournalAudit(identity); rows = []; pairs = []
    for stream in range(8):
        events = iter(read_lines(output / f"events_{stream:02}.jsonl.gz")); branches = {}
        operator = next(v for v in m["operators_oracle"][stream]["states_oracle"] if v["id"] == "A")
        for record in read_lines(output / f"episodes_{stream:02}.jsonl.gz"):
            if any(record[k] != v for k, v in identity.items()) or record["stream"] != stream or record["seed"] != run.task_seed(stream, record["task"]) or record["operator_id_oracle"] != "A": raise ValueError("foreign raw episode")
            business = deque(); needed = 3 + len(record["decisions"]) + 2 * len(record["trace"])
            while len(business) < needed:
                item = journal.accept(next(events))
                if item is not None: business.append(item)
            verify_record(record, models[record["task"]], profile["rms_m"][record["task"]], m["task_measures"], operator, business, clocks[record["task"]]["env_step_seconds"])
            if business or journal.ledger != record["ledger_after"]: raise ValueError("episode journal did not terminate")
            rows.append({**{k: record[k] for k in (*run.IDENTITY, "stream", "task", "replicate", "seed", "method", "operator_id_oracle")}, **record["outcome"]})
            key = (record["task"], record["replicate"])
            if record["method"] in ("POINT8", "POINT16_CYCLE"): branches.setdefault(key, {})[record["method"]] = record
        if next(events, None) is not None: raise ValueError("unexpected trailing events")
        journal.boundary()
        for (task, replicate), values in branches.items():
            pairs.append({"stream": stream, "task": task, "replicate": replicate, "reason": run.pairing(values["POINT16_CYCLE"], values["POINT8"])})
        print(f"Audited stream {stream + 1}/8: {len(rows)}/768", flush=True)
    stats = statistics(m, rows, pairs); steps = sum(r["total_steps"] for r in rows)
    counts = journal.ledger["counts"]; control = journal.ledger["by_phase"]["CONTROL"]; reset = journal.ledger["by_phase"]["CONTROLLED_RESET"]
    if control["simulation_completed"] != steps or reset["reset_completed"] != 768 or counts["simulation_frames_completed"] > 24000000 or steps > 384000 or counts["simulation_frames_completed"] != 500 * counts["reset_completed"] + 5 * steps:
        raise ValueError("complete step/reset/frame arithmetic differs")
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8")); status = json.loads((output / "status.json").read_text(encoding="utf-8"))
    expected_status = "COMPLETED_TARGET_REPEAT_PASS" if stats["repeat_gate"]["passed"] else "COMPLETED_TARGET_REPEAT_FAILED"
    expected = {**identity, "status": expected_status, "episodes": 768, "controlled_steps": steps, "controlled_resets": 768, "api_calls": 0, "memory_writes": 0, "lifecycle": journal.ledger}
    if status != expected or any(summary[k] != v for k, v in expected.items()) or summary["cases"] != rows or summary["pairs"] != pairs or summary["statistics"] != stats:
        raise ValueError("terminal population, statistics or ledger differs")
    return {**identity, "integrity": "PASSED", "status": expected_status, "episodes": 768, "controlled_steps": steps, "controlled_resets": 768,
            "statistics": stats, "lifecycle": journal.ledger, "events_checked": journal.sequence, "clock_units": clocks,
            "frozen_git_inputs_checked": len(m["input_sha256"]), "api_calls": 0, "memory_writes": 0,
            "artifact_sha256": {p.name: run.digest(p) for p in output.iterdir() if p.is_file()},
            "scope": "Recorded-action/RNG/program/choice and full lifecycle replay; Gaussian/point mathematical helpers, state pairing and repeat formulas explicitly reused. No robot resimulation, complete hidden-state or physical/probability qualification."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--manifest", type=Path, required=True); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); output = args.output.resolve()
    if output.exists() or args.manifest.resolve().parent in output.parents: raise FileExistsError("new external audit directory required")
    result = analyze(args.manifest.resolve()); output.mkdir(parents=True, exist_ok=False); run.write_json(output / "audit.json", result)
    print(json.dumps({k: result[k] for k in ("integrity", "status", "episodes", "controlled_steps", "controlled_resets")}))

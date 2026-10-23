"""Describe recorded support for delayed switching; do not estimate its value."""

import argparse
from collections import Counter
import csv
import gzip
import json
import math
from pathlib import Path
from time import perf_counter_ns

from replay_paired_probe_results_v1 import ROOT, STUDY, RECEIPTS, sha, verify_saved


PROGRAMS = ("PROBE_KEEP", "PROBE_UPDATE_KEEP")
CHECKPOINT = 100  # Illustrative retrospective boundary, never a fitted trigger.


def require(ok, message):
    if not ok:
        raise ValueError(message)


def abstract_support_witness():
    """A standard finite-MDP nonidentification example, not robot dynamics."""
    def run(world, actions):
        state = "START"
        cost = 0
        trace = []
        for action in actions:
            if state == "START":
                nxt, amount = ("OLD_PATH" if action == "OLD" else "NEW_PATH"), 1
            elif state == "OLD_PATH":
                nxt, amount = "END", 1 if action == "OLD" else 3
            elif state == "NEW_PATH":
                nxt, amount = "END", 3 if action == "NEW" else (1 if world == "A" else 5)
            else:
                raise ValueError("abstract terminal state stepped")
            trace.append({"before": state, "action": action, "after": nxt, "cost": amount})
            state, cost = nxt, cost + amount
        return {"trace": trace, "loss": cost}
    results = {world: {name: run(world, actions) for name, actions in
                      (("constant_old", ("OLD", "OLD")), ("constant_new", ("NEW", "NEW")),
                       ("new_then_old", ("NEW", "OLD")))} for world in ("A", "B")}
    for name in ("constant_old", "constant_new"):
        require(results["A"][name] == results["B"][name], "observed baseline worlds differ")
    effects = {w: results[w]["constant_new"]["loss"] - results[w]["new_then_old"]["loss"] for w in results}
    require(effects == {"A": 2, "B": -2}, "opposite switch effects missing")
    return {"worlds": results, "keep_minus_switch_loss": effects,
            "unobserved_state_action": ["NEW_PATH", "OLD"], "abstract_transitions_computed": 12,
            "scope": "Elementary support counterexample, not a new theorem, identified robot model or empirical switching result."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = (ROOT / args.output).resolve()
    if not output.is_relative_to(RECEIPTS.resolve()) or output == RECEIPTS.resolve() or output.exists():
        parser.error("new replay output directory required")
    started = perf_counter_ns()
    manifest, bindings, _ = verify_saved("MAIN")
    population = RECEIPTS / "push_mode_population_v1"
    prior = json.loads((population / "receipt.json").read_text(encoding="utf-8"))
    for name, expected in prior["artifact_sha256"].items():
        require(sha(population / name) == expected, "prior descriptive bytes differ")
    with (population / "program_modes.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    records = {(int(r["stream"]), int(r["episode"]), int(r["future"]), r["program"]): r for r in rows}
    pairs = sorted({k[:3] for k in records})
    require(len(records) == 2048 and len(pairs) == 1024, "full push population required")
    choices = {key: {} for key in records}
    policy_counts = Counter()
    snapshots = {}
    calls = Counter()
    lines = selected = 0
    with gzip.open(STUDY / "main/events.jsonl.gz", "rb") as handle:
        for line in handle:
            lines += 1
            if b'"task": "push-v3"' not in line or b'"role": "EVAL"' not in line:
                continue
            if not any(('"program": "' + p + '"').encode() in line for p in PROGRAMS):
                continue
            if b'"event": "AGENT_EVENT"' not in line:
                continue
            if b'"agent_event": "CHOICE"' not in line and b'"agent_event": "COMMAND"' not in line:
                continue
            event = json.loads(line)
            require(event["manifest_id"] == manifest["manifest_id"], "source identity differs")
            key = (event["stream"], event["episode"], event["future"], event["program"])
            public = event["public_payload"]
            selected += 1
            if event["agent_event"] == "CHOICE":
                require(public["sequence"] not in choices[key], "duplicate public choice")
                choices[key][public["sequence"]] = (event["sequence"], public)
                calls[public["at_calls"]] += 1
                continue
            decision_global, decision = choices[key][public["decision_sequence"]]
            require(decision_global < event["sequence"] and decision["saved_ns"] <= public["saved_ns"], "choice follows command")
            if public["phase"] != "POLICY":
                continue
            policy_counts[key] += 1
            require(decision["at_calls"] == 8 and "controller" in decision, "unexpected late policy choice")
            require(public["at_calls"] == 7 + policy_counts[key], "policy time gap")
            if public["at_calls"] == CHECKPOINT:
                require(key not in snapshots, "duplicate checkpoint")
                snapshots[key] = {"observation": public["before"]["observation"],
                                  "controller": decision["controller"], "saved_choice_action": decision["action"],
                                  "saved_choice_at_calls": decision["at_calls"],
                                  "choice_global_sequence": decision_global,
                                  "checkpoint_command_sequence": event["sequence"]}
    for key, row in records.items():
        require(policy_counts[key] == int(row["policy_steps"]), "policy count differs")
        require((key in snapshots) == (int(row["total_steps"]) > CHECKPOINT), "checkpoint survival differs")
    require(set(calls) == {4, 8}, "unanticipated control-selection times")
    curves = []
    checkpoint_pairs = []
    for at in range(8, 500):
        categories = Counter()
        harmed = Counter()
        rescued = Counter()
        for identity in pairs:
            p, k = [records[(*identity, program)] for program in PROGRAMS]
            alive = (int(p["total_steps"]) > at, int(k["total_steps"]) > at)
            category = ("P_LIVE" if alive[0] else "P_ENDED") + ("_K_LIVE" if alive[1] else "_K_ENDED")
            categories[category] += 1
            harmful = p["success"] == "True" and k["success"] == "False"
            rescue = p["success"] == "False" and k["success"] == "True"
            if harmful:
                harmed[category] += 1
            if rescue:
                rescued[category] += 1
            if at == CHECKPOINT:
                row = {"stream_evaluator_only": identity[0], "episode_evaluator_only": identity[1],
                       "future_evaluator_only": identity[2], "category": category,
                       "P_total_steps": int(p["total_steps"]), "K_total_steps": int(k["total_steps"]),
                       "P_success": p["success"] == "True", "K_success": k["success"] == "True",
                       "same_public_observation_at_checkpoint": None, "max_abs_public_observation_difference": None}
                if all(alive):
                    x, y = [snapshots[(*identity, program)]["observation"] for program in PROGRAMS]
                    row["same_public_observation_at_checkpoint"] = x == y
                    row["max_abs_public_observation_difference"] = max(abs(a - b) for a, b in zip(x, y))
                checkpoint_pairs.append(row)
        curves.append({"completed_steps": at,
                       **{name: categories[name] for name in ("P_ENDED_K_ENDED", "P_LIVE_K_ENDED", "P_LIVE_K_LIVE", "P_ENDED_K_LIVE")},
                       "harmed_with_P_ended_K_live": harmed["P_ENDED_K_LIVE"],
                       "harmed_with_both_live": harmed["P_LIVE_K_LIVE"],
                       "rescued_with_P_live_K_ended": rescued["P_LIVE_K_ENDED"],
                       "rescued_with_both_live": rescued["P_LIVE_K_LIVE"]})
    both = [x for x in checkpoint_pairs if x["category"] == "P_LIVE_K_LIVE"]
    summary = {"scope": "Retrospective support audit; no delayed-switch outcome has been executed or imputed.",
               "programs": len(records), "pairs": len(pairs), "all_integer_boundaries": [8, 499],
               "illustrative_checkpoint": CHECKPOINT, "checkpoint_counts": curves[CHECKPOINT - 8],
               "choice_at_calls_counts": dict(calls), "policy_commands_checked": sum(policy_counts.values()),
               "recorded_choices_after_step8": sum(v for k, v in calls.items() if k > 8),
               "live_checkpoint_observations": len(snapshots),
               "both_live_same_public_observation": sum(x["same_public_observation_at_checkpoint"] for x in both),
               "both_live_different_public_observation": sum(not x["same_public_observation_at_checkpoint"] for x in both),
               "both_live_max_abs_observation_difference_min_max": [min(x["max_abs_public_observation_difference"] for x in both), max(x["max_abs_public_observation_difference"] for x in both)],
               "abstract_counterexample": abstract_support_witness()}
    for p, expected in bindings.items():
        require(sha(p) == expected, "old source changed during audit")
    output.mkdir(parents=True, exist_ok=False)
    for name, data in (("availability_by_step.csv", curves), ("checkpoint100_pairs.csv", checkpoint_pairs)):
        with (output / name).open("x", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(data[0])); writer.writeheader(); writer.writerows(data)
    snapshot_rows = [{"evaluator_identity": list(key), "public_boundary": value} for key, value in sorted(snapshots.items())]
    for name, value in (("summary.json", summary), ("checkpoint100_observations.json", snapshot_rows)):
        with (output / name).open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, indent=2, allow_nan=False); handle.write("\n")
    receipt = {"schema": "delayed_switch_recorded_support_v1", "source_manifest_id": manifest["manifest_id"],
               "source_events_sha256": sha(STUDY / "main/events.jsonl.gz"),
               "prior_population_receipt_sha256": sha(population / "receipt.json"),
               "script_sha256": sha(Path(__file__)), "source_lines_scanned": lines,
               "selected_choice_command_events": selected, "generation_body_wall_ns": perf_counter_ns() - started,
               "new_environment_steps": 0, "new_resets": 0, "new_api_calls": 0,
               "new_fits": 0, "new_full_policy_queries": 0, "abstract_transitions_computed": 12,
               "artifact_sha256": {p.name: sha(p) for p in output.iterdir() if p.is_file()}}
    with (output / "receipt.json").open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(receipt, handle, indent=2, allow_nan=False); handle.write("\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "abstract_counterexample"}))


if __name__ == "__main__":
    main()

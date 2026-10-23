"""One-shot development reuse: nested group cross-fit and saved branch replay."""
import argparse
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import run_acquisition_value as source
from scripts.report_acquisition_value import case as source_case
from src.probe.task_value_learner import (BranchRow, LENGTHS, METHODS, TASKS, ValueEvidence,
                                        fit_policy, pre_choice, post_choice)

CONFIG = ROOT / "configs/autoresearch/task_value_learner_development_v1.json"
PROTOCOL = ROOT / "docs/protocols/task_value_learner_development_v1.md"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate(config):
    expected = {"groups": 8, "cases": 192, "tasks": list(TASKS), "ridge": 1.0, "scale_floor": 1e-6, "loss_scale": 500.0,
                "pre_actions": ["CACHE_CONTINUE", "PROBE8_WIDE", "PROBE16_WIDE"], "post_actions": ["KEEP", "UPDATE"],
                "kernel": "RBF_TRAIN_MEDIAN_SQUARED_DISTANCE", "task_models": "SEPARATE",
                "outer_split": "LEAVE_ONE_OPERATOR_STREAM_OUT", "inner_split": "LEAVE_ONE_OPERATOR_STREAM_OUT",
                "post_tie_action": "KEEP", "pre_tie_order": ["CACHE_CONTINUE", "PROBE8_WIDE", "PROBE16_WIDE"],
                "new_simulator_steps": 0, "new_api_calls": 0}
    if any(config.get(k) != v for k, v in expected.items()):
        raise ValueError("configuration and implemented fixed protocol differ")


def prepare():
    if subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT).strip():
        raise ValueError("clean committed implementation required")
    config = read(CONFIG)
    validate(config)
    audit = ROOT / config["source_audit"]
    if source.digest(audit) != config["source_audit_sha256"]:
        raise ValueError("foreign source audit")
    source.load(ROOT / config["source_manifest"])
    names = subprocess.check_output(["git", "ls-files", "src", "scripts", "tests"], cwd=ROOT, text=True).splitlines()
    names += [CONFIG.relative_to(ROOT).as_posix(), PROTOCOL.relative_to(ROOT).as_posix(), ".gitattributes", "AGENTS.md", "requirements.txt",
              "docs/research/task_value_learner_prior_art_v1.md"]
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    base = ROOT / config["output_root"]
    if list(base.glob("*/manifest.json")):
        raise FileExistsError("this development reuse was already prepared")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    manifest = {"run_id": f"task_value_learner_{stamp}_{commit[:12]}", "source_git_commit": commit,
                "config": config, "input_sha256": {name: source.digest(ROOT / name) for name in names}}
    manifest["manifest_id"] = digest(manifest)
    output = base / manifest["run_id"]
    output.mkdir(parents=True, exist_ok=False)
    write(output / "manifest.json", manifest)
    print(output / "manifest.json")


def evidence(record, probe_steps):
    boundary = 6 + probe_steps
    trace = record["trace"][:boundary]
    if len(trace) != boundary or any(trace[-1]["after"][k] for k in ("success", "terminated", "truncated")):
        raise ValueError("registered full nonterminal decision history required")
    old = record["source_cache"]
    parameters = tuple(v for matrix, bias in zip(old["matrix_xy"], old["bias_xy"]) for v in (*matrix, bias))
    fit = None
    if probe_steps:
        fits = [d["fit"] for d in record["decisions"] if d["at_host_calls"] == boundary and d.get("fit") is not None]
        if len(fits) != 1:
            raise ValueError("unique actual post-measurement fit required")
        fit = fits[0]
    fitted = None
    if fit is not None and fit["valid"]:
        fitted = tuple(v for matrix, bias in zip(fit["matrix_xy"], fit["bias_xy"]) for v in (*matrix, bias))
    return ValueEvidence(record["task"], tuple([record["initial"]["observation"]] + [r["after"]["observation"] for r in trace]),
                         tuple(r["command"] for r in trace), tuple(r["raw_policy"] for r in trace), parameters,
                         probe_steps, 500 - boundary, None if fit is None else fit["valid"], fitted,
                         None if fit is None else fit.get("residual_rmse_m"))


def encode(row):
    return {"case_id": row.case_id, "group": row.group, "pre": asdict(row.pre),
            "post": {str(n): asdict(e) for n, e in row.post.items()}, "outcomes_evaluator_only": row.outcomes}


def decode(value):
    return BranchRow(value["case_id"], value["group"], ValueEvidence.from_dict(value["pre"]),
                     {int(n): ValueEvidence.from_dict(e) for n, e in value["post"].items()}, value["outcomes_evaluator_only"])


def extract(config):
    manifest = ROOT / config["source_manifest"]
    m = source.load(manifest)
    audit_path = ROOT / config["source_audit"]
    if source.digest(audit_path) != config["source_audit_sha256"]:
        raise ValueError("source audit changed")
    audit = read(audit_path)
    if audit["integrity"] != "PASSED" or audit["episodes"] != 2304:
        raise ValueError("complete original execution audit required")
    for name, expected in audit["artifact_sha256"].items():
        if source.digest(manifest.parent / name) != expected:
            raise ValueError("original audited bytes changed")
    rows = []
    for stream in range(8):
        contexts = {}
        with gzip.open(manifest.parent / f"episodes_{stream:02}.jsonl.gz", "rt", encoding="utf-8") as handle:
            for line in handle:
                record = json.loads(line)
                if record["method"] not in METHODS:
                    continue
                key = (record["task"], record["scenario"], record["replicate"])
                methods = contexts.setdefault(key, {})
                if record["method"] in methods:
                    raise ValueError("duplicate physical branch")
                methods[record["method"]] = record
        if len(contexts) != 24:
            raise ValueError("registered stream population differs")
        for (task, scenario, replicate), records in contexts.items():
            if set(records) != set(METHODS):
                raise ValueError("missing selectable actual branch")
            old = records["CACHE_CONTINUE"]
            post = {}
            for length in LENGTHS:
                updated, kept = records[f"MID{length}_WIDE"], records[f"MID{length}_WIDE_KEEP"]
                if source.update_pair(updated, kept, old)["reason"] != "MATCHED_UPDATE":
                    raise ValueError("unmatched physical measurement branches")
                post[length] = evidence(updated, length)
            outcomes = {}
            for method, record in records.items():
                value = source_case(record)
                outcomes[method] = {"success": value["success"], "stopped": value["stopped"], "steps": value["total_steps"], "loss": value["deadline_loss"]}
            rows.append(BranchRow(f"s{stream}/{task}/{scenario}/r{replicate}", stream, evidence(old, 0), post, outcomes))
        print(f"Extracted and matched source stream {stream + 1}/8", flush=True)
    if len(rows) != 192 or len({r.case_id for r in rows}) != 192:
        raise ValueError("registered complete source population differs")
    return rows, audit


def replay_choice(row, policy, direct):
    # Evaluator orchestration alone holds offline outcomes. Inference functions
    # receive only one currently available strict evidence object at a time.
    pre = pre_choice(row.pre, policy["direct" if direct else "pre"])
    if pre["action"] == "CACHE_CONTINUE":
        return {"pre": pre, "post": None, "selected_method": "CACHE_CONTINUE"}
    length = 8 if pre["action"] == "PROBE8_WIDE" else 16
    post = None if direct else post_choice(row.post[length], policy["post"][length])
    method = f"MID{length}_WIDE" + ("_KEEP" if post is not None and post["action"] == "KEEP" else "")
    return {"pre": pre, "post": post, "selected_method": method}


def summary(values):
    n = len(values)
    return {"cases": n, "successes": sum(r["success"] for r in values), "stops": sum(r["stopped"] for r in values),
            "mean_historical_selected_steps": sum(r["steps"] for r in values) / n,
            "mean_deadline_loss": sum(r["loss"] for r in values) / n}


def save_policy(policy):
    return {"pre": policy["pre"].saved(), "post": {str(n): m.saved() for n, m in policy["post"].items()},
            "direct": policy["direct"].saved(), "inner": policy["inner"], "training_case_ids": policy["training_case_ids"]}


def run(path):
    manifest = read(path)
    validate(manifest["config"])
    identity = {k: manifest[k] for k in ("run_id", "manifest_id", "source_git_commit")}
    candidate = {k: v for k, v in manifest.items() if k != "manifest_id"}
    if digest(candidate) != manifest["manifest_id"] or any(source.digest(ROOT / n) != h for n, h in manifest["input_sha256"].items()):
        raise ValueError("frozen learner source differs")
    if subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip() != manifest["source_git_commit"]:
        raise ValueError("frozen learner commit differs")
    output = path.parent
    if (output / "dataset.json").exists():
        raise FileExistsError("one-shot reuse already started; preserve failure")
    rows, audit = extract(manifest["config"])
    write(output / "dataset.json", {**identity, "kind": "DEVELOPMENT_OFFLINE_SUPERVISED_DATA", "rows": [encode(r) for r in rows]})
    values = {"TWO_STAGE": [], "DIRECT_VALUE": []}
    selected = {method: Counter() for method in values}
    with (output / "decisions.jsonl").open("x", encoding="utf-8", newline="\n") as decisions, (output / "outcomes.jsonl").open("x", encoding="utf-8", newline="\n") as outcomes:
        for group in range(8):
            policies = {}
            for task in TASKS:
                training_rows = [r for r in rows if r.group != group and r.pre.task == task]
                policies[task] = fit_policy(training_rows, (group,))
            write(output / f"fold_{group:02}.json", {**identity, "excluded_group": group, "tasks": {t: save_policy(p) for t, p in policies.items()}})
            for row in rows:
                if row.group != group:
                    continue
                for method, direct in (("TWO_STAGE", False), ("DIRECT_VALUE", True)):
                    decision = {**identity, "case_id": row.case_id, "method": method, "excluded_group": group,
                                "kind": "DEVELOPMENT_REPLAY_NOT_NEW_ONLINE_EXECUTION", **replay_choice(row, policies[row.pre.task], direct)}
                    decision["decision_digest"] = digest(decision)
                    decisions.write(json.dumps(decision, ensure_ascii=False) + "\n"); decisions.flush()
                    value = row.outcomes[decision["selected_method"]]
                    outcome = {**identity, "case_id": row.case_id, "method": method, "decision_digest": decision["decision_digest"], **value}
                    outcomes.write(json.dumps(outcome, ensure_ascii=False) + "\n"); outcomes.flush()
                    values[method].append(value); selected[method][decision["selected_method"]] += 1
            print(f"Completed nested outer fold {group + 1}/8", flush=True)
    # Final models use every development group; they have not been evaluated
    # on a new stream and may be used only by a separately frozen successor.
    final = {task: save_policy(fit_policy([r for r in rows if r.pre.task == task])) for task in TASKS}
    write(output / "models.json", {**identity, "scope": "TRAINED_ON_ALL_OLD_DEVELOPMENT_GROUPS_NOT_INDEPENDENTLY_CONFIRMED", "tasks": final})
    result = {**identity, "status": "COMPLETED_DEVELOPMENT_REPLAY", "methods": {k: summary(v) for k, v in values.items()},
              "selected_methods": {k: dict(v) for k, v in selected.items()}, "original_all_baselines": audit["statistics"]["methods"],
              "full_paired_source_steps": audit["controlled_steps"], "full_paired_source_controlled_resets": audit["controlled_resets"],
              "full_prior_nominal_steps": 21010, "full_prior_nominal_controlled_resets": 288,
              "new_environment_steps": 0, "new_api_calls": 0, "independent_confirmation": False,
              "algorithm_novelty_established": False, "physical_response_qualified": False, "probability_guarantee": False}
    write(output / "summary.json", result)
    print(json.dumps({"status": result["status"], "methods": result["methods"], "selected_methods": result["selected_methods"]}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    if args.prepare == bool(args.manifest):
        parser.error("choose preparation or one manifest")
    if args.prepare:
        prepare()
    else:
        run(args.manifest.resolve())

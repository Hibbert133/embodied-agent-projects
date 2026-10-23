"""One-shot, zero-simulation descriptive extraction from a frozen audited bank."""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
from itertools import groupby
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import run_chronological_cache_reference as source
from src.analysis.cache_continuation_alignment_v1 import METHODS, process_unit, describe
from src.probe.cache_acquisition_evidence_v1 import canonical, digest

CONFIG = ROOT/"configs/cache_continuation_alignment/development_v1.json"
PROTOCOL = "docs/protocols/cache_continuation_alignment_development_v1.md"
QUESTION = "docs/research/cache_continuation_alignment_question_v1.md"
ZERO_RESOURCES = ("new_environment_steps", "new_controlled_resets", "new_factory_resets", "new_api_calls",
                  "new_nominal_model_fits", "new_controller_fits", "policy_weight_updates", "selector_fits")
OUTPUTS = ("dispositions.jsonl.gz", "reuse_pairs.jsonl.gz", "unique_reuse_pairs.jsonl.gz",
           "refresh_controls.jsonl.gz", "visible_evidence.jsonl.gz", "summary.json", "costs.json")


def sha(path):
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for part in iter(lambda: handle.read(1024*1024), b""):
            value.update(part)
    return value.hexdigest()


def read(path): return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n")


def git(*args): return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def clean():
    if git("status", "--porcelain", "--untracked-files=no"):
        raise ValueError("commit frozen implementation first")


def validate(config):
    if (config["protocol_id"] != "cache_continuation_alignment_development_v1" or
        tuple(config["behavior_methods"]) != METHODS or config["reference_method"] != "ALWAYS8" or
        (config["source_executions"], config["source_units"], config["source_streams"], config["cutoff_steps"], config["budget"]) != (4752, 432, 36, 4, 500)):
        raise ValueError("frozen population or scope changed")
    if any(type(config[k]) is not int or config[k] != 0 for k in ZERO_RESOURCES):
        raise ValueError("no new physical interaction, API or fitting authorized")
    if (config["inference"] != "DESCRIPTIVE_ONLY_NO_CI_NO_SELECTOR" or config["complete_hidden_state_qualified"] is not False or
        config["scope"] != "CONDITIONAL_EXISTING_TRACE_ALIGNMENT_AND_REALIZED_CURRENT_TASK_DESCRIPTION" or
        config["deduplicate"] != "SAME_ACTUAL_UNIT_AND_IDENTICAL_PUBLIC_PACKET_ONLY"):
        raise ValueError("qualification or estimand changed")


def load_sources(config):
    for key in ("source_manifest", "source_completion", "source_summary", "source_record_audit", "source_statistics_audit", "source_costs"):
        if sha(ROOT/config[key]) != config[key+"_sha256"]:
            raise ValueError("bound source changed: "+key)
    original, _, _ = source.load(ROOT/config["source_manifest"])
    summary = read(ROOT/config["source_summary"])
    completion = read(ROOT/config["source_completion"])
    record = read(ROOT/config["source_record_audit"])
    statistics = read(ROOT/config["source_statistics_audit"])
    identity = ("experiment_run_id", "manifest_id", "source_git_commit")
    for value in (summary, completion, record, statistics):
        if any(value[k] != original[k] for k in identity):
            raise ValueError("mixed source run")
    if (summary["status"] != "COMPLETED_REFERENCE" or summary["executions"] != config["source_executions"] or
        record["integrity"] != "PASSED" or statistics["integrity"] != "PASSED" or
        any(v["summary_sha256"] != config["source_summary_sha256"] for v in (record, statistics)) or
        statistics["record_audit_sha256"] != config["source_record_audit_sha256"]):
        raise ValueError("complete independently audited source required")
    if record["script_sha256"] != sha(ROOT/"scripts/audit_chronological_cache_reference.py"):
        raise ValueError("source audit implementation changed")
    return original, summary, completion


def load(path):
    manifest = read(path)
    validate(manifest["config"])
    if digest({k: v for k, v in manifest.items() if k != "manifest_id"}) != manifest["manifest_id"]:
        raise ValueError("manifest changed")
    if any(sha(ROOT/n) != h for n, h in manifest["input_sha256"].items()):
        raise ValueError("frozen implementation changed")
    original, summary, completion = load_sources(manifest["config"])
    if manifest["source_manifest_id"] != original["manifest_id"] or manifest["source_episode_sha256"] != {
        n: h for n, h in completion["artifact_sha256"].items() if n.startswith("episodes_")}:
        raise ValueError("source bank identity changed")
    return manifest, original, summary


def lines(path):
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            yield json.loads(line)


def units(manifest, original):
    folder = (ROOT/manifest["config"]["source_summary"]).parent
    count = 0
    for stream in original["population_oracle"]["MAIN"]:
        name = f"episodes_{stream['stream']:02}.jsonl.gz"
        path = folder/name
        if sha(path) != manifest["source_episode_sha256"][name]:
            raise ValueError("raw source episode bytes changed")
        cases = iter(stream["cases"])
        for episode, records in groupby(lines(path), key=lambda r: r["episode"]):
            records = list(records)
            case = next(cases)
            if episode != case["episode"] or [r["method"] for r in records] != list(source.METHODS):
                raise ValueError("source unit order or methods changed")
            for record in records:
                if (record["stream"] != stream["stream"] or record["phase"] != "MAIN" or
                    any(record[k] != original[k] for k in source.IDENTITY) or
                    any(record[k] != case[k] for k in ("seed", "task"))):
                    raise ValueError("source unit identity differs")
            count += 1
            yield stream["stream"], records
        if next(cases, None) is not None:
            raise ValueError("incomplete source stream")
    if count != manifest["config"]["source_units"]:
        raise ValueError("incomplete source population")


def prepare():
    clean()
    config = read(CONFIG)
    validate(config)
    original, _, completion = load_sources(config)
    parent = ROOT/config["output_root"]
    if list(parent.glob("*/manifest.json")):
        raise FileExistsError("one frozen analysis already exists")
    names = git("ls-files", "src", "scripts", "tests").splitlines()+[
        CONFIG.relative_to(ROOT).as_posix(), PROTOCOL, QUESTION, "AGENTS.md", ".gitattributes", "requirements.txt",
        "outputs/cache_continuation_alignment/.gitattributes"]
    commit = git("rev-parse", "HEAD")
    run_id = "cache_continuation_alignment_"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_"+commit[:12]
    manifest = {"experiment_run_id": run_id, "source_git_commit": commit, "config": config,
        "source_manifest_id": original["manifest_id"], "input_sha256": {n: sha(ROOT/n) for n in sorted(set(names))},
        "source_episode_sha256": {n: h for n, h in completion["artifact_sha256"].items() if n.startswith("episodes_")}}
    manifest["manifest_id"] = digest(manifest)
    target = parent/run_id
    target.mkdir(parents=True)
    write(target/"manifest.json", manifest)
    print((target/"manifest.json").relative_to(ROOT), flush=True)


def execute(path):
    clean()
    manifest, original, source_summary = load(path)
    if git("rev-parse", "HEAD") != manifest["source_git_commit"]:
        raise ValueError("frozen commit differs")
    target = path.parent/"analysis_v1"
    target.mkdir()
    started = perf_counter()
    dispositions, pairs, unique, controls, evidence = [], [], [], [], {}
    past, current_stream, queries = {}, None, 0
    for stream, records in units(manifest, original):
        if stream != current_stream:
            past, current_stream = {}, stream
        result = process_unit(records, past)
        dispositions.extend(result["dispositions"])
        pairs.extend(result["reuse_pairs"])
        unique.extend(result["unique_reuse_pairs"])
        controls.extend(result["refresh_controls"])
        for key, packet in result["evidence"].items():
            if key in evidence:
                raise ValueError("duplicate actual unit decision key")
            evidence[key] = packet
        queries += result["policy_queries"]
        if records[0]["episode"] == 11:
            print(f"aligned stream={stream}: source_cases={len(dispositions)}", flush=True)
    if len(dispositions) != manifest["config"]["source_executions"]:
        raise ValueError("source cases silently dropped")
    for name, rows in (("dispositions", dispositions), ("reuse_pairs", pairs), ("unique_reuse_pairs", unique),
                       ("refresh_controls", controls), ("visible_evidence", [{"decision_id": k, "public_evidence": v} for k, v in evidence.items()])):
        with gzip.open(target/(name+".jsonl.gz"), "xt", encoding="utf-8") as handle:
            for row in rows:
                handle.write(canonical(row)+"\n")
    identity = {k: manifest[k] for k in source.IDENTITY}
    summary = {**identity, "status": "COMPLETED_CONDITIONAL_DESCRIPTION", **describe(dispositions, pairs, unique, controls, queries)}
    write(target/"summary.json", summary)
    costs = {**identity, **{k: 0 for k in ZERO_RESOURCES}, "local_policy_queries": queries,
        "analysis_wall_seconds": perf_counter()-started, "source_cost_ledger": read(ROOT/manifest["config"]["source_costs"]),
        "source_main_actual_environment_steps": source_summary["controlled_steps"],
        "source_main_lifecycle": source_summary["lifecycle"],
        "interpretation": "Existing source collected once; no new free physical counterfactual, model fit or API. Shared controls and duplicate decisions are dependent."}
    write(target/"costs.json", costs)
    write(target/"completion.json", {**identity, "artifact_sha256": {n: sha(target/n) for n in OUTPUTS}})
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "run"))
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare()
    elif args.manifest is None:
        parser.error("--manifest required")
    else:
        try:
            execute(args.manifest.resolve())
        except BaseException as error:
            failure = args.manifest.resolve().parent/"failure.json"
            if not failure.exists():
                write(failure, {"status": "FAILED_PRESERVE_PARTIAL", "error_type": type(error).__name__, "error": str(error)})
            raise

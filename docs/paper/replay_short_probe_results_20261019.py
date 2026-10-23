"""Replay saved short-probe artifacts without collection or API calls.

Hash mode uses only the standard library. Numeric and record modes reuse the
frozen auditors; they are reproducibility checks, not new independent audits.
"""

import argparse
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter_ns
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / "outputs/short_probe_reference/development_v1/short_probe_reference_20261019T042309Z_39300e556379"
RECEIPTS = ROOT / "outputs/reproduction_reviews/short_probe_reference_v1"
MANIFEST_ID = "470c763b64db660ba5f0f075508f625bda894cbadd597aab8ae7cc84cb84576f"
SOURCE_COMMIT = "39300e55637971c8426effd20b49d3f0644fecd3"
IDENTITY = ("experiment_run_id", "manifest_id", "source_git_commit")
STAGES = ("collect", "record_audit", "analyze", "numeric_audit", "report")


def anchor_path(phase):
    return ROOT / f"docs/paper/short_probe_{phase.lower()}_anchors_20261019.json"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def saved_file(base, name):
    result = (base / name).resolve()
    if not result.is_relative_to(base.resolve()) or not result.is_file():
        raise ValueError("missing or out-of-root saved file: " + name)
    return result


def verify_saved(phase):
    manifest = read(STUDY / "manifest.json")
    canonical = json.dumps({k: v for k, v in manifest.items() if k != "manifest_id"},
                           sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if (manifest["manifest_id"] != MANIFEST_ID or hashlib.sha256(canonical).hexdigest() != MANIFEST_ID
            or manifest["source_git_commit"] != SOURCE_COMMIT):
        raise ValueError("foreign or changed experiment manifest")
    bindings = {}

    def bind(base, mapping):
        for name, expected in mapping.items():
            path = saved_file(base, name)
            if path in bindings and bindings[path] != expected:
                raise ValueError("conflicting binding: " + name)
            if sha(path) != expected:
                raise ValueError("changed saved bytes: " + name)
            bindings[path] = expected

    anchor_file = anchor_path(phase)
    anchors = read(anchor_file)
    if any(anchors[k] != manifest[k] for k in IDENTITY) or anchors["phase"] != phase:
        raise ValueError("delivery anchor identity differs")
    bind(ROOT, anchors["artifact_sha256"])
    bindings[anchor_file] = sha(anchor_file)
    bind(ROOT, manifest["input_sha256"])
    name = phase.lower()
    folder, analysis = STUDY / name, STUDY / (name + "_analysis")
    collected = read(folder / "completion.json")
    analyzed = read(analysis / "analysis_completion.json")
    record = read(STUDY / (name + "_record_audit.json"))
    numeric = read(STUDY / (name + "_numeric_audit.json"))
    report = read(analysis / "report_receipt.json")
    pipeline = read(STUDY / (name + "_pipeline_completion.json"))
    for receipt in (collected, analyzed, record, numeric, report, pipeline):
        if any(receipt[k] != manifest[k] for k in IDENTITY) or receipt["phase"] != phase:
            raise ValueError("receipt identity differs")
    if (collected["status"] != "COLLECTED_FOR_INDEPENDENT_AUDIT"
            or record["integrity"] != "PASSED" or numeric["integrity"] != "PASSED"
            or pipeline["status"] != "COMPLETED_FOR_REVIEW" or pipeline["failure"] is not None
            or tuple(s["stage"] for s in pipeline["steps"]) != STAGES
            or any(s["returncode"] != 0 for s in pipeline["steps"])):
        raise ValueError("incomplete or failed delivered pipeline")
    bind(folder, collected["artifact_sha256"])
    bind(analysis, analyzed["artifact_sha256"])
    bind(ROOT, {report["report_path"]: report["report_sha256"]})
    bind(STUDY / (name + "_pipeline"), {s["stage"] + ".txt": s["log_sha256"] for s in pipeline["steps"]})
    for receipt in (analyzed, record, numeric):
        bind(folder, {"summary.json": receipt["summary_sha256"]})
    for receipt in (analyzed, numeric, report):
        bind(STUDY, {name + "_record_audit.json": receipt["record_audit_sha256"]})
    bind(folder, {"completion.json": record["completion_sha256"]})
    bind(analysis, {"statistics.json": numeric["statistics_sha256"], "costs.json": numeric["costs_sha256"],
                    "analysis_completion.json": numeric["analysis_completion_sha256"]})
    bind(STUDY, {name + "_numeric_audit.json": report["numeric_audit_sha256"]})
    return manifest, bindings, record


def json_lines(paths):
    for path in paths:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for line in handle:
                yield json.loads(line)


def replay(mode, phase):
    started = perf_counter_ns()
    manifest, bindings, original_record = verify_saved(phase)
    result = {
        "schema": "short_probe_saved_artifact_replay_v1", "mode": mode, "phase": phase,
        **{k: manifest[k] for k in IDENTITY}, "helper_sha256": sha(Path(__file__)),
        "anchor_file_sha256": sha(anchor_path(phase)), "python_version": sys.version,
        "python_executable": sys.executable, "verified_frozen_inputs": len(manifest["input_sha256"]),
        "verified_bound_files": len(bindings), "numeric_replay": None, "record_replay": None,
        "new_environment_steps": 0, "new_reset_calls": 0, "new_api_calls": 0,
        "scope": "Consistency with versioned delivery anchors; trust requires the delivered code and anchors. "
                 "Reuses frozen auditors. No fresh physical replication or independent audit implementation. "
                 "Hash mode does not check installed native libraries or recompute statistics.",
    }
    if mode != "hashes":
        sys.path.insert(0, str(ROOT))
        from src.analysis import short_probe_study_io_v1 as io
        from src.analysis.short_probe_numeric_audit_v1 import reconstruct, compare
        import numpy as np
        result["numpy_version"] = np.__version__
        checked_manifest, models, designs = io.load(STUDY / "manifest.json")
        if checked_manifest != manifest:
            raise ValueError("runtime source validation differs")
        summary = read(STUDY / phase.lower() / "summary.json")
        identity = {k: manifest[k] for k in IDENTITY}
        stat, fees = reconstruct(summary)
        analysis = STUDY / (phase.lower() + "_analysis")
        checks = compare({"statistics": read(analysis / "statistics.json"), "costs": read(analysis / "costs.json")},
                         {"statistics": {**identity, **stat}, "costs": {**identity, **fees}})
        csv_rows = 0
        for name, rows in (("all_executions.csv", summary["rows"]),
                           ("all_failures.csv", [r for r in summary["rows"] if not r["success"]]),
                           ("all_stops.csv", [r for r in summary["rows"] if r["stopped"]])):
            with (analysis / name).open(encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                if reader.fieldnames != list(summary["rows"][0]) or list(reader) != [{k: str(v) for k, v in r.items()} for r in rows]:
                    raise ValueError("saved CSV differs: " + name)
            csv_rows += len(rows)
        result["numeric_replay"] = {**checks, "csv_rows_checked": csv_rows}
        if mode == "records":
            from src.analysis.short_probe_study_audit_v1 import audit_records, population
            folder = STUDY / phase.lower()
            replayed = audit_records(manifest, phase, summary,
                json_lines(folder / f"cases_{s['stream']:02}.jsonl.gz" for s in population(phase)),
                json_lines([folder / "events.jsonl.gz"]), models, designs)
            expected = {k: v for k, v in original_record.items() if k not in ("summary_sha256", "completion_sha256")}
            result["record_replay"] = {
                "comparison": compare(replayed, expected),
                **{k: replayed[k] for k in ("integrity", "events_checked", "executions_checked", "audit_recomputation")},
            }
    for path, expected in bindings.items():
        if sha(path) != expected:
            raise ValueError("saved input changed during replay: " + str(path.relative_to(ROOT)))
    result.update(bound_inputs_unchanged=True, replay_body_wall_ns=perf_counter_ns() - started,
                  integrity="VERIFIED_SAVED_ARTIFACT_HASHES" if mode == "hashes" else "PASSED")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("hashes", "numeric", "records"), default="numeric")
    parser.add_argument("--phase", choices=("SMOKE", "MAIN"), default="MAIN")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    default = RECEIPTS / (stamp + "_" + args.phase.lower() + "_" + args.mode + "_" + uuid4().hex[:8] + ".json")
    output = (ROOT / args.output if args.output is not None else default).resolve()
    if not output.is_relative_to(RECEIPTS.resolve()) or output.suffix != ".json":
        parser.error("output must be a new JSON file inside " + str(RECEIPTS.relative_to(ROOT)))
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        handle = output.open("x", encoding="utf-8", newline="\n")
    except FileExistsError:
        parser.error("receipt already exists; it will not be overwritten")
    with handle:
        code = 0
        try:
            result = replay(args.mode, args.phase)
        except (Exception, KeyboardInterrupt) as error:
            result = {"schema": "short_probe_saved_artifact_replay_v1", "mode": args.mode, "phase": args.phase,
                      "integrity": "INTERRUPTED_NOT_RETRIED" if isinstance(error, KeyboardInterrupt) else "FAILED_NOT_RETRIED",
                      "helper_sha256": sha(Path(__file__)), "error_type": type(error).__name__, "error": str(error)}
            code = 130 if isinstance(error, KeyboardInterrupt) else 1
        result["checked_utc"] = datetime.now(timezone.utc).isoformat()
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps({"integrity": result["integrity"], "receipt": output.relative_to(ROOT).as_posix()}))
    return code


if __name__ == "__main__":
    raise SystemExit(main())

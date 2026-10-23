"""Read-only replay of the delivered paired-probe artifact, with fresh receipts.

This paper helper never starts collection or calls an API. The historical
auditors are reused; this is not another independent auditor implementation.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter_ns
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / (
    "outputs/paired_probe_effects/development_v1/"
    "paired_probe_effects_20261016T191951Z_591c353cd1e2"
)
MANIFEST_ID = "758755b6e0b07419c631f6c8cc83696de4d05a9be8ca1d66f334b8fd6cb7f1f7"
DELIVERY_COMMIT = "f267f4dad08e40279708968baa6c97f77d1ba90b"
RECEIPTS = ROOT / "outputs/reproduction_reviews/paired_probe_v1"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def relative_file(base, name):
    """Resolve artifact names without allowing references outside their root."""
    path = (base / name).resolve()
    if not path.is_relative_to(base.resolve()) or not path.is_file():
        raise ValueError("missing or out-of-root artifact: " + name)
    return path


def verify_saved(phase):
    folder = STUDY / phase.lower()
    analysis = STUDY / (phase.lower() + "_analysis_v1")
    anchors = [
        STUDY / "manifest.json",
        folder / "completion.json",
        analysis / "completion.json",
        analysis / "report_receipt.json",
        analysis / "figures/receipt.json",
        STUDY / (phase.lower() + "_audit.json"),
        STUDY / (phase.lower() + "_statistics_audit.json"),
        STUDY / (phase.lower() + "_pipeline_completion.json"),
    ]
    for path in anchors:
        name = path.relative_to(ROOT).as_posix()
        committed = subprocess.run(
            ["git", "show", DELIVERY_COMMIT + ":" + name], cwd=ROOT,
            check=True, capture_output=True,
        ).stdout
        if path.read_bytes() != committed:
            raise ValueError("artifact anchor differs from delivered Git object: " + name)

    manifest = read(STUDY / "manifest.json")
    canonical = json.dumps(
        {k: v for k, v in manifest.items() if k != "manifest_id"},
        sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    if manifest["manifest_id"] != MANIFEST_ID or hashlib.sha256(canonical).hexdigest() != MANIFEST_ID:
        raise ValueError("unexpected manifest identity")

    bindings = {p: sha(p) for p in anchors}

    def bind(base, mapping):
        for name, expected in mapping.items():
            path = relative_file(base, name)
            if path in bindings and bindings[path] != expected:
                raise ValueError("conflicting artifact binding: " + name)
            if sha(path) != expected:
                raise ValueError("artifact hash mismatch: " + name)
            bindings[path] = expected

    bind(ROOT, manifest["input_sha256"])
    for base in (folder, analysis, analysis / "figures"):
        receipt = read(base / ("receipt.json" if base.name == "figures" else "completion.json"))
        bind(base, receipt["artifact_sha256"])

    report = read(analysis / "report_receipt.json")
    bind(ROOT, {report["report_path"]: report["report_sha256"]})
    record = read(STUDY / (phase.lower() + "_audit.json"))
    numeric = read(STUDY / (phase.lower() + "_statistics_audit.json"))
    pipeline = read(STUDY / (phase.lower() + "_pipeline_completion.json"))
    if record["integrity"] != "PASSED" or numeric["integrity"] != "PASSED":
        raise ValueError("delivered source audit did not pass")
    if (pipeline["status"] != "COMPLETED_FOR_REVIEW" or pipeline["failure"] is not None
            or len(pipeline["steps"]) != 6 or any(s["returncode"] for s in pipeline["steps"])):
        raise ValueError("source pipeline was incomplete")
    return manifest, bindings, len(anchors)


def replay(mode, phase):
    started = perf_counter_ns()
    manifest, bindings, anchors = verify_saved(phase)
    result = {
        "schema": "paired_probe_paper_replay_v1",
        "mode": mode, "phase": phase,
        "experiment_run_id": manifest["experiment_run_id"],
        "manifest_id": MANIFEST_ID, "delivery_commit": DELIVERY_COMMIT,
        "collector_source_commit": manifest["source_git_commit"],
        "helper_sha256": sha(Path(__file__)),
        "python_version": sys.version, "python_executable": sys.executable,
        "verified_git_anchors": anchors,
        "verified_frozen_inputs": len(manifest["input_sha256"]),
        "verified_unique_bound_files": len(bindings),
        "new_environment_steps": 0, "new_api_calls": 0,
        "numeric_replay": None, "record_replay": None,
        "scope": (
            "Existing saved-artifact hashes and optional existing auditor reruns. "
            "No fresh physical replication, new independent audit implementation "
            "or universal hidden-state qualification. Hash-only mode does not "
            "recompute statistics or verify installed native runtime bytes."
        ),
    }
    if mode != "hashes":
        sys.path.insert(0, str(ROOT))
        import numpy as np
        result["numpy_version"] = np.__version__
        if mode == "records":
            from scripts.audit_paired_probe_effects_v1 import audit as record_audit
            result["record_replay"] = record_audit(STUDY / "manifest.json", phase)
        from scripts.audit_paired_probe_statistics_v1 import audit as numeric_audit
        result["numeric_replay"] = numeric_audit(STUDY / "manifest.json", phase)
    for path, expected in bindings.items():
        if sha(path) != expected:
            raise ValueError("bound input changed during replay: " + str(path.relative_to(ROOT)))
    result["bound_inputs_unchanged"] = True
    result["integrity"] = "VERIFIED_SAVED_ARTIFACT_HASHES" if mode == "hashes" else "PASSED"
    result["replay_body_wall_ns"] = perf_counter_ns() - started
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("hashes", "numeric", "records"), default="numeric")
    parser.add_argument("--phase", choices=("SMOKE", "MAIN"), default="MAIN")
    parser.add_argument("--output", type=Path, help="New JSON path inside outputs/reproduction_reviews/paired_probe_v1")
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    default = RECEIPTS / (stamp + "_" + args.phase.lower() + "_" + args.mode + "_" + uuid4().hex[:8] + ".json")
    output = (ROOT / args.output if args.output is not None else default).resolve()
    if not output.is_relative_to(RECEIPTS.resolve()) or output.suffix != ".json":
        parser.error("output must be a new .json inside " + str(RECEIPTS.relative_to(ROOT)))
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
            result = {
                "schema": "paired_probe_paper_replay_v1", "mode": args.mode,
                "phase": args.phase,
                "integrity": "INTERRUPTED_NOT_RETRIED" if isinstance(error, KeyboardInterrupt) else "FAILED_NOT_RETRIED",
                "helper_sha256": sha(Path(__file__)),
                "error_type": type(error).__name__, "error": str(error),
            }
            code = 130 if isinstance(error, KeyboardInterrupt) else 1
        result["checked_utc"] = datetime.now(timezone.utc).isoformat()
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps({"integrity": result["integrity"], "receipt": output.relative_to(ROOT).as_posix()}))
    return code


if __name__ == "__main__":
    raise SystemExit(main())

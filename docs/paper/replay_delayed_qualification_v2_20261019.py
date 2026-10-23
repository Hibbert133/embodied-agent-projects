"""Recheck the complete frozen v2 journals without creating an environment.

Writes one fresh receipt only. Reuses the disclosed frozen audit, projection,
policy and estimators; this is reproducibility, not independent robot evidence.
"""
import argparse
from pathlib import Path
import json
import sys
from time import perf_counter_ns

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import audit_delayed_intervention_v2 as audit
from src.analysis import delayed_qualification_io_v2 as io
from src.analysis.short_probe_public_audit_v1 import same

RUN = ROOT / "outputs/delayed_intervention/qualification_v2/delayed_intervention_v2_20261019T090014Z_1ba6b7b81e55"
EXPECTED_MANIFEST = "ae549ee2e9cfdcac76a8f565db1f04321c22f6ebaac93d18694eec783aee6b6a"


def replay(target):
    allowed = ROOT / "outputs/reproduction_reviews/delayed_intervention_v2"
    target = target.resolve()
    if not target.is_relative_to(allowed) or target == allowed or target.exists():
        raise ValueError("a fresh receipt in the registered reproduction folder is required")
    target.parent.mkdir(parents=True, exist_ok=True)
    started = perf_counter_ns()
    receipt = {"status": "FAILED", "failure": None}
    try:
        manifest, models = io.load(RUN / "manifest.json")
        same(manifest["manifest_id"], EXPECTED_MANIFEST)
        identity = {k: manifest[k] for k in io.IDENTITY}
        receipt.update(identity)
        previous = io.read(RUN / "audit/record_audit.json")
        same(previous["integrity"], "PASSED")
        for key in io.IDENTITY:
            same(previous[key], identity[key])
        for name, value in previous["collection_artifact_sha256"].items():
            same(io.sha(RUN / "collection" / name), value)
        completion = io.read(RUN / "collection/completion.json")
        same(completion["status"], "COLLECTED_FOR_INDEPENDENT_AUDIT")
        for key in io.IDENTITY:
            same(completion[key], identity[key])
        expected_files = {"events.jsonl.gz", "cases.jsonl.gz", "state_witnesses.jsonl.gz", "summary.json", "status.json"}
        audit.require(set(completion["artifact_sha256"]) == expected_files, "complete file set required")
        for name, value in completion["artifact_sha256"].items():
            same(io.sha(RUN / "collection" / name), value)
        report = io.read(RUN / "audit/report_receipt.json")
        same(report["record_audit_sha256"], io.sha(RUN / "audit/record_audit.json"))
        same(report["report_sha256"], io.sha(RUN / "audit/report_zh.md"))
        same(report["report_source_sha256"], io.sha(ROOT / "scripts/audit_delayed_intervention_v2.py"))
        records, events, private = [audit.previous.read_lines(RUN / "collection" / name)
            for name in ("cases.jsonl.gz", "events.jsonl.gz", "state_witnesses.jsonl.gz")]
        summary = io.read(RUN / "collection/summary.json")
        same(io.read(RUN / "collection/status.json"), {k: v for k, v in summary.items() if k != "rows"})
        computed = audit.audit_records(manifest, models, records, events, private, summary)
        for key, value in computed.items():
            same(previous[key], value)
        receipt.update(status="PASSED", registered_qualification=computed["qualification"],
            executions=len(records), event_count=len(events), private_witness_records=len(private),
            recomputation=computed["audit_computations"], new_environment_steps=0, new_resets=0, new_api_calls=0,
            frozen_input_count=len(manifest["input_sha256"]), source_sha256=io.sha(Path(__file__)),
            frozen_auditor_sha256=io.sha(ROOT / "scripts/audit_delayed_intervention_v2.py"),
            original_audit_sha256=io.sha(RUN / "audit/record_audit.json"),
            scope="Read-only full-record replay; shared frozen projection and audit; no new robot experiment.")
    except BaseException as error:
        receipt["failure"] = {"type": type(error).__name__, "message": str(error)}
        raise
    finally:
        receipt["wall_ns"] = perf_counter_ns() - started
        io.write(target, receipt)
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(replay(args.receipt), ensure_ascii=False))

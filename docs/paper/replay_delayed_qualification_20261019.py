"""Replay all saved delayed-qualification journals without creating environments.

Writes only one fresh task-local receipt. Frozen estimators/policies/auditor are
shared, explicitly; this is reproducibility, not another independent experiment.
"""
import argparse
import gzip
import json
from pathlib import Path
import sys
from time import perf_counter_ns

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import audit_delayed_intervention_v1 as audit
from src.analysis import delayed_qualification_io_v1 as io
from src.analysis.short_probe_public_audit_v1 import same

RUN = ROOT / "outputs/delayed_intervention/qualification_v1/delayed_intervention_20261019T081007Z_72cd966d73d9"
EXPECTED_MANIFEST = "764fa8ef1c65e0bef7d40b085641c0d5cf6c4318aa6fcd3a4278a545d6c4f8ab"


def replay(target):
    allowed = ROOT / "outputs/reproduction_reviews/delayed_intervention_v1"
    target = target.resolve()
    if not target.is_relative_to(allowed) or target == allowed or target.exists():
        raise ValueError("fresh reproduction receipt inside the registered task folder required")
    target.parent.mkdir(parents=True, exist_ok=True)
    started = perf_counter_ns();receipt = {"status": "FAILED", "failure": None}
    try:
        manifest, models = io.load(RUN / "manifest.json");same(manifest["manifest_id"], EXPECTED_MANIFEST)
        identity = {k: manifest[k] for k in io.IDENTITY};receipt.update(identity)
        previous = io.read(RUN / "audit/record_audit.json");same(previous["integrity"], "PASSED")
        for key in io.IDENTITY: same(previous[key], identity[key])
        for name, value in previous["collection_artifact_sha256"].items(): same(io.sha(RUN / "collection" / name), value)
        report = io.read(RUN / "audit/report_receipt.json")
        same(report["record_audit_sha256"], io.sha(RUN / "audit/record_audit.json"))
        same(report["report_sha256"], io.sha(RUN / "audit/report_zh.md"))
        with gzip.open(RUN / "collection/cases.jsonl.gz", "rt", encoding="utf-8") as handle: records = [json.loads(line) for line in handle]
        with gzip.open(RUN / "collection/events.jsonl.gz", "rt", encoding="utf-8") as handle: events = [json.loads(line) for line in handle]
        population = audit.compare_population(records, manifest["config"])
        for key, value in population.items(): same(previous[key], value)
        ledger = {"counts": {}, "by_phase": {}};sequence = stamp = -1;position = 0
        counts = {k: 0 for k in previous["audit_computations"]}
        for row in records:
            spec = {k: row[k] for k in ("unit", "task", "seed", "variant")};group = []
            while position < len(events) and all(events[position].get(k) == v for k, v in spec.items()):
                group.append(events[position]);position += 1
            checked = audit.audit_case(group, row, {**identity, **spec}, manifest["config"]["fault_oracle"], models[row["task"]],
                initial_ledger=ledger, previous_sequence=sequence, previous_saved_ns=stamp)
            ledger = checked["ledger"];sequence = checked["last_sequence"];stamp = checked["last_saved_ns"]
            for key in counts: counts[key] += checked[key]
        same(position, len(events));same(ledger, previous["costs"]["lifecycle"]);same(counts, previous["audit_computations"])
        receipt.update(status="PASSED", registered_qualification=population["qualification"], event_count=len(events), executions=len(records),
            recomputation=counts, new_environment_steps=0, new_resets=0, new_api_calls=0,
            source_sha256=io.sha(Path(__file__)), frozen_auditor_sha256=io.sha(ROOT / "scripts/audit_delayed_intervention_v1.py"),
            original_audit_sha256=io.sha(RUN / "audit/record_audit.json"), frozen_input_count=len(manifest["input_sha256"]),
            scope="Read-only repetition of the frozen record audit; no independent physics or qualification promotion.")
    except BaseException as error:
        receipt["failure"] = {"type": type(error).__name__, "message": str(error)}
        raise
    finally:
        receipt["wall_ns"] = perf_counter_ns() - started;io.write(target, receipt)
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__);parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args();print(json.dumps(replay(args.receipt), ensure_ascii=False))

"""Run frozen independent numerics plus exact comparison to preserved partial v1."""
import argparse
import gzip
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import run_cross_task_cache_validity_v2 as repair
from scripts import audit_cross_task_cache_validity as original_audit


def audit(path, output):
    if output.exists():
        raise FileExistsError("preserve v2 audit")
    configured = repair.configure()
    first = ROOT/repair.V1_RUN/"predictions_scores.jsonl.gz"
    second = path.parent/"predictions_scores.jsonl.gz"
    count = 0
    with gzip.open(first, "rt", encoding="utf-8") as old, gzip.open(second, "rt", encoding="utf-8") as new:
        for line in old:
            left, right = json.loads(line), json.loads(next(new))
            field = "prediction" if left["event"] == "PREDICTION" else "score"
            if left[field] != right[field]:
                raise ValueError("numeric repair changed preserved partial v1")
            count += 1
    if count != 12:
        raise ValueError("unexpected original partial scope")
    numeric_output = output.with_name(output.stem+"_numeric_v1.json")
    original_audit.audit(path, numeric_output)
    value = configured.read(numeric_output)
    value.update({"v2_entrypoint_sha256": configured.file_digest(Path(__file__)),
                  "v1_partial_events_exactly_matched": count, "v1_partial_scores_exactly_matched": 6,
                  "v1_partial_sha256": configured.file_digest(first),
                  "numeric_audit_sha256": configured.file_digest(numeric_output),
                  "repair_scope": "Only evaluator static-A metadata normalization; original forecast, score and independent numerical implementation unchanged."})
    configured.write(output, value)
    print(json.dumps({"v2_integrity": "PASSED", "v1_partial_scores_exactly_matched": 6}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--manifest", required=True, type=Path); parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(); audit(args.manifest.resolve(), args.output.resolve())

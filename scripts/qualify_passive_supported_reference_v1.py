"""Save explicitly synthetic software fixtures; no scientific robot collection."""
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.test_passive_supported_reference_v1 import ToyHost, prior
from tests.test_operator_identification import model
from scripts.audit_passive_supported_reference_v1 import verify
from src.probe.cache_acquisition_evidence_v1 import canonical, digest

CONFIG = "configs/passive_supported_reference/qualification_v1.json"
PROTOCOL = "docs/protocols/passive_supported_reference_qualification_v1.md"
KIND = "SOFTWARE_TEST_FIXTURES_NOT_METAWORLD"


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n")


def git(*args): return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def main():
    if git("status", "--porcelain", "--untracked-files=no"):
        raise ValueError("commit implementation and software-qualification config first")
    config = json.loads((ROOT/CONFIG).read_text(encoding="utf-8"))
    if config["artifact_type"] != KIND or config["budget"] != 500 or len(config["cases"]) != 5:
        raise ValueError("fixed software fixtures required")
    if (any(config[k] != 0 for k in ("new_scientific_environment_steps", "new_api_calls", "new_nominal_model_fits", "policy_weight_updates")) or
        config["robotic_task_result"] is not False or config["new_algorithm_established"] is not False):
        raise ValueError("software qualification cannot claim robot results")
    parent = ROOT/config["output_root"]
    if list(parent.glob("*/manifest.json")):
        raise FileExistsError("software qualification already recorded")
    commit = git("rev-parse", "HEAD")
    run_id = "passive_supported_reference_"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_"+commit[:12]
    names = git("ls-files", "src", "scripts", "tests").splitlines()+[CONFIG, PROTOCOL,
        "docs/research/strong_passive_reference_boundary_20261016_zh.md", "outputs/passive_supported_reference/.gitattributes",
        "AGENTS.md", ".gitattributes", "requirements.txt"]
    manifest = {"experiment_run_id": run_id, "source_git_commit": commit, "artifact_type": KIND, "config": config,
                "input_sha256": {n: sha(ROOT/n) for n in sorted(set(names))}}
    manifest["manifest_id"] = digest(manifest)
    target = parent/run_id
    target.mkdir(parents=True)
    write(target/"manifest.json", manifest)
    try:
        with gzip.open(target/"software_fixtures.jsonl.gz", "xt", encoding="utf-8") as handle:
            for case in config["cases"]:
                host = ToyHost(end=case["end"], varied=case["varied"], success=case["success"])
                record = host.run(mode=case["mode"], previous=prior(case["mode"]) if case["old_cache"] else None, episode=case["episode"])
                handle.write(canonical({"artifact_type": KIND, "case_id": case["id"], "record": record})+"\n")
        audits, totals = [], {"test_callback_steps": 0, "test_fit_attempts": 0, "test_optimizer_nfev": 0, "test_policy_queries": 0, "audit_policy_queries": 0}
        with gzip.open(target/"software_fixtures.jsonl.gz", "rt", encoding="utf-8") as handle:
            rows = [json.loads(line) for line in handle]
        if [r["case_id"] for r in rows] != [c["id"] for c in config["cases"]]:
            raise ValueError("software fixtures silently dropped")
        for row, case in zip(rows, config["cases"]):
            if row["artifact_type"] != KIND:
                raise ValueError("test artifact relabeled as robot evidence")
            checker = ToyHost(end=case["end"], varied=case["varied"], success=case["success"])
            audit = verify(row["record"], model("LINEAR_ARX"), checker.policy)
            audits.append({"case_id": row["case_id"], **audit})
            outcome = row["record"]["outcome"]
            for key, field in (("test_callback_steps", "total_steps"), ("test_fit_attempts", "fit_attempts"),
                               ("test_optimizer_nfev", "optimizer_nfev"), ("test_policy_queries", "policy_queries")):
                totals[key] += outcome[field]
            totals["audit_policy_queries"] += outcome["total_steps"]
        summary = {"experiment_run_id": run_id, "manifest_id": manifest["manifest_id"], "source_git_commit": commit,
            "artifact_type": KIND, "control_flow_integrity": "PASSED", "cases": len(rows), "audits": audits, **totals,
            "new_scientific_environment_steps": 0, "new_api_calls": 0, "new_nominal_model_fits": 0,
            "physical_host_qualified": False, "robotic_task_result": False, "new_algorithm_established": False,
            "scope": "Synthetic software callbacks and saved-control-flow replay only; shared numerical fitter, encoder and cache schema. Not robot success or utility."}
        write(target/"summary.json", summary)
        write(target/"completion.json", {"artifact_sha256": {n: sha(target/n) for n in ("manifest.json", "software_fixtures.jsonl.gz", "summary.json")}})
        print(json.dumps(summary, ensure_ascii=False), flush=True)
        print(target.relative_to(ROOT), flush=True)
    except BaseException as error:
        write(target/"failure.json", {"status": "FAILED_PRESERVE_SOFTWARE_FIXTURES", "error_type": type(error).__name__, "error": str(error)})
        raise


if __name__ == "__main__": main()

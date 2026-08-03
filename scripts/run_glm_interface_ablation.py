"""Run the frozen 90-call ProbeMem-Online Gate-A shadow ablation."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_probemem_acr_utility_stability import _sha256, _write_json  # noqa: E402
from src.probemem.online_glm_contract import INTERFACES, OnlineGroundingDecision, OnlineGroundingGlmPolicy  # noqa: E402
from src.reasoning.evidence import validate_no_oracle_evidence  # noqa: E402


def _git(*args: str) -> str:
    return subprocess.run(["git", "-c", f"safe.directory={ROOT.as_posix()}", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def _validate(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if path.parent.name != manifest["experiment_run_id"] or _git("rev-parse", "HEAD") != manifest["source_git_commit"]:
        raise RuntimeError("interface-ablation manifest identity or commit mismatch")
    if _git("status", "--porcelain", "--untracked-files=no"):
        raise RuntimeError("interface ablation requires a clean tracked worktree")
    config_path = ROOT / manifest["config_path"]
    if _sha256(config_path) != manifest["config_sha256"]:
        raise RuntimeError("interface-ablation config changed")
    for relative, expected in manifest["implementation_sha256"].items():
        if _sha256(ROOT / relative) != expected:
            raise RuntimeError(f"interface implementation changed: {relative}")
    source = ROOT / manifest["source_collection_run"]
    for name, expected in manifest["source_artifact_sha256"].items():
        if _sha256(source / name) != expected:
            raise RuntimeError(f"source collection artifact changed: {name}")
    return manifest, json.loads(config_path.read_text(encoding="utf-8"))


def build_tasks(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    source = ROOT / manifest["source_collection_run"]
    rows = json.loads((source / "agent_evidence.json").read_text(encoding="utf-8"))
    if len(rows) != 30:
        raise RuntimeError("Gate-A source must contain exactly 30 evidence rows")
    tasks: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda item: int(item["episode_id"])):
        episode_id = int(row["episode_id"])
        rotation = (episode_id - 1) % len(INTERFACES)
        order = INTERFACES[rotation:] + INTERFACES[:rotation]
        for interface in order:
            evidence = row["agent_visible_full_evidence"] if interface == "FULL_PAYLOAD" else row["agent_visible_compact_evidence"]
            validate_no_oracle_evidence(evidence)
            tasks.append({
                "call_id": f"episode{episode_id:03d}_{interface.lower()}", "episode_id": episode_id,
                "interface": interface, "condition_id_evaluator_only": row["condition_id_evaluator_only"],
                "agent_visible_evidence": evidence,
            })
    if len(tasks) != 90:
        raise RuntimeError("Gate-A Latin-square task list must contain 90 calls")
    return tasks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--api-timeout", type=float, default=None)
    args = parser.parse_args()
    manifest: dict[str, Any] | None = None
    status_path: Path | None = None
    try:
        manifest, config = _validate(args.manifest.resolve())
        run_dir = args.manifest.resolve().parent
        status_path = run_dir / "run_status.json"
        if status_path.exists():
            raise FileExistsError("interface ablation cannot restart or overwrite")
        timeout = float(config["timeout_seconds"] if args.api_timeout is None else args.api_timeout)
        policy = OnlineGroundingGlmPolicy(model=os.environ.get("LLM_MODEL", config["model"]), timeout_seconds=timeout, max_tokens=int(config["max_tokens"]))
        tasks = build_tasks(manifest)
        results: list[dict[str, Any]] = []
        _write_json(status_path, {"status": "RUNNING_BASE_CALLS", "manifest_id": manifest["manifest_id"], "completed_calls": 0})
        for task in tasks:
            decision, attempt = policy.request_once(task["agent_visible_evidence"], interface=task["interface"])
            results.append({**task, "base_attempt": attempt, "repair_attempt": None, "final_decision": None if decision is None else decision.to_dict(), "final_valid": decision is not None, "action_executed": False})
            _write_json(run_dir / "ablation_audit.json", results)
            _write_json(status_path, {"status": "RUNNING_BASE_CALLS", "manifest_id": manifest["manifest_id"], "completed_calls": len(results)})
            print(f"base {len(results)}/90 episode={task['episode_id']} interface={task['interface']} valid={decision is not None}", flush=True)
        invalid = [row for row in results if not row["final_valid"]]
        repair_capacity = int(config["maximum_api_calls"]) - len(results)
        if len(invalid) > repair_capacity:
            for row in invalid:
                row["final_decision"] = OnlineGroundingDecision.fail_closed("repair budget insufficient").to_dict()
            _write_json(run_dir / "ablation_audit.json", results)
            _write_json(status_path, {"status": "INCOMPLETE_API_BUDGET", "manifest_id": manifest["manifest_id"], "base_calls": 90, "invalid_base_outputs": len(invalid), "repairs": 0, "api_calls": 90})
            print(f"[INCOMPLETE] invalid base outputs {len(invalid)} exceed repair capacity {repair_capacity}", file=sys.stderr)
            return 2
        repairs = 0
        for row in invalid:
            previous_error = str(row["base_attempt"].get("error", "invalid structured output"))
            decision, attempt = policy.request_once(row["agent_visible_evidence"], interface=row["interface"], previous_error=previous_error)
            repairs += 1
            row["repair_attempt"] = attempt
            row["final_valid"] = decision is not None
            row["final_decision"] = (decision or OnlineGroundingDecision.fail_closed(f"repair failed: {attempt.get('error', 'invalid output')}")).to_dict()
            _write_json(run_dir / "ablation_audit.json", results)
            print(f"repair {repairs}/{len(invalid)} call={row['call_id']} valid={decision is not None}", flush=True)
        summary = {
            "protocol": config["protocol"], "experiment_run_id": manifest["experiment_run_id"],
            "manifest_id": manifest["manifest_id"], "source_git_commit": manifest["source_git_commit"],
            "model": policy.model, "cases": 30, "base_calls": 90, "repair_calls": repairs,
            "api_calls": 90 + repairs, "raw_valid": sum(row["base_attempt"]["valid"] for row in results),
            "post_repair_valid": sum(row["final_valid"] for row in results),
            "environment_steps": 0, "model_actions_executed": 0,
        }
        _write_json(run_dir / "summary.json", summary)
        _write_json(status_path, {"status": "COMPLETED", **summary})
        print(f"run: {run_dir}")
        return 0
    except Exception as exc:
        if manifest is not None and status_path is not None:
            _write_json(status_path, {"status": "FAILED", "manifest_id": manifest["manifest_id"], "error_type": type(exc).__name__, "error": str(exc)})
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

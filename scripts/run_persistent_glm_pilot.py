"""Run the frozen ten-call GLM pilot on persistent-regime evidence."""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_probemem_acr_utility_stability import _write_json  # noqa: E402
from src.probemem.acr_shadow_policy import AcrGlmShadowPolicy  # noqa: E402
from src.reasoning.evidence import validate_no_oracle_evidence  # noqa: E402


PERSISTENT_SYSTEM_PROMPT = """You are a shadow-mode embodied action-selection agent.
Use only the supplied Agent-visible initial-rollout and registered repeated-probe
evidence. Predict the outcome of both bounded candidate interventions, then
select one registered discrete decision or abstain. Never infer or request the
injected condition identity, frozen host threshold, evaluator outcomes,
continuous robot actions, or skill parameters. Return exactly one JSON object
matching the schema. Your output is audited only and never controls the robot."""


def _git(*args: str) -> str:
    return subprocess.run(["git", "-c", f"safe.directory={ROOT.as_posix()}", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def select_cases(config: dict[str, Any]) -> list[dict[str, Any]]:
    run_dir = ROOT / config["source_run"]
    manifest = json.loads((run_dir / "immutable_manifest.json").read_text(encoding="utf-8"))
    if manifest["manifest_id"] != config["source_manifest_id"]:
        raise RuntimeError("persistent source manifest mismatch")
    decisions = {int(row["episode_id"]): row for row in json.loads((run_dir / "agent_decisions.json").read_text(encoding="utf-8"))}
    selected: list[dict[str, Any]] = []
    operational = [row for row in _csv(run_dir / "case_results.csv") if row["paired_comparable"].lower() == "true"]
    for condition in sorted({row["condition_id_oracle"] for row in operational}):
        rows = sorted((row for row in operational if row["condition_id_oracle"] == condition), key=lambda row: int(row["episode_id"]))
        for row in rows[:int(config["cases_per_condition"])]:
            decision = decisions[int(row["episode_id"])]
            evidence = decision["agent_visible_evidence"]
            validate_no_oracle_evidence(evidence)
            selected.append({"episode_id": int(row["episode_id"]), "selection_stratum_evaluator_only": condition, "deterministic_skill_evaluator_only": row["selected_skill"], "agent_visible_evidence": evidence})
    if len(selected) != int(config["maximum_cases"]):
        raise RuntimeError("frozen stratified pilot population is incomplete")
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/probemem_acr/persistent_glm_pilot_v1.json")
    parser.add_argument("--api-timeout", type=float, default=300.0)
    args = parser.parse_args()
    try:
        config = json.loads(args.config.resolve().read_text(encoding="utf-8"))
        cases = select_cases(config)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"persistent_glm_pilot_{stamp}_{_git('rev-parse', 'HEAD')[:12]}"
        run_dir = ROOT / "outputs/probemem_acr/persistent_glm_pilot_runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        policy = AcrGlmShadowPolicy(model=os.environ.get("LLM_MODEL", config["model"]), timeout_seconds=args.api_timeout, system_prompt=PERSISTENT_SYSTEM_PROMPT)
        results: list[dict[str, Any]] = []
        calls = 0
        for case in cases:
            decision, audit = policy.decide(case["agent_visible_evidence"], allow_repair=False)
            calls += len(audit["attempts"])
            if calls > int(config["maximum_api_calls"]):
                raise RuntimeError("frozen API call cap exceeded")
            results.append({**case, "model_decision": decision.to_dict(), "api_audit": audit, "action_executed": False})
            print(f"episode={case['episode_id']} decision={decision.selected_decision} status={audit['status']}", flush=True)
        summary = {
            "protocol": config["protocol"], "run_id": run_id, "source_git_commit": _git("rev-parse", "HEAD"),
            "source_manifest_id": config["source_manifest_id"], "model": policy.model, "cases": len(results),
            "api_calls": calls, "valid_cases": sum(row["api_audit"]["status"] == "valid" for row in results),
            "fail_closed_cases": sum(row["api_audit"]["status"] == "fail_closed" for row in results),
            "environment_steps": 0, "model_actions_executed": 0, "statistical_performance_claim_authorized": False,
        }
        _write_json(run_dir / "pilot_audit.json", {"summary": summary, "results": results})
        _write_json(run_dir / "summary.json", summary)
        print(f"run: {run_dir}")
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

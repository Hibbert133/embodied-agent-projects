"""Run the frozen GLM-5.2 shadow smoke without executing model decisions."""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_probemem_acr_utility_stability import _write_json  # noqa: E402
from src.probemem.acr_shadow_policy import AcrGlmShadowPolicy  # noqa: E402


def _git(*args: str) -> str:
    return subprocess.run(["git", "-c", f"safe.directory={ROOT.as_posix()}", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def build_shadow_evidence(row: dict[str, str], *, remaining_budget: int) -> dict[str, object]:
    """Allowlist causally available fields; never forward an evaluator CSV row."""
    return {
        "evidence_id": f"shadow_episode{int(row['episode_id']):03d}_realization{int(row['realization_index'])}",
        "episode_id": int(row["episode_id"]), "realization_index": int(row["realization_index"]),
        "first_intervention": "INDEPENDENT_STOCHASTIC_RETRY",
        "first_verification_status": row["first_verification_status"],
        "first_observed_progress": float(row["first_observed_progress"]),
        "first_final_object_goal_distance": float(row["first_final_object_goal_distance"]),
        "remaining_second_attempt_budget": int(remaining_budget),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/probemem_acr/glm_shadow_smoke_v1.json")
    parser.add_argument("--api-timeout", type=float, default=300.0)
    args = parser.parse_args()
    try:
        config = json.loads(args.config.resolve().read_text(encoding="utf-8"))
        with (ROOT / config["source_cases"]).open("r", encoding="utf-8", newline="") as handle:
            rows = sorted(csv.DictReader(handle), key=lambda row: (int(row["episode_id"]), int(row["realization_index"])))[:int(config["maximum_cases"])]
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"acr_glm_shadow_{stamp}_{_git('rev-parse', 'HEAD')[:12]}"
        run_dir = ROOT / "outputs/probemem_acr/glm_shadow_runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        policy = AcrGlmShadowPolicy(model=os.environ.get("LLM_MODEL", config["model"]), timeout_seconds=args.api_timeout)
        results = []
        calls = 0
        for row in rows:
            evidence = build_shadow_evidence(row, remaining_budget=int(config["remaining_second_attempt_budget"]))
            decision, audit = policy.decide(evidence, allow_repair=True)
            calls += len(audit["attempts"])
            if calls > int(config["maximum_api_calls"]):
                raise RuntimeError("frozen API call budget exceeded")
            results.append({"evidence": evidence, "decision": decision.to_dict(), "audit": audit, "action_executed": False})
            print(f"episode={evidence['episode_id']} realization={evidence['realization_index']} decision={decision.selected_decision} status={audit['status']}", flush=True)
        summary = {
            "protocol": config["protocol"], "run_id": run_id, "source_git_commit": _git("rev-parse", "HEAD"),
            "model": policy.model, "cases": len(results), "api_calls": calls,
            "valid_cases": sum(item["audit"]["status"] == "valid" for item in results),
            "fail_closed_cases": sum(item["audit"]["status"] == "fail_closed" for item in results),
            "environment_steps": 0, "model_actions_executed": 0, "performance_claim_authorized": False,
        }
        _write_json(run_dir / "shadow_audit.json", {"summary": summary, "results": results})
        _write_json(run_dir / "summary.json", summary)
        print(f"run: {run_dir}")
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

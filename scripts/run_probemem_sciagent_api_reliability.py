"""Run the non-executing SciAgent API Reliability v1.1 shadow gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from scripts.run_mixed_regime_tuning import MixedRegime  # noqa: E402
from scripts.run_probemem_v2_smoke import _probe_context, _read_jsonl  # noqa: E402
from src.probemem.compact_evidence import build_compact_causal_evidence  # noqa: E402
from src.probemem_sciagent.agent_orchestrator import SciAgentCallBudget  # noqa: E402
from src.probemem_sciagent.agent_payload import build_decision_payload  # noqa: E402
from src.probemem_sciagent.api_reliability import ApiReliabilityClient, build_health_check_payload, certify_payload  # noqa: E402
from src.probemem_sciagent.api_envelope import EnvelopeTolerantApiReliabilityClient  # noqa: E402
from src.probemem_sciagent.capability_contract import attach_capability_contract  # noqa: E402
from src.probemem_sciagent.memory_retrieval import ScientificMemorySnapshot  # noqa: E402
from src.probemem_sciagent.probe_value import attach_probe_value_contract  # noqa: E402
from src.reasoning import EvidenceSource, build_structured_evidence_state  # noqa: E402
from src.rollout import create_push_environment, create_push_policy, run_episode  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--manifest", type=Path, required=True); args = parser.parse_args()
    manifest = None; status_path = None
    try:
        manifest, config = _validate(args.manifest.resolve()); run = args.manifest.resolve().parent; status_path = run / "run_status.json"
        if status_path.exists(): raise FileExistsError("shadow run cannot overwrite or resume")
        if not os.environ.get("ANTHROPIC_API_KEY") or not os.environ.get("ANTHROPIC_BASE_URL"):
            _write(status_path, {"status": "BLOCKED_MISSING_GLM_CREDENTIALS", "fresh_seed_consumed": False, "initial_units": 0, "api_calls": 0})
            return 3
        api = config["api"]
        budget = SciAgentCallBudget(
            int(api["health_check_primary_calls"]) + int(api["case_primary_calls"]),
            int(api["maximum_schema_repairs"]), int(api["maximum_total_calls"]),
        )
        client_type = (
            EnvelopeTolerantApiReliabilityClient
            if api.get("response_envelope_mode") == "UNIQUE_CERTIFIED_OBJECT"
            else ApiReliabilityClient
        )
        client = client_type(
            model=str(api["model"]), timeout_seconds=float(api["timeout_seconds"]), max_tokens=int(api["max_tokens"]),
            call_budget=budget, maximum_consecutive_failures=int(api["maximum_consecutive_logical_failures"]),
        )
        empty = ScientificMemorySnapshot(1, (), (), (), ())
        health_payload = build_health_check_payload()
        if api.get("capability_contract_mode") == "PER_REQUEST_TOKENS_V1":
            health_payload = attach_capability_contract(
                health_payload, snapshot=empty,
                current_evidence_id="api_health_check_evidence",
            )
        health = client.certified_decide(
            health_payload, snapshot=empty, current_evidence_id="api_health_check_evidence",
        )
        health_valid = bool(
            health.valid and health.certified_decision is not None
            and health.certified_decision.decision.decision_mode == "ABSTAIN"
        )
        _write(run / "health_check.json", _result(health))
        if not health_valid:
            _write(status_path, {"status": "BLOCKED_API_HEALTH_CHECK", "fresh_seed_consumed": False, "initial_units": 0, "api_calls": budget.total_calls})
            return 4
        regimes = {row["regime_id"]: MixedRegime(row["regime_id"], tuple(row["bias"]), float(row["noise_std"])) for row in config["regimes"]}
        population = []; outputs = []; initial_units = operational = 0
        for unit in manifest["population_units"]:
            if operational >= int(config["target_operational_cases"]): break
            initial_units += 1; seed = int(unit["environment_seed"]); regime = regimes[unit["regime_id_oracle"]]
            trajectory = run / "initial_trajectories" / f"unit{int(unit['unit_id']):03d}_seed{seed}.jsonl"; trajectory.parent.mkdir(parents=True, exist_ok=True)
            env = create_push_environment(seed)
            try:
                initial = run_episode(
                    env, create_push_policy(), seed=seed, max_steps=int(config["budget"]["initial_max_steps"]),
                    perturbation=regime.build(), perturbation_seed=int(unit["initial_seed"]), agent_trajectory_path=trajectory,
                )
            finally: env.close()
            state = build_structured_evidence_state(_read_jsonl(trajectory), evidence_id=f"api_rel_unit{unit['unit_id']}_initial", source=EvidenceSource.FAILED_ROLLOUT, attempt_id=0)
            row = {"unit_id": unit["unit_id"], "seed": seed, "regime_id_oracle": unit["regime_id_oracle"], "decision_required": state.decision_required}
            if not state.decision_required: population.append(row); _flush(run, population, outputs, client); continue
            mandatory = _probe_context(regime, seed, {"registered_probe": config["mandatory_probe"]}, int(unit["mandatory_probe_seed"]))
            if int(mandatory["probe_environment_steps"]) > int(config["budget"]["mandatory_probe_max_steps"]): raise RuntimeError("mandatory probe exceeded budget")
            operational += 1; episode_id = operational
            evidence = {
                "evidence_id": f"api_reliability_episode{episode_id:03d}", "episode_id": episode_id,
                "initial_evidence": {**state.to_dict(), "episode_id": episode_id, "evidence_id": f"api_reliability_episode{episode_id:03d}_initial"},
                "registered_probe_evidence": mandatory, "remaining_verification_budget": 500,
            }
            compact = build_compact_causal_evidence(evidence)
            base = build_decision_payload(
                evidence=compact.to_dict(), memory=empty,
                remaining_budget={"micro_probe_steps": 192, "verification_steps": 500}, stage="PRE_PROBE",
            )
            request_payload = certify_payload(base)
            if api.get("capability_contract_mode") == "PER_REQUEST_TOKENS_V1":
                request_payload = attach_capability_contract(
                    request_payload, snapshot=empty,
                    current_evidence_id=compact.evidence_id,
                )
            if api.get("probe_value_contract_mode") == "EXPECTED_VALUE_OF_SAMPLE_INFORMATION_V1":
                request_payload = attach_probe_value_contract(request_payload)
            result = client.certified_decide(request_payload, snapshot=empty, current_evidence_id=compact.evidence_id)
            assessment = next(
                (row.get("probe_value_assessment") for row in reversed(client.audit)
                 if row.get("probe_value_contract_applied")), None,
            )
            outputs.append({"episode_id": episode_id, "seed": seed, **_result(result), "probe_value_assessment": assessment, "shadow_only": True, "action_executed": False, "memory_written": False})
            population.append(row); _flush(run, population, outputs, client)
        valid = sum(bool(row["valid"]) for row in outputs); repairs = budget.repair_calls
        gate = config["success_gate"]
        value_assessments = [row["probe_value_assessment"] for row in outputs if row.get("probe_value_assessment") is not None]
        probe_admitted = sum(bool(row["admitted"]) for row in value_assessments)
        probe_rejected = len(value_assessments) - probe_admitted
        probe_admission_rate = probe_admitted / operational if operational else 0.0
        passed = (
            operational >= int(config["minimum_operational_cases"])
            and valid >= int(gate["minimum_certified_valid_outputs"])
            and (valid / operational if operational else 0.0) >= float(gate["minimum_grounded_output_rate"])
            and operational - valid <= int(gate["maximum_fail_closed_outputs"])
            and repairs <= int(gate["maximum_repairs"])
            and len(value_assessments) >= int(gate.get("minimum_probe_value_valid_outputs", 0))
            and probe_admission_rate <= float(gate.get("maximum_probe_admission_rate", 1.0))
            and probe_rejected >= int(gate.get("minimum_probe_rejections", 0))
        )
        summary = {
            "status": "COMPLETED_GATE_PASSED" if passed else "COMPLETED_GATE_FAILED",
            "experiment_run_id": manifest["experiment_run_id"], "manifest_id": manifest["manifest_id"],
            "initial_units": initial_units, "operational_cases": operational, "health_check_valid": health_valid,
            "certified_valid_outputs": valid, "grounded_output_rate": 0.0 if not operational else valid / operational,
            "fail_closed_outputs": operational - valid, "repairs": repairs, "api_calls": budget.total_calls,
            "cache_hits": sum(bool(row.get("cache_hit")) for row in outputs), "circuit_open": client.circuit_open,
            "bare_json_calls": sum(row.get("extraction_mode") == "BARE_JSON" for row in client.audit),
            "wrapped_unique_json_calls": sum(row.get("extraction_mode") == "WRAPPED_UNIQUE_JSON" for row in client.audit),
            "capability_valid_calls": sum(row.get("valid_capability_contract") is True for row in client.audit),
            "capability_invalid_calls": sum(row.get("capability_contract_applied") and row.get("valid_capability_contract") is False for row in client.audit),
            "probe_value_valid_outputs": len(value_assessments),
            "probe_value_invalid_calls": sum(row.get("probe_value_contract_applied") and row.get("valid_probe_value_certificate") is False for row in client.audit),
            "probe_admitted_count": probe_admitted, "probe_rejected_count": probe_rejected,
            "probe_admission_rate": probe_admission_rate,
            "action_execution_count": 0, "memory_write_count": 0, "principle_update_count": 0,
            "integrity_violations": 0,
            "claim_boundary": config["claim_boundary"],
        }
        _write(run / "summary.json", summary); _write(status_path, summary); return 0 if passed else 2
    except Exception as exc:
        if status_path is not None: _write(status_path, {"status": "FAILED", "error_type": type(exc).__name__, "error": str(exc)})
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr); return 1


def _result(result):
    return {
        "valid": result.valid, "repaired": result.repaired, "cache_hit": result.cache_hit,
        "request_hash": result.request_hash, "error": result.error,
        "certified_decision": None if result.certified_decision is None else result.certified_decision.to_dict(),
        "fail_closed_decision": result.fail_closed_decision.to_dict(),
    }


def _flush(run: Path, population: list, outputs: list, client: ApiReliabilityClient):
    _write(run / "population.json", population); _write(run / "certified_shadow_outputs.json", outputs); _write(run / "api_audit.json", client.audit)


def _validate(path: Path):
    if _git("status", "--porcelain"): raise RuntimeError("shadow execution requires a clean worktree")
    manifest = json.loads(path.read_text(encoding="utf-8")); config_path = ROOT / manifest["config_path"]
    config = json.loads(config_path.read_text(encoding="utf-8")); head = _git("rev-parse", "HEAD"); source = manifest["source_git_commit"]
    if hashlib.sha256(config_path.read_bytes()).hexdigest() != manifest["config_sha256"]: raise RuntimeError("config hash mismatch")
    canonical = dict(manifest); recorded_id = canonical.pop("manifest_id")
    if hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest() != recorded_id: raise RuntimeError("manifest ID mismatch")
    ancestry = subprocess.run(["git", "-c", f"safe.directory={ROOT.as_posix()}", "merge-base", "--is-ancestor", source, head], cwd=ROOT)
    if ancestry.returncode != 0: raise RuntimeError("manifest source is not an ancestor of HEAD")
    if source != head:
        changed = set(_git("diff", "--name-only", source, head).splitlines()); allowed = {path.relative_to(ROOT).as_posix()}
        if changed - allowed: raise RuntimeError(f"tracked changes after source commit: {sorted(changed - allowed)}")
    for relative, expected in {**manifest["implementation_sha256"], **manifest["input_sha256"]}.items():
        file = ROOT / relative
        if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != expected: raise RuntimeError(f"manifest-bound file changed: {relative}")
    return manifest, config


def _write(path: Path, value: Any):
    path.parent.mkdir(parents=True, exist_ok=True); temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"); temporary.replace(path)
def _git(*args: str): return subprocess.run(["git", "-c", f"safe.directory={ROOT.as_posix()}", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
if __name__ == "__main__": raise SystemExit(main())

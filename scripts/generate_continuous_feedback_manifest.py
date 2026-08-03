"""Generate immutable manifest for prospective continuous-feedback development."""

from __future__ import annotations

import hashlib, json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from scripts.run_probemem_v2_smoke import _seed  # noqa: E402

CONFIG_PATH = Path("configs/probemem_acr/continuous_feedback_development_v1.json")
IMPLEMENTATION_PATHS = tuple(map(Path, (
    "scripts/check_continuous_feedback_seeds.py", "scripts/generate_continuous_feedback_manifest.py",
    "scripts/run_continuous_feedback_development.py", "scripts/analyze_continuous_feedback_development.py",
    "scripts/run_probemem_acr_utility_stability.py", "scripts/run_probemem_v2_smoke.py",
    "src/probemem/continuous_feedback_policy.py", "src/probemem/resonance_policy.py",
    "src/reasoning/structured_evidence.py", "src/rollout/engine.py")))
INPUT_PATHS = tuple(map(Path, ("configs/autoresearch/default_recovery_config.json", "outputs/autoresearch/noise_calibration/selected.json", "docs/protocols/seed_registry.json")))

def _git(*args: str) -> str:
    return subprocess.run(["git", "-c", f"safe.directory={ROOT.as_posix()}", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
def _sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def _hash(value: Any) -> str: return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def build_units(config: dict[str, Any]) -> list[dict[str, Any]]:
    start, end = config["seed_partitions"]["development"]; ns = config["random_namespaces"]
    return [{"episode_id": i, "environment_seed": seed, "condition_id_oracle": "fault_05",
             "initial_perturbation_seed": _seed(seed, ns["initial_perturbation"]),
             "diagnostic_probe_seed": _seed(seed, ns["registered_probe"]),
             "first_verification_seed": _seed(seed, ns["first_verification"]),
             "paired_second_verification_seed": _seed(seed, ns["paired_second_verification"])}
            for i, seed in enumerate(range(start, end + 1), 1)]

def main() -> int:
    try:
        if _git("status", "--porcelain"): raise RuntimeError("manifest requires clean worktree")
        subprocess.run([sys.executable, str(ROOT / "scripts/check_continuous_feedback_seeds.py")], cwd=ROOT, check=True)
        config = json.loads((ROOT / CONFIG_PATH).read_text(encoding="utf-8")); units = build_units(config)
        if len(units) != config["population"]["maximum_initial_units"]: raise ValueError("population mismatch")
        if {u["environment_seed"] for u in units} & (set(range(3100, 3200)) | set(range(3800, 3900))): raise ValueError("reserved seed present")
        commit = _git("rev-parse", "HEAD"); stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"acr_continuous_feedback_{stamp}_{commit[:12]}"
        manifest: dict[str, Any] = {"schema_version": 1, "experiment_run_id": run_id, "source_git_commit": commit,
            "created_at_utc": stamp, "config_path": CONFIG_PATH.as_posix(), "config_sha256": _sha(ROOT / CONFIG_PATH),
            "implementation_sha256": {p.as_posix(): _sha(ROOT / p) for p in IMPLEMENTATION_PATHS},
            "input_sha256": {p.as_posix(): _sha(ROOT / p) for p in INPUT_PATHS}, "population_units": units,
            "continuous_rule_hash": _hash(config["continuous_rule"]), "promotion_gate_hash": _hash(config["promotion_gate"]), "claim_scope": config["claim_scope"]}
        manifest["manifest_id"] = _hash(manifest)
        run_dir = ROOT / "outputs/probemem_acr/continuous_feedback_runs" / run_id; run_dir.mkdir(parents=True, exist_ok=False)
        (run_dir / "immutable_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"manifest_id: {manifest['manifest_id']}\nexperiment_run_id: {run_id}\nmanifest: {run_dir / 'immutable_manifest.json'}"); return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr); return 1
if __name__ == "__main__": raise SystemExit(main())

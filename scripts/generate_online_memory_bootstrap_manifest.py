"""Generate the immutable ProbeMem-Online Gate-B bootstrap manifest."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_probemem_v2_smoke import _seed  # noqa: E402


CONFIG = Path("configs/probemem_online/bootstrap_memory_v1.json")
IMPLEMENTATION = (
    Path("scripts/generate_online_memory_bootstrap_manifest.py"),
    Path("scripts/build_regime_memory_bootstrap.py"),
    Path("src/probemem/regime_memory.py"),
    Path("src/probemem/memory_tools.py"),
    Path("src/probemem/memory_resonance.py"),
    Path("scripts/run_probemem_v2_smoke.py"),
    Path("src/rollout/engine.py"),
)
INPUTS = (
    Path("configs/autoresearch/default_recovery_config.json"),
    Path("outputs/autoresearch/noise_calibration/selected.json"),
    Path("configs/probemem_online/seed_registry_v1.json"),
    Path("outputs/probemem_online/interface_ablation_runs/probemem_online_interface_ablation_20260803T072817Z_1c19c23bafb3/analysis_summary.json"),
)


def _git(*args: str) -> str:
    return subprocess.run(["git", "-c", f"safe.directory={ROOT.as_posix()}", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def build_units(config: dict[str, Any]) -> list[dict[str, Any]]:
    start, stop = map(int, config["seed_range"])
    assignments = (
        ("fault_01", "BOUNDED_PLANAR_COMPENSATION"),
        ("fault_01", "INDEPENDENT_STOCHASTIC_RETRY"),
        ("fault_05", "BOUNDED_PLANAR_COMPENSATION"),
        ("fault_05", "INDEPENDENT_STOCHASTIC_RETRY"),
    )
    namespaces = config["random_namespaces"]
    return [
        {
            "unit_id": index + 1,
            "environment_seed": seed,
            "condition_id_oracle": assignments[(seed - start) % 4][0],
            "selected_skill": assignments[(seed - start) % 4][1],
            "initial_perturbation_seed": _seed(seed, int(namespaces["initial_perturbation"])),
            "diagnostic_probe_seed": _seed(seed, int(namespaces["registered_probe"])),
            "selected_verification_seed": _seed(seed, int(namespaces["selected_verification"])),
        }
        for index, seed in enumerate(range(start, stop + 1))
    ]


def main() -> int:
    try:
        if _git("status", "--porcelain"):
            raise RuntimeError("bootstrap manifest requires a clean worktree")
        config = json.loads((ROOT / CONFIG).read_text(encoding="utf-8"))
        gate = json.loads((ROOT / INPUTS[-1]).read_text(encoding="utf-8"))
        if not gate["gate_b_authorized"]:
            raise RuntimeError("Gate A did not authorize Gate B")
        units = build_units(config)
        if len(units) != 100:
            raise ValueError("bootstrap queue must contain exactly 100 assigned units")
        commit = _git("rev-parse", "HEAD")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"probemem_online_bootstrap_{stamp}_{commit[:12]}"
        manifest = {
            "schema_version": 1, "experiment_run_id": run_id, "source_git_commit": commit,
            "created_at_utc": stamp, "config_path": CONFIG.as_posix(), "config_sha256": _sha(ROOT / CONFIG),
            "implementation_sha256": {path.as_posix(): _sha(ROOT / path) for path in IMPLEMENTATION},
            "input_sha256": {path.as_posix(): _sha(ROOT / path) for path in INPUTS},
            "candidate_units": units,
            "assignment_hash": _hash({"assignment": config["assignment"], "units": units}),
        }
        manifest["manifest_id"] = _hash(manifest)
        run_dir = ROOT / "outputs/probemem_online/bootstrap_runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        (run_dir / "immutable_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"manifest: {run_dir / 'immutable_manifest.json'}")
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

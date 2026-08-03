"""Generate an immutable manifest for ProbeMem-Online Gate C."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_probemem_v2_smoke import _seed  # noqa: E402


CONFIG = Path("configs/probemem_online/sequential_development_v1.json")
IMPLEMENTATION = (
    Path("scripts/generate_online_memory_manifest.py"),
    Path("src/probemem/compact_evidence.py"),
    Path("src/probemem/regime_memory.py"),
    Path("src/probemem/memory_tools.py"),
    Path("src/probemem/memory_resonance.py"),
    Path("src/probemem/online_memory_policy.py"),
    Path("src/probemem/persistent_regime.py"),
    Path("src/perturbations.py"),
)


def build_units(config: dict[str, Any]) -> list[dict[str, Any]]:
    namespaces = config["random_namespaces"]
    units: list[dict[str, Any]] = []
    unit_id = 0
    for segment in config["segments"]:
        start, stop = map(int, segment["seed_range"])
        cycle = tuple(str(item) for item in segment["regime_cycle"])
        for offset, seed in enumerate(range(start, stop + 1)):
            unit_id += 1
            regime = cycle[offset % len(cycle)]
            units.append({
                "unit_id": unit_id,
                "environment_seed": seed,
                "segment_id_oracle": str(segment["segment_id"]),
                "regime_id_oracle": regime,
                "initial_perturbation_seed": _seed(seed, int(namespaces["initial_perturbation"])),
                "diagnostic_probe_seed": _seed(seed, int(namespaces["registered_probe"])),
                "paired_verification_seed": _seed(seed, int(namespaces["method_verification_base"])),
            })
    if len(units) != 200 or len({row["environment_seed"] for row in units}) != 200:
        raise ValueError("Gate C manifest requires exactly 200 unique preregistered seeds")
    return units


def main() -> int:
    try:
        if _git("status", "--porcelain"):
            raise RuntimeError("Gate C manifest requires a clean worktree")
        config = json.loads((ROOT / CONFIG).read_text(encoding="utf-8"))
        commit = _git("rev-parse", "HEAD")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"probemem_online_gate_c_{stamp}_{commit[:12]}"
        input_paths = (
            Path(config["memory"]["bootstrap_snapshot"]),
            Path(config["memory"]["bootstrap_records"]),
            Path(config["recovery_policy_config"]),
            Path("configs/probemem_online/seed_registry_v1.json"),
        )
        manifest = {
            "schema_version": 1,
            "experiment_run_id": run_id,
            "created_at_utc": stamp,
            "source_git_commit": commit,
            "config_path": CONFIG.as_posix(),
            "config_sha256": _sha(ROOT / CONFIG),
            "implementation_sha256": {path.as_posix(): _sha(ROOT / path) for path in IMPLEMENTATION},
            "input_sha256": {path.as_posix(): _sha(ROOT / path) for path in input_paths},
            "population_units": build_units(config),
        }
        manifest["manifest_id"] = _hash(manifest)
        output = ROOT / "outputs/probemem_online/sequential_runs" / run_id
        output.mkdir(parents=True, exist_ok=False)
        path = output / "immutable_manifest.json"
        path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"manifest: {path}")
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", *args],
        cwd=ROOT, check=True, capture_output=True, text=True,
    ).stdout.strip()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())

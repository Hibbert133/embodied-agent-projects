"""Generate the immutable ProbeMem verifier Demo manifest."""

from __future__ import annotations

import argparse
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


DEFAULT_CONFIG = Path("configs/probemem_verifier/demo_v1.json")
IMPLEMENTATION = (
    Path("scripts/generate_probemem_verifier_manifest.py"),
    Path("scripts/run_probemem_verifier_demo.py"),
    Path("scripts/analyze_probemem_verifier_demo.py"),
    Path("scripts/render_probemem_verifier_demo.py"),
    Path("src/probemem_verifier/admission.py"),
    Path("src/probemem_verifier/candidate_verifier.py"),
    Path("src/probemem_verifier/glm_verifier.py"),
    Path("src/probemem_verifier/override_guard.py"),
    Path("src/probemem_verifier/online_policy.py"),
    Path("src/probemem_verifier/schemas.py"),
    Path("src/probemem/regime_memory.py"),
    Path("src/probemem/compact_evidence.py"),
    Path("src/probemem/persistent_regime.py"),
    Path("src/probe/directional.py"),
)


def build_units(config: dict[str, Any]) -> list[dict[str, Any]]:
    start, stop = map(int, config["seed_range"])
    cycle = tuple(str(item) for item in config["regime_cycle"])
    namespaces = config["random_namespaces"]
    units = []
    for index, seed in enumerate(range(start, stop + 1)):
        units.append({
            "unit_id": index + 1,
            "environment_seed": seed,
            "regime_id_oracle": cycle[index % len(cycle)],
            "initial_perturbation_seed": _seed(seed, int(namespaces["initial_perturbation"])),
            "diagnostic_probe_seed": _seed(seed, int(namespaces["registered_probe"])),
            "paired_verification_seed": _seed(seed, int(namespaces["paired_verification"])),
        })
    if len(units) != 50 or [row["environment_seed"] for row in units] != list(range(4700, 4750)):
        raise ValueError("verifier Demo manifest requires exactly seeds 4700--4749")
    if any(len({row["initial_perturbation_seed"], row["diagnostic_probe_seed"], row["paired_verification_seed"]}) != 3 for row in units):
        raise ValueError("verifier Demo random namespaces overlap")
    return units


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    try:
        config_path = args.config.resolve()
        if _git("status", "--porcelain"):
            raise RuntimeError("verifier Demo manifest requires a clean worktree")
        config = json.loads(config_path.read_text(encoding="utf-8"))
        if config["status"] != "DEMO_FROZEN_BEFORE_EXECUTION" or config["verifier_mode"] != "deterministic":
            raise RuntimeError("unexpected verifier Demo protocol state")
        commit = _git("rev-parse", "HEAD")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"probemem_verifier_demo_{stamp}_{commit[:12]}"
        config_relative = config_path.relative_to(ROOT)
        inputs = (
            Path(config["memory"]["bootstrap_records"]),
            Path(config["recovery_policy_config"]),
            Path(config["seed_registry"]),
            Path("docs/protocols/probemem_verifier_demo_v1.md"),
        )
        manifest = {
            "schema_version": 1,
            "experiment_run_id": run_id,
            "created_at_utc": stamp,
            "source_git_commit": commit,
            "config_path": config_relative.as_posix(),
            "config_sha256": _sha(config_path),
            "implementation_sha256": {path.as_posix(): _sha(ROOT / path) for path in IMPLEMENTATION},
            "input_sha256": {path.as_posix(): _sha(ROOT / path) for path in inputs},
            "population_units": build_units(config),
        }
        manifest["manifest_id"] = _hash(manifest)
        output = ROOT / "outputs/probemem_verifier_demo/runs" / run_id
        output.mkdir(parents=True, exist_ok=False)
        manifest_path = output / "immutable_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"manifest: {manifest_path}")
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", *args], cwd=ROOT,
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())

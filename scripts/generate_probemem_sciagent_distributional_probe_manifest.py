"""Generate the immutable SciAgent distributional probe-identifiability manifest."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.run_probemem_v2_smoke import _seed  # noqa: E402


DEFAULT_CONFIG = ROOT / "configs/probemem_sciagent/distributional_probe_identifiability_v1_8.json"


def build_units(config: dict[str, Any]) -> list[dict[str, Any]]:
    start, stop = map(int, config["seed_range"])
    cycle = tuple(config["regime_cycle"])
    ns = config["random_namespaces"]
    units = []
    for index, seed in enumerate(range(start, stop + 1)):
        units.append({
            "unit_id": index + 1,
            "environment_seed": seed,
            "regime_id_oracle": cycle[index % len(cycle)],
            "initial_seed": _seed(seed, int(ns["initial"])),
            "mandatory_probe_seed": _seed(seed, int(ns["mandatory_probe"])),
            "compensation_probe_seed": _seed(seed, int(ns["compensation_probe"])),
            "retry_probe_seeds": [
                _seed(seed, int(ns["retry_probe_base"]) + trial) for trial in range(3)
            ],
            "verification_seeds": [
                _seed(seed, int(ns["verification_base"]) + realization)
                for realization in range(int(config["verification_realizations_per_skill"]))
            ],
        })
    if (start, stop) != (6950, 7099) or len(units) != 150:
        raise ValueError("v1.8 requires exactly seeds 6950--7099")
    for unit in units:
        ids = [
            unit["initial_seed"], unit["mandatory_probe_seed"], unit["compensation_probe_seed"],
            *unit["retry_probe_seeds"], *unit["verification_seeds"],
        ]
        if len(ids) != len(set(ids)):
            raise ValueError("random namespaces overlap")
    return units


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    try:
        config_path = args.config.resolve()
        if _git("status", "--porcelain"):
            raise RuntimeError("manifest requires a clean worktree")
        config = json.loads(config_path.read_text(encoding="utf-8"))
        if config["status"] != "DEVELOPMENT_FROZEN_BEFORE_EXECUTION":
            raise ValueError("protocol is not frozen")
        commit = _git("rev-parse", "HEAD")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"probemem_sciagent_probe_identifiability_{stamp}_{commit[:12]}"
        implementation = [
            ROOT / "src/probemem_sciagent/probe_identifiability.py",
            ROOT / "src/probemem_sciagent/compensation_probe.py",
            ROOT / "src/probemem_sciagent/retry_probe.py",
            ROOT / "src/probemem_sciagent/probe_registry.py",
            ROOT / "scripts/generate_probemem_sciagent_distributional_probe_manifest.py",
            ROOT / "scripts/run_probemem_sciagent_distributional_probe_identifiability.py",
        ]
        inputs = [
            config_path, ROOT / config["seed_registry"], ROOT / config["recovery_policy_config"],
            ROOT / "docs/protocols/probemem_sciagent_distributional_probe_identifiability_v1_8.md",
        ]
        manifest = {
            "schema_version": 1, "experiment_run_id": run_id, "created_at_utc": stamp,
            "source_git_commit": commit, "config_path": config_path.relative_to(ROOT).as_posix(),
            "config_sha256": _sha(config_path),
            "implementation_sha256": {path.relative_to(ROOT).as_posix(): _sha(path) for path in implementation},
            "input_sha256": {path.relative_to(ROOT).as_posix(): _sha(path) for path in inputs},
            "population_units": build_units(config),
        }
        manifest["manifest_id"] = _hash(manifest)
        output = ROOT / config["output_root"] / run_id
        output.mkdir(parents=True, exist_ok=False)
        (output / "immutable_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"manifest: {output / 'immutable_manifest.json'}")
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

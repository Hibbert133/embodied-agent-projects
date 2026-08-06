"""Generate an immutable ProbeMem-SciAgent Demo manifest."""

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
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from scripts.run_probemem_v2_smoke import _seed  # noqa: E402


DEFAULT_CONFIG = ROOT / "configs/probemem_sciagent/demo_v1.json"


def build_units(config: dict[str, Any]) -> list[dict[str, Any]]:
    start, stop = map(int, config["seed_range"])
    cycle = tuple(config["regime_cycle"])
    ns = config["random_namespaces"]
    units = []
    for index, seed in enumerate(range(start, stop + 1)):
        retry_seeds = [_seed(seed, int(ns["retry_probe_base"]) + trial) for trial in range(3)]
        row = {
            "unit_id": index + 1, "environment_seed": seed,
            "regime_id_oracle": cycle[index % len(cycle)],
            "initial_seed": _seed(seed, int(ns["initial"])),
            "mandatory_probe_seed": _seed(seed, int(ns["mandatory_probe"])),
            "compensation_probe_seed": _seed(seed, int(ns["compensation_probe"])),
            "retry_probe_seeds": retry_seeds,
            "paired_verification_seed": _seed(seed, int(ns["paired_verification"])),
        }
        if len(set((row["initial_seed"], row["mandatory_probe_seed"], row["compensation_probe_seed"], *retry_seeds, row["paired_verification_seed"]))) != 7:
            raise ValueError("SciAgent random namespaces overlap")
        units.append(row)
    if (start, stop) != (5300, 5349) or len(units) != 50:
        raise ValueError("SciAgent Demo requires exactly seeds 5300--5349")
    return units


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    try:
        config_path = args.config.resolve()
        if _git("status", "--porcelain"):
            raise RuntimeError("SciAgent manifest requires a clean committed worktree")
        config = json.loads(config_path.read_text(encoding="utf-8"))
        if config.get("status") != "DEMO_FROZEN_BEFORE_EXECUTION":
            raise ValueError("SciAgent Demo config is not frozen")
        commit = _git("rev-parse", "HEAD")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"probemem_sciagent_demo_{stamp}_{commit[:12]}"
        implementation = [
            path for path in sorted((ROOT / "src/probemem_sciagent").glob("*.py"))
        ] + [
            ROOT / "scripts/generate_probemem_sciagent_manifest.py",
            ROOT / "scripts/run_probemem_sciagent_demo.py",
            ROOT / "scripts/analyze_probemem_sciagent.py",
            ROOT / "scripts/render_probemem_sciagent.py",
            ROOT / "scripts/run_probemem_sciagent_synthetic_audit.py",
        ]
        inputs = [
            config_path, ROOT / config["seed_registry"], ROOT / config["recovery_policy_config"],
            ROOT / "docs/protocols/probemem_sciagent_v1.md",
        ]
        manifest = {
            "schema_version": 1, "experiment_run_id": run_id,
            "created_at_utc": stamp, "source_git_commit": commit,
            "config_path": config_path.relative_to(ROOT).as_posix(),
            "config_sha256": _sha(config_path),
            "implementation_sha256": {path.relative_to(ROOT).as_posix(): _sha(path) for path in implementation},
            "input_sha256": {path.relative_to(ROOT).as_posix(): _sha(path) for path in inputs},
            "population_units": build_units(config),
        }
        manifest["manifest_id"] = _hash(manifest)
        output = ROOT / config["output_root"] / run_id
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
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", *args], cwd=ROOT,
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def _sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def _hash(value: Any) -> str: return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


if __name__ == "__main__": raise SystemExit(main())

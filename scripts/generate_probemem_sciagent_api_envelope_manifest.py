"""Generate the immutable SciAgent API Envelope v1.2 shadow manifest."""

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


DEFAULT_CONFIG = ROOT / "configs/probemem_sciagent/api_reliability_v1_2.json"


def build_units(config: dict[str, Any]) -> list[dict[str, Any]]:
    start, stop = map(int, config["seed_range"])
    cycle = tuple(config["regime_cycle"])
    namespaces = config["random_namespaces"]
    units = [{
        "unit_id": index + 1,
        "environment_seed": seed,
        "regime_id_oracle": cycle[index % len(cycle)],
        "initial_seed": _seed(seed, int(namespaces["initial"])),
        "mandatory_probe_seed": _seed(seed, int(namespaces["mandatory_probe"])),
    } for index, seed in enumerate(range(start, stop + 1))]
    if (start, stop) != (6000, 6049) or len(units) != 50:
        raise ValueError("API Envelope v1.2 requires seeds 6000--6049")
    if any(row["initial_seed"] == row["mandatory_probe_seed"] for row in units):
        raise ValueError("random namespaces overlap")
    return units


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    try:
        config_path = args.config.resolve()
        if _git("status", "--porcelain"):
            raise RuntimeError("manifest requires a completely clean worktree")
        config = json.loads(config_path.read_text(encoding="utf-8"))
        if config["status"] != "SHADOW_FROZEN_BEFORE_EXECUTION":
            raise ValueError("shadow protocol is not frozen")
        commit = _git("rev-parse", "HEAD")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"probemem_sciagent_api_envelope_{stamp}_{commit[:12]}"
        implementation = [
            ROOT / "src/probemem_sciagent/api_reliability.py",
            ROOT / "src/probemem_sciagent/api_envelope.py",
            ROOT / "src/probemem_sciagent/certified_decision.py",
            ROOT / "src/probemem_sciagent/agent_orchestrator.py",
            ROOT / "src/probemem_sciagent/agent_payload.py",
            ROOT / "src/probemem_sciagent/decision_validator.py",
            ROOT / "scripts/generate_probemem_sciagent_api_envelope_manifest.py",
            ROOT / "scripts/run_probemem_sciagent_api_reliability.py",
            ROOT / "scripts/analyze_probemem_sciagent_api_reliability.py",
        ]
        inputs = [
            config_path,
            ROOT / config["seed_registry"],
            ROOT / "docs/protocols/probemem_sciagent_api_envelope_v1_2.md",
        ]
        manifest = {
            "schema_version": 1,
            "experiment_run_id": run_id,
            "created_at_utc": stamp,
            "source_git_commit": commit,
            "config_path": config_path.relative_to(ROOT).as_posix(),
            "config_sha256": _sha(config_path),
            "implementation_sha256": {
                path.relative_to(ROOT).as_posix(): _sha(path) for path in implementation
            },
            "input_sha256": {
                path.relative_to(ROOT).as_posix(): _sha(path) for path in inputs
            },
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
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", *args],
        cwd=ROOT, check=True, capture_output=True, text=True,
    ).stdout.strip()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())

"""Generate an immutable manifest for ProbeMem additional experiments v1."""

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


DEFAULT_CONFIG = Path("configs/probemem_additional/ablation_development_v1.json")
IMPLEMENTATION = (
    Path("src/probemem/additional_experiments.py"),
    Path("scripts/generate_probemem_additional_manifest.py"),
    Path("scripts/run_probemem_additional_ablation.py"),
    Path("scripts/analyze_probemem_additional_ablation.py"),
    Path("scripts/render_probemem_additional_ablation.py"),
    Path("src/planner/evidence_grounded.py"),
    Path("src/reasoning/structured_evidence.py"),
    Path("src/probe/directional.py"),
)


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", *args], cwd=ROOT,
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def _tracked_dirty() -> bool:
    return bool(_git("diff", "--name-only") or _git("diff", "--cached", "--name-only"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def build_units(config: dict[str, Any]) -> list[dict[str, Any]]:
    start, stop = map(int, config["seed_range"])
    cycle = tuple(config["condition_cycle"])
    namespaces = config["random_namespaces"]
    realizations = int(config["budget"]["verification_realizations_per_action"])
    units = []
    for index, seed in enumerate(range(start, stop + 1)):
        unit = {
            "unit_id": index + 1,
            "environment_seed": seed,
            "condition_id_oracle": cycle[index % len(cycle)],
            "initial_perturbation_seed": _seed(seed, int(namespaces["initial_perturbation"])),
            "probe_seed": _seed(seed, int(namespaces["registered_probe"])),
            "verification_seeds": [
                _seed(seed, int(namespaces["verification_base"]) + realization)
                for realization in range(realizations)
            ],
        }
        if len({unit["initial_perturbation_seed"], unit["probe_seed"], *unit["verification_seeds"]}) != 2 + realizations:
            raise ValueError("random namespaces overlap within a population unit")
        units.append(unit)
    if len(units) != int(config["maximum_initial_units"]):
        raise ValueError("manifest population length differs from frozen maximum")
    if [row["environment_seed"] for row in units] != list(range(7200, 7400)):
        raise ValueError("additional experiment requires exactly seeds 7200--7399")
    return units


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    try:
        if _tracked_dirty():
            raise RuntimeError("manifest generation requires no tracked changes")
        config_path = args.config.resolve()
        config = json.loads(config_path.read_text(encoding="utf-8"))
        if config["status"] != "DEVELOPMENT_FROZEN_BEFORE_EXECUTION":
            raise RuntimeError("unexpected protocol state")
        if config["verifier"]["mode"] != "deterministic" or not config["prohibitions"]["glm_calls"]:
            raise RuntimeError("registered run must prohibit GLM calls")
        commit = _git("rev-parse", "HEAD")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"probemem_additional_ablation_{stamp}_{commit[:12]}"
        inputs = (
            Path(config["seed_registry"]), Path(config["recovery_policy_config"]),
            Path(config["passive_tuning_cases"]), Path(config["noise_selection"]),
            Path("docs/protocols/probemem_additional_experiments_v1.md"),
        )
        manifest = {
            "schema_version": 1, "experiment_run_id": run_id,
            "created_at_utc": stamp, "source_git_commit": commit,
            "config_path": config_path.relative_to(ROOT).as_posix(),
            "config_sha256": _sha(config_path),
            "implementation_sha256": {path.as_posix(): _sha(ROOT / path) for path in IMPLEMENTATION},
            "input_sha256": {path.as_posix(): _sha(ROOT / path) for path in inputs},
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


if __name__ == "__main__":
    raise SystemExit(main())

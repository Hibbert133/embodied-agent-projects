"""Independent production-input replay and sampled production-feature verification.

No environment creation. This verifier checks all actuator noise arithmetic and
six evenly spaced causal prediction queries per recorded episode. It does not
claim to independently recompute every aggregate or every prediction.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from scripts import analyze_input_model_error as candidate
from src.operator_perturbations_v1 import AffineNoisePerturbation
from src.probe.forward_prediction import ForwardQuery, design, features


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(manifest, diagnostic):
    m = json.loads(manifest.read_text(encoding="utf-8"))
    d = json.loads(diagnostic.read_text(encoding="utf-8"))
    if any(m[k] != d[k] for k in candidate.IDENTITY) or d["analysis_source_sha256"] != digest(ROOT / "scripts/analyze_input_model_error.py"):
        raise ValueError("diagnostic/source identity changed")
    for name, sha in d["source_artifact_sha256"].items():
        if digest(manifest.parent / name) != sha:
            raise ValueError("original source changed")
    model_path = ROOT / m["config"]["forward_model_path"]
    if digest(model_path) != d["forward_bank_sha256"]:
        raise ValueError("nominal bank changed")
    models = json.loads(model_path.read_text(encoding="utf-8"))["models"]
    indexed = {(r["episode_index"], r["predictor"], r["phase"]): r for r in d["episode_metrics"]}
    episodes = steps = sampled_queries = checked_phase_counts = 0
    for method in candidate.METHODS:
        with gzip.open(manifest.parent / ("episodes_" + method + ".jsonl.gz"), "rt", encoding="utf-8") as handle:
            for line in handle:
                record = json.loads(line)
                operator = next(o for o in m["config"]["operators_oracle"] if o["id"] == record["operator_oracle"])
                seed = int(np.random.SeedSequence([record["seed"], m["config"]["tasks"].index(record["task"]),
                           next(i for i,o in enumerate(m["config"]["operators_oracle"]) if o["id"] == record["operator_oracle"]), 0xF091]).generate_state(1)[0])
                injector = AffineNoisePerturbation(operator["matrix_xy"], operator["bias_xy"], m["config"]["noise_std"])
                injector.reset(seed)
                mean, actual = candidate.reconstruct_inputs(record, operator, m["config"]["noise_std"])
                for index, row in enumerate(record["trace"]):
                    original = np.clip(injector.apply(np.array(row["command"], dtype=np.float32)), -1, 1)
                    if not np.array_equal(original, actual[index]):
                        raise ValueError("input reconstruction differs from original executor injection")
                trace = record["trace"]
                before = np.array([r["before"]["observation"] for r in trace])
                after = np.array([r["after"]["observation"] for r in trace])
                deltas = after[:, :3] - before[:, :3]
                samples = np.unique(np.linspace(2, len(trace) - 1, min(6, max(0, len(trace) - 2)), dtype=int))
                for kind in candidate.MODELS:
                    model = models[record["task"]][kind]
                    for commands in (mean, actual):
                        predictions = candidate.predict_batch(model, before, deltas, commands)
                        for index in samples:
                            q = ForwardQuery(before[index], deltas[index-1], deltas[index-2], commands[index])
                            z = (features(q, kind) - np.array(model["mean"])) / np.array(model["scale"])
                            reference = (design(z, kind == "QUADRATIC_STATE") @ np.array(model["coefficients"]))[0]
                            if not np.allclose(predictions[index-2], reference, atol=1e-12, rtol=1e-10):
                                raise ValueError("independent feature prediction differs")
                            sampled_queries += 1
                    for phase in ("PROBE", "POLICY"):
                        saved = indexed[(record["episode_index"], kind, phase)]
                        count = sum(r["phase"] == phase for r in trace[2:])
                        if saved["samples"] != count:
                            raise ValueError("phase count/warmup changed")
                        reconstructed_square = saved["model_squared_sum"] + saved["input_squared_sum"] + saved["cross_sum"]
                        if not np.isclose(saved["total_squared_sum"], reconstructed_square, atol=1e-12, rtol=1e-10):
                            raise ValueError("saved squared-error identity differs")
                        checked_phase_counts += 1
                episodes += 1
                steps += len(trace)
    if episodes != d["replayed_episodes"] or steps != d["replayed_environment_steps"]:
        raise ValueError("verified population incomplete")
    return {"diagnostic_sha256": digest(diagnostic), "verifier_sha256": digest(Path(__file__)),
            "verification_parent_git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "integrity": "PASSED", "episodes": episodes, "exact_injected_inputs": steps,
            "independent_sampled_predictions": sampled_queries, "saved_phase_count_and_squared_identities": checked_phase_counts,
            "new_environment_steps": 0, "new_api_calls": 0, "model_refits": 0,
            "scope": "All reconstructed injections checked against original executor class; six evenly spaced past-history queries per episode use original feature/design functions; saved phase counts and squared-error identities checked. Not full independent aggregate reconstruction or dynamics simulation."}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--diagnostic", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    source = a.manifest.resolve()
    target = a.output.resolve()
    if target == source.parent or source.parent in target.parents:
        raise ValueError("verification cannot write inside immutable collection")
    if target.exists():
        raise FileExistsError("verification output already exists")
    result = verify(source, a.diagnostic.resolve())
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((json.dumps(result, indent=2) + "\n").encode("utf-8"))
    print(json.dumps({k:v for k,v in result.items() if k != "scope"}))

"""Authenticate the completed counterfactual source and build offline supervision."""
from dataclasses import asdict
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import numpy as np

from scripts import run_conditional_continuation as source
from src.probe.continuation_selector import BRANCHES, FULL_BRANCHES, ContinuationEvidence, TrainingCase, train, validate_model

ROOT = Path(__file__).resolve().parents[1]


def evidence(task, observations, commands, reference, raw, remaining=492):
    return ContinuationEvidence(task, tuple(observations), tuple(commands), tuple(reference["mean"]),
                                tuple(reference["covariance"]), tuple(raw), remaining)


def extract_source(config):
    path = ROOT / config["training_source_manifest"]
    audit_path = ROOT / config["training_source_audit"]
    if source.digest(path) != config["training_source_manifest_sha256"] or source.digest(audit_path) != config["training_source_audit_sha256"]:
        raise ValueError("registered offline source changed")
    manifest = json.loads(path.read_text(encoding="utf-8")); audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if source.manifest_digest(manifest) != manifest["manifest_id"] or audit["integrity"] != "PASSED" or audit["episodes"] != 672 or any(manifest[k] != audit[k] for k in source.IDENTITY):
        raise ValueError("complete matching immutable source audit required")
    if source.policy_hashes(source.TASKS) != manifest["policy_sha256"] or config["forward_model_sha256"] != manifest["config"]["forward_model_sha256"]:
        raise ValueError("source policy or nominal-model scope changed")
    # The old tree is authenticated at its historical commit, not the new tree's
    # AGENTS or protocol. Its immutable raw outputs remain the training source.
    for name, expected in manifest["input_sha256"].items():
        data = subprocess.check_output(["git","show",manifest["source_git_commit"]+":"+name],cwd=ROOT)
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError("historical source Git binding differs")
    for name, expected in audit["artifact_sha256"].items():
        if source.digest(path.parent/name) != expected:
            raise ValueError("audited offline source bytes changed")
    cases = []
    for stream in range(8):
        with gzip.open(path.parent/f"episodes_{stream:02}.jsonl.gz","rt",encoding="utf-8") as handle:
            records = {(r["task"],r["replicate"],r["method"]):r for r in map(json.loads,handle)}
        for task in source.TASKS:
            base = records[(task,0,"DIRECT_G8")]
            if len(base["trace"]) < 8 or any(base["trace"][7]["after"][k] for k in ("success","terminated","truncated")):
                raise ValueError("source lacks a registered active eight-step prefix")
            controls = [d["controller"] for d in base["decisions"] if d["action"] == "BUILD_GAUSSIAN" and d["at_host_calls"] == 8]
            if len(controls) != 1:
                raise ValueError("source eighth-step controller missing")
            observations = [base["initial"]["observation"]]+[r["after"]["observation"] for r in base["trace"][:8]]
            commands = [r["command"] for r in base["trace"][:8]]
            policy = source.create_task_policy(task)
            raw = np.asarray(policy.get_action(np.asarray(observations[-1])),np.float32).tolist()
            current = evidence(task,observations,commands,controls[0],raw)
            for method in BRANCHES:
                for future in range(4):
                    if source.prefix_match(records[(task,future,method)],base) != "MATCHED_ACTIVE_PREFIX":
                        raise ValueError("counterfactual source prefix mismatch")
            for method in FULL_BRANCHES:
                for future in range(4):
                    other=records[(task,future,method)]
                    if other["initial"]!=base["initial"] or other["initial_physics_witness_oracle"]!=base["initial_physics_witness_oracle"] or other["initial_noise_hash"]!=base["initial_noise_hash"]:
                        raise ValueError("full portfolio source initial-state witnesses differ")
            losses = tuple(tuple(records[(task,future,m)]["outcome"]["deadline_loss"] for future in range(4)) for m in FULL_BRANCHES)
            cases.append(TrainingCase(f"source-stream-{stream}:{task}",stream,current,losses))
    return cases, {"role":"OFFLINE_COUNTERFACTUAL_SUPERVISION_NOT_NATURAL_EXPERIENCE",
                    "source_manifest_sha256":source.digest(path),"source_audit_sha256":source.digest(audit_path),
                    "historical_git_inputs_checked":len(manifest["input_sha256"]),
                    "source_episodes":672,"source_steps":audit["controlled_steps"],"source_controlled_resets":672,
                    "source_contexts":24,"source_groups":8,"source_futures":4,"paired_branch_outcomes":480,"all_initial_portfolio_outcomes":672,
                    "new_environment_steps":0,"api_calls":0}


def build(config):
    output = ROOT/config["training_output"]
    if output.exists():
        raise FileExistsError("one-shot training source cannot be rebuilt")
    cases, provenance = extract_source(config)
    models = train(cases)
    dataset = {"role":provenance["role"],"cases":[asdict(c) for c in cases]}
    output.mkdir(parents=True,exist_ok=False)
    for name, value in (("models.json",models),("dataset.json",dataset),("provenance.json",provenance)):
        source.write_json(output/name,value)
    return {name:source.digest(output/name) for name in ("models.json","dataset.json","provenance.json")}


def load(config, binding):
    directory = ROOT/config["training_output"]
    if set(binding) != {"models.json","dataset.json","provenance.json"} or any(source.digest(directory/n) != h for n,h in binding.items()):
        raise ValueError("frozen trained artifacts changed")
    artifact = json.loads((directory/"models.json").read_text(encoding="utf-8"))
    return validate_model(artifact)

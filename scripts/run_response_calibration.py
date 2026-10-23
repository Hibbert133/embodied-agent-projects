"""Freeze, collect, qualify, and audit a known-command response calibration."""
from dataclasses import asdict
from datetime import datetime,timezone
import argparse
import hashlib
import itertools
import importlib.metadata
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
from scripts.run_evidence_persistence import git,digest,manifest_digest,check_clean,append
from scripts.run_probemem_acr_utility_stability import _write_json
from scripts.run_continuous_probe import LiveHost,normalized
from src.probe.continuous import StepObservation,ContinuousTransition,ContinuousEvidence,collect_continuous
from src.probe.response_calibration import ResponseModel,fit_response,trajectory_features,known_offset_program,infer_features
from src.perturbations import BiasNoisePerturbation
from src.rollout import create_push_environment

CONFIG=ROOT/"configs/response_calibration/development_v1.json"
PROTOCOL=ROOT/"docs/protocols/response_calibration_development_v1.md"


def validate(c):
    if (c["training_seeds"],c["qualification_seeds"],c["training_levels"],c["qualification_levels"],
        c["noise_std"],c["steps_per_trial"],c["maximum_physical_steps"],c["maximum_mean_offset_error"],
        c["maximum_90th_percentile_error"],c["api_calls"],c["memory_writes"]) != (
        list(range(8900,8908)),list(range(8908,8916)),[-.2,0.,.2],[-.15,0.,.15],.05,16,2304,.05,.1,0,0):
        raise ValueError("frozen calibration configuration mismatch")


def units(c,phase):
    return [(seed,tuple(offset)) for seed in c[f"{phase}_seeds"] for offset in itertools.product(c[f"{phase}_levels"],repeat=2)]


def prepare():
    check_clean(); c=json.loads(CONFIG.read_text()); validate(c)
    root=ROOT/c["output_root"]
    if list(root.glob("*/manifest.json")): raise FileExistsError("protocol already frozen")
    commit=git("rev-parse","HEAD"); stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    names=git("ls-files","src","scripts").splitlines()+[CONFIG.relative_to(ROOT).as_posix(),PROTOCOL.relative_to(ROOT).as_posix(),"requirements.txt"]
    m={"experiment_run_id":f"response_calibration_{stamp}_{commit[:12]}","source_git_commit":commit,
       "config":c,"input_sha256":{n:digest(ROOT/n) for n in names},
       "versions":{p:importlib.metadata.version(p) for p in ("metaworld","mujoco","numpy")}}
    m["manifest_id"]=manifest_digest(m)
    output=root/m["experiment_run_id"]; output.mkdir(parents=True,exist_ok=False)
    _write_json(output/"manifest.json",m); print(output/"manifest.json")


def load(path):
    m=json.loads(path.read_text()); validate(m["config"])
    if manifest_digest(m)!=m["manifest_id"]: raise ValueError("manifest mismatch")
    for name,sha in m["input_sha256"].items():
        if digest(ROOT/name)!=sha: raise ValueError(f"frozen source changed: {name}")
    return m


def restore(raw):
    return ContinuousEvidence(tuple(ContinuousTransition(tuple(t["command"]),tuple(t["before"]),tuple(t["after"])) for t in raw["transitions"]),
                              StepObservation(**raw["final"]),raw["stop_reason"],raw["requested_steps"])


def score(rows,c):
    expected=units(c,"qualification")
    if [(r["seed"],tuple(r["known_command_offset"])) for r in rows]!=expected: raise ValueError("qualification population mismatch")
    methods={}
    for method in ("affine","nearest"):
        errors=[float(np.linalg.norm(np.array(r["predictions"][method])-r["known_command_offset"])) for r in rows]
        methods[method]={"mean_error":float(np.mean(errors)),"median_error":float(np.median(errors)),
            "p90_error":float(np.quantile(errors,.9,method="linear")),
            "per_seed_mean":{str(seed):float(np.mean([e for e,r in zip(errors,rows) if r["seed"]==seed])) for seed in c["qualification_seeds"]}}
    a=methods["affine"]
    gates={"mean_error":a["mean_error"]<=c["maximum_mean_offset_error"],"p90_error":a["p90_error"]<=c["maximum_90th_percentile_error"]}
    return {"methods":methods,"gates":gates,"gate_passed":all(gates.values()),"qualification_trials":len(rows),
            "mean_feature_reconstruction_rmse":float(np.mean([r["feature_reconstruction_rmse"] for r in rows]))}


def run(path):
    check_clean(); m=load(path)
    if git("rev-parse","HEAD")!=m["source_git_commit"]: raise ValueError("source commit mismatch")
    output=path.parent; c=m["config"]; identity={k:m[k] for k in ("experiment_run_id","manifest_id","source_git_commit")}
    if (output/"status.json").exists(): raise FileExistsError("one-shot collection cannot restart")
    status={**identity,"status":"RUNNING","training_trials":0,"qualification_trials":0,"physical_steps":0,"environment_resets":0,
            "api_calls":0,"memory_writes":0}; _write_json(output/"status.json",status)
    training=[]; qualification=[]; sequence=0; model=None; model_sha=None
    try:
        for phase_index,phase in enumerate(("training","qualification")):
            for unit_index,(seed,offset) in enumerate(units(c,phase)):
                env=create_push_environment(seed)
                noise_seed=int(np.random.SeedSequence([seed,unit_index%9,0xCA1,phase_index]).generate_state(1)[0])
                try:
                    host=LiveHost(env,BiasNoisePerturbation([0,0,0,0],.05),seed,noise_seed)
                    evidence=collect_continuous(host.step,host.current,known_offset_program(offset),remaining_budget=16,task_reserve=0)
                    sequence+=1
                    row={**identity,"sequence":sequence,"phase":phase,"seed":seed,"known_command_offset":offset,
                         "evidence":evidence.to_dict(),"host_calls":host.calls,"environment_resets":host.resets,"rng_final":host.rng_hash()}
                    status["physical_steps"]+=host.calls; status["environment_resets"]+=host.resets
                    if evidence.steps!=16 or evidence.stop_reason!="PROGRAM_COMPLETE":
                        append(output/"incomplete_trial.jsonl",row)
                        raise ValueError("incomplete calibration probe; no replacement")
                    if phase=="training": training.append((offset,evidence))
                    else:
                        feature=trajectory_features(evidence)
                        predictions={name:infer_features(model,feature,method=name) for name in ("affine","nearest")}
                        residual=feature-np.array(model.nominal)-np.array(model.sensitivity)@np.array(predictions["affine"])
                        row.update(model_sha256=model_sha,predictions=predictions,feature_reconstruction_rmse=float(np.sqrt(np.mean(residual**2))))
                        qualification.append(normalized(row))
                    append(output/f"{phase}.jsonl",row); status[f"{phase}_trials"]+=1
                finally: env.close()
                _write_json(output/"status.json",status)
                if (unit_index+1)%9==0: print(f"Completed {phase} seed {seed}: {unit_index+1}/72 trials",flush=True)
            if phase=="training":
                model=fit_response(training)
                _write_json(output/"model.json",{**identity,"frozen_after_sequence":sequence,
                    "training_artifact_sha256":digest(output/"training.jsonl"),"model":model.to_dict()})
                model_sha=digest(output/"model.json")
                status["model_sha256"]=model_sha; _write_json(output/"status.json",status)
        if status["physical_steps"]>c["maximum_physical_steps"]: raise ValueError("physical budget exceeded")
        result=score(qualification,c)
        status["status"]="COMPLETED_QUALIFICATION_PASS" if result["gate_passed"] else "COMPLETED_QUALIFICATION_FAILED"
        _write_json(output/"summary.json",{**status,"statistics":result}); _write_json(output/"status.json",status)
        print(json.dumps({"status":status["status"],"statistics":result}))
    except BaseException as exc:
        status.update(status="INCOMPLETE",error_type=type(exc).__name__,error=str(exc)); _write_json(output/"status.json",status)
        raise


def audit(path):
    m=load(path); c=m["config"]; output=path.parent
    identity={k:m[k] for k in ("experiment_run_id","manifest_id","source_git_commit")}
    status=json.loads((output/"status.json").read_text()); summary=json.loads((output/"summary.json").read_text())
    saved=json.loads((output/"model.json").read_text())
    records={phase:[json.loads(x) for x in (output/f"{phase}.jsonl").read_text().splitlines()] for phase in ("training","qualification")}
    all_rows=records["training"]+records["qualification"]
    if [r["sequence"] for r in all_rows]!=list(range(1,145)): raise ValueError("sequence/population mismatch")
    if any(any(r.get(k)!=v for k,v in identity.items()) for r in all_rows+[status,summary,saved]): raise ValueError("provenance mismatch")
    restored={}
    for phase_index,phase in enumerate(("training","qualification")):
        rows=records[phase]
        if [(r["seed"],tuple(r["known_command_offset"])) for r in rows]!=units(c,phase): raise ValueError("calibration schedule mismatch")
        restored[phase]=[]
        for i,row in enumerate(rows):
            evidence=restore(row["evidence"]); trajectory_features(evidence)
            if row["phase"]!=phase or row["host_calls"]!=16 or row["environment_resets"]!=1 or evidence.requested_steps!=16:
                raise ValueError("probe cost/phase mismatch")
            if tuple(t.command for t in evidence.transitions)!=known_offset_program(row["known_command_offset"]): raise ValueError("commanded offset mismatch")
            for t in evidence.transitions:
                if len(t.before)!=39 or len(t.after)!=39 or not np.isfinite(t.before+t.after).all(): raise ValueError("invalid observation")
            rng=np.random.default_rng(int(np.random.SeedSequence([row["seed"],i%9,0xCA1,phase_index]).generate_state(1)[0]))
            for _ in range(16): rng.normal(0,.05,3)
            expected_rng=hashlib.sha256(json.dumps(rng.bit_generator.state,sort_keys=True).encode()).hexdigest()
            if expected_rng!=row["rng_final"]: raise ValueError("actuator RNG continuity mismatch")
            restored[phase].append((tuple(row["known_command_offset"]),evidence))
    model=fit_response(restored["training"])
    if normalized(model.to_dict())!=saved["model"] or saved["frozen_after_sequence"]!=72 or saved["training_artifact_sha256"]!=digest(output/"training.jsonl"):
        raise ValueError("training-only model reconstruction mismatch")
    model_sha=digest(output/"model.json")
    for row,(_,evidence) in zip(records["qualification"],restored["qualification"]):
        feature=trajectory_features(evidence)
        predictions={name:infer_features(model,feature,method=name) for name in ("affine","nearest")}
        residual=feature-np.array(model.nominal)-np.array(model.sensitivity)@np.array(predictions["affine"])
        if row["model_sha256"]!=model_sha or normalized(predictions)!=row["predictions"] or float(np.sqrt(np.mean(residual**2)))!=row["feature_reconstruction_rmse"]:
            raise ValueError("qualification prediction/model mismatch")
    rebuilt=score(records["qualification"],c)
    if rebuilt!=summary["statistics"]: raise ValueError("qualification statistics mismatch")
    expected_status="COMPLETED_QUALIFICATION_PASS" if rebuilt["gate_passed"] else "COMPLETED_QUALIFICATION_FAILED"
    values={"status":expected_status,"training_trials":72,"qualification_trials":72,"physical_steps":2304,"environment_resets":144,
            "api_calls":0,"memory_writes":0,"model_sha256":model_sha}
    if any(status.get(k)!=v or summary.get(k)!=v for k,v in values.items()): raise ValueError("completion/cost mismatch")
    return {**identity,**values,"integrity":"PASSED","statistics":rebuilt,
        "sensitivity_singular_values":np.linalg.svd(np.array(model.sensitivity),compute_uv=False).tolist(),
        "artifact_sha256":{p.name:digest(p) for p in output.iterdir() if p.is_file()}}


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__); g=p.add_mutually_exclusive_group(required=True)
    g.add_argument("--prepare",action="store_true"); g.add_argument("--manifest",type=Path); g.add_argument("--audit",type=Path)
    p.add_argument("--output",type=Path); a=p.parse_args()
    if a.prepare: prepare()
    elif a.manifest: run(a.manifest.resolve())
    else:
        if a.output is None or a.output.exists() or a.audit.resolve().parent in a.output.resolve().parents:
            raise ValueError("choose a new audit file outside immutable collection")
        result=audit(a.audit.resolve()); a.output.parent.mkdir(parents=True,exist_ok=True); _write_json(a.output,result)
        print(json.dumps({"status":result["status"],"integrity":result["integrity"],"statistics":result["statistics"]}))

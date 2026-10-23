"""Frozen numerical qualification, not a robot experiment or novel method study."""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import random
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.probe.relative_effects import RelativeRequest, RelativeEffectMonitor, digest

CONFIG = ROOT / "configs/relative_update_evidence/qualification_v1.json"
INPUTS = ("src/probe/relative_effects.py", "tests/test_relative_effects.py", "scripts/qualify_relative_update_evidence.py",
          "scripts/audit_relative_update_evidence.py", "configs/relative_update_evidence/qualification_v1.json",
          "docs/research/relative_update_evidence_v1.md", "docs/protocols/relative_update_evidence_qualification_v1.md", "AGENTS.md", ".gitattributes")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False, allow_nan=False); handle.write("\n")


def load(path):
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if digest({k:v for k,v in manifest.items() if k != "manifest_id"}) != manifest["manifest_id"]:
        raise ValueError("manifest identity differs")
    for name, expected in manifest["input_sha256"].items():
        if sha(ROOT / name) != expected:
            raise ValueError("frozen qualification inputs changed")
        historical=subprocess.check_output(["git","show",manifest["source_git_commit"]+":"+name],cwd=ROOT)
        if hashlib.sha256(historical).hexdigest()!=expected:
            raise ValueError("declared frozen Git bytes differ")
    c = manifest["config"]
    expected = {"scenarios":["STATIC_NULL","DRIFT_NULL","SMALL_GAIN","STRONG_GAIN","EFFECT_FLIP"],
                "replicates":256,"horizon":64,"checkpoints":[8,16,32,64],"alpha":.05,"rho":4.,
                "assignment_seed_base":700001,"noise_seed_base":900001,"seed_scenario_stride":10000,"counterexample_seed":1100001,
                "new_environment_steps":0,"api_calls":0,"controller_fits":0}
    if any(c.get(k) != v for k,v in expected.items()) or c["protocol_id"] != "relative_update_evidence_mathematical_qualification_v1":
        raise ValueError("registered complete synthetic design required")
    return manifest


def prepare():
    for arguments in (("diff","--quiet"),("diff","--cached","--quiet")):
        if subprocess.call(["git",*arguments],cwd=ROOT): raise ValueError("freeze tracked inputs before qualification")
    c=json.loads(CONFIG.read_text(encoding="utf-8")); parent=ROOT/c["output_root"]
    if list(parent.glob("*/manifest.json")): raise FileExistsError("one-shot qualification already prepared")
    commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    for name in INPUTS:
        historical=subprocess.check_output(["git","show",commit+":"+name],cwd=ROOT)
        if hashlib.sha256(historical).hexdigest()!=sha(ROOT/name):raise ValueError("freeze every qualification source in Git")
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    m={"run_id":f"relative_evidence_{stamp}_{commit[:12]}","source_git_commit":commit,"config":c,
       "input_sha256":{name:sha(ROOT/name) for name in INPUTS},"python":sys.version.split()[0]}
    m["manifest_id"]=digest(m); destination=parent/m["run_id"];destination.mkdir(parents=True,exist_ok=False)
    write(destination/"manifest.json",m);load(destination/"manifest.json")
    print(destination/"manifest.json")


def scenario_values(name,trial,previous):
    if name == "STATIC_NULL": return 0.,0.,.5,0.
    if name == "DRIFT_NULL":
        base=.55*math.sin(trial*.2)+.1*(2*previous-1)
        return base,0.,.25 if previous else .75,0.
    if name == "SMALL_GAIN":
        base=.4*math.sin(trial*.2)+.1*(2*previous-1)
        return base,.2,.5,base
    if name == "STRONG_GAIN": return 0.,1.4,.5,0.
    if name == "EFFECT_FLIP": return 0.,1.4 if trial<=48 else -1.4,.5,0.
    raise ValueError("unknown synthetic scenario")


def run(path):
    m=load(path);c=m["config"];folder=path.parent
    if (folder/"events.jsonl.gz").exists(): raise FileExistsError("preserve the first qualification")
    counts={name:{"paths":0,"any_past_mean_coverage_failure":0,"any_positive_interval_while_current_effect_negative":0,
                  "checkpoints":{str(n):{"covered":0,"positive":0,"negative":0,"empty":0,"mean_width":0.} for n in c["checkpoints"]}}
            for name in c["scenarios"]}
    sequence=0
    with gzip.open(folder/"events.jsonl.gz","xt",encoding="utf-8",newline="\n") as handle:
        def emit(kind,key,value):
            nonlocal sequence
            sequence+=1;handle.write(json.dumps({"sequence":sequence,"kind":kind,**key,**value},separators=(",",":"),allow_nan=False)+"\n")
        for index,name in enumerate(c["scenarios"]):
            for replicate in range(c["replicates"]):
                assignment_rng=random.Random(c["assignment_seed_base"]+index*c["seed_scenario_stride"]+replicate)
                noise_rng=random.Random(c["noise_seed_base"]+index*c["seed_scenario_stride"]+replicate)
                monitor=RelativeEffectMonitor(assignment_rng.random,alpha=c["alpha"],rho=c["rho"])
                history=digest({"initial_visible_observation":0.})
                previous=0;tau_sum=0.;missed=False;wrong_target=False
                for trial in range(1,c["horizon"]+1):
                    base,tau,p,pred=scenario_values(name,trial,previous)
                    request=RelativeRequest(trial,history,(0.,0.,0.,0.),(.4,0.,0.,0.),p,pred,pred,501-trial)
                    key={"scenario":name,"replicate":replicate,"trial":trial}
                    saved=monitor.prepare(request);emit("REQUEST",key,saved)
                    assignment=monitor.randomize();emit("ASSIGNMENT",key,assignment)
                    noise=(.1 if name in ("STATIC_NULL","DRIFT_NULL") else .05)*(1 if noise_rng.random()<.5 else -1)
                    observed=base+(assignment["assignment"]-.5)*tau+noise
                    record=monitor.observe(saved["request_id"],observed)
                    tau_sum+=tau;target=tau_sum/trial;interval=record["interval"]
                    covered=interval["lower"]<=target<=interval["upper"]
                    missed|=not covered;wrong_target|=interval["lower"]>0 and tau<0
                    emit("OUTCOME",key,{"record":record,"evaluation_only":{"conditional_effect":tau,"past_mean_effect":target,"covered":covered}})
                    history=digest({"previous":history,"request_id":saved["request_id"],"assignment":assignment["assignment"],"observed":observed})
                    previous=assignment["assignment"]
                    if trial in c["checkpoints"]:
                        b=counts[name]["checkpoints"][str(trial)]
                        b["covered"]+=int(covered);b["positive"]+=int(interval["lower"]>0 and not interval["empty"])
                        b["negative"]+=int(interval["upper"]<0 and not interval["empty"]);b["empty"]+=int(interval["empty"])
                        b["mean_width"]+=max(0.,interval["upper"]-interval["lower"])/c["replicates"]
                counts[name]["paths"]+=1;counts[name]["any_past_mean_coverage_failure"]+=int(missed)
                counts[name]["any_positive_interval_while_current_effect_negative"]+=int(wrong_target)
    counter=RelativeEffectMonitor(random.Random(c["counterexample_seed"]).random,alpha=c["alpha"],rho=c["rho"])
    identical=[]
    for trial in range(1,65):
        req=RelativeRequest(trial,digest({"counterexample_visible_trial":trial}),(0.,0.,0.,0.),(.4,0.,0.,0.),.5,0.,0.,501-trial)
        saved=counter.prepare(req);a=counter.randomize();identical.append(counter.observe(saved["request_id"],.5 if a["assignment"] else -.5))
    counterexample={"construction":"All assignments have identical proximal distributions in both worlds through step 64; terminal occurs at 65.",
                    "saved_identical_proximal_records":identical,"old_terminal_value_both_worlds":.5,
                    "candidate_terminal_values":{"A":1.,"B":0.},"minimax_terminal_regret_lower_bound":.25,
                    "positive_proximal_interval_at_64":identical[-1]["interval"]["lower"]>0,
                    "scope":"Standard two-world finite-horizon counterexample, not a fitted robot dynamics model."}
    write(folder/"counterexample.json",counterexample)
    result={k:m[k] for k in ("run_id","manifest_id","source_git_commit")}
    result.update(status="COMPLETED_MATHEMATICAL_QUALIFICATION",events=sequence,paths=1280,synthetic_responses=81920,
                  scenarios=counts,new_environment_steps=0,new_resets=0,api_calls=0,controller_fits=0,
                  algorithm_novelty_established=False,task_utility_established=False)
    write(folder/"results.json",result)
    print(json.dumps({k:result[k] for k in ("status","events","paths","synthetic_responses")}))


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--prepare",action="store_true");parser.add_argument("--manifest",type=Path)
    args=parser.parse_args()
    if args.prepare: prepare()
    elif args.manifest: run(args.manifest.resolve())
    else: parser.error("--prepare or --manifest required")

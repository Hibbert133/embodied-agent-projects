"""Independently recompute every randomized synthetic outcome and contrast."""
import argparse
import gzip
import json
import math
from pathlib import Path
import random
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.qualify_relative_update_evidence import load,sha,digest,write


def close(actual,expected):
    if isinstance(expected,dict):
        if set(actual)!=set(expected):raise ValueError("audit field population differs")
        for k,v in expected.items():close(actual[k],v)
    elif type(expected) is float:
        if not math.isfinite(actual) or not math.isclose(actual,expected,rel_tol=1e-11,abs_tol=1e-11):raise ValueError("independent numeric reconstruction differs")
    elif actual!=expected:raise ValueError("independent reconstruction differs")


def interval(total,v,n,alpha,rho):
    half=math.sqrt((rho+v)*math.log((rho+v)/(rho*alpha**2)))/n
    lo=max(-2.,total/n-half);hi=min(2.,total/n+half)
    return {"estimate":total/n,"lower":lo,"upper":hi,"empty":lo>hi,"half_width_before_intersection":half}


def audit(path,output):
    m=load(path);c=m["config"];folder=path.parent
    result=json.loads((folder/"results.json").read_text(encoding="utf-8"))
    if any(result[k]!=m[k] for k in ("run_id","manifest_id","source_git_commit")):raise ValueError("source identity mismatch")
    expected={};sequence=0;numeric_fields=0
    with gzip.open(folder/"events.jsonl.gz","rt",encoding="utf-8") as handle:
        def take(kind,key):
            nonlocal sequence
            item=json.loads(next(handle));sequence+=1
            if item["sequence"]!=sequence or item["kind"]!=kind or any(item[k]!=v for k,v in key.items()):raise ValueError("request, assignment and outcome order differs")
            return item
        for index,name in enumerate(c["scenarios"]):
            stats={"paths":0,"any_past_mean_coverage_failure":0,"any_positive_interval_while_current_effect_negative":0,
                   "checkpoints":{str(n):{"covered":0,"positive":0,"negative":0,"empty":0,"mean_width":0.} for n in c["checkpoints"]}}
            for replicate in range(c["replicates"]):
                assignment_rng=random.Random(c["assignment_seed_base"]+index*c["seed_scenario_stride"]+replicate)
                noise_rng=random.Random(c["noise_seed_base"]+index*c["seed_scenario_stride"]+replicate)
                history=digest({"initial_visible_observation":0.});previous=0;total=v=tau_sum=0.;missed=wrong=False
                for trial in range(1,65):
                    base=0.;tau=0.;p=.5;prediction=0.
                    if name=="DRIFT_NULL":base=.55*math.sin(trial/5)+.1*(2*previous-1);p=.25 if previous else .75
                    elif name=="SMALL_GAIN":base=.4*math.sin(trial/5)+.1*(2*previous-1);tau=.2;prediction=base
                    elif name=="STRONG_GAIN":tau=1.4
                    elif name=="EFFECT_FLIP":tau=1.4 if trial<=48 else -1.4
                    key={"scenario":name,"replicate":replicate,"trial":trial}
                    request={"trial":trial,"history_digest":history,"baseline_action":[0.,0.,0.,0.],"candidate_action":[.4,0.,0.,0.],
                             "probability":p,"predicted_baseline":prediction,"predicted_candidate":prediction,"remaining_steps":501-trial}
                    saved=take("REQUEST",key);close(saved["request"],request)
                    # Preserve exact serialized source floats for identity; numeric formula above is independent.
                    request_id=digest(saved["request"])
                    if saved["request_id"]!=request_id:raise ValueError("request identity changed")
                    assigned=take("ASSIGNMENT",key);z=int(assignment_rng.random()<p)
                    if assigned["assignment"]!=z or assigned["request_id"]!=request_id or assigned["command"]!=request["candidate_action" if z else "baseline_action"]:raise ValueError("assigned command differs from saved randomization")
                    noise=(.1 if name in ("STATIC_NULL","DRIFT_NULL") else .05)*(1 if noise_rng.random()<.5 else -1)
                    y=base+(z-.5)*tau+noise
                    outcome=take("OUTCOME",key);record=outcome["record"]
                    m0=saved["request"]["predicted_baseline"];m1=saved["request"]["predicted_candidate"]
                    score=m1-m0+(y-m1)/p if z else m1-m0-(y-m0)/(1-p)
                    endpoints=[m1-m0+(yy-m1)/p if zz else m1-m0-(yy-m0)/(1-p) for zz in (0,1) for yy in (-1.,1.)]
                    total+=score;v+=(max(endpoints)-min(endpoints))**2/4;tau_sum+=tau
                    ci=interval(total,v,trial,c["alpha"],c["rho"]);covered=ci["lower"]<=tau_sum/trial<=ci["upper"]
                    close({k:record[k] for k in ("observed_outcome","pseudo_outcome","total","variance_proxy","interval")},
                          {"observed_outcome":y,"pseudo_outcome":score,"total":total,"variance_proxy":v,"interval":ci})
                    close(record["predictable_range"],[min(endpoints),max(endpoints)])
                    if record["request_id"]!=request_id or record["samples"]!=trial or record["assignment"]!=z or record["task_utility_guarantee"] is not False or record["controller_returned"] is not False or record["target"]!="REALIZED_HISTORY_AVERAGE_PROXIMAL_EFFECT" or record["scope"]!="STANDARD_RANDOMIZED_PROXIMAL_REFERENCE":raise ValueError("scope or record identity differs")
                    close(outcome["evaluation_only"],{"conditional_effect":tau,"past_mean_effect":tau_sum/trial,"covered":covered})
                    numeric_fields+=12;missed|=not covered;wrong|=ci["lower"]>0 and tau<0
                    # The recorded observed float is bound to the independently reconstructed response.
                    history=digest({"previous":history,"request_id":request_id,"assignment":z,"observed":record["observed_outcome"]});previous=z
                    if trial in c["checkpoints"]:
                        b=stats["checkpoints"][str(trial)];b["covered"]+=int(covered);b["positive"]+=int(ci["lower"]>0 and not ci["empty"])
                        b["negative"]+=int(ci["upper"]<0 and not ci["empty"]);b["empty"]+=int(ci["empty"])
                        b["mean_width"]+=max(0.,ci["upper"]-ci["lower"])/c["replicates"]
                stats["paths"]+=1;stats["any_past_mean_coverage_failure"]+=int(missed);stats["any_positive_interval_while_current_effect_negative"]+=int(wrong)
            expected[name]=stats
        if handle.read().strip():raise ValueError("unexpected trailing events")
    close(result["scenarios"],expected)
    if (result["events"],result["paths"],result["synthetic_responses"])!=(245760,1280,81920) or sequence!=245760:raise ValueError("complete population differs")
    if any(result[k]!=0 for k in ("new_environment_steps","new_resets","api_calls","controller_fits")):raise ValueError("physical execution forbidden")
    if result["status"]!="COMPLETED_MATHEMATICAL_QUALIFICATION" or result["algorithm_novelty_established"] is not False or result["task_utility_established"] is not False:raise ValueError("qualification is not a task or novelty result")
    counter=json.loads((folder/"counterexample.json").read_text(encoding="utf-8"));rng=random.Random(c["counterexample_seed"])
    for n,record in enumerate(counter["saved_identical_proximal_records"],1):
        z=int(rng.random()<.5)
        close(record["observed_outcome"],.5 if z else -.5);close(record["pseudo_outcome"],1.)
        close(record["interval"],interval(float(n),4.*n,n,c["alpha"],c["rho"]))
        if record["assignment"]!=z:raise ValueError("counterexample random path differs")
    if len(counter["saved_identical_proximal_records"])!=64 or not counter["positive_proximal_interval_at_64"] or counter["candidate_terminal_values"]!={"A":1.,"B":0.} or counter["old_terminal_value_both_worlds"]!=.5 or counter["minimax_terminal_regret_lower_bound"]!=.25:raise ValueError("terminal-order counterexample differs")
    output.mkdir(parents=True,exist_ok=False)
    record={k:m[k] for k in ("run_id","manifest_id","source_git_commit")}
    record.update(integrity="PASSED",events=sequence,paths=1280,synthetic_responses=81920,numeric_fields_checked=numeric_fields,
                  artifact_sha256={p.name:sha(p) for p in folder.iterdir() if p.is_file()},new_environment_steps=0,api_calls=0,
                  scope="Independent scalar formulas and RNG replay; manifest identity loader reused. Mathematical synthetic qualification, no robot or terminal utility guarantee.")
    write(output/"audit.json",record);print(json.dumps({k:record[k] for k in ("integrity","events","numeric_fields_checked")}))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--manifest",type=Path,required=True);parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();audit(args.manifest.resolve(),args.output.resolve())

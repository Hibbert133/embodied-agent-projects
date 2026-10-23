"""Postcollection query coverage and implied future-block calibration diagnosis.

No decisions are changed. The numerical intervals below are reconstructed from
saved predecision designs on realized future commands, not new live outputs.
Finite listed query compatibility does not certify an entire clipped policy
image or state-dependent response model.
"""
import argparse
from collections import defaultdict
from fractions import Fraction
import gzip
import hashlib
import json
import numbers
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
from src.probe.action_response_validity import ResidualDesign,set_intervals,point_residual

METHODS=("NO_PROBE","FIXED8","FIXED16","FIXED8_WIDE","FIXED16_WIDE","CACHE_ONLY","PERIODIC2","PERIODIC3",
         "RECENT_WINDOW","RESIDUAL_CUSUM","G_OPTIMAL","RESPONSE_SET","RESPONSE_POINT","RESPONSE_GEOMETRY","RESPONSE_NO_COST","ORACLE16")
GUARDED=("G_OPTIMAL","RESPONSE_SET","RESPONSE_POINT","RESPONSE_GEOMETRY","RESPONSE_NO_COST")


def sha(path):
    digest=hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda:handle.read(1024*1024),b""):digest.update(chunk)
    return digest.hexdigest()


def rational_point(row):
    if len(row)<2 or any(isinstance(v,(bool,np.bool_)) or not isinstance(v,numbers.Real) or not np.isfinite(v) for v in row[:2]):raise ValueError("finite sent xy required")
    return tuple(Fraction.from_float(float(v)) for v in row[:2])


def cross(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def hull(points):
    points=sorted(set(rational_point(row) for row in points))
    if len(points)<=1:return tuple(points)
    lower=[]
    for p in points:
        while len(lower)>=2 and cross(lower[-2],lower[-1],p)<=0:lower.pop()
        lower.append(p)
    upper=[]
    for p in reversed(points):
        while len(upper)>=2 and cross(upper[-2],upper[-1],p)<=0:upper.pop()
        upper.append(p)
    return tuple(lower[:-1]+upper[:-1])


def inside(boundary,query):
    q=rational_point(query)
    if not boundary:return False
    if len(boundary)==1:return q==boundary[0]
    if len(boundary)==2:
        a,b=boundary
        return cross(a,b,q)==0 and all(min(a[j],b[j])<=q[j]<=max(a[j],b[j]) for j in range(2))
    return all(cross(a,b,q)>=0 for a,b in zip(boundary,boundary[1:]+boundary[:1]))


def implied_interval(validation,commands):
    """Evaluate the immutable predecision fit on realized future mean covariates."""
    design=ResidualDesign(**validation["residual_groups"])
    assessment=validation["assessment"];sigma=assessment["noise_reference_rms_m"]
    query=np.mean(np.array(commands)[:,:2],axis=0)
    mode=assessment["mode"]
    if mode=="SET":
        result=set_intervals(design,(query,),sigma)
        if result["status"]!="FINITE":return {"status":result["status"]}
        lower=np.array(result["intervals_mm"][0]["lower"]);upper=np.array(result["intervals_mm"][0]["upper"])
    else:
        q=np.array([*query,1.]);mean=q@point_residual(design)
        if mode=="GAUSSIAN":
            gram=(design.x.T*np.array(design.counts))@design.x+1e-6*np.eye(3)
            radius=2000*sigma*np.sqrt(q@np.linalg.inv(gram)@q)
        else:radius=0.
        lower=mean-radius;upper=mean+radius
    # New measurement error is a separate, explicitly assumed block scale.
    noise=2000*sigma/np.sqrt(len(commands))
    return {"status":"FINITE","lower_mm":(lower-noise).tolist(),"upper_mm":(upper+noise).tolist(),
            "future_mean_sent_xy":query.tolist(),"assumed_future_block_scale_mm":float(noise)}


def case_scope(record):
    reuse=[d for d in record["decisions"] if d["action"]=="REUSE_CACHE" and "validation" in d]
    if not reuse:return None
    if len(reuse)!=1:raise ValueError("unexpected multiple final cache validations")
    choice=reuse[0];validation=choice["validation"]
    if "envelope" not in validation:return None  # Scalar CUSUM has no query envelope.
    boundary=hull(validation["envelope"]["sent_xy"])
    future=[r for r in record["trace"] if r["phase"]=="POLICY" and r["decision_sequence"]==choice["sequence"]]
    outside=[r["host_calls"] for r in future if not inside(boundary,r["command"])]
    row={k:record[k] for k in ("episode_index","stream","task","scenario","episode_in_stream","method","seed")}
    row.update(policy_queries=len(future),outside_listed_query_hull=len(outside),first_outside_step=min(outside) if outside else None,
               prediction_scope_qualified=False,query_hull_diagnosis_is_not_registered_budget_or_leakage_violation=True)
    first=future[:4]
    if len(first)==4 and all(r["forecast_xy"] is not None for r in first):
        interval=implied_interval(validation,[r["command"] for r in first])
        residual=np.mean([np.array(r["target_xy"])-np.array(r["forecast_xy"]) for r in first],axis=0)*1000
        covered=None if interval["status"]!="FINITE" else bool(np.all(residual>=interval["lower_mm"]) and np.all(residual<=interval["upper_mm"]))
        row.update(first_four_policy_mean_residual_mm=residual.tolist(),implied_future_interval=interval,
                   first_four_policy_mean_covered=covered)
    else:row.update(first_four_policy_mean_covered=None,incomplete_future_block=True)
    return row


def analyze(manifest,audit_path):
    m=json.loads(manifest.read_text(encoding="utf-8"));a=json.loads(audit_path.read_text(encoding="utf-8"))
    if a["integrity"]!="PASSED" or any(a[k]!=m[k] for k in ("experiment_run_id","manifest_id","source_git_commit")):raise ValueError("matching full audit required")
    for name,expected in a["artifact_sha256"].items():
        if sha(manifest.parent/name)!=expected:raise ValueError("original audited bytes changed")
    records=[];lags=defaultdict(list)
    for method in METHODS:
        with gzip.open(manifest.parent/("episodes_"+method+".jsonl.gz"),"rt",encoding="utf-8") as handle:
            for line in handle:
                record=json.loads(line)
                by_calls={r["host_calls"]:r for r in record["trace"]}
                for decision in record["decisions"]:
                    previous=by_calls.get(decision["at_host_calls"])
                    if previous is not None:
                        lag=(decision["saved_ns"]-previous["completed_ns"])/1e6
                        if lag<0:raise ValueError("decision preceded required completed observation")
                        lags[method].append(lag)
                row=case_scope(record)
                if row is not None:records.append(row)
    summaries={}
    for method in GUARDED:
        selected=[r for r in records if r["method"]==method]
        complete=[r for r in selected if r["first_four_policy_mean_covered"] is not None]
        summaries[method]={"reuse_cases":len(selected),"policy_queries":sum(r["policy_queries"] for r in selected),
            "outside_listed_query_hull":sum(r["outside_listed_query_hull"] for r in selected),
            "cases_with_outside_queries":sum(r["outside_listed_query_hull"]>0 for r in selected),
            "future_four_step_blocks":len(complete),"future_four_step_blocks_covered":sum(r["first_four_policy_mean_covered"] for r in complete),
            "coverage_among_complete_reuse_blocks":sum(r["first_four_policy_mean_covered"] for r in complete)/len(complete) if complete else None,
            "incomplete_or_undefined_reuse_blocks":len(selected)-len(complete)}
    timing={p:{"observed_posttransition_decisions":len(values),"median_ms":float(np.median(values)),
                "p90_ms":float(np.quantile(values,.9)),"max_ms":max(values)} for p,values in lags.items()}
    return {**{k:m[k] for k in ("experiment_run_id","manifest_id","source_git_commit")},"primary_audit_sha256":sha(audit_path),
        "analysis_source_sha256":sha(Path(__file__)),"cases":records,"method_summaries":summaries,"posttransition_decision_lags":timing,
        "new_environment_steps":0,"new_api_calls":0,"physical_response_qualified":False,
        "scope":"Exploratory exact hull diagnosis and implied predecision-fit future-block coverage on realized commands; no fitted threshold, changed decision, prospective interval claim or confidence certification. Decision lags include overhead and are not isolated solver latency."}


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--manifest",type=Path,required=True);p.add_argument("--audit",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args()
    source=a.manifest.resolve();target=a.output.resolve()
    if target.exists() or target==source.parent or source.parent in target.parents:raise FileExistsError("new external diagnosis required")
    result=analyze(source,a.audit.resolve());target.mkdir(parents=True,exist_ok=False)
    (target/"scope.json").write_bytes((json.dumps(result,indent=2,ensure_ascii=False)+"\n").encode("utf-8"))
    print(json.dumps(result["method_summaries"]))

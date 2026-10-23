"""Independently evaluate the linear coefficients and finite-change accounting."""
import argparse
import json
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import run_inverse_error_attribution as run


def close(actual,expected,tolerance=1e-9):
    a,b=np.asarray(actual,float),np.asarray(expected,float)
    if a.shape!=b.shape or not np.isfinite(a).all() or not np.allclose(a,b,atol=tolerance,rtol=0):
        raise ValueError("independent numerical accounting differs")


def independent(model,block,oracle):
    samples=block["samples"]; saved=np.asarray(block["saved_parameters"],float)
    matrix=np.asarray(oracle.matrix_xy,np.float32); bias=np.asarray(oracle.bias_xy,np.float32)
    truth=np.column_stack((matrix,bias)).astype(float).ravel()
    sent=np.array([s.query.command for s in samples]); actual=np.asarray(block["executed_actions"],float)
    target=np.array([s.displacement for s in samples]); x=np.column_stack((sent[:,:2],np.ones(len(sent))))
    true_raw=x@truth.reshape(2,3).T; saved_raw=x@saved.reshape(2,3).T
    tru=sent.copy(); tru[:,:2]=np.clip(true_raw,-1,1)
    fit=sent.copy(); fit[:,:2]=np.clip(saved_raw,-1,1)
    host=np.asarray(sent,np.float32).copy(); host[:,:2]=host[:,:2]@matrix.T+bias
    # Host execution computes each matrix-vector product individually.
    for i in range(len(host)): host[i,:2]=matrix@np.asarray(sent[i,:2],np.float32)+bias
    host=np.clip(host,-1,1).astype(float)
    coefficient=np.asarray(model["coefficients"],float); mean=np.asarray(model["mean"],float); scale=np.asarray(model["scale"],float)
    def predict(commands):
        features=np.asarray([[*s.query.last_displacement,*s.query.prior_displacement,*a] for s,a in zip(samples,commands)])
        return np.column_stack((np.ones(len(features)),(features-mean)/scale))@coefficient
    f0,fs,fa,fm=predict(tru),predict(fit),predict(actual),predict(host)
    residuals={"applied_input_prediction_residual":target-fa,"propagated_input_noise":fa-fm,"host_rounding":fm-f0}
    response=coefficient[7:9,:].T/scale[6:8]
    secant=np.zeros((2*len(samples),6))
    for i in range(len(samples)):
        for act in range(2):
            left,right=true_raw[i,act],saved_raw[i,act]
            weight=(np.clip(right,-1,1)-np.clip(left,-1,1))/(right-left) if left!=right else float(-1<left<1)
            for output in range(2):
                for k in range(3): secant[2*i+output,3*act+k]=response[output,act]*weight*x[i,k]
    inverse=np.linalg.pinv(secant,rcond=1e-10); delta=saved-truth
    components={name:inverse@value.ravel() for name,value in residuals.items()}
    components["fit_residual_adjustment"]=-inverse@(target-fs).ravel()
    components["secant_nullspace"]=delta-inverse@(secant@delta)
    close(sum(components.values()),delta,1e-8)
    scaled=delta/np.array((1.,1.,.3,1.,1.,.3)); norm=float(np.linalg.norm(scaled))
    signed={name:float(scaled@(value/np.array((1.,1.,.3,1.,1.,.3)))/norm) if norm else 0. for name,value in components.items()}
    phase={}
    for name,mask in (("PROBE",np.array([s.step<=8 for s in samples])),("POLICY",np.array([s.step>8 for s in samples]))):
        if mask.any(): phase[name]={"samples":int(mask.sum()),"total_rmse_m":float(np.sqrt(np.mean((target-f0)[mask]**2))),
                                    **{k+"_rmse_m":float(np.sqrt(np.mean(v[mask]**2))) for k,v in residuals.items()}}
    names=tuple(residuals)
    return {"oracle_host_parameters":truth.tolist(),"parameter_error":delta.tolist(),
            "parameter_components":{k:v.tolist() for k,v in components.items()},"signed_scaled_error_contributions":signed,
            "component_mse":{k:float(np.mean(v*v)) for k,v in residuals.items()},
            "cross_mse":{f"{names[i]}__{names[j]}":float(2*np.mean(residuals[names[i]]*residuals[names[j]])) for i in range(3) for j in range(i+1,3)},
            "gain_error_frobenius":float(np.linalg.norm(delta.reshape(2,3)[:,:2])),"bias_error_norm":float(np.linalg.norm(delta.reshape(2,3)[:,2])),
            "scaled_parameter_error_norm":norm,"residual_rmse_m":float(np.sqrt(np.mean((target-f0)**2))),"phase_scores":phase,
            "samples":len(samples),"true_noiseless_xy_clipped_samples":int(np.any(np.abs(true_raw)>=1,axis=1).sum()),
            "saved_noiseless_xy_clipped_samples":int(np.any(np.abs(saved_raw)>=1,axis=1).sum()),
            "actual_xy_boundary_samples":int(np.any(np.abs(actual[:,:2])==1,axis=1).sum()),
            "saved_parameter_bound_active":bool(np.any(np.abs(saved)>=np.array((2.,2.,.3,2.,2.,.3))-1e-8))}


def audit(path):
    manifest=run.load(path); output=path.parent; verified=run.sources(manifest["config"]); pairs=run.extract_pairs(manifest["config"],verified)
    models={declared["id"]:bank for declared,_,_,_,bank in verified}
    result=json.loads((output/"results.json").read_text(encoding="utf-8")); status=json.loads((output/"status.json").read_text(encoding="utf-8"))
    if result["pairs"]!=192 or status["status"]!="COMPLETED_ORACLE_ACCOUNTING" or any(result[k]!=manifest[k] or status[k]!=manifest[k] for k in run.IDENTITY):
        raise ValueError("matching completed reuse analysis required")
    rows={(r["cohort"],r["stream"],r["task"],r["future"]):r for r in result["rows"]}
    if len(rows)!=192 or len(result["rows"])!=192: raise ValueError("complete diagnostic pair population required")
    count=0; comparisons=0
    for pair in pairs:
        row=rows[(pair["cohort"],pair["stream"],pair["task"],pair["future"])]
        if row["direct_outcome"]!=pair["direct_outcome"] or row["passive_outcome"]!=pair["passive_outcome"] or set(row["prefixes"])!={str(k) for k in pair["blocks"]}:
            raise ValueError("source outcomes or eligibility changed")
        for boundary,block in pair["blocks"].items():
            expected=independent(models[pair["cohort"]][pair["task"]],block,pair["oracle"]); actual=row["prefixes"][str(boundary)]
            if actual["scope"]!="EVALUATOR_ONLY_SAVED_INVERSE_ERROR_ACCOUNTING" or any(actual[k] is not False for k in ("controller_returned","physical_response_qualified","probability_guarantee")):
                raise ValueError("oracle-only analysis scope changed")
            if any(not np.isfinite(actual["identity_errors"][k]) or not 0<=actual["identity_errors"][k]<=limit for k,limit in (("residual_max_abs",1e-12),("secant_max_abs",1e-12),("parameter_max_abs",1e-8))):
                raise ValueError("reported numerical identity bound differs")
            for key,value in expected.items():
                if key=="phase_scores":
                    if set(actual[key])!=set(value): raise ValueError("phase population differs")
                    for phase,metrics in value.items():
                        for metric,number in metrics.items(): close(actual[key][phase][metric],number,1e-12); comparisons+=1
                elif isinstance(value,dict):
                    if set(actual[key])!=set(value): raise ValueError("accounting fields differ")
                    for name,number in value.items(): close(actual[key][name],number,1e-8 if "components" in key else 1e-9); comparisons+=1
                else: close(actual[key],value,1e-9); comparisons+=1
            close(actual["covariance_trace"],block["covariance_trace"],1e-12); count+=1
    if result["analyzed_prefixes"]!=count or status["analyzed_prefixes"]!=count or result["group_summaries"]!=run.summarize(result["rows"]):
        raise ValueError("diagnostic summary differs")
    return {**{k:manifest[k] for k in run.IDENTITY},"integrity":"PASSED","pairs":192,"prefixes_checked":count,"numeric_fields_checked":comparisons,
            "artifact_sha256":{p.name:run.digest(p) for p in output.iterdir() if p.is_file()},
            "new_environment_steps":0,"api_calls":0,"controller_fits":0,
            "scope":"Source extraction and authentication reused; linear predictions, clipped secant and projection accounting independently computed. Numerical consistency, not physical cause identification or new method confirmation."}


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("--manifest",type=Path,required=True); parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args(); destination=args.output.resolve()
    if destination.exists() or args.manifest.resolve().parent in destination.parents: raise FileExistsError("new external audit directory required")
    result=audit(args.manifest.resolve()); destination.mkdir(parents=True,exist_ok=False); run.write_json(destination/"audit.json",result)
    print(json.dumps({k:result[k] for k in ("integrity","pairs","prefixes_checked","numeric_fields_checked")}))

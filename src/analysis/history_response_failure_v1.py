"""Posthoc diagnostics of frozen predictors; pure arrays, no fitting or actuation."""
from collections import defaultdict
from contextlib import contextmanager
import builtins
from unittest.mock import patch
import numpy as np

from src.analysis.movement_diagnostic_guard_v1 import read_only_analysis_guard
from src.probe import observable_history_model_v1 as public

MODELS=public.METHODS+("ZERO_DISPLACEMENT","LAST_DISPLACEMENT")
STAGES=("ALL_RESPONSE","FIXED_PROBE","PRE_BOUNDARY","MOVEMENT_ALL","LIFT","POST_LIFT","MEASUREMENT","POST_TASK")
EXCLUSIVE=("FIXED_PROBE","PRE_BOUNDARY","LIFT","POST_LIFT","MEASUREMENT","POST_TASK")
LAGS=(0,1,2)


@contextmanager
def diagnostic_guard():
    """The numerical fitting entry points and unsafe imports fail closed."""
    def denied(*args,**kwargs):raise RuntimeError("zero-fit posthoc diagnostic")
    with read_only_analysis_guard():
        importer=builtins.__import__
        def safe_import(name,*args,**kwargs):
            if name=="torch" or name.startswith("torch.") or name.startswith("scripts.train_observable_history"):
                raise RuntimeError("diagnostic forbids training runtime import")
            return importer(name,*args,**kwargs)
        with patch.object(builtins,"__import__",safe_import),patch.object(public,"fit_linear",denied),patch.object(public,"gru_normalization",denied),patch.object(np.linalg,"solve",denied),patch.object(np.linalg,"lstsq",denied),patch.object(np.linalg,"pinv",denied):yield


def visible(case):
    return public.HistoryTrajectory.from_dict({"task":case["task"],"trajectory_id":case["case_id"],"split":case["split"],
        "initial":case["initial"]["observation"],"commands":[r["command"] for r in case["physical_rows"]],
        "observations":[r["after"]["observation"] for r in case["physical_rows"]]})


def phase_labels(case):
    entry=next((e["payload"] for e in case["behavior"]["events"] if e["kind"]=="ACQUISITION_ENTRY"),None)
    lifted=entry is not None and entry["before"]["observation"][2]>=entry["anchor"][2]-.015;labels=[]
    for r in case["physical_rows"]:
        if r["phase"]=="REPOSITION":
            if entry is None:raise ValueError("movement lacks its actual acquisition entry")
            label="POST_LIFT" if lifted else "LIFT";lifted=lifted or r["after"]["observation"][2]>=entry["anchor"][2]-.015
        else:label={"FIXED_PROBE":"FIXED_PROBE","POLICY":"PRE_BOUNDARY","MEASURE_FEEDBACK":"MEASUREMENT","MEASURE_BALANCED":"MEASUREMENT","TASK_AFTER_MEASUREMENT":"POST_TASK"}[r["phase"]]
        labels.append(label)
    return np.asarray(labels[2:],str)


def mask_for(labels,stage):
    if stage not in STAGES:raise ValueError("registered stage")
    return np.ones(len(labels),bool) if stage=="ALL_RESPONSE" else np.isin(labels,("LIFT","POST_LIFT")) if stage=="MOVEMENT_ALL" else labels==stage


def correlation_matrix(target,source,indices):
    """Target rows have real time indices; source may include the first two inputs."""
    target=np.asarray(target,float);source=np.asarray(source,float);indices=np.asarray(indices,int)
    out=[]
    for lag in LAGS:
        take=indices-lag;valid=(take>=0)&(take<len(source));a=target[valid];b=source[take[valid]];n=len(a);matrix=[]
        if n<3:
            out.append({"lag":lag,"pairs":n,"correlations":[[None]*source.shape[1] for _ in range(target.shape[1])]});continue
        for x in a.T:
            row=[]
            for y in b.T:
                xc=x-x.mean();yc=y-y.mean();den=np.sqrt(float(xc@xc)*float(yc@yc))
                row.append(None if n<3 or den<=1e-24 else float(np.clip(float(xc@yc)/den,-1,1)))
            matrix.append(row)
        out.append({"lag":lag,"pairs":n,"correlations":matrix if n else [[None]*source.shape[1] for _ in range(target.shape[1])]})
    return out


def training_ranges(records,programs,tasks):
    """Descriptive ranges, using only the original TRAIN source-bank trajectories."""
    result={b:{} for b in programs}
    for c in records:
        if c["split"]!="TRAIN":raise ValueError("TRAIN ranges may not consume CAL/TEST")
        bank=c["measurement_program"];task=c["task"];x=public.inputs43(visible(c))[2:]
        if not len(x):raise ValueError("source TRAIN lacks common targets")
        cell=result[bank].get(task)
        if cell is None:cell={"minimum":np.full(43,np.inf),"maximum":np.full(43,-np.inf),"trajectories":0,"responses":0};result[bank][task]=cell
        cell["minimum"]=np.minimum(cell["minimum"],x.min(axis=0));cell["maximum"]=np.maximum(cell["maximum"],x.max(axis=0));cell["trajectories"]+=1;cell["responses"]+=len(x)
    for bank in programs:
        for task in tasks:
            if task not in result[bank]:raise ValueError("missing TRAIN source/task")
            cell=result[bank][task];cell["minimum"]=cell["minimum"].tolist();cell["maximum"]=cell["maximum"].tolist()
    return result


def gru_trace(model,t):
    """Exact frozen GRU, instrumented only at each prediction's last real frame."""
    steps=np.arange(2,len(t.commands));n=len(steps);length=model["window"]
    if length not in (1,16):raise ValueError("frozen history window")
    names=("reset_saturated","update_saturated","candidate_saturated","hidden_saturated","input_affine_rms","hidden_affine_rms")
    trace={k:np.zeros(n) for k in names}
    if not n:return np.empty((0,2)),trace
    x=(public.inputs43(t)-model["input_mean"])/model["input_scale"];h=np.zeros((n,32));starts=np.maximum(0,steps-length+1);lens=steps-starts+1
    p=model["gru"];wi=np.array(p["weight_ih_l0"]);wh=np.array(p["weight_hh_l0"]);bi=np.array(p["bias_ih_l0"]);bh=np.array(p["bias_hh_l0"])
    for k in range(length):
        active=np.flatnonzero(k<lens)
        if not len(active):break
        a=x[starts[active]+k]@wi.T+bi;b=h[active]@wh.T+bh
        ar,az,an=np.split(a,3,axis=1);br,bz,bn=np.split(b,3,axis=1)
        r=np.exp(-np.logaddexp(0,-ar-br));z=np.exp(-np.logaddexp(0,-az-bz));candidate=np.tanh(an+r*bn)
        h[active]=(1-z)*candidate+z*h[active];last=k==lens[active]-1;indices=active[last]
        trace["reset_saturated"][indices]=np.mean((r[last]<.01)|(r[last]>.99),axis=1)
        trace["update_saturated"][indices]=np.mean((z[last]<.01)|(z[last]>.99),axis=1)
        trace["candidate_saturated"][indices]=np.mean(abs(candidate[last])>.99,axis=1)
        trace["hidden_saturated"][indices]=np.mean(abs(h[indices])>.99,axis=1)
        trace["input_affine_rms"][indices]=np.sqrt(np.mean(a[last]**2,axis=1));trace["hidden_affine_rms"][indices]=np.sqrt(np.mean(b[last]**2,axis=1))
    prediction=(h@np.array(model["output_weight"]).T+model["output_bias"])*model["target_scale"]+model["target_mean"]
    if not np.allclose(prediction,public.predict(model,t),atol=1e-12,rtol=1e-9):raise ValueError("tracing changed frozen GRU forward")
    return prediction,trace


def reference_predictions(t,name):
    if name=="ZERO_DISPLACEMENT":return np.zeros((max(len(t.commands)-2,0),2))
    if name=="LAST_DISPLACEMENT":return np.diff(public.states(t)[:,:2],axis=0)[1:-1]
    raise ValueError("descriptive fixed reference only")


def analyze_case(case,bank,ranges,noise,original=None):
    if any(r["logical_step"]!=j or r["noise_cursor_after"]!=j+1 for j,r in enumerate(case["physical_rows"])):raise ValueError("saved physical/noise cursor mismatch")
    t=visible(case);target=public.targets(t);labels=phase_labels(case);count=len(target);x=public.inputs43(t)[2:];outputs=[]
    if np.shape(noise)!=(len(t.commands),3) or len(labels)!=count:raise ValueError("actual noise cursor/history alignment")
    for source,models in bank.items():
        ref=models["GRU_WINDOW16"];scale=np.asarray(ref["target_scale"]);z=(x-ref["input_mean"])/ref["input_scale"]
        geometry=ranges[source][case["task"]];outside=(x<np.asarray(geometry["minimum"])-1e-12)|(x>np.asarray(geometry["maximum"])+1e-12)
        for name in MODELS:
            trace=None
            if name.startswith("GRU_"):prediction,trace=gru_trace(models[name],t)
            elif name in public.METHODS:prediction=public.predict(models[name],t)
            else:prediction=reference_predictions(t,name)
            error=target-prediction
            if original is not None and name in public.METHODS:
                for j in range(count):
                    saved=next(original)
                    if (saved["case_id"],saved["source_bank"],saved["method"],saved["step"],saved["stage"])!=(case["case_id"],source,name,j+2,labels[j]):raise ValueError("original TEST chronology changed")
                    if not np.allclose(saved["prediction"],prediction[j],atol=1e-12,rtol=1e-8) or not np.array_equal(saved["target"],target[j]):raise ValueError("original TEST prediction/target changed")
            for stage in STAGES:
                mask=mask_for(labels,stage);n=int(mask.sum());e=error[mask];y=target[mask];p=prediction[mask];times=np.flatnonzero(mask)+2
                row={**{k:case[k] for k in ("case_id","split","group","task","context","measurement_program")},"source_bank":source,"method":name,"stage":stage,"responses":n,
                    "common_trajectory_responses":count,"missing_reason":None if n else "NO_EXECUTED_COMMON_RESPONSE_IN_STAGE","same_training_source":source==case["measurement_program"],
                    "rmse":None if not n else float(np.sqrt(np.mean(e**2))),"target_rms":None if not n else float(np.sqrt(np.mean(y**2))),"prediction_rms":None if not n else float(np.sqrt(np.mean(p**2))),
                    "bias_xy":None if not n else e.mean(axis=0).tolist(),"standardized_mse":None if not n else float(np.mean((e/scale)**2)),
                    "optimization_sampling_mass":None if not count else n/count,"optimization_error_mass":None if not n else float(np.sum((e/scale)**2)/(2*count)),
                    "raw_noise_correlation":correlation_matrix(e,noise,times),"residual_autocorrelation":correlation_matrix(e,error,times-2)}
                if trace is not None:
                    w=np.asarray(models[name]["gru"]["weight_ih_l0"]);contributions=abs(z)*np.sqrt(np.mean(w*w,axis=0))
                    row["gru"]={"current_input_max_abs_z_mean":None if not n else float(np.mean(np.max(abs(z[mask]),axis=1))),
                        "current_input_any_abs_z_over_3":None if not n else float(np.mean(np.any(abs(z[mask])>3,axis=1))),
                        "current_input_any_abs_z_over_5":None if not n else float(np.mean(np.any(abs(z[mask])>5,axis=1))),
                        "current_input_any_abs_z_over_10":None if not n else float(np.mean(np.any(abs(z[mask])>10,axis=1))),
                        "current_input_any_outside_train_range":None if not n else float(np.mean(np.any(outside[mask],axis=1))),
                        "feature_abs_z_q95":None if not n else np.quantile(abs(z[mask]),.95,axis=0).tolist(),
                        "feature_outside_train_fraction":None if not n else outside[mask].mean(axis=0).tolist(),
                        "feature_input_affine_rms_contribution":None if not n else contributions[mask].mean(axis=0).tolist(),
                        **{k:None if not n else float(v[mask].mean()) for k,v in trace.items()}}
                outputs.append(row)
            masses=[r for r in outputs if r["source_bank"]==source and r["method"]==name and r["stage"] in EXCLUSIVE]
            whole=next(r for r in outputs if r["source_bank"]==source and r["method"]==name and r["stage"]=="ALL_RESPONSE")
            if count and (not np.isclose(sum(r["optimization_sampling_mass"] for r in masses),1) or not np.isclose(sum(r["optimization_error_mass"] or 0 for r in masses),whole["standardized_mse"])):raise ValueError("phase objective mass identity failed")
    return outputs


def average(values):
    valid=[v for v in values if v is not None]
    return None if not valid else float(np.mean(valid))


def grouped(rows,keys):
    """Every row is a trajectory-stage cell; sources and groups never become replicates."""
    cells=defaultdict(list)
    for row in rows:cells[tuple(row[k] for k in keys)].append(row)
    out=[]
    scalar=("rmse","target_rms","prediction_rms","standardized_mse","optimization_sampling_mass","optimization_error_mass","noise_x_lag0","noise_y_lag0","residual_x_lag1","residual_y_lag1",
        "gru_current_input_max_abs_z_mean","gru_current_input_any_abs_z_over_3","gru_current_input_any_abs_z_over_5","gru_current_input_any_abs_z_over_10","gru_current_input_any_outside_train_range",
        "gru_reset_saturated","gru_update_saturated","gru_candidate_saturated","gru_hidden_saturated","gru_input_affine_rms","gru_hidden_affine_rms")
    def value(row,name):
        if name=="optimization_error_mass" and row["responses"]==0 and row["common_trajectory_responses"]>0:return 0.  # Actual empty objective mass, never an imputed predictive error.
        if name.startswith("gru_"):return row.get("gru",{}).get(name[4:])
        if name.startswith("noise_"):return row["raw_noise_correlation"][0]["correlations"][0 if "_x_" in name else 1][0 if "_x_" in name else 1]
        if name.startswith("residual_"):return row["residual_autocorrelation"][1]["correlations"][0 if "_x_" in name else 1][0 if "_x_" in name else 1]
        return row[name]
    for key,part in sorted(cells.items()):
        groups=defaultdict(list)
        for row in part:groups[row["group"]].append(row)
        per_group=[]
        for g,rs in sorted(groups.items()):per_group.append({"group":g,"allocated_trajectory_source_cells":len(rs),"available":sum(r["responses"]>0 for r in rs),**{k:average([value(r,k) for r in rs]) for k in scalar}})
        out.append({**dict(zip(keys,key)),"allocated_cells":len(part),"available_cells":sum(r["responses"]>0 for r in part),"allocated_groups":len(groups),"available_groups":sum(g["available"]>0 for g in per_group),
            "group_values":per_group,**{k:average([g[k] for g in per_group]) for k in scalar}})
    return out


def feature_tables(rows):
    selected=defaultdict(list)
    names=("feature_abs_z_q95","feature_outside_train_fraction","feature_input_affine_rms_contribution")
    for r in rows:selected[tuple(r[k] for k in ("split","task","source_bank","measurement_program","stage"))].append(r)
    tables=[]
    for key,part in sorted(selected.items()):
        groups=[]
        for g in sorted({r["group"] for r in part}):
            valid=[r for r in part if r["group"]==g and r["responses"]>0]
            groups.append({"group":g,"available":len(valid),**{name:None if not valid else np.mean([r["gru"][name] for r in valid],axis=0).tolist() for name in names}})
        valid=[g for g in groups if g["available"]]
        tables.append({**dict(zip(("split","task","source_bank","measurement_program","stage"),key)),"allocated":len(part),"available":sum(r["responses"]>0 for r in part),"groups":groups,
            **{name:None if not valid else np.mean([g[name] for g in valid],axis=0).tolist() for name in names}})
    return tables

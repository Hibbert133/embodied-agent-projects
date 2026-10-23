"""Posthoc evaluation of fixed models only: geometry, terms, semantics and lag evidence."""
from collections import defaultdict
import numpy as np

MODELS=("FROZEN_OLD_LINEAR_ARX","FRESH_LINEAR_ARX","FRESH_QUADRATIC_STATE")
MODES=("TRUE_INTERFACE","APPLIED_INPUT_DIAGNOSTIC","SENT_INPUT")
STAGES=("ALL_RESPONSE","FIXED_PROBE","PRE_BOUNDARY","MOVEMENT_ALL","LIFT","POST_LIFT","POST_TASK",
        "MOVE_1_8","MOVE_9_16","MOVE_17_32","MOVE_33_64")
I,J=np.triu_indices(20)
GROUPS=np.array(["STATE"]*3+["HISTORY"]*6+["COMMAND"]*4+["STATE"]*7)
TERMS=("CONSTANT","LINEAR_STATE","LINEAR_HISTORY","LINEAR_COMMAND","COMMAND_COMMAND","COMMAND_HISTORY","COMMAND_STATE","HISTORY_HISTORY","HISTORY_STATE","STATE_STATE")


def require(ok,message):
    if not ok:raise ValueError(message)


def arrays(case):
    physical=case["physical_rows"];states=np.array([case["initial"]["observation"],*[r["after"]["observation"] for r in physical]],float)
    commands=np.array([r["command"] for r in physical],float).reshape(-1,4)
    require(states.shape==(len(commands)+1,39) and np.isfinite(states).all(),"complete real history required")
    require(all(r["logical_step"]==i and r["noise_cursor_after"]==i+1 for i,r in enumerate(physical)),"continuous actual step/noise cursor required")
    return states,commands


def base_features(states,commands):
    require(len(states)==len(commands)+1,"one current history per command")
    if len(commands)<3:return np.empty((0,20))
    before=states[2:-1];hand=before[:,:3]
    return np.c_[hand,states[2:-1,:3]-states[1:-2,:3],states[1:-2,:3]-states[:-3,:3],commands[2:],before[:,3],before[:,4:7]-hand,before[:,-3:]-hand]


def expanded(z):return np.c_[np.ones(len(z)),z,z[:,I]*z[:,J]]


def geometry(records,model):
    require(records and all(c["split"]=="TRAIN" for c in records),"TRAIN-only geometry; never qualify a model or tune a threshold")
    values=[];weights=[]
    for case in records:
        x=base_features(*arrays(case));require(len(x)>0,"TRAIN real history unavailable")
        values.extend(x);weights.extend([1/len(x)]*len(x))
    x=np.array(values);w=np.array(weights);z=(x-model["mean"])/model["scale"];phi=expanded(z)
    gram=phi.T@(w[:,None]*phi);penalty=.001*np.eye(231);penalty[0,0]=0
    inverse=np.linalg.solve(gram+penalty,np.eye(231))  # geometry, not response fitting
    singular=np.linalg.svd(np.sqrt(w[:,None])*phi,compute_uv=False)
    rank=int(np.sum(singular>singular[0]*max(phi.shape)*np.finfo(float).eps))
    positive=np.linalg.eigvalsh(gram+penalty)
    return {"minimum":x.min(axis=0),"maximum":x.max(axis=0),"inverse":inverse,
        "summary":{"training_trajectories":len(records),"responses":len(x),"columns":231,"design_rank":rank,
            "unregularized_condition":None if rank<231 else float(singular[0]/singular[-1]),
            "penalized_gram_condition":float(positive[-1]/positive[0]),"effective_df":float(np.trace(inverse@gram)),
            "coefficient_l2":float(np.linalg.norm(model["coefficients"])),"feature_minimum":x.min(axis=0).tolist(),"feature_maximum":x.max(axis=0).tolist(),
            "leverage_is_probability_or_safety_bound":False,"new_response_model_fits":0}}


def components(z,coefficient):
    coefficient=np.asarray(coefficient);out={"CONSTANT":np.broadcast_to(coefficient[0],(len(z),2)).copy()}
    for group in ("STATE","HISTORY","COMMAND"):
        mask=GROUPS==group;out["LINEAR_"+group]=z[:,mask]@coefficient[1:21][mask]
    for name in TERMS[4:]:
        left,right=name.split("_");mask=np.array([sorted((GROUPS[i],GROUPS[j]))==[left,right] for i,j in zip(I,J)])
        out[name]=(z[:,I[mask]]*z[:,J[mask]])@coefficient[21:][mask]
    require(np.allclose(sum(out.values()),expanded(z)@coefficient,atol=1e-12,rtol=1e-9),"fixed polynomial term decomposition")
    return out


def stages(case):
    entry=next((e["payload"] for e in case["behavior"]["events"] if e["kind"]=="ACQUISITION_ENTRY"),None)
    lifted=False if entry is None else entry["before"]["observation"][2]>=entry["anchor"][2]-.015
    result=[];move=0
    for r in case["physical_rows"]:
        label="FIXED_PROBE" if r["phase"]=="FIXED_PROBE" else "PRE_BOUNDARY" if r["phase"]=="POLICY" else "POST_TASK"
        labels=["ALL_RESPONSE",label]
        if r["phase"]=="REPOSITION":
            require(entry is not None,"movement entry required");label="POST_LIFT" if lifted else "LIFT"
            move+=1;bin_name="MOVE_1_8" if move<=8 else "MOVE_9_16" if move<=16 else "MOVE_17_32" if move<=32 else "MOVE_33_64"
            labels=["ALL_RESPONSE","MOVEMENT_ALL",label,bin_name]
            lifted=lifted or r["after"]["observation"][2]>=entry["anchor"][2]-.015
        result.append(labels)
    return result


def forecast(model,x):
    values=x if model["method"]==MODELS[2] else x[:,3:13]
    z=(values-model["mean"])/model["scale"]
    phi=expanded(z) if model["method"]==MODELS[2] else np.c_[np.ones(len(z)),z]
    return phi@np.array(model["coefficients"])


def correlations(error,field,indices,lag):
    now=np.array(indices,int);past=now-lag;valid=past>=0;now,past=now[valid],past[valid]
    coefficients=[];pairs=[]
    for axis in (0,1):
        a=error[now,axis];b=field[past,axis];mask=np.isfinite(a)&np.isfinite(b);a,b=a[mask],b[mask];pairs.append(len(a))
        if len(a)>=3 and np.ptp(a)>0 and np.ptp(b)>0:coefficients.append(float(np.corrcoef(a,b)[0,1]))
    return {"value":None if not coefficients else float(np.mean(coefficients)),"valid_axes":len(coefficients),"pairs":min(pairs,default=0),
        "missing_reason":None if coefficients else "SHORT_OR_CONSTANT_SERIES"}


def analyze_case(case,models,train_geometry,noise):
    states,commands=arrays(case);n=len(commands);eligible=max(n-2,0);x=base_features(states,commands);target=np.diff(states[:,:2],axis=0)[2:]
    require(np.shape(noise)==(n,3),"actual noise must match the full actual timeline")
    mode_x={m:x.copy() for m in MODES};support=[]
    for i in range(n):
        r=case["physical_rows"][i];fault=case["fault_oracle"]
        if case["fault_transition"] and i>=case["fault_transition"]["at_calls"]:fault=case["fault_transition"]["active_fault_oracle"]
        mapped=np.array(fault["matrix_xy"])@commands[i,:2]+fault["bias_xy"]
        # Independent float32 replay; no early clipping.
        sent=commands[i].astype(np.float32);latent=np.array(fault["matrix_xy"],np.float32)@sent[:2]+np.array(fault["bias_xy"],np.float32)
        zone=np.array(fault["deadzone_xy"],np.float32);sent[:2]=np.sign(latent)*np.maximum(abs(latent)-zone,0)/(1-zone)
        sent[:3]+=noise[i];applied=np.clip(sent,-1,1)
        require(np.array_equal(applied,np.array(r["executed_action_oracle"],np.float32)),"actuator order or noise alignment")
        if i>=2:
            j=i-2;mode_x[MODES[0]][j,9:11]=np.clip(mapped,-1,1);mode_x[MODES[1]][j,9:13]=r["executed_action_oracle"]
            support.append(bool(np.any(abs(mapped)>1)))
    predictions={mode:{name:forecast(models[name],value) for name in MODELS} for mode,value in mode_x.items()}
    true=mode_x[MODES[0]];quad=models[MODELS[2]];z=(true-quad["mean"])/quad["scale"];phi=expanded(z);parts=components(z,quad["coefficients"])
    leverage=np.einsum("ij,jk,ik->i",phi,train_geometry["inverse"],phi)
    outside=(true<train_geometry["minimum"])|(true>train_geometry["maximum"])
    zmax=np.max(abs(z),axis=1) if eligible else np.array([])
    qpred=predictions[MODES[0]][MODELS[2]];error=target-qpred;applied_error=target-predictions[MODES[1]][MODELS[2]]
    delta=predictions[MODES[1]][MODELS[2]]-qpred
    require(np.allclose(np.sum(error**2,axis=1),np.sum(applied_error**2+delta**2+2*applied_error*delta,axis=1),atol=1e-18,rtol=1e-9),"input semantics decomposition")
    labels=stages(case);rows=[]
    metadata={k:case[k] for k in ("case_id","split","task","group","variant","planned_boundary")}
    for i in range(n):
        row={**metadata,"step":i,"stages":labels[i],"eligible":i>=2,"missing_reason":"TWO_REAL_DISPLACEMENTS_UNAVAILABLE" if i<2 else None}
        if i>=2:
            j=i-2;row.update(target=target[j].tolist(),predictions={m:{k:v[j].tolist() for k,v in bank.items()} for m,bank in predictions.items()},
                max_abs_train_z=float(zmax[j]),outside_train_range_fraction=float(np.mean(outside[j])),regularized_design_leverage=float(leverage[j]),
                transformed_outside_command_envelope=support[j],polynomial_terms={k:v[j].tolist() for k,v in parts.items()},
                input_semantics_delta=delta[j].tolist(),hand_object_distance=float(np.linalg.norm(states[i,:3]-states[i,4:7])),
                object_step_displacement=float(np.linalg.norm(states[i+1,4:7]-states[i,4:7])))
        rows.append(row)
    full_error=np.full((n,2),np.nan);full_error[2:]=error
    linear_error=np.full((n,2),np.nan);linear_error[2:]=target-predictions[MODES[0]][MODELS[1]]
    history=np.full((n,2),np.nan);history[1:]=np.diff(states[:-1,:2],axis=0)
    cells=[]
    for stage in STAGES:
        indices=[i for i in range(2,n) if stage in labels[i]];idx=np.array(indices,int)-2;count=len(idx)
        rmse={m:{name:None if not count else float(np.sqrt(np.mean((target[idx]-predictions[m][name][idx])**2))) for name in MODELS} for m in MODES}
        cell={**metadata,"stage":stage,"executed_steps":sum(stage in s for s in labels),"responses":count,"rmse":rmse,
            "missing_reason":None if count else "NO_REAL_AR2_RESPONSE_IN_STAGE"}
        scalar={"mean_max_abs_train_z":zmax,"mean_outside_train_range_fraction":np.mean(outside,axis=1),"mean_regularized_leverage":leverage,
            "mean_transformed_outside_envelope":np.array(support,float),"quad_error_mse":np.mean(error**2,axis=1),"quad_applied_error_mse":np.mean(applied_error**2,axis=1),
            "input_semantics_delta_mse":np.mean(delta**2,axis=1),"semantics_cross_term":np.mean(2*applied_error*delta,axis=1),
            "polynomial_component_energy":sum(np.mean(v**2,axis=1) for v in parts.values()),"quad_prediction_energy":np.mean(qpred**2,axis=1)}
        cell["descriptors"]={k:None if not count else float(np.mean(v[idx])) for k,v in scalar.items()}
        cell["descriptors"].update(max_abs_train_z=None if not count else float(np.max(zmax[idx])),
            p90_abs_train_z=None if not count else float(np.quantile(zmax[idx],.9)),
            max_regularized_leverage=None if not count else float(np.max(leverage[idx])))
        cell["term_rms"]={k:None if not count else float(np.sqrt(np.mean(v[idx]**2))) for k,v in parts.items()}
        corr={}
        for lag in (0,1,2):
            for name,field in (("sent",commands[:,:2]),("history",history),("noise",noise[:,:2])):corr[f"quad_error__{name}__lag{lag}"]=correlations(full_error,field,indices,lag)
            if lag:
                corr[f"quad_error__self__lag{lag}"]=correlations(full_error,full_error,indices,lag)
                corr[f"linear_error__self__lag{lag}"]=correlations(linear_error,linear_error,indices,lag)
        cell["correlations"]=corr;cells.append(cell)
    return rows,cells


def grouped_summary(cells):
    """Every statistic is trajectory-first then equal independent groups; no step pooling."""
    outputs=[]
    for split in ("TRAIN","CAL","QUAL"):
        for task in ("ALL","push-v3","reach-v3","door-open-v3"):
            for condition in (("ALL","N47001","N47002") if split!="QUAL" else ("ALL","UNCHANGED","CHANGED")):
                for stage in STAGES:
                    part=[c for c in cells if c["split"]==split and (task=="ALL" or c["task"]==task) and (condition=="ALL" or c["variant"]==condition) and c["stage"]==stage]
                    def reduce(get):
                        groups=defaultdict(list)
                        for c in part:
                            v=get(c)
                            if v is not None:groups[c["group"]].append(v)
                        return None if not groups else float(np.mean([np.mean(v) for v in groups.values()]))
                    outputs.append({"split":split,"task":task,"condition":condition,"stage":stage,"allocated":len(part),"available":sum(c["responses"]>0 for c in part),
                        "available_groups":len({c["group"] for c in part if c["responses"]}),
                        "rmse":{m:{n:reduce(lambda c,m=m,n=n:c["rmse"][m][n]) for n in MODELS} for m in MODES},
                        "descriptors":{k:reduce(lambda c,k=k:c["descriptors"][k]) for k in part[0]["descriptors"]},
                        "term_rms":{k:reduce(lambda c,k=k:c["term_rms"][k]) for k in TERMS},
                        "correlations":{k:{"mean":reduce(lambda c,k=k:c["correlations"][k]["value"]),"available_trajectories":sum(c["correlations"][k]["value"] is not None for c in part)} for k in part[0]["correlations"]}})
    return outputs

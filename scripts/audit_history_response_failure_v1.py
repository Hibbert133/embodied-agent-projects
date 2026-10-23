"""Independent scalar/statistical replay of frozen-history posthoc diagnostics."""
import argparse
from collections import defaultdict
from pathlib import Path
import sys
from time import perf_counter_ns
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
from src.analysis import observable_history_io_v1 as io
from src.analysis.history_response_failure_v1 import diagnostic_guard
from src.probe.observable_history_model_v1 import HistoryTrajectory,predict
from scripts.analyze_history_response_failure_v1 import SOURCE,OUTPUT


def near(a,b):
    if b is None:io.require(a is None,"missing numeric cell changed")
    else:io.require(a is not None and np.shape(a)==np.shape(b) and np.allclose(a,b,atol=2e-11,rtol=2e-8),"independent diagnostic value differs")


def arrays(c):
    s=np.array([c["initial"]["observation"],*[r["after"]["observation"] for r in c["physical_rows"]]],float)
    u=np.array([r["command"] for r in c["physical_rows"]]).reshape(-1,4)
    return s,u,np.concatenate([s[:-1],u],axis=1),np.array([s[k+1,:2]-s[k,:2] for k in range(2,len(u))]).reshape(-1,2)


def labels(c):
    e=next((e["payload"] for e in c["behavior"]["events"] if e["kind"]=="ACQUISITION_ENTRY"),None)
    lifted=False if e is None else e["before"]["observation"][2]>=e["anchor"][2]-.015;out=[]
    for r in c["physical_rows"]:
        phase=r["phase"]
        if phase=="REPOSITION":
            out.append("POST_LIFT" if lifted else "LIFT");lifted|=r["after"]["observation"][2]>=e["anchor"][2]-.015
        else:out.append({"FIXED_PROBE":"FIXED_PROBE","POLICY":"PRE_BOUNDARY","MEASURE_FEEDBACK":"MEASUREMENT","MEASURE_BALANCED":"MEASUREMENT","TASK_AFTER_MEASUREMENT":"POST_TASK"}[phase])
    return out[2:]


def selector(labels,stage):return np.array([stage=="ALL_RESPONSE" or x==stage or stage=="MOVEMENT_ALL" and x in ("LIFT","POST_LIFT") for x in labels],bool)


def correlations(a,b,indices,lag):
    a=np.asarray(a,float);b=np.asarray(b,float)
    pairs=[(a[j],b[k-lag]) for j,k in enumerate(indices) if 0<=k-lag<len(b)];n=len(pairs)
    out=[[None for _ in range(b.shape[1])] for _ in range(a.shape[1])]
    if n>=3:
        xs=np.array([p[0] for p in pairs]);ys=np.array([p[1] for p in pairs])
        for i in range(xs.shape[1]):
            for j in range(ys.shape[1]):
                x=xs[:,i]-sum(xs[:,i])/n;y=ys[:,j]-sum(ys[:,j])/n;den=np.sqrt(sum(x*x)*sum(y*y))
                if den>1e-24:out[i][j]=float(np.clip(sum(x*y)/den,-1,1))
    return n,out


def independently_traced(model,x):
    n=max(len(x)-2,0);last_steps=np.arange(2,len(x));start=np.maximum(0,last_steps-model["window"]+1);lengths=last_steps-start+1
    h=np.zeros((n,32));zinput=(x-model["input_mean"])/model["input_scale"]
    wi=np.asarray(model["gru"]["weight_ih_l0"]);wh=np.asarray(model["gru"]["weight_hh_l0"]);bi=np.asarray(model["gru"]["bias_ih_l0"]);bh=np.asarray(model["gru"]["bias_hh_l0"])
    names=("reset_saturated","update_saturated","candidate_saturated","hidden_saturated","input_affine_rms","hidden_affine_rms");out={k:np.zeros(n) for k in names}
    for j in range(model["window"]):
        idx=np.flatnonzero(j<lengths)
        if not len(idx):break
        a=np.einsum("bi,ki->bk",zinput[start[idx]+j],wi)+bi;b=np.einsum("bi,ki->bk",h[idx],wh)+bh
        reset=1/(1+np.exp(np.clip(-a[:,:32]-b[:,:32],-700,700)));update=1/(1+np.exp(np.clip(-a[:,32:64]-b[:,32:64],-700,700)))
        candidate=np.tanh(a[:,64:]+reset*b[:,64:]);h[idx]=update*h[idx]+(1-update)*candidate
        final=j==lengths[idx]-1;at=idx[final]
        out["reset_saturated"][at]=np.count_nonzero((reset[final]<.01)|(reset[final]>.99),axis=1)/32
        out["update_saturated"][at]=np.count_nonzero((update[final]<.01)|(update[final]>.99),axis=1)/32
        out["candidate_saturated"][at]=np.count_nonzero(abs(candidate[final])>.99,axis=1)/32
        out["hidden_saturated"][at]=np.count_nonzero(abs(h[at])>.99,axis=1)/32
        out["input_affine_rms"][at]=np.sqrt(np.sum(a[final]**2,axis=1)/96);out["hidden_affine_rms"][at]=np.sqrt(np.sum(b[final]**2,axis=1)/96)
    return (np.einsum("bi,ki->bk",h,np.array(model["output_weight"]))+model["output_bias"])*model["target_scale"]+model["target_mean"],out


def flatten(row,k):
    if k=="optimization_error_mass" and row["responses"]==0 and row["common_trajectory_responses"]:return 0.
    if k.startswith("gru_"):return row.get("gru",{}).get(k[4:])
    if k.startswith("noise_"):
        j=0 if "_x_" in k else 1;return row["raw_noise_correlation"][0]["correlations"][j][j]
    if k.startswith("residual_"):
        j=0 if "_x_" in k else 1;return row["residual_autocorrelation"][1]["correlations"][j][j]
    return row[k]


def audit(output=OUTPUT):
    start=perf_counter_ns();completion=io.read(output/"completion.json");io.require(completion["status"]=="COMPLETE_FOR_INDEPENDENT_AUDIT","complete analysis required")
    for n,h in completion["analysis_sha256"].items():io.require(io.sha(ROOT/n)==h,"analysis source changed")
    for n,h in completion["artifact_sha256"].items():io.require(io.sha(output/n)==h,"analysis output changed")
    catalog=io.read(output/"source_hashes.json");io.require(all(io.sha(ROOT/n)==h for n,h in catalog.items()),"source mutated")
    with diagnostic_guard():
        models=io.read(SOURCE/"training/models.json")["models"];ranges=io.read(output/"training_ranges.json");own_ranges={}
        for c in io.rows(SOURCE/"train/cases.jsonl.gz"):
            _,_,x,_=arrays(c);key=c["measurement_program"],c["task"]
            if key not in own_ranges:own_ranges[key]=[np.full(43,np.inf),np.full(43,-np.inf),0,0]
            value=own_ranges[key];value[0]=np.minimum(value[0],np.min(x[2:],axis=0));value[1]=np.maximum(value[1],np.max(x[2:],axis=0));value[2]+=1;value[3]+=len(x)-2
        for (b,t),(low,high,n,responses) in own_ranges.items():
            near(ranges[b][t]["minimum"],low);near(ranges[b][t]["maximum"],high);io.require(ranges[b][t]["trajectories"]==n==36 and ranges[b][t]["responses"]==responses,"range population")
        saved=iter(io.rows(output/"trajectory_stage_diagnostics.jsonl.gz"));verified=[];cases=responses=steps=0;registry=io.read(output/"case_registry.json")
        io.require(len(registry)==756,"registry population")
        for split in io.SPLITS:
            for c in io.rows(SOURCE/split.lower()/"cases.jsonl.gz"):
                s,u,x,y=arrays(c);phases=labels(c);count=len(y)
                io.require(all(registry[cases][k]==c[k] for k in ("case_id","split","group","task","context","measurement_program","planned_boundary","success","stop_reason","total_steps","task_steps")) and registry[cases]["common_responses"]==count,"registry changed")
                cases+=1;responses+=count;steps+=len(u)
                key=int(np.random.SeedSequence([c["seed"],57001]).generate_state(1)[0]);noise=np.random.default_rng(key).normal(0,.05,(500,3)).astype("<f4")[:len(u)]
                public=HistoryTrajectory(c["task"],c["case_id"],split,s[0],u,s[1:])
                for source in io.PROGRAMS:
                    bank=models[source][c["task"]];ref=bank["GRU_WINDOW16"];norm=(x[2:]-ref["input_mean"])/ref["input_scale"]
                    outside=(x[2:]<np.asarray(ranges[source][c["task"]]["minimum"])-1e-12)|(x[2:]>np.asarray(ranges[source][c["task"]]["maximum"])+1e-12)
                    for name in (*io.MODELS,"ZERO_DISPLACEMENT","LAST_DISPLACEMENT"):
                        gates=None
                        if name.startswith("GRU_"):
                            prediction,gates=independently_traced(bank[name],x);near(prediction,predict(bank[name],public))
                        elif name=="ZERO_DISPLACEMENT":prediction=np.zeros_like(y)
                        elif name=="LAST_DISPLACEMENT":prediction=s[2:-1,:2]-s[1:-2,:2]
                        else:prediction=predict(bank[name],public)
                        error=y-prediction
                        for stage in ("ALL_RESPONSE","FIXED_PROBE","PRE_BOUNDARY","MOVEMENT_ALL","LIFT","POST_LIFT","MEASUREMENT","POST_TASK"):
                            r=next(saved);io.require((r["case_id"],r["source_bank"],r["method"],r["stage"])==(c["case_id"],source,name,stage),"diagnostic population/order")
                            mask=selector(phases,stage);n=int(sum(mask));e=error[mask];target=y[mask];p=prediction[mask]
                            io.require(r["responses"]==n and r["common_trajectory_responses"]==count and r["missing_reason"]==(None if n else "NO_EXECUTED_COMMON_RESPONSE_IN_STAGE"),"missing population")
                            near(r["rmse"],None if not n else np.sqrt(sum(float(v@v) for v in e)/(2*n)));near(r["target_rms"],None if not n else np.sqrt(sum(float(v@v) for v in target)/(2*n)))
                            near(r["prediction_rms"],None if not n else np.sqrt(sum(float(v@v) for v in p)/(2*n)));near(r["bias_xy"],None if not n else np.sum(e,axis=0)/n)
                            standardized=(e/ref["target_scale"])**2;near(r["standardized_mse"],None if not n else standardized.sum()/(2*n));near(r["optimization_error_mass"],None if not n else standardized.sum()/(2*count));near(r["optimization_sampling_mass"],None if not count else n/count)
                            for lag in range(3):
                                for label,source_array,indices in (("raw_noise_correlation",noise,np.flatnonzero(mask)+2),("residual_autocorrelation",error,np.flatnonzero(mask))):
                                    pairs,corr=correlations(e,source_array,indices,lag);io.require(r[label][lag]["pairs"]==pairs and r[label][lag]["lag"]==lag,"correlation alignment")
                                    for a,b in zip(r[label][lag]["correlations"],corr):
                                        for aa,bb in zip(a,b):near(aa,bb)
                            if gates is not None:
                                g=r["gru"]
                                for k,v in gates.items():near(g[k],None if not n else sum(v[mask])/n)
                                near(g["current_input_max_abs_z_mean"],None if not n else np.mean(np.max(abs(norm[mask]),axis=1)))
                                for limit in (3,5,10):near(g["current_input_any_abs_z_over_"+str(limit)],None if not n else np.count_nonzero(np.any(abs(norm[mask])>limit,axis=1))/n)
                                near(g["current_input_any_outside_train_range"],None if not n else np.count_nonzero(np.any(outside[mask],axis=1))/n)
                                near(g["feature_abs_z_q95"],None if not n else np.percentile(abs(norm[mask]),95,axis=0));near(g["feature_outside_train_fraction"],None if not n else np.sum(outside[mask],axis=0)/n)
                                w=np.asarray(bank[name]["gru"]["weight_ih_l0"]);per_feature=np.sqrt(np.sum(w*w,axis=0)/96)
                                near(g["feature_input_affine_rms_contribution"],None if not n else np.sum(abs(norm[mask])*per_feature,axis=0)/n)
                            verified.append(r)
        io.require(next(saved,None) is None and cases==756 and responses==70261 and steps==71773 and len(verified)==84672,"full diagnostic population required")
        tables=io.read(output/"grouped_tables.json");keys_by_table={"overall":("split","method","stage"),"matched_training":("task","source_bank","method","stage"),"task_context_program":("split","task","context","measurement_program","method","stage"),"source_program_transfer":("split","source_bank","measurement_program","method","stage")}
        for table_name,keys in keys_by_table.items():
            expected=defaultdict(list)
            for r in verified:
                if table_name=="matched_training" and not (r["split"]=="TRAIN" and r["same_training_source"]):continue
                expected[tuple(r[k] for k in keys)].append(r)
            actual=tables[table_name];io.require(len(actual)==len(expected) and {tuple(r[k] for k in keys) for r in actual}==set(expected),"missing/extra grouped cells")
            for cell in actual:
                part=expected[tuple(cell[k] for k in keys)];groups=sorted({r["group"] for r in part})
                io.require(cell["allocated_cells"]==len(part) and cell["available_cells"]==sum(r["responses"]>0 for r in part) and cell["allocated_groups"]==len(groups) and len(cell["group_values"])==len(groups) and cell["available_groups"]==sum(any(r["responses"]>0 for r in part if r["group"]==g) for g in groups),"group counts")
                numeric=[k for k in cell["group_values"][0] if k not in ("group","allocated_trajectory_source_cells","available")]
                values={k:[] for k in numeric}
                for g,old in zip(groups,cell["group_values"]):
                    rs=[r for r in part if r["group"]==g];io.require(old["group"]==g and old["allocated_trajectory_source_cells"]==len(rs) and old["available"]==sum(r["responses"]>0 for r in rs),"independent group denominator")
                    for k in numeric:
                        xs=[flatten(r,k) for r in rs];xs=[x for x in xs if x is not None];value=None if not xs else sum(xs)/len(xs);near(old[k],value)
                        if value is not None:values[k].append(value)
                for k,xs in values.items():near(cell[k],None if not xs else sum(xs)/len(xs))
        original=io.read(SOURCE/"evaluation/statistics.json")
        for name,value in original["means"].items():
            r=next(r for r in tables["overall"] if (r["split"],r["method"],r["stage"])==("TEST",name,"POST_TASK"));near(r["rmse"],value)
        features=io.read(output/"feature_tables.json");population=defaultdict(list)
        for r in verified:
            if r["method"]=="GRU_WINDOW16" and r["stage"] in ("ALL_RESPONSE","POST_TASK"):population[tuple(r[k] for k in ("split","task","source_bank","measurement_program","stage"))].append(r)
        io.require(len(features)==len(population),"feature population")
        for cell in features:
            part=population[tuple(cell[k] for k in ("split","task","source_bank","measurement_program","stage"))];group_ids=sorted({r["group"] for r in part})
            io.require(cell["allocated"]==len(part) and cell["available"]==sum(r["responses"]>0 for r in part) and len(cell["groups"])==len(group_ids),"feature counts")
            for name in ("feature_abs_z_q95","feature_outside_train_fraction","feature_input_affine_rms_contribution"):
                all_groups=[]
                for g,saved_group in zip(group_ids,cell["groups"]):
                    rs=[r for r in part if r["group"]==g and r["responses"]>0];expected=None if not rs else sum(np.array(r["gru"][name]) for r in rs)/len(rs)
                    io.require(saved_group["group"]==g and saved_group["available"]==len(rs),"feature group count");near(saved_group[name],expected)
                    if expected is not None:all_groups.append(expected)
                near(cell[name],None if not all_groups else sum(all_groups)/len(all_groups))
    io.require(all(io.sha(ROOT/n)==h for n,h in catalog.items()),"source changed during audit")
    result={"integrity":"PASSED","scope":"POSTHOC_DESCRIPTIVE_ONLY","executions_checked":756,"real_responses_checked":70261,"trajectory_stage_model_cells_checked":84672,
        "all_gru_gate_and_input_descriptors_recomputed":True,"original_qualification":"NOT_QUALIFIED","new_environment_steps":0,"new_api_calls":0,"new_model_fits":0,"wall_ns":perf_counter_ns()-start,
        "completion_sha256":io.sha(output/"completion.json"),"source_sha256":io.sha(__file__)}
    io.write(output/"independent_audit.json",result);print(result);return result


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--output",type=Path,default=OUTPUT);audit(p.parse_args().output.resolve())

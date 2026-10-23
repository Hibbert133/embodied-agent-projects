"""Independent record/array audit; never import a collector, fit or environment."""
from collections import defaultdict
from pathlib import Path
import sys
from time import perf_counter_ns

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
import numpy.testing
from src.analysis import response_qualification_io_v1 as io
from src.analysis.movement_diagnostic_guard_v1 import read_only_analysis_guard

SOURCE=ROOT/"outputs/response_model_qualification/development_v1/response_qualification_20261020T092011Z_636d6b1f9e39"
OUTPUT=ROOT/"outputs/response_qualification_failure/analysis_v1"
NAMES=("FROZEN_OLD_LINEAR_ARX","FRESH_LINEAR_ARX","FRESH_QUADRATIC_STATE")
MODES=("TRUE_INTERFACE","APPLIED_INPUT_DIAGNOSTIC","SENT_INPUT")
STAGES=("ALL_RESPONSE","FIXED_PROBE","PRE_BOUNDARY","MOVEMENT_ALL","LIFT","POST_LIFT","POST_TASK","MOVE_1_8","MOVE_9_16","MOVE_17_32","MOVE_33_64")


def check(a,b,label="independent numeric differs",atol=2e-11):
    if b is None:io.require(a is None,label)
    else:io.require(a is not None and np.shape(a)==np.shape(b) and np.allclose(a,b,atol=atol,rtol=3e-7),label)


def vector(states,commands):
    values=[]
    for i in range(2,len(commands)):
        s=states[i];values.append([*s[:3],*(s[:3]-states[i-1,:3]),*(states[i-1,:3]-states[i-2,:3]),*commands[i],s[3],*(s[4:7]-s[:3]),*(s[-3:]-s[:3])])
    return np.array(values).reshape(-1,20)


def polynomial(z):return np.column_stack([np.ones(len(z)),z,*[z[:,i]*z[:,j] for i in range(20) for j in range(i,20)]])


def correlation(a,b,indices,lag):
    values=[];lengths=[]
    for axis in (0,1):
        pairs=[(a[i,axis],b[i-lag,axis]) for i in indices if i>=lag and np.isfinite(a[i,axis]) and np.isfinite(b[i-lag,axis])]
        lengths.append(len(pairs))
        if len(pairs)<3:continue
        left,right=np.array(pairs).T
        if max(left)==min(left) or max(right)==min(right):continue
        left=left-left.mean();right=right-right.mean();den=np.linalg.norm(left)*np.linalg.norm(right)
        if den>0:values.append(float(np.dot(left,right)/den))
    return (None if not values else float(np.mean(values))),len(values),min(lengths,default=0)


def run(output=OUTPUT):
    start=perf_counter_ns()
    with read_only_analysis_guard():
        completion=io.read(output/"completion.json");io.require(completion["scope"]=="POSTHOC_DESCRIPTIVE_ONLY","scope")
        io.load(SOURCE/"manifest.json")
        for n,h in completion["artifact_sha256"].items():io.require(io.sha(output/n)==h,"diagnostic artifact changed")
        for n,h in completion["analysis_sha256"].items():io.require(io.sha(ROOT/n)==h,"diagnostic implementation changed")
        for n,h in io.read(output/"source_hashes.json").items():io.require(io.sha(ROOT/n)==h,"original source changed")
        models=io.read(SOURCE/"training/models.json")["models"];geometry=io.read(output/"training_geometry.json");inverses={}
        train=defaultdict(list)
        for case in io.rows(SOURCE/"train/cases.jsonl.gz"):
            states=np.array([case["initial"]["observation"],*[r["after"]["observation"] for r in case["physical_rows"]]])
            train[case["task"]].append(vector(states,np.array([r["command"] for r in case["physical_rows"]])))
        for task,parts in train.items():
            x=np.vstack(parts);weights=np.concatenate([np.full(len(v),1/len(v)) for v in parts]);m=models[task][NAMES[2]]
            z=(x-m["mean"])/m["scale"];phi=polynomial(z);g=phi.T@(weights[:,None]*phi);reg=np.diag([0]+[.001]*230)
            inverses[task]=np.linalg.solve(g+reg,np.eye(231));cell=geometry[task]
            check(cell["feature_minimum"],x.min(axis=0));check(cell["feature_maximum"],x.max(axis=0))
            io.require(cell["responses"]==len(x) and cell["training_trajectories"]==len(parts),"training geometry population")
            check(cell["effective_df"],np.trace(inverses[task]@g),atol=2e-5)
        saved=iter(io.rows(output/"step_diagnostics.jsonl.gz"));cells=io.read(output/"trajectory_stages.json");cell_index={(c["case_id"],c["stage"]):c for c in cells}
        io.require(len(cell_index)==len(cells)==270*11,"all cases and phases required")
        steps=responses=forecasts=identities=0;registry=io.read(output/"case_registry.json");seen=[]
        for split in ("TRAIN","CAL","QUAL"):
            for case in io.rows(SOURCE/split.lower()/"cases.jsonl.gz"):
                seen.append(case["case_id"]);states=np.array([case["initial"]["observation"],*[r["after"]["observation"] for r in case["physical_rows"]]])
                commands=np.array([r["command"] for r in case["physical_rows"]]);n=len(commands);x=vector(states,commands);qs=[];labels=[]
                entry=next((e["payload"] for e in case["behavior"]["events"] if e["kind"]=="ACQUISITION_ENTRY"),None)
                raised=entry is not None and entry["before"]["observation"][2]>=entry["anchor"][2]-.015;movement=0
                for i,physical in enumerate(case["physical_rows"]):
                    row=next(saved);qs.append(row);steps+=1
                    for k in ("case_id","split","task","group","variant","planned_boundary"):io.require(row[k]==case[k],"step source identity")
                    io.require(row["step"]==i and row["eligible"]==(i>=2),"real history chronology")
                    phase=physical["phase"];stage="FIXED_PROBE" if phase=="FIXED_PROBE" else "PRE_BOUNDARY" if phase=="POLICY" else "POST_TASK"
                    tags=["ALL_RESPONSE",stage]
                    if phase=="REPOSITION":
                        movement+=1;stage="POST_LIFT" if raised else "LIFT"
                        segment=next(name for name,a,b in (("MOVE_1_8",1,8),("MOVE_9_16",9,16),("MOVE_17_32",17,32),("MOVE_33_64",33,64)) if a<=movement<=b)
                        tags=["ALL_RESPONSE","MOVEMENT_ALL",stage,segment];raised=raised or physical["after"]["observation"][2]>=entry["anchor"][2]-.015
                    io.require(row["stages"]==tags,"stage definition");labels.append(tags)
                    if i<2:io.require(row["missing_reason"]=="TWO_REAL_DISPLACEMENTS_UNAVAILABLE" and "predictions" not in row,"first history fabricated");continue
                    responses+=1;check(row["target"],states[i+1,:2]-states[i,:2])
                mode_x={mode:x.copy() for mode in MODES};supports=[]
                noise=io.noise(case["seed"],case["noise_namespace"])
                for i,r in enumerate(case["physical_rows"]):
                    fault=case["fault_oracle"] if not case["fault_transition"] or i<case["fault_transition"]["at_calls"] else case["fault_transition"]["active_fault_oracle"]
                    mapped=np.array(fault["matrix_xy"])@commands[i,:2]+fault["bias_xy"]
                    u=commands[i].astype(np.float32);v=np.array(fault["matrix_xy"],np.float32)@u[:2]+np.array(fault["bias_xy"],np.float32)
                    dz=np.array(fault["deadzone_xy"],np.float32);u[:2]=np.sign(v)*np.maximum(abs(v)-dz,0)/(1-dz);u[:3]+=noise[i]
                    io.require(np.array_equal(np.clip(u,-1,1),np.array(r["executed_action_oracle"],np.float32)),"all-step actuator identity")
                    if i>=2:mode_x[MODES[0]][i-2,9:11]=np.clip(mapped,-1,1);mode_x[MODES[1]][i-2,9:13]=r["executed_action_oracle"];supports.append(bool(np.any(abs(mapped)>1)))
                predictions={}
                for mode,inputs in mode_x.items():
                    predictions[mode]={}
                    for name in NAMES:
                        m=models[case["task"]][name];base=inputs if name==NAMES[2] else inputs[:,3:13];z=(base-m["mean"])/m["scale"]
                        phi=polynomial(z) if name==NAMES[2] else np.column_stack([np.ones(len(z)),z]);prediction=phi@np.array(m["coefficients"]);predictions[mode][name]=prediction
                        check([r["predictions"][mode][name] for r in qs[2:]],prediction);forecasts+=len(prediction)
                m=models[case["task"]][NAMES[2]];z=(mode_x[MODES[0]]-m["mean"])/m["scale"];phi=polynomial(z)
                check([r["regularized_design_leverage"] for r in qs[2:]],np.sum((phi@inverses[case["task"]])*phi,axis=1),atol=1e-6)
                outside=(mode_x[MODES[0]]<geometry[case["task"]]["feature_minimum"])|(mode_x[MODES[0]]>geometry[case["task"]]["feature_maximum"])
                check([r["outside_train_range_fraction"] for r in qs[2:]],outside.mean(axis=1));check([r["max_abs_train_z"] for r in qs[2:]],np.max(abs(z),axis=1))
                target=np.diff(states[:,:2],axis=0)[2:];true_error=target-predictions[MODES[0]][NAMES[2]];applied_error=target-predictions[MODES[1]][NAMES[2]]
                delta=predictions[MODES[1]][NAMES[2]]-predictions[MODES[0]][NAMES[2]]
                for j,r in enumerate(qs[2:]):
                    check(sum(np.array(v) for v in r["polynomial_terms"].values()),predictions[MODES[0]][NAMES[2]][j]);check(r["input_semantics_delta"],delta[j])
                    check(np.dot(true_error[j],true_error[j]),np.dot(applied_error[j],applied_error[j])+np.dot(delta[j],delta[j])+2*np.dot(applied_error[j],delta[j]));identities+=1
                    io.require(r["transformed_outside_command_envelope"]==supports[j],"interface domain flag")
                full_error=np.full((n,2),np.nan);full_error[2:]=true_error;linear_error=np.full((n,2),np.nan);linear_error[2:]=target-predictions[MODES[0]][NAMES[1]]
                history=np.full((n,2),np.nan);history[1:]=np.diff(states[:-1,:2],axis=0)
                for stage in STAGES:
                    cell=cell_index[case["case_id"],stage];indices=[i for i in range(2,n) if stage in labels[i]];idx=np.array(indices,int)-2
                    io.require(cell["responses"]==len(indices) and cell["executed_steps"]==sum(stage in t for t in labels),"phase population")
                    io.require(cell["missing_reason"]==(None if indices else "NO_REAL_AR2_RESPONSE_IN_STAGE"),"phase missingness")
                    for mode in MODES:
                        for name in NAMES:check(cell["rmse"][mode][name],None if not indices else np.sqrt(np.mean((target[idx]-predictions[mode][name][idx])**2)))
                    for term in cell["term_rms"]:check(cell["term_rms"][term],None if not indices else np.sqrt(np.mean([np.array(qs[i]["polynomial_terms"][term])**2 for i in indices])))
                    for key,value in cell["correlations"].items():
                        a,field,lag=key.split("__");e=linear_error if a=="linear_error" else full_error;b={"sent":commands[:,:2],"history":history,"noise":noise[:n,:2],"self":e}[field]
                        expected,axes,pairs=correlation(e,b,indices,int(lag[-1]));check(value["value"],expected);io.require((value["valid_axes"],value["pairs"])==(axes,pairs),"lag missingness")
        io.require(next(saved,None) is None and seen==[r["case_id"] for r in registry],"extra/missing diagnostic records")
        summaries=io.read(output/"group_summaries.json")
        for summary in summaries:
            part=[c for c in cells if c["split"]==summary["split"] and c["stage"]==summary["stage"] and (summary["task"]=="ALL" or c["task"]==summary["task"]) and (summary["condition"]=="ALL" or c["variant"]==summary["condition"])]
            io.require(summary["allocated"]==len(part) and summary["available"]==sum(c["responses"]>0 for c in part),"summary full denominator")
            def reduce(get):
                groups=defaultdict(list)
                for c in part:
                    if get(c) is not None:groups[c["group"]].append(get(c))
                return None if not groups else sum(sum(v)/len(v) for v in groups.values())/len(groups)
            for mode in MODES:
                for name in NAMES:check(summary["rmse"][mode][name],reduce(lambda c:c["rmse"][mode][name]))
            for k,value in summary["descriptors"].items():check(value,reduce(lambda c:c["descriptors"][k]))
            for k,value in summary["term_rms"].items():check(value,reduce(lambda c:c["term_rms"][k]))
            for k,value in summary["correlations"].items():check(value["mean"],reduce(lambda c:c["correlations"][k]["value"]))
        io.require((steps,responses,forecasts)==(completion["actual_source_steps"],completion["eligible_real_history_responses"],responses*9),"all actual responses checked")
        result={"integrity":"PASSED","scope":"POSTHOC_DESCRIPTIVE_ONLY","source_steps_checked":steps,"real_history_responses_checked":responses,
            "fixed_predictions_checked":forecasts,"semantics_identities_checked":identities,"trajectory_stage_cells_checked":len(cells),"summary_cells_checked":len(summaries),
            "completion_sha256":io.sha(output/"completion.json"),"auditor_sha256":io.sha(__file__),"wall_ns":perf_counter_ns()-start,
            "new_environment_creations":0,"new_environment_steps":0,"new_all_resets":0,"new_simulation_frames":0,"new_api_calls":0,"new_model_fits":0}
        io.write(output/"independent_audit.json",result)
    print(result)


if __name__=="__main__":run(Path(sys.argv[1]).resolve() if len(sys.argv)>1 else OUTPUT)

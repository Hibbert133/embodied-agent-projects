"""Independent chronological and numerical auditors; never run a collector or environment."""
from collections import Counter,defaultdict
from copy import deepcopy
from dataclasses import asdict
from itertools import groupby
from time import perf_counter_ns

import numpy as np

from src.analysis import response_qualification_io_v1 as io
from src.analysis.capsule_record_json_v2 import normalize
from src.analysis.continuous_state_witness_v1 import compare_witnesses,verify_witness
from src.analysis.short_probe_journal_audit_v1 import applied,check_ledger,ledger_add,simulation
from src.probe.cold_start_response import ColdPrefix,infer_operator
from src.probe.short_joint_reference_v1 import infer_four
from src.probe.continuous import StepObservation
from src.probe.local_reprobe_v1 import anchor_ready,control_update,selected_anchor
from src.probe.physical_reprobe_v1 import Start
from src.probe.operator_identification import affine_controller,encode_controller
from src.rollout.task_registry import create_task_policy


def same(a,b,message="record differs"):
    io.require(io.digest(normalize(a))==io.digest(normalize(b)),message)


def close(a,b,message="numeric audit differs",atol=2e-10):
    if b is None:io.require(a is None,message)
    else:io.require(a is not None and np.shape(a)==np.shape(b) and np.allclose(a,b,atol=atol,rtol=1e-7),message)


def fit_close(saved,expected):
    expected=normalize(expected);io.require(set(saved)==set(expected),"cold fit fields differ")
    for k,v in expected.items():
        if isinstance(v,(list,float)):
            try:close(saved[k],v,"cold fit numeric differs",2e-8)
            except (TypeError,ValueError):same(saved[k],v,"cold fit structure differs")
        else:same(saved[k],v,"cold fit status differs")


def audit_case(spec,case,events,private,model,ledger_before):
    for k,v in spec.items():same(case[k],v,"allocation differs")
    io.require(case["completed"] and case["error"] is None and case["close_error"] is None and case["environment_closed"],"incomplete execution retained, cannot pass audit")
    same(case["ledger_before"],ledger_before);same(case["fault_oracle"],io.initial_fault(spec["split"]));same(case["scheduled_fault_oracle"],io.destination(spec))
    same(case["state_witnesses"],private,"private witness export differs")
    io.require([p["label"] for p in private]==["INITIAL","BOUNDARY","POST_MOVEMENT","FINAL"],"four state witnesses required")
    for p in private:
        same(p["ledger_before"],p["ledger_after"],"witness performed physical work")
        verify_witness(p["witness"],full_sha256=p["source_witness"]["python_semantic_sha256"],native_sha256=p["source_witness"]["native_sha256"])
        io.require(p["source_anchor_saved_ns"]<=p["started_ns"]<=p["completed_ns"]<=p["saved_ns"],"private witness chronology")
        anchor=next((e for e in events if e["sequence"]==p["source_anchor_sequence"]),None)
        io.require(anchor is not None and anchor["saved_ns"]==p["source_anchor_saved_ns"],"witness anchor missing")
    ledger=deepcopy(ledger_before);current=None;steps=[];public=[];global_public={};clock=None;resets=0;queries=0;fits=0;fit_nfev=0
    tape=io.noise(spec["seed"],spec["noise_namespace"]);fault=io.initial_fault(spec["split"]);controller=None;choice_id=None
    policy=create_task_policy(spec["task"]);move_start=None;move_obs=[];integral=[0.,0.];lifted=False;expected_move=None;move_count=tail_count=0
    pending=None;fit_result=None;fit_intent=None;transition=None;task_entry=None;fault_intent=None;initial=None;command_complete=None
    for e in events:
        kind=e["event"]
        if kind=="LIFECYCLE_RESET_INTENT":
            io.require(not steps and e["phase"] in ("GOAL_GENERATION","CONTROLLED_RESET"),"mid-run reset")
            same(e["before"],ledger);ledger=ledger_add(ledger,e["phase"],"reset_attempts",1);resets+=1
        elif kind=="LIFECYCLE_RESET_COMPLETE":
            ledger=simulation(ledger,e["phase"],100,500);ledger=ledger_add(ledger,e["phase"],"reset_completed",1);same(e["after"],ledger,"native reset cost differs")
        elif kind in ("FACTORY_INTENT","FACTORY_COMPLETE"):same(e["ledger"],ledger)
        elif kind=="CONTROLLED_INITIAL":
            same(e["ledger"],ledger);same(e["observation"],case["initial"]["observation"])
            current=deepcopy(case["initial"]);initial=current["observation"];clock=e["simulation_time"]
            io.require(resets==51,"50 factory resets plus one controlled initial reset")
        elif kind=="NOISE_COMMITMENT":
            io.require(not steps and e["namespace_oracle"]==spec["noise_namespace"],"noise namespace differs")
            same(e["tape_sha256_oracle"],io.digest(tape.tolist()))
        elif kind=="AGENT_EVENT":
            p=e["public_payload"];label=e["agent_event"]
            io.require(p["sequence"]==len(public) and p["at_calls"]==len(steps) and p["saved_ns"]<=e["saved_ns"],"public chronology")
            public.append({"kind":label,"payload":deepcopy(p)});global_public[p["sequence"]]=e
            if label=="PROGRAM":
                same(p["initial"],current);same(p["nominal_sha256"],io.digest(model))
                io.require(p["boundary"]==spec["planned_boundary"] and p["maximum_move"]==64 and p["maximum_task"]==32 and p["maximum_total"]==160,"program budget")
            elif label=="FIT_INTENT":
                io.require(len(steps) in (4,8),"unexpected cold fit")
                prefix=ColdPrefix.from_dict(p["prefix"])
                same(prefix.initial_observation,initial);same(prefix.commands,[r["command"] for r in steps]);same(prefix.observations,[r["after"]["observation"] for r in steps])
                same(p["prefix_sha256"],io.digest(p["prefix"]));fit_intent=p
            elif label=="FIT_RESULT":
                io.require(fit_intent is not None and p["intent_sequence"]==fit_intent["sequence"],"fit lacks past evidence")
                prefix=ColdPrefix.from_dict(fit_intent["prefix"])
                expected=infer_four(model,prefix) if len(steps)==4 else infer_operator(model,prefix)
                fit_close(p["fit"],expected);fit_result=p;fits+=1;fit_nfev+=int(expected.get("nfev",0))
            elif label=="CHOICE":
                if p["action"]=="PROBE_FOUR":io.require(len(steps) in (0,4),"unexpected repeated probe")
                else:
                    io.require(fit_result is not None and fit_result["fit"]["valid"] and p["fit_sequence"]==fit_result["sequence"],"invalid cold fit applied")
                    same(p["controller"],affine_controller(fit_result["fit"]["matrix_xy"],fit_result["fit"]["bias_xy"]))
                    io.require(p["action"]==("SAVE_C4_ONLY" if len(steps)==4 else "RUN_C8"),"C4 cannot control task")
                    if len(steps)==8:controller=p["controller"];choice_id=p["sequence"]
            elif label=="ACQUISITION_ENTRY":
                io.require(len(steps)==spec["planned_boundary"] and not any(current[k] for k in ("success","terminated","truncated")),"acquisition boundary")
                same(p["controller"],controller);io.require(p["source_choice_sequence"]==choice_id,"C8 source changed")
                move_start=Start(spec["task"],len(steps),StepObservation(**current),controller["matrix_xy"],controller["offset"][:2])
                same(p["anchor"],selected_anchor(move_start,"LOCAL_PID"));move_obs=[current["observation"]];lifted=current["observation"][2]>=p["anchor"][2]-.015
            elif label=="INTEGRAL_UPDATE":
                io.require(move_start is not None and move_count<64,"extra movement update")
                updated,expected_move=control_update(move_start,move_obs,lifted,integral,"LOCAL_PID")
                same(p["integral_before"],integral);same(p["integral_after"],updated);integral=updated
            elif label=="TASK_ENTRY":
                io.require(move_start is not None and (move_count==64 or anchor_ready(move_obs,selected_anchor(move_start,"LOCAL_PID")) or any(current[k] for k in ("success","terminated","truncated"))),"movement stopped early")
                same(p["controller"],controller);same(p["before"],current);io.require(p["movement_steps"]==move_count,"move cost")
                task_entry=p
            elif label=="COMMAND":
                io.require(pending is None and len(steps)<160 and not any(current[k] for k in ("success","terminated","truncated")),"extra physical command")
                same(p["before"],current);io.require(p["decision_sequence"]<p["sequence"],"future decision")
                source=public[p["decision_sequence"]];phase=p["phase"]
                if phase=="FIXED_PROBE":
                    io.require(source["kind"]=="CHOICE" and source["payload"]["action"]=="PROBE_FOUR" and len(steps)<8,"bad probe selection")
                    program=[[.4,0,0,0],[0,.4,0,0],[-.4,0,0,0],[0,-.4,0,0]]
                    same(p["command"],np.asarray(program[len(steps)%4],np.float32).tolist());io.require(p["raw_policy"] is None,"probe policy query")
                elif phase in ("POLICY","TASK_AFTER_MOVEMENT"):
                    if phase=="POLICY":io.require(8<=len(steps)<spec["planned_boundary"] and p["decision_sequence"]==choice_id,"bad C8 approach")
                    else:io.require(task_entry is not None and p["decision_sequence"]==task_entry["sequence"] and tail_count<32,"task cap or decision")
                    raw=np.asarray(policy.get_action(np.array(current["observation"])),np.float32).tolist();queries+=1
                    same(p["raw_policy"],raw,"fixed-policy output differs");same(p["command"],encode_controller(controller,raw))
                elif phase=="REPOSITION":
                    io.require(transition is not None and source["kind"]=="ACQUISITION_ENTRY" and move_count<64 and not anchor_ready(move_obs,selected_anchor(move_start,"LOCAL_PID")),"invalid movement command")
                    same(p["command"],expected_move);io.require(p["raw_policy"] is None,"movement policy query")
                else:raise ValueError("unknown control phase")
                pending=(p,e)
            elif label=="STEP_RESULT":
                io.require(command_complete is not None and p["command_sequence"]==command_complete["sequence"],"missing command receipt")
                same(p["after"],current)
            elif label=="OUTCOME":
                same(p["final"],current)
                expected={"total_steps":len(steps),"reposition_steps":move_count,"task_steps":tail_count,"policy_queries":queries,
                    "success":current["success"],"terminated":current["terminated"],"truncated":current["truncated"],
                    "stop_reason":case["stop_reason"],"task_utility_established":False,"new_response_model_fits":0}
                same(p["outcome"],expected);same(case["behavior"]["outcome"],expected)
                if case["stop_reason"]=="WINDOW_COMPLETE":io.require(tail_count==32,"early task cutoff")
                if case["stop_reason"] in ("EARLY_PREFIX_END","ENDED_BEFORE_BOUNDARY","EARLY_SUCCESS_OR_ENV_END"):
                    io.require(any(current[k] for k in ("success","terminated","truncated")),"false early ending")
                if case["stop_reason"].startswith("INVALID_"):io.require(fit_result and fit_result["fit"]["valid"] is False,"false invalid fit")
            else:raise ValueError("unknown public event")
        elif kind=="STEP_INTENT":
            io.require(pending is not None and e["logical_step"]==len(steps) and e["global_command_sequence"]==pending[1]["sequence"],"unsaved step intent")
            same(e["ledger_before"],ledger);same(e["command"],pending[0]["command"])
        elif kind=="STEP_COMPLETE":
            p,outer=pending;io.require(e["logical_step"]==len(steps) and e["noise_cursor_after"]==len(steps)+1,"noise cursor")
            same(e["ledger_before"],ledger)
            ledger=simulation(ledger,"CONTROL",1,5);same(e["ledger_after"],ledger)
            io.require(outer["saved_ns"]<=e["execution_started_ns"]<=e["completed_ns"]<=e["saved_ns"],"decision/execution chronology")
            close(e["simulation_time_before"],clock);clock+=.0125;close(e["simulation_time_after"],clock)
            same(e["executed_action_oracle"],applied(p["command"],fault,tape[len(steps)]),"actuator order / actual noise differs")
            for k in ("command","raw_policy","phase"):same(e[k],p[k])
            raw_case_row=case["physical_rows"][len(steps)]
            same({k:e[k] for k in raw_case_row},raw_case_row,"physical export differs")
            steps.append(raw_case_row);current=e["after"];command_complete=p;pending=None
            if p["phase"]=="REPOSITION":
                move_count+=1;move_obs.append(current["observation"]);expected_move=None;lifted=lifted or current["observation"][2]>=selected_anchor(move_start,"LOCAL_PID")[2]-.015
            if p["phase"]=="TASK_AFTER_MOVEMENT":tail_count+=1
        elif kind=="EVALUATOR_FAULT_SET_INTENT":
            io.require(move_start is not None and len(steps)==spec["planned_boundary"] and transition is None,"late or repeated fault change")
            same(e["source_fault_oracle"],io.initial_fault(spec["split"]));same(e["target_fault_oracle"],io.destination(spec));same(e["ledger"],ledger);fault_intent=e
        elif kind=="EVALUATOR_FAULT_SET_COMPLETE":
            io.require(fault_intent is not None and e["intent_sequence"]==fault_intent["sequence"],"unsaved evaluator change")
            same(e["ledger"],ledger)
            for k in ("native_sha256","python_semantic_sha256","noise_past_sha256","simulation_time"):same(e[k],fault_intent[k],"fault change changed physical world")
            fault=io.destination(spec);same(e["active_fault_oracle"],fault)
            transition={"intent_sequence":fault_intent["sequence"],"complete_sequence":e["sequence"],"at_calls":len(steps),"source_fault_oracle":io.initial_fault(spec["split"]),"active_fault_oracle":fault}
        elif kind=="PHYSICAL_BOUNDARY":io.require(len(steps) in (4,8),"unexpected private prefix marker")
        else:raise ValueError("unknown outer event: "+kind)
    same(public,case["behavior"]["events"]);same(public,case["partial_public_events"]);same(transition,case["fault_transition"])
    same(case["ledger_before_close"],ledger);same(case["ledger_after_close"],ledger);check_ledger(ledger)
    io.require(len(steps)==case["total_steps"]==case["host_attempts"]==case["host_returned"] and pending is None,"incomplete physical case")
    io.require(case["policy_queries"]==queries and case["c4_c8_fit_attempts"]==case["c4_c8_fit_results"]==fits<=2,"computation cost differs")
    io.require(not case["captures"] and not case["restores"],"copy/restore forbidden")
    same(current,case["final_observation"])
    return ledger,{"steps":len(steps),"policy_queries":queries,"independent_cold_fit_recomputations":fits,"independent_cold_fit_nfev":fit_nfev}


def audit_split(manifest_path,split):
    manifest=io.load(manifest_path);root=manifest_path.parent;folder=root/split.lower();completion=io.read(folder/"completion.json");start=perf_counter_ns()
    io.require(completion["status"]=="COLLECTED_FOR_INDEPENDENT_AUDIT","partial collection cannot pass")
    for name,h in completion["artifact_sha256"].items():io.require(io.sha(folder/name)==h,"collection hash changed")
    specs=manifest["config"]["population"][split];cases=list(io.rows(folder/"cases.jsonl.gz"))
    io.require(len(cases)==len(specs),"full allocation")
    event_groups=iter(groupby(io.rows(folder/"events.jsonl.gz"),key=lambda e:e["case_id"]))
    private_groups=iter(groupby(io.rows(folder/"witnesses.jsonl.gz"),key=lambda e:e["case_id"]))
    ledger={"counts":{},"by_phase":{}};counts=Counter();sequence=private_sequence=0;stamp=0;qual_prefix={};comparisons=0
    models=io.read(io.ROOT/io.C8)["joint"]
    lock_ns=None if split!="QUAL" else io.read(root/"qualification_lock.json")["saved_ns"]
    for spec,case in zip(specs,cases):
        for k in io.IDENTITY:same(case[k],manifest[k])
        key,event_iterator=next(event_groups);events=list(event_iterator);pkey,piterator=next(private_groups);private=list(piterator)
        io.require(key==pkey==spec["case_id"],"case journal order")
        for e in events:
            io.require(e["sequence"]==sequence and e["saved_ns"]>=stamp,"outer journal sequence/time")
            for k in io.IDENTITY:same(e[k],manifest[k])
            for k in ("case_id","split","group","unit","task","seed","variant"):same(e[k],spec[k])
            sequence+=1;stamp=e["saved_ns"]
        for e in private:
            io.require(e["sequence"]==private_sequence,"private journal sequence");private_sequence+=1
            for k in io.IDENTITY:same(e[k],manifest[k])
            for k in ("case_id","split","group","unit","task","seed","variant"):same(e[k],spec[k])
        if lock_ns is not None:io.require(events[0]["saved_ns"]>lock_ns,"QUAL began before model/CAL lock")
        ledger,cost=audit_case(spec,case,events,private,models[spec["task"]],ledger);counts.update(cost)
        if split=="QUAL":
            key=spec["unit"]
            stop=min(spec["planned_boundary"],len(case["physical_rows"]))
            payload=[{k:r[k] for k in ("logical_step","phase","command","raw_policy","executed_action_oracle","after","noise_cursor_after","simulation_time_before","simulation_time_after")} for r in case["physical_rows"][:stop]]
            if key not in qual_prefix:qual_prefix[key]=(payload,private)
            else:
                same(payload,qual_prefix[key][0],"QUAL conditions differ before boundary")
                for index in (0,1):
                    io.require(compare_witnesses(qual_prefix[key][1][index]["witness"],private[index]["witness"])["comparison_equal"],"paired initial/boundary physical witness differs")
                comparisons+=1
    io.require(next(event_groups,None) is None and next(private_groups,None) is None,"extra unallocated records")
    summary=io.read(folder/"summary.json");same(summary["lifecycle"],ledger);io.require(counts["steps"]==summary["control_steps"] and sequence==summary["events"],"summary cost differs")
    result={**{k:manifest[k] for k in io.IDENTITY},"integrity":"PASSED","split":split,"executions":len(cases),"events_checked":sequence,
        "witness_records_checked":private_sequence,"qual_paired_prefixes_checked":comparisons,"costs":dict(counts),"lifecycle":ledger,
        "completion_sha256":io.sha(folder/"completion.json"),"source_sha256":io.sha(__file__),"wall_ns":perf_counter_ns()-start,
        "new_environment_steps":0,"new_api_calls":0,"new_response_model_fits":0}
    io.write(folder/"audit.json",result);return result


def feature_array(before,last,prior,command,kind):
    if kind=="FRESH_QUADRATIC_STATE":return np.r_[before[:3],last,prior,command,before[3],before[4:7]-before[:3],before[-3:]-before[:3]]
    return np.r_[last,prior,command]


def independent_prediction(model,x):
    z=(x-np.array(model["mean"]))/np.array(model["scale"])
    values=[1.,*z]
    if model["method"]=="FRESH_QUADRATIC_STATE":values.extend(z[i]*z[j] for i in range(20) for j in range(i,20))
    return np.array(values)@np.array(model["coefficients"])


def audit_training(root,bank):
    records=list(io.rows(root/"train/cases.jsonl.gz"));models=bank["models"]
    io.require(len(records)==108 and bank["split_access"]==["TRAIN"] and bank["fits"]==6,"TRAIN-only source")
    same(bank["training_case_ids"],[r["case_id"] for r in records]);same(bank["source_train_sha256"],io.sha(root/"train/cases.jsonl.gz"))
    for task in io.TASKS:
        frozen=io.read(io.ROOT/io.OLD_ARX)["models"][task]["LINEAR_ARX"]
        same(models[task]["FROZEN_OLD_LINEAR_ARX"],{**frozen,"method":"FROZEN_OLD_LINEAR_ARX","task":task})
        for kind in ("FRESH_LINEAR_ARX","FRESH_QUADRATIC_STATE"):
            x=[];y=[];w=[];trajectory_count=0
            for case in records:
                if case["task"]!=task:continue
                states=np.array([case["initial"]["observation"],*[r["after"]["observation"] for r in case["physical_rows"]]])
                count=len(case["physical_rows"])-2;io.require(count>0,"missing TRAIN real history")
                trajectory_count+=1
                for i in range(2,len(states)-1):
                    x.append(feature_array(states[i],states[i,:3]-states[i-1,:3],states[i-1,:3]-states[i-2,:3],case["physical_rows"][i]["command"],kind))
                    y.append(states[i+1,:2]-states[i,:2]);w.append(1/count)
            x,y,w=np.array(x),np.array(y),np.array(w);mean=np.sum(w[:,None]*x,axis=0)/sum(w)
            scale=np.sqrt(np.sum(w[:,None]*(x-mean)**2,axis=0)/sum(w));scale=np.where(scale>1e-6,scale,1.)
            z=(x-mean)/scale;a=np.c_[np.ones(len(x)),z]
            if kind=="FRESH_QUADRATIC_STATE":a=np.column_stack([a,*[z[:,i]*z[:,j] for i in range(20) for j in range(i,20)]])
            reg=np.sqrt(.001)*np.eye(a.shape[1]);reg[0,0]=0
            coefficient=np.linalg.lstsq(np.r_[np.sqrt(w[:,None])*a,reg],np.r_[np.sqrt(w[:,None])*y,np.zeros((a.shape[1],2))],rcond=None)[0]
            saved=models[task][kind];close(saved["mean"],mean);close(saved["scale"],scale);close(saved["coefficients"],coefficient,"independent weighted ridge coefficients",2e-8)
            io.require(saved["training_trajectories"]==trajectory_count and saved["training_responses"]==len(x),"training weight/source count")


def audit_numeric(manifest_path):
    manifest=io.load(manifest_path);root=manifest_path.parent;start=perf_counter_ns();bank=io.read(root/"training/models.json");audit_training(root,bank)
    io.phase_gate(root,"QUAL")
    completion=io.read(root/"evaluation/completion.json")
    io.require(completion["status"]=="COMPLETE_QUALIFICATION_EVALUATION","incomplete evaluation")
    for name,h in completion["artifact_sha256"].items():io.require(io.sha(root/"evaluation"/name)==h,"evaluation changed")
    saved_metrics=io.read(root/"evaluation/trajectory_metrics.json");metric_index={(r["case_id"],r["method"],r["input_mode"],r["stage"]):r for r in saved_metrics}
    predictions=iter(io.rows(root/"evaluation/step_predictions.jsonl.gz"));buckets=defaultdict(list);prediction_count=0;registry=list(io.rows(root/"qual/cases.jsonl.gz"))
    model_names=("FROZEN_OLD_LINEAR_ARX","FRESH_LINEAR_ARX","FRESH_QUADRATIC_STATE")
    same([r["case_id"] for r in registry],[r["case_id"] for r in manifest["config"]["population"]["QUAL"]])
    expected_keys={(c["case_id"],n,m,s) for c in registry for n in model_names for m in ("TRUE_INTERFACE","APPLIED_INPUT_DIAGNOSTIC","SENT_INPUT")
        for s in ("ALL_RESPONSE","FIXED_PROBE","PRE_BOUNDARY","MOVEMENT_ALL","LIFT","POST_LIFT","POST_TASK")}
    io.require(len(saved_metrics)==len(metric_index)==len(expected_keys) and set(metric_index)==expected_keys,"full trajectory/method/input/stage population required")
    for case in registry:
        model_bank=bank["models"][case["task"]];states=np.array([case["initial"]["observation"],*[r["after"]["observation"] for r in case["physical_rows"]]])
        entry=next((e["payload"] for e in case["behavior"]["events"] if e["kind"]=="ACQUISITION_ENTRY"),None)
        lifted=False if entry is None else entry["before"]["observation"][2]>=entry["anchor"][2]-.015
        for i,row in enumerate(case["physical_rows"]):
            stage="FIXED_PROBE" if row["phase"]=="FIXED_PROBE" else "PRE_BOUNDARY" if row["phase"]=="POLICY" else "POST_TASK"
            if row["phase"]=="REPOSITION":stage="POST_LIFT" if lifted else "LIFT";lifted=lifted or row["after"]["observation"][2]>=entry["anchor"][2]-.015
            if i<2:continue
            before=states[i];last=before[:3]-states[i-1,:3];prior=states[i-1,:3]-states[i-2,:3];target=states[i+1,:2]-before[:2]
            fault=case["fault_oracle"] if case["fault_transition"] is None or i<case["fault_transition"]["at_calls"] else case["fault_transition"]["active_fault_oracle"]
            true=np.array(row["command"],float);mapped=np.array(fault["matrix_xy"])@true[:2]+fault["bias_xy"];true[:2]=np.clip(mapped,-1,1)
            for mode,command in (("TRUE_INTERFACE",true),("APPLIED_INPUT_DIAGNOSTIC",row["executed_action_oracle"]),("SENT_INPUT",row["command"])):
                for name in model_names:
                    saved=next(predictions);io.require((saved["case_id"],saved["step"],saved["method"],saved["input_mode"],saved["stage"])==(case["case_id"],i,name,mode,stage),"prediction causal identity")
                    pred=independent_prediction(model_bank[name],feature_array(before,last,prior,command,name));error=target-pred
                    close(saved["prediction"],pred);close(saved["target"],target);close(saved["error"],error)
                    io.require(saved["transformed_input_outside_support"]==bool(np.any(abs(mapped)>1)),"support-domain label")
                    for label in ["ALL_RESPONSE",stage]+(["MOVEMENT_ALL"] if stage in ("LIFT","POST_LIFT") else []):buckets[case["case_id"],name,mode,label].append(error)
                    prediction_count+=1
    io.require(next(predictions,None) is None,"extra future predictions")
    for key,cell in metric_index.items():
        errors=buckets[key];io.require(cell["n"]==len(errors),"stage availability count")
        case=next(c for c in registry if c["case_id"]==key[0])
        for field in ("task","group","unit"):same(cell[field],case[field])
        same(cell["condition"],case["variant"]);same(cell["missing_reason"],None if errors else "NO_EXECUTED_RESPONSE_IN_STAGE")
        close(cell["rmse"],None if not errors else float(np.sqrt(np.sum(np.array(errors)**2)/(2*len(errors)))),"trajectory RMSE")
    stats=io.read(root/"evaluation/statistics.json");group_means=[]
    same([g["group"] for g in stats["groups"]],list(range(18)))
    same([(c["task"],c["condition"]) for c in stats["task_condition_cells"]],[(t,v) for t in io.TASKS for v in ("UNCHANGED","CHANGED")])
    for g in range(18):
        cases=[c for c in registry if c["group"]==g];means={}
        for name in model_names:
            values=[metric_index[c["case_id"],name,"TRUE_INTERFACE","POST_TASK"]["rmse"] for c in cases]
            valid=[v for v in values if v is not None];means[name]=None if not valid else sum(valid)/len(valid)
        for name in model_names:close(stats["groups"][g]["mean_rmse"][name],means[name])
        group_means.append(means)
    complete=all(v[model_names[0]] is not None for v in group_means);means={name:None if not complete else sum(v[name] for v in group_means)/18 for name in model_names}
    for name in model_names:close(stats["means"][name],means[name])
    delta=ci=None
    if complete:
        d=np.array([v[model_names[2]]-v[model_names[1]] for v in group_means]);delta=float(np.mean(d))
        rng=np.random.default_rng(20261025);indices=np.column_stack([3*rng.integers(0,6,(10000,6))+s for s in range(3)])
        distribution=np.sort(np.sum(d[indices],axis=1)/18)
        ci=[]
        for q in (.025,.975):
            t=q*9999;i=int(t);ci.append(float(distribution[i]+(t-i)*(distribution[min(i+1,9999)]-distribution[i])))
    close(stats["primary_difference"],delta);close(stats["primary_group_bootstrap_95"],ci)
    cell_checks=[]
    for cell in stats["task_condition_cells"]:
        mean_cell={}
        for name in model_names:
            values=[metric_index[c["case_id"],name,"TRUE_INTERFACE","POST_TASK"]["rmse"] for c in registry if c["task"]==cell["task"] and c["variant"]==cell["condition"]]
            valid=[v for v in values if v is not None];mean_cell[name]=None if not valid else sum(valid)/len(valid)
            close(cell["means"][name],mean_cell[name]);io.require(cell["available"]==len(valid),"cell denominator")
        cell_checks.append(bool(cell["available"] and mean_cell[model_names[2]]<=max(mean_cell[model_names[0]],mean_cell[model_names[1]])))
    requirements={"all_18_groups_have_observed_primary_response":complete,"all_six_cells_available":all(c["available"]>0 for c in stats["task_condition_cells"]),
        "primary_95_upper_below_zero":ci is not None and ci[1]<0,"quadratic_overall_mean_below_old_linear":complete and means[model_names[2]]<means[model_names[0]],
        "no_cell_worse_than_both_linears":all(cell_checks)}
    same(stats["requirements"],requirements);io.require(stats["qualification"]==("PASSED_PREDICTIVE_QUALIFICATION_ONLY" if all(requirements.values()) else "NOT_QUALIFIED"),"qualification gate changed")
    result={**{k:manifest[k] for k in io.IDENTITY},"integrity":"PASSED","new_environment_steps":0,"new_api_calls":0,"audit_train_model_reconstructions":6,
        "predictions_checked":prediction_count,"trajectory_stage_metrics_checked":len(metric_index),"independent_groups":18,"qualification":stats["qualification"],
        "source_sha256":io.sha(__file__),"models_sha256":io.sha(root/"training/models.json"),"evaluation_sha256":io.sha(root/"evaluation/statistics.json"),"wall_ns":perf_counter_ns()-start}
    io.write(root/"evaluation/numeric_audit.json",result);return result


def audit_models(manifest_path):
    manifest=io.load(manifest_path);root=manifest_path.parent;start=perf_counter_ns()
    audit_training(root,io.read(root/"training/models.json"))
    result={**{k:manifest[k] for k in io.IDENTITY},"integrity":"PASSED","audit_train_model_reconstructions":6,
        "models_sha256":io.sha(root/"training/models.json"),"wall_ns":perf_counter_ns()-start,
        "new_environment_steps":0,"new_api_calls":0,"new_scientific_response_fits":0}
    io.write(root/"training/audit.json",result);return result


def audit_calibration(manifest_path):
    manifest=io.load(manifest_path);root=manifest_path.parent;start=perf_counter_ns()
    models=io.read(root/"training/models.json")["models"];description=io.read(root/"calibration/description.json")
    io.require(description["new_fits"]==0 and not any(description[k] for k in ("model_selection","probability_guarantee","safety_guarantee")),"CAL cannot select/refit or certify")
    same(description["model_sha256"],io.sha(root/"training/models.json"))
    index={(c["case_id"],c["method"]):c for c in description["cases"]};expected_keys=set()
    io.require(len(index)==len(description["cases"])==162,"full CAL model/trajectory population required")
    cases=list(io.rows(root/"cal/cases.jsonl.gz"));io.require(len(cases)==54,"all CAL cases required")
    for case in cases:
        states=np.array([case["initial"]["observation"],*[r["after"]["observation"] for r in case["physical_rows"]]])
        for name,model in models[case["task"]].items():
            key=case["case_id"],name;expected_keys.add(key);errors=[]
            for i in range(2,len(states)-1):
                x=feature_array(states[i],states[i,:3]-states[i-1,:3],states[i-1,:3]-states[i-2,:3],case["physical_rows"][i]["command"],name)
                errors.append(states[i+1,:2]-states[i,:2]-independent_prediction(model,x))
            saved=index[key];io.require(saved["n"]==len(errors),"CAL real history count")
            close(saved["rmse"],None if not errors else float(np.sqrt(np.sum(np.array(errors)**2)/(2*len(errors)))))
            close(saved["maximum_l2"],None if not errors else float(max(np.sqrt(np.dot(e,e)) for e in errors)))
    same(sorted(index),sorted(expected_keys));io.require(len(description["summaries"])==9,"CAL summary population")
    for cell in description["summaries"]:
        values=sorted(c["rmse"] for c in index.values() if c["task"]==cell["task"] and c["method"]==cell["method"] and c["rmse"] is not None)
        io.require(cell["allocated_trajectories"]==18 and cell["available_trajectories"]==len(values),"CAL denominator")
        for q in (.5,.9,.95):
            expected=None
            if values:
                pos=q*(len(values)-1);j=int(pos);expected=values[j]+(pos-j)*(values[min(j+1,len(values)-1)]-values[j])
            close(cell["empirical_rmse_quantiles"][str(q)],expected)
    result={**{k:manifest[k] for k in io.IDENTITY},"integrity":"PASSED","trajectories_checked":54,"model_trajectory_cells_checked":len(index),
        "new_api_calls":0,"new_environment_steps":0,"new_model_fits":0,"wall_ns":perf_counter_ns()-start,
        "description_sha256":io.sha(root/"calibration/description.json")}
    io.write(root/"calibration/audit.json",result);return result

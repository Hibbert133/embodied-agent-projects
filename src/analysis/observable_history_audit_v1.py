"""Independent saved-journal parser: no collector, actor, reset or Env.step calls."""
from collections import Counter
from copy import deepcopy
from itertools import groupby
from time import perf_counter_ns
import numpy as np

from src.analysis import observable_history_io_v1 as io
from src.analysis.response_qualification_audit_v1 import same,close,fit_close
from src.analysis.continuous_state_witness_v1 import compare_witnesses,verify_witness
from src.analysis.short_probe_journal_audit_v1 import applied,check_ledger,ledger_add,simulation
from src.probe.cold_start_response import ColdPrefix,infer_operator
from src.probe.short_joint_reference_v1 import infer_four
from src.probe.continuous import StepObservation
from src.probe.local_reprobe_v1 import anchor_ready,control_update,selected_anchor
from src.probe.physical_reprobe_v1 import Start
from src.probe.operator_identification import affine_controller,encode_controller
from src.rollout.task_registry import create_task_policy

LABELS=("INITIAL","BOUNDARY","POST_MOVEMENT","POST_MEASUREMENT","FINAL")
PHYSICAL=("logical_step","phase","command","raw_policy","executed_action_oracle","after","noise_cursor_after","simulation_time_before","simulation_time_after")


def stopped(state):return any(state[k] for k in ("success","terminated","truncated"))


def audit_case(spec,case,events,private,model,ledger_before):
    for k,v in spec.items():same(case[k],v,"allocation differs")
    io.require(case["completed"] and case["error"] is None and case["close_error"] is None and case["environment_closed"],"incomplete execution cannot pass")
    same(case["ledger_before"],ledger_before);same(case["fault_oracle"],io.initial_fault(spec));same(case["scheduled_fault_oracle"],io.destination(spec))
    actions=io.measurement_program(spec);same(case["planned_balanced_actions"],actions)
    same(case["state_witnesses"],private);io.require([p["label"] for p in private]==list(LABELS),"five ordered witnesses required")
    for p in private:
        same(p["ledger_before"],p["ledger_after"],"witness did physical work")
        verify_witness(p["witness"],full_sha256=p["source_witness"]["python_semantic_sha256"],native_sha256=p["source_witness"]["native_sha256"])
        io.require(p["source_anchor_saved_ns"]<=p["started_ns"]<=p["completed_ns"]<=p["saved_ns"],"witness chronology")
        anchor=next((e for e in events if e["sequence"]==p["source_anchor_sequence"]),None)
        io.require(anchor is not None and anchor["saved_ns"]==p["source_anchor_saved_ns"],"missing witness anchor")
    ledger=deepcopy(ledger_before);current=initial=clock=None;steps=[];public=[];resets=queries=fits=fit_nfev=0
    tape=io.noise(spec["seed"]);fault=io.initial_fault(spec);controller=choice_id=None;policy=create_task_policy(spec["task"])
    move_start=None;move_obs=[];integral=[0.,0.];lifted=False;expected_move=None;move_count=measure_count=tail_count=0
    pending=fit_result=fit_intent=transition=measurement=tail=fault_intent=command_complete=None
    outcome_count=0
    for e in events:
        kind=e["event"]
        if kind=="LIFECYCLE_RESET_INTENT":
            io.require(not steps and e["phase"] in ("GOAL_GENERATION","CONTROLLED_RESET"),"mid-run reset")
            same(e["before"],ledger);ledger=ledger_add(ledger,e["phase"],"reset_attempts",1);resets+=1
        elif kind=="LIFECYCLE_RESET_COMPLETE":
            ledger=simulation(ledger,e["phase"],100,500);ledger=ledger_add(ledger,e["phase"],"reset_completed",1);same(e["after"],ledger)
        elif kind in ("FACTORY_INTENT","FACTORY_COMPLETE"):same(e["ledger"],ledger)
        elif kind=="CONTROLLED_INITIAL":
            same(e["ledger"],ledger);same(e["observation"],case["initial"]["observation"])
            current=deepcopy(case["initial"]);initial=current["observation"];clock=e["simulation_time"]
            io.require(resets==51,"50 factory plus one controlled reset required")
        elif kind=="NOISE_COMMITMENT":
            io.require(not steps and e["namespace_oracle"]==57001,"noise source changed");same(e["tape_sha256_oracle"],io.digest(tape.tolist()))
        elif kind=="AGENT_EVENT":
            p=e["public_payload"];label=e["agent_event"]
            io.require(p["sequence"]==len(public) and p["at_calls"]==len(steps) and p["saved_ns"]<=e["saved_ns"],"public chronology")
            public.append({"kind":label,"payload":deepcopy(p)})
            if label=="PROGRAM":
                same(p["initial"],current);same(p["nominal_sha256"],io.digest(model));same(p["balanced_actions"],actions)
                io.require(p["measurement_program"]==spec["measurement_program"] and p["boundary"]==spec["planned_boundary"],"program differs")
                io.require([p[k] for k in ("maximum_move","maximum_measurement","maximum_task","maximum_total")]==[64,8,32,168],"program cap changed")
            elif label=="FIT_INTENT":
                io.require(len(steps) in (4,8) and fit_intent is None,"extra cold fit")
                prefix=ColdPrefix.from_dict(p["prefix"]);same(prefix.initial_observation,initial)
                same(prefix.commands,[r["command"] for r in steps]);same(prefix.observations,[r["after"]["observation"] for r in steps])
                same(p["prefix_sha256"],io.digest(p["prefix"]));fit_intent=p
            elif label=="FIT_RESULT":
                io.require(fit_intent is not None and p["intent_sequence"]==fit_intent["sequence"],"fit lacks prior evidence")
                prefix=ColdPrefix.from_dict(fit_intent["prefix"]);expected=infer_four(model,prefix) if len(steps)==4 else infer_operator(model,prefix)
                fit_close(p["fit"],expected);fit_result=p;fit_intent=None;fits+=1;fit_nfev+=int(expected.get("nfev",0))
            elif label=="CHOICE":
                if p["action"]=="PROBE_FOUR":io.require(len(steps) in (0,4) and (not fit_result or fit_result["fit"]["valid"]),"extra probe after invalid estimate")
                else:
                    io.require(fit_result is not None and fit_result["fit"]["valid"] and p["fit_sequence"]==fit_result["sequence"],"invalid fit applied")
                    same(p["controller"],affine_controller(fit_result["fit"]["matrix_xy"],fit_result["fit"]["bias_xy"]))
                    io.require(p["action"]==("SAVE_C4_ONLY" if len(steps)==4 else "RUN_C8"),"C4 cannot control")
                    if len(steps)==8:controller=p["controller"];choice_id=p["sequence"]
            elif label=="ACQUISITION_ENTRY":
                io.require(move_start is None and len(steps)==spec["planned_boundary"] and not stopped(current),"live single boundary required")
                same(p["before"],current);same(p["controller"],controller);io.require(p["source_choice_sequence"]==choice_id,"C8 source differs")
                move_start=Start(spec["task"],len(steps),StepObservation(**current),controller["matrix_xy"],controller["offset"][:2])
                same(p["anchor"],selected_anchor(move_start,"LOCAL_PID"));move_obs=[current["observation"]];lifted=current["observation"][2]>=p["anchor"][2]-.015
            elif label=="INTEGRAL_UPDATE":
                io.require(move_start is not None and measurement is None and expected_move is None and move_count<64,"extra movement update")
                updated,expected_move=control_update(move_start,move_obs,lifted,integral,"LOCAL_PID")
                same(p["integral_before"],integral);same(p["integral_after"],updated);integral=updated
            elif label=="MEASUREMENT_ENTRY":
                io.require(move_start is not None and measurement is None and (move_count==64 or anchor_ready(move_obs,selected_anchor(move_start,"LOCAL_PID")) or stopped(current)),"movement stopped early")
                same(p["before"],current);same(p["controller"],controller);same(p["balanced_actions"],actions)
                io.require(p["movement_steps"]==move_count and p["measurement_program"]==spec["measurement_program"] and p["source_choice_sequence"]==choice_id,"measurement source/cost")
                io.require(p["anchor_reached"]==anchor_ready(move_obs,selected_anchor(move_start,"LOCAL_PID")),"anchor status differs");measurement=p
            elif label=="TASK_ENTRY":
                io.require(measurement is not None and tail is None and (measure_count==8 or stopped(current)),"measurement not completed")
                same(p["before"],current);same(p["controller"],controller)
                io.require(p["measurement_steps"]==measure_count and p["source_choice_sequence"]==choice_id,"tail source/cost");tail=p
            elif label=="COMMAND":
                io.require(pending is None and len(steps)<168 and not stopped(current),"extra command")
                same(p["before"],current);io.require(0<=p["decision_sequence"]<p["sequence"],"future decision")
                source=public[p["decision_sequence"]];phase=p["phase"]
                if phase=="FIXED_PROBE":
                    io.require(source["kind"]=="CHOICE" and source["payload"]["action"]=="PROBE_FOUR" and len(steps)<8,"bad fixed probe")
                    expected=np.array([[.4,0,0,0],[0,.4,0,0],[-.4,0,0,0],[0,-.4,0,0]],np.float32)[len(steps)%4]
                    same(p["command"],expected);io.require(p["raw_policy"] is None and p["measurement_desired"] is None,"probe metadata")
                elif phase in ("POLICY","MEASURE_FEEDBACK","TASK_AFTER_MEASUREMENT"):
                    if phase=="POLICY":io.require(measurement is None and move_start is None and 8<=len(steps)<spec["planned_boundary"] and p["decision_sequence"]==choice_id,"bad C8 approach")
                    elif phase=="MEASURE_FEEDBACK":io.require(spec["measurement_program"]=="FEEDBACK8" and measurement is not None and tail is None and measure_count<8 and p["decision_sequence"]==measurement["sequence"],"feedback cap/choice")
                    else:io.require(tail is not None and tail_count<32 and p["decision_sequence"]==tail["sequence"],"task cap/choice")
                    raw=np.asarray(policy.get_action(np.array(current["observation"])),np.float32).tolist();queries+=1
                    same(p["raw_policy"],raw);same(p["command"],encode_controller(controller,raw));io.require(p["measurement_desired"] is None,"unexpected measurement action")
                elif phase=="MEASURE_BALANCED":
                    io.require(spec["measurement_program"]=="BALANCED8" and measurement is not None and tail is None and measure_count<8 and p["decision_sequence"]==measurement["sequence"],"balanced cap/choice")
                    same(p["measurement_desired"],actions[measure_count]);same(p["command"],encode_controller(controller,actions[measure_count]));io.require(p["raw_policy"] is None,"balanced policy query")
                elif phase=="REPOSITION":
                    io.require(transition is not None and measurement is None and source["kind"]=="ACQUISITION_ENTRY" and expected_move is not None and move_count<64 and not anchor_ready(move_obs,selected_anchor(move_start,"LOCAL_PID")),"bad movement")
                    same(p["command"],expected_move);io.require(p["raw_policy"] is None and p["measurement_desired"] is None,"movement metadata")
                else:raise ValueError("unknown phase")
                pending=p,e
            elif label=="STEP_RESULT":
                io.require(command_complete is not None and p["command_sequence"]==command_complete["sequence"],"missing physical receipt");same(p["after"],current);command_complete=None
            elif label=="OUTCOME":
                outcome_count+=1;same(p["final"],current)
                expected={"total_steps":len(steps),"reposition_steps":move_count,"measurement_steps":measure_count,"task_steps":tail_count,"policy_queries":queries,
                    "success":current["success"],"terminated":current["terminated"],"truncated":current["truncated"],"stop_reason":case["stop_reason"],"new_response_model_fits":0,"task_utility_established":False}
                same(p["outcome"],expected);same(case["behavior"]["outcome"],expected)
                if case["stop_reason"]=="WINDOW_COMPLETE":io.require(tail_count==32,"early cutoff")
                elif case["stop_reason"].startswith("INVALID_"):io.require(fit_result and not fit_result["fit"]["valid"],"false invalid fit")
                else:io.require(stopped(current),"false early ending")
            else:raise ValueError("unknown public event")
        elif kind=="STEP_INTENT":
            io.require(pending is not None and e["logical_step"]==len(steps) and e["global_command_sequence"]==pending[1]["sequence"],"unsaved physical intent")
            same(e["ledger_before"],ledger);same(e["command"],pending[0]["command"])
        elif kind=="STEP_COMPLETE":
            io.require(pending is not None,"no saved command");p,outer=pending
            io.require(e["logical_step"]==len(steps) and e["noise_cursor_after"]==len(steps)+1,"noise cursor")
            same(e["ledger_before"],ledger);ledger=simulation(ledger,"CONTROL",1,5);same(e["ledger_after"],ledger)
            io.require(outer["saved_ns"]<=e["execution_started_ns"]<=e["completed_ns"]<=e["saved_ns"],"command saved after execution")
            close(e["simulation_time_before"],clock);clock+=.0125;close(e["simulation_time_after"],clock)
            same(e["executed_action_oracle"],applied(p["command"],fault,tape[len(steps)]),"float32 transform/noise/clip differs")
            for k in ("command","raw_policy","phase"):same(e[k],p[k])
            raw=case["physical_rows"][len(steps)];same({k:e[k] for k in raw},raw,"physical export differs")
            steps.append(raw);current=e["after"];command_complete=p;pending=None
            if p["phase"]=="REPOSITION":
                move_count+=1;move_obs.append(current["observation"]);expected_move=None;lifted=lifted or current["observation"][2]>=selected_anchor(move_start,"LOCAL_PID")[2]-.015
            if p["phase"] in ("MEASURE_BALANCED","MEASURE_FEEDBACK"):measure_count+=1
            if p["phase"]=="TASK_AFTER_MEASUREMENT":tail_count+=1
        elif kind=="EVALUATOR_FAULT_SET_INTENT":
            io.require(move_start is not None and len(steps)==spec["planned_boundary"] and transition is None,"late/repeated context change")
            same(e["source_fault_oracle"],io.initial_fault(spec));same(e["target_fault_oracle"],io.destination(spec));same(e["ledger"],ledger);fault_intent=e
        elif kind=="EVALUATOR_FAULT_SET_COMPLETE":
            io.require(fault_intent is not None and e["intent_sequence"]==fault_intent["sequence"],"unsaved context change");same(e["ledger"],ledger)
            for k in ("native_sha256","python_semantic_sha256","noise_past_sha256","simulation_time"):same(e[k],fault_intent[k],"context changed physical state")
            fault=io.destination(spec);same(e["active_fault_oracle"],fault)
            transition={"intent_sequence":fault_intent["sequence"],"complete_sequence":e["sequence"],"at_calls":len(steps),"source_fault_oracle":io.initial_fault(spec),"active_fault_oracle":fault}
        elif kind=="PHYSICAL_BOUNDARY":io.require(len(steps) in (4,8),"extra prefix marker")
        else:raise ValueError("unknown outer event: "+kind)
    same(public,case["behavior"]["events"]);same(public,case["partial_public_events"]);same(transition,case["fault_transition"])
    same(case["ledger_before_close"],ledger);same(case["ledger_after_close"],ledger);check_ledger(ledger)
    io.require(len(steps)==case["total_steps"]==case["host_attempts"]==case["host_returned"] and pending is None and command_complete is None and outcome_count==1,"incomplete physical execution")
    io.require(case["policy_queries"]==queries and case["c4_c8_fit_attempts"]==case["c4_c8_fit_results"]==fits<=2,"compute cost differs")
    io.require(not case["captures"] and not case["restores"],"copy/restore forbidden");same(current,case["final_observation"])
    for index,label in enumerate(LABELS):
        at=0 if index==0 else (next((e["payload"]["at_calls"] for e in public if e["kind"]=={"BOUNDARY":"ACQUISITION_ENTRY","POST_MOVEMENT":"MEASUREMENT_ENTRY","POST_MEASUREMENT":"TASK_ENTRY"}.get(label)),len(steps)) if index<4 else len(steps))
        io.require(private[index]["logical_step"]==at,"witness at wrong physical step")
    return ledger,{"steps":len(steps),"measurement_steps":measure_count,"policy_queries":queries,"independent_cold_fit_recomputations":fits,"independent_cold_fit_nfev":fit_nfev}


def prefix(case,stop):return [{k:r[k] for k in PHYSICAL} for r in case["physical_rows"][:stop]]


def compare_pair(first,second,indices,stop):
    same(prefix(first,stop),prefix(second,stop),"common physical prefix differs")
    for index in indices:
        io.require(compare_witnesses(first["state_witnesses"][index]["witness"],second["state_witnesses"][index]["witness"])["comparison_equal"],"paired actual-state witness differs")


def audit_split(manifest_path,split):
    manifest=io.load(manifest_path);root=manifest_path.parent;folder=root/split.lower();completion=io.read(folder/"completion.json");start=perf_counter_ns()
    io.require(completion["status"]=="COLLECTED_FOR_INDEPENDENT_AUDIT","partial collection cannot pass")
    for n,h in completion["artifact_sha256"].items():io.require(io.sha(folder/n)==h,"collection hash changed")
    specs=manifest["config"]["population"][split];cases=list(io.rows(folder/"cases.jsonl.gz"));io.require(len(cases)==len(specs),"full allocated population required")
    outer=iter(groupby(io.rows(folder/"events.jsonl.gz"),key=lambda e:e["case_id"]));private=iter(groupby(io.rows(folder/"witnesses.jsonl.gz"),key=lambda e:e["case_id"]))
    ledger={"counts":{},"by_phase":{}};counts=Counter();sequence=psequence=stamp=0;program_pairs={};context_pairs={};pairs=context_checks=0;diverged=0
    models=io.read(io.ROOT/io.C8)["joint"];lock=None if split!="TEST" else io.read(root/"test_lock.json")["saved_ns"]
    for spec,case in zip(specs,cases):
        for k in io.IDENTITY:same(case[k],manifest[k])
        key,it=next(outer);events=list(it);pkey,pit=next(private);ps=list(pit);io.require(key==pkey==spec["case_id"],"journal allocation/order")
        for e in events:
            io.require(e["sequence"]==sequence and e["saved_ns"]>=stamp,"journal sequence/time");sequence+=1;stamp=e["saved_ns"]
            for k in (*io.IDENTITY,"case_id","split","group","unit","task","seed","variant"):same(e[k],manifest[k] if k in io.IDENTITY else spec[k])
        for e in ps:
            io.require(e["sequence"]==psequence,"witness sequence");psequence+=1
            for k in (*io.IDENTITY,"case_id","split","group","unit","task","seed","variant"):same(e[k],manifest[k] if k in io.IDENTITY else spec[k])
        if lock is not None:io.require(events[0]["saved_ns"]>lock,"TEST before lock")
        ledger,cost=audit_case(spec,case,events,ps,models[spec["task"]],ledger);counts.update(cost)
        key=spec["unit"],spec["context"]
        if key not in program_pairs:program_pairs[key]=case
        else:
            first=program_pairs.pop(key);stop=next((e["payload"]["at_calls"] for e in first["behavior"]["events"] if e["kind"]=="MEASUREMENT_ENTRY"),first["total_steps"])
            compare_pair(first,case,(0,1,2),stop);pairs+=1
            diverged+=not compare_witnesses(first["state_witnesses"][3]["witness"],case["state_witnesses"][3]["witness"])["comparison_equal"]
        if split=="TEST":
            key=spec["unit"],spec["context"].split("_")[0],spec["measurement_program"]
            if key not in context_pairs:context_pairs[key]=case
            else:
                first=context_pairs.pop(key);compare_pair(first,case,(0,1),min(spec["planned_boundary"],first["total_steps"]));context_checks+=1
    io.require(not program_pairs and not context_pairs and next(outer,None) is None and next(private,None) is None,"missing/extra pairs")
    summary=io.read(folder/"summary.json");same(summary["lifecycle"],ledger)
    io.require(counts["steps"]==summary["control_steps"] and sequence==summary["events"] and psequence==summary["witness_records"]==5*len(cases),"summary counters")
    result={**{k:manifest[k] for k in io.IDENTITY},"integrity":"PASSED","split":split,"executions":len(cases),"events_checked":sequence,"witness_records_checked":psequence,
        "common_pre_measurement_pairs":pairs,"common_pre_context_change_pairs":context_checks,"post_measurement_diverged_pairs":diverged,"costs":dict(counts),"lifecycle":ledger,
        "completion_sha256":io.sha(folder/"completion.json"),"source_sha256":io.sha(__file__),"wall_ns":perf_counter_ns()-start,"new_environment_steps":0,"new_api_calls":0,"new_response_model_fits":0,
        "scope":"Source-generated native/Python witnesses, not independent physics reproduction."}
    io.write(folder/"audit.json",result);return result


def public_dict(case):
    return {"task":case["task"],"trajectory_id":case["case_id"],"split":case["split"],"initial":case["initial"]["observation"],
        "commands":[r["command"] for r in case["physical_rows"]],"observations":[r["after"]["observation"] for r in case["physical_rows"]]}


def independent_arrays(case,method):
    s=np.array([case["initial"]["observation"],*[r["after"]["observation"] for r in case["physical_rows"]]])
    x=[];y=[]
    for k in range(2,len(s)-1):
        o=s[k];last=o[:3]-s[k-1,:3];prior=s[k-1,:3]-s[k-2,:3];u=case["physical_rows"][k]["command"]
        x.append(np.r_[last,prior,u] if method=="HISTORY_LINEAR10" else np.r_[o[:3],last,prior,u,o[3],o[4:7]-o[:3],o[-3:]-o[:3]])
        y.append(s[k+1,:2]-o[:2])
    return np.array(x).reshape(-1,10 if method=="HISTORY_LINEAR10" else 20),np.array(y).reshape(-1,2)


def independent_design(x,method,mean,scale):
    z=(x-mean)/scale;columns=[np.ones(len(z)),*[z[:,i] for i in range(z.shape[1])]]
    if method=="QUADRATIC_STATE20":columns.extend(z[:,i]*z[:,j] for i in range(20) for j in range(i,20))
    return np.column_stack(columns)


def independent_predictions(case,model):
    if model["method"].startswith("GRU_"):
        # These equations are additionally checked against the isolated Torch
        # implementation on every actual TRAIN/CAL/TEST public trajectory.
        from src.probe.observable_history_model_v1 import HistoryTrajectory,predict
        return predict(model,HistoryTrajectory.from_dict(public_dict(case)))
    x,_=independent_arrays(case,model["method"])
    return independent_design(x,model["method"],model["mean"],model["scale"])@model["coefficients"]


def independent_stages(case):
    entry=next((e["payload"] for e in case["behavior"]["events"] if e["kind"]=="ACQUISITION_ENTRY"),None)
    lifted=entry is not None and entry["before"]["observation"][2]>=entry["anchor"][2]-.015;out=[]
    for r in case["physical_rows"]:
        if r["phase"]=="REPOSITION":
            label="POST_LIFT" if lifted else "LIFT";lifted=lifted or r["after"]["observation"][2]>=entry["anchor"][2]-.015
        else:label={"FIXED_PROBE":"FIXED_PROBE","POLICY":"PRE_BOUNDARY","MEASURE_FEEDBACK":"MEASUREMENT","MEASURE_BALANCED":"MEASUREMENT","TASK_AFTER_MEASUREMENT":"POST_TASK"}[r["phase"]]
        out.append(label)
    return out[2:]


def verify_artifacts(folder,completion):
    for n,h in completion["artifact_sha256"].items():io.require(io.sha(folder/n)==h,"artifact changed: "+n)


def audit_models(manifest_path):
    m=io.load(manifest_path);root=manifest_path.parent;output=root/"training";start=perf_counter_ns()
    saved=io.read(output/"models.json");records=list(io.rows(root/"train/cases.jsonl.gz"));completion=io.read(output/"completion.json")
    io.require(len(records)==216 and saved["fits"]==30 and saved["split_access"]==["TRAIN"] and completion["status"]=="THIRTY_MODELS_SAVED_TRAIN_ONLY","thirty TRAIN-only models required")
    verify_artifacts(output,completion);same(saved["training_case_ids"],[c["case_id"] for c in records]);same(saved["source_train_sha256"],io.sha(root/"train/cases.jsonl.gz"))
    bundle=io.read(output/"public_train_bundle.json");io.require(set(bundle)=={"schema","entries"} and bundle["schema"]=="PUBLIC_TRAIN_BUNDLE_V1" and len(bundle["entries"])==6,"public TRAIN schema")
    entry_index={(e["source_bank"],e["task"]):e for e in bundle["entries"]};io.require(len(entry_index)==6,"duplicate source bank")
    for b,bank in enumerate(io.PROGRAMS):
        for j,task in enumerate(io.TASKS):
            part=[c for c in records if c["measurement_program"]==bank and c["task"]==task];io.require(len(part)==36,"complete source bank")
            entry=entry_index[bank,task];same(entry["trajectories"],[public_dict(c) for c in part])
            io.require(entry["initialization_seed"]==202610260+3*b+j and entry["sampling_seed"]==202610270+3*b+j,"initialization/source schedule")
            for name in io.MODELS[:3]:
                arrays=[independent_arrays(c,name) for c in part];io.require(all(len(x)>0 for x,y in arrays),"TRAIN missing common history")
                x=np.concatenate([x for x,y in arrays]);y=np.concatenate([y for x,y in arrays]);w=np.concatenate([np.repeat(1/len(x),len(x)) for x,y in arrays])
                mean=np.average(x,axis=0,weights=w);scale=np.sqrt(np.average((x-mean)**2,axis=0,weights=w));scale=np.where(scale>1e-6,scale,1.)
                a=independent_design(x,name,mean,scale);r=np.sqrt(.001)*np.eye(a.shape[1]);r[0,0]=0
                coef=np.linalg.lstsq(np.vstack([np.sqrt(w[:,None])*a,r]),np.vstack([np.sqrt(w[:,None])*y,np.zeros((len(r),2))]),rcond=None)[0]
                model=saved["models"][bank][task][name];close(model["mean"],mean);close(model["scale"],scale);close(model["coefficients"],coef,"independent augmented ridge",2e-7)
                io.require(model["method"]==name and model["task"]==task and model["training_trajectories"]==36 and model["training_responses"]==len(x),"source/weight count")
            one=saved["models"][bank][task]["GRU_WINDOW1"];sixteen=saved["models"][bank][task]["GRU_WINDOW16"]
            for field in ("initial_parameters_sha256","sampling_schedule_sha256","input_mean","input_scale","target_mean","target_scale"):same(one[field],sixteen[field],"history controls differ")
            for model in (one,sixteen):
                io.require(model["updates"]==5000 and model["parameter_count"]==7458 and model["training_trajectories"]==36,"fixed GRU capacity/updates")
                for field in ("input_mean","input_scale","target_mean","target_scale"):same(model[field],entry["statistics"][field])
    from src.analysis.observable_history_evaluation_v1 import worker
    worker("audit",output/"public_train_bundle.json",output/"models.json",output/"gru_numeric_audit.json",output/"gru_audit_process.txt")
    io.require(io.read(output/"gru_numeric_audit.json")["integrity"]=="PASSED","independent GRU forward/sampling audit")
    result={**{k:m[k] for k in io.IDENTITY},"integrity":"PASSED","linear_augmented_regressions_reconstructed":18,"gru_models_forward_and_schedule_checked":12,
        "optimizer_replay":False,"model_sha256":io.sha(output/"models.json"),"wall_ns":perf_counter_ns()-start,"new_scientific_fits":0,"new_environment_steps":0,"new_api_calls":0}
    io.write(output/"audit.json",result);return result


def audit_calibration(manifest_path):
    m=io.load(manifest_path);root=manifest_path.parent;start=perf_counter_ns();output=root/"calibration";saved=io.read(output/"description.json")
    verify_artifacts(output,io.read(output/"completion.json"));cases=list(io.rows(root/"cal/cases.jsonl.gz"));models=io.read(root/"training/models.json")["models"]
    io.require(len(cases)==108 and saved["new_fits"]==0 and not any(saved[k] for k in ("model_selection","safety_guarantee","probability_guarantee")),"CAL only describes")
    same(saved["model_sha256"],io.sha(root/"training/models.json"));same(io.read(output/"public_forward_bundle.json")["trajectories"],[public_dict(c) for c in cases])
    index={(r["case_id"],r["source_bank"],r["method"]):r for r in saved["cases"]};io.require(len(index)==len(saved["cases"])==1080,"CAL full population")
    for case in cases:
        _,target=independent_arrays(case,"STATE_LINEAR20")
        for bank in io.PROGRAMS:
            for name in io.MODELS:
                prediction=independent_predictions(case,models[bank][case["task"]][name]);error=target-prediction;r=index[case["case_id"],bank,name]
                io.require(r["n"]==len(target) and r["stage"]=="ALL_RESPONSE","CAL response count")
                close(r["rmse"],None if not len(error) else float(np.sqrt(sum(float(e@e) for e in error)/(2*len(error)))))
    io.require(len(saved["summaries"])==30,"CAL summary population")
    for r in saved["summaries"]:
        values=sorted(x["rmse"] for x in index.values() if (x["task"],x["source_bank"],x["method"])==(r["task"],r["source_bank"],r["method"]) and x["rmse"] is not None)
        io.require(r["allocated"]==36 and r["available"]==len(values),"CAL denominator")
        for q in (.5,.9,.95):
            expected=None
            if values:
                position=q*(len(values)-1);j=int(position);expected=values[j]+(position-j)*(values[min(j+1,len(values)-1)]-values[j])
            close(r["empirical_rmse_quantiles"][str(q)],expected)
    io.require(io.read(output/"torch_forward_audit.json")["integrity"]=="PASSED","independent CAL forward")
    result={**{k:m[k] for k in io.IDENTITY},"integrity":"PASSED","trajectories_checked":108,"model_trajectory_metrics_checked":1080,"wall_ns":perf_counter_ns()-start,"new_api_calls":0,"new_environment_steps":0,"new_scientific_fits":0}
    io.write(output/"audit.json",result);return result


def audit_statistics(stats,metrics,registry):
    """Recompute frozen endpoints with whole groups; no evaluator statistics call."""
    index={(r["case_id"],r["source_bank"],r["method"]):r for r in metrics if r["stage"]=="POST_TASK"}
    means_by_case={}
    for c in registry:
        name=c["case_id"];values={model:[index[name,b,model]["rmse"] for b in io.PROGRAMS] for model in io.MODELS}
        flags=[v is not None for xs in values.values() for v in xs];io.require(all(flags) or not any(flags),"response population differs across models")
        means_by_case[name]={model:None if not all(flags) else sum(xs)/2 for model,xs in values.items()}
    group_values=[]
    for g in range(18):
        ids=[c["case_id"] for c in registry if c["group"]==g];io.require(len(ids)==24,"group allocation")
        valid=[i for i in ids if means_by_case[i][io.MODELS[0]] is not None];values={model:None if not valid else sum(means_by_case[i][model] for i in valid)/len(valid) for model in io.MODELS}
        row=stats["groups"][g];io.require(row["group"]==g and row["allocated"]==24 and row["available"]==len(valid),"group denominator")
        for model in io.MODELS:close(row["means"][model],values[model])
        group_values.append(values)
    complete=all(v[io.MODELS[0]] is not None for v in group_values);overall={model:None if not complete else sum(v[model] for v in group_values)/18 for model in io.MODELS}
    for model in io.MODELS:close(stats["means"][model],overall[model])
    delta=ci=None
    if complete:
        differences=np.array([v["GRU_WINDOW16"]-v["GRU_WINDOW1"] for v in group_values]);rng=np.random.default_rng(20261028)
        strata=[rng.choice(list(range(s,18,3)),size=(10000,6),replace=True) for s in range(3)]
        distribution=np.mean(differences[np.column_stack(strata)],axis=1);delta=sum(differences)/18;ci=np.percentile(distribution,[2.5,97.5])
    close(stats["primary_difference"],delta);close(stats["primary_group_bootstrap_95"],ci)
    io.require(len(stats["task_context_program_cells"])==24,"full 24 cells")
    checks=[]
    for cell in stats["task_context_program_cells"]:
        ids=[c["case_id"] for c in registry if (c["task"],c["context"],c["measurement_program"])==(cell["task"],cell["context"],cell["measurement_program"])];io.require(len(ids)==18,"cell allocation")
        valid=[i for i in ids if means_by_case[i][io.MODELS[0]] is not None];io.require(cell["allocated"]==18 and cell["available"]==len(valid),"cell denominator")
        values={model:None if not valid else sum(means_by_case[i][model] for i in valid)/len(valid) for model in io.MODELS}
        for model in io.MODELS:close(cell["means"][model],values[model])
        check=bool(valid and values["GRU_WINDOW16"]<=max(values["HISTORY_LINEAR10"],values["STATE_LINEAR20"]));io.require(cell["gru16_not_worse_than_both_linears"]==check,"cell gate");checks.append(check)
    requirements={"all_18_groups_have_paired_response":complete,"all_24_cells_nonempty":all(c["available"] for c in stats["task_context_program_cells"]),"primary_95_upper_below_zero":ci is not None and ci[1]<0,
        "gru16_overall_below_history_linear10":bool(complete and overall["GRU_WINDOW16"]<overall["HISTORY_LINEAR10"]),"gru16_overall_below_state_linear20":bool(complete and overall["GRU_WINDOW16"]<overall["STATE_LINEAR20"]),"no_cell_worse_than_both_linears":all(checks)}
    same(stats["requirements"],requirements);io.require(stats["qualification"]==("PASSED_PREDICTIVE_QUALIFICATION_ONLY" if all(requirements.values()) else "NOT_QUALIFIED"),"qualification changed")
    io.require(stats["allocated_executions"]==432 and stats["independent_groups"]==18 and stats["available_primary_trajectories"]==sum(v[io.MODELS[0]] is not None for v in means_by_case.values()),"global denominator")
    io.require(len(stats["source_transfer"])==5,"all transfer representations")
    for row in stats["source_transfer"]:
        for key,cell in row["crosses"].items():
            bank,program=key.split("->");group_means=[]
            for g in range(18):
                xs=[index[c["case_id"],bank,row["method"]]["rmse"] for c in registry if c["group"]==g and c["measurement_program"]==program];xs=[x for x in xs if x is not None]
                group_means.append(None if not xs else sum(xs)/len(xs))
            io.require(len(cell["group_means"])==18,"transfer groups")
            for actual,expected in zip(cell["group_means"],group_means):close(actual,expected)
            close(cell["mean"],None if any(x is None for x in group_means) else sum(group_means)/18)
        interactions=[]
        for g in range(18):
            xs=[row["crosses"][a+"->"+b]["group_means"][g] for a,b in (("FEEDBACK8","FEEDBACK8"),("FEEDBACK8","BALANCED8"),("BALANCED8","FEEDBACK8"),("BALANCED8","BALANCED8"))]
            interactions.append(None if any(x is None for x in xs) else xs[0]-xs[1]-xs[2]+xs[3])
        io.require(len(row["group_difference_in_differences"])==18,"interaction groups")
        for actual,expected in zip(row["group_difference_in_differences"],interactions):close(actual,expected)
        close(row["descriptive_interaction_mean"],None if any(x is None for x in interactions) else sum(interactions)/18)


def audit_numeric(manifest_path):
    m=io.load(manifest_path);root=manifest_path.parent;output=root/"evaluation";start=perf_counter_ns();completion=io.read(output/"completion.json");verify_artifacts(output,completion)
    cases=list(io.rows(root/"test/cases.jsonl.gz"));registry=io.read(output/"case_registry.json");metrics=io.read(output/"trajectory_metrics.json");models=io.read(root/"training/models.json")["models"]
    io.require(len(cases)==432 and len(registry)==432 and len(metrics)==432*10*8,"TEST full population")
    same(io.read(output/"public_forward_bundle.json")["trajectories"],[public_dict(c) for c in cases]);io.require(io.read(output/"torch_forward_audit.json")["integrity"]=="PASSED","independent TEST GRU equations")
    table={(r["case_id"],r["source_bank"],r["method"],r["stage"]):r for r in metrics};io.require(len(table)==len(metrics),"duplicated metric")
    logged=iter(io.rows(output/"step_predictions.jsonl.gz"));count=0
    for case,registered in zip(cases,registry):
        same(registered,{k:case[k] for k in registered});_,target=independent_arrays(case,"STATE_LINEAR20");labels=independent_stages(case)
        for bank in io.PROGRAMS:
            for name in io.MODELS:
                prediction=independent_predictions(case,models[bank][case["task"]][name]);error=target-prediction
                for k in range(len(target)):
                    r=next(logged);io.require((r["case_id"],r["source_bank"],r["method"],r["step"],r["stage"])==(case["case_id"],bank,name,k+2,labels[k]),"prediction chronology/source")
                    close(r["prediction"],prediction[k]);close(r["target"],target[k]);close(r["error"],error[k]);count+=1
                for label in ("ALL_RESPONSE","FIXED_PROBE","PRE_BOUNDARY","MOVEMENT_ALL","LIFT","POST_LIFT","MEASUREMENT","POST_TASK"):
                    selected=[e for e,s in zip(error,labels) if label=="ALL_RESPONSE" or label==s or label=="MOVEMENT_ALL" and s in ("LIFT","POST_LIFT")]
                    r=table[case["case_id"],bank,name,label];io.require(r["n"]==len(selected),"stage count")
                    close(r["rmse"],None if not selected else np.sqrt(sum(float(e@e) for e in selected)/(2*len(selected))))
                    io.require(r["missing_reason"]==(None if selected else "NO_EXECUTED_COMMON_RESPONSE_IN_STAGE"),"missing stage must remain null")
    io.require(next(logged,None) is None,"extra predictions");audit_statistics(io.read(output/"statistics.json"),metrics,registry)
    result={**{k:m[k] for k in io.IDENTITY},"integrity":"PASSED","actual_trajectories_checked":432,"stage_metrics_checked":len(metrics),"predictions_checked":count,
        "independent_groups":18,"new_environment_steps":0,"new_api_calls":0,"new_scientific_fits":0,"wall_ns":perf_counter_ns()-start,"statistics_sha256":io.sha(output/"statistics.json")}
    io.write(output/"numeric_audit.json",result);return result

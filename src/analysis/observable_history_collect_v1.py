"""Continuous collector with five causal witnesses and saved measurement commands."""
from copy import deepcopy
from dataclasses import asdict
import gzip
import json
from time import perf_counter_ns
import numpy as np

from src.analysis import observable_history_io_v1 as io
from src.analysis.capsule_record_json_v2 import JsonJournal,normalize
from src.analysis.paired_probe_host_v1 import ProbeSession
from src.analysis.stale_reprobe_context_v1 import install_context
from src.probe import observable_history_behavior_v1 as behavior
from src.probe.cold_start_response import ColdPrefix
from src.probe.lifecycle_ledger import LifecycleLedger
from src.probe.local_reprobe_v1 import anchor_ready,control_update,selected_anchor
from src.probe.operator_identification import affine_controller,encode_controller
from src.probe.physical_reprobe_v1 import Start
from src.rollout.task_registry import create_task_environment,create_task_policy
from scripts.qualify_delayed_intervention_v2 import observe_state


class CollectionFailure(RuntimeError):
    def __init__(self,row):super().__init__(str(row.get("error")));self.record=row


def execute_case(spec,model,emit,emit_private,ledger,budget,position):
    actions=io.measurement_program(spec)
    row={**spec,"completed":False,"error":None,"close_error":None,"environment_closed":False,"fault_oracle":io.initial_fault(spec),
        "scheduled_fault_oracle":io.destination(spec),"fault_transition":None,"planned_balanced_actions":actions,"state_witnesses":[],"physical_rows":[],"ledger_before":ledger.snapshot()}
    session=env=None;events=[];pending_raw=None;controller=None;move_start=None;move_obs=[];integral=[0.,0.];lifted=False;expected_move=None;measurement=None
    labels=[];started=perf_counter_ns()
    def witness(label):
        row["state_witnesses"].append(observe_state(session,label,session.witness(),position,emit_private));labels.append(label)
    try:
        emit("FACTORY_INTENT",{"ledger":ledger.snapshot()})
        with ledger.scope("FACTORY_SETUP"):env=create_task_environment(spec["task"],spec["seed"])
        emit("FACTORY_COMPLETE",{"ledger":ledger.snapshot()})
        with ledger.scope("CONTROLLED_RESET"):initial,_=env.reset(seed=spec["seed"])
        session=ProbeSession(env,create_task_policy(spec["task"]),initial,spec["task"],spec["seed"],row["fault_oracle"],emit,ledger,budget)
        session.ctx["noise_rows"]=io.noise(spec["seed"],spec["noise_namespace"])
        tape=session.ctx["noise_rows"];base=env.unwrapped;addresses=(base.model._address,base.data._address);clock=float(base.data.time)
        resets={k:ledger.counts.get(k,0) for k in ("reset_attempts","reset_completed","reset_errors")};frames=ledger.counts.get("simulation_frames_completed",0);steps=budget["completed"]
        session.branch={"role":"OBSERVABLE_HISTORY_FIXED_COLLECTION","future":0,"program":"C8_PID_MEASURE8_C8_32"}
        row["initial"]=asdict(session.public());witness("INITIAL")
        emit("NOISE_COMMITMENT",{"at_calls":0,"namespace_oracle":spec["noise_namespace"],"tape_sha256_oracle":io.digest(tape.tolist())})
        def continuous():
            io.require(session.env.unwrapped is base and (base.model._address,base.data._address)==addresses,"world replaced")
            io.require(session.ctx["noise_rows"] is tape and not tape.flags.writeable,"noise tape replaced")
            io.require(all(ledger.counts.get(k,0)==v for k,v in resets.items()),"reset after controlled initial")
            calls=session.ctx["calls"]
            io.require(calls==session.completed==session.attempts==len(session.last_rows)<=168,"physical counters")
            io.require(budget["completed"]-steps==calls and ledger.counts.get("simulation_frames_completed",0)-frames==5*calls,"physical cost discontinuity")
            io.require(np.isclose(float(base.data.time)-clock,.0125*calls,atol=1e-9,rtol=0),"clock discontinuity")
            io.require(not session.captures and not session.restores and not session._snapshots,"copy/restore forbidden")
        def policy(observation):
            nonlocal pending_raw
            continuous();io.require(pending_raw is None and np.array_equal(observation,session.public().observation),"duplicate or stale policy query")
            pending_raw=session.policy_query(observation).tolist();return np.array(pending_raw,np.float32)
        def save(name,payload):
            nonlocal controller,move_start,move_obs,integral,lifted,expected_move,measurement
            continuous();io.require(payload["at_calls"]==session.ctx["calls"] and session._pending is None,"stale event")
            if name=="PROGRAM":io.require(payload["measurement_program"]==spec["measurement_program"] and payload["balanced_actions"]==actions,"prescribed program changed")
            if name=="FIT_INTENT":
                p=ColdPrefix.from_dict(payload["prefix"])
                io.require(p.initial_observation==tuple(initial) and np.array_equal(p.commands,session.ctx["commands"]) and np.array_equal(p.observations,session.ctx["observations"]),"non-causal cold prefix")
            if name=="CHOICE" and payload["action"] in ("SAVE_C4_ONLY","RUN_C8"):
                source=events[payload["fit_sequence"]];io.require(source["kind"]=="FIT_RESULT" and source["payload"]["fit"]["valid"],"invalid fit used")
                f=source["payload"]["fit"];io.require(payload["controller"]==affine_controller(f["matrix_xy"],f["bias_xy"]),"inverse differs")
                if payload["action"]=="RUN_C8":controller=deepcopy(payload["controller"])
            if name=="ACQUISITION_ENTRY":
                io.require(session.alive() and session.ctx["calls"]==spec["planned_boundary"] and payload["controller"]==controller,"bad live boundary")
                move_start=Start(spec["task"],session.ctx["calls"],session.public(),controller["matrix_xy"],controller["offset"][:2]);anchor=selected_anchor(move_start,"LOCAL_PID")
                io.require(payload["anchor"]==list(anchor),"anchor changed");move_obs=[session.public().observation];integral=[0.,0.];lifted=move_obs[-1][2]>=anchor[2]-.015
            if name=="INTEGRAL_UPDATE":
                updated,expected_move=control_update(move_start,move_obs,lifted,integral,"LOCAL_PID")
                io.require(payload["integral_before"]==integral and payload["integral_after"]==updated,"PID changed");integral=updated
            if name=="MEASUREMENT_ENTRY":
                io.require(payload["controller"]==controller and payload["measurement_program"]==spec["measurement_program"] and payload["balanced_actions"]==actions,"measurement admission")
                io.require(not session.alive() or len(move_obs)-1==64 or anchor_ready(move_obs,selected_anchor(move_start,"LOCAL_PID")),"movement stopped prematurely")
                measurement=deepcopy(payload)
            if name=="COMMAND":
                io.require(payload["before"]==normalize(asdict(session.public())) and payload["decision_sequence"]<len(events),"unsaved command source")
                chosen=events[payload["decision_sequence"]];phase=payload["phase"]
                if phase=="FIXED_PROBE":
                    io.require(chosen["kind"]=="CHOICE" and chosen["payload"]["action"]=="PROBE_FOUR" and pending_raw is None,"bad fixed probe")
                    i=session.ctx["calls"]-chosen["payload"]["at_calls"];io.require(0<=i<4 and payload["command"]==behavior.PROBE[i],"probe action changed")
                elif phase in ("POLICY","MEASURE_FEEDBACK","TASK_AFTER_MEASUREMENT"):
                    io.require(pending_raw is not None and payload["raw_policy"]==pending_raw and payload["measurement_desired"] is None,"policy query missing or changed")
                    io.require(payload["command"]==encode_controller(controller,pending_raw).tolist(),"saved C8 not consumed")
                    if phase=="MEASURE_FEEDBACK":io.require(spec["measurement_program"]=="FEEDBACK8" and chosen["kind"]=="MEASUREMENT_ENTRY","feedback program differs")
                elif phase=="MEASURE_BALANCED":
                    i=session.ctx["calls"]-measurement["at_calls"]
                    io.require(spec["measurement_program"]=="BALANCED8" and chosen["kind"]=="MEASUREMENT_ENTRY" and 0<=i<8 and pending_raw is None,"balanced admission")
                    io.require(payload["measurement_desired"]==actions[i] and payload["command"]==encode_controller(controller,actions[i]).tolist() and payload["raw_policy"] is None,"balanced action/controller differs")
                elif phase=="REPOSITION":io.require(chosen["kind"]=="ACQUISITION_ENTRY" and expected_move is not None and payload["command"]==expected_move and payload["raw_policy"] is None,"PID action changed")
                else:raise ValueError("unknown phase")
            if name=="TASK_ENTRY":io.require(payload["controller"]==controller and (not session.alive() or payload["measurement_steps"]==8),"measurement stopped early or updated controller")
            saved=session._agent_emit(name,normalize(payload));events.append({"kind":name,"payload":deepcopy(saved)})
            if name=="ACQUISITION_ENTRY":
                witness("BOUNDARY");row["fault_transition"]=install_context(session,row["fault_oracle"],row["scheduled_fault_oracle"],planned_boundary=spec["planned_boundary"])
            if name=="MEASUREMENT_ENTRY":witness("POST_MOVEMENT")
            if name=="TASK_ENTRY":witness("POST_MEASUREMENT")
            return saved
        def step(saved):
            nonlocal pending_raw,expected_move,lifted
            continuous();io.require(session.ctx["calls"]<168 and saved==session._pending,"unsaved/exhausted physical step")
            result=session._agent_step(saved)
            if saved["phase"] in ("POLICY","MEASURE_FEEDBACK","TASK_AFTER_MEASUREMENT"):pending_raw=None
            if saved["phase"]=="REPOSITION":move_obs.append(result.observation);expected_move=None;lifted=lifted or result.observation[2]>=selected_anchor(move_start,"LOCAL_PID")[2]-.015
            continuous();return result
        row["behavior"]=normalize(behavior.run(spec["task"],session.public(),model,spec["planned_boundary"],spec["measurement_program"],actions,policy,step,save))
        continuous();io.require(pending_raw is None and session._pending is None,"unconsumed policy or command")
        for label in ("BOUNDARY","POST_MOVEMENT","POST_MEASUREMENT"):
            if label not in labels:witness(label)
        witness("FINAL");io.require(labels==["INITIAL","BOUNDARY","POST_MOVEMENT","POST_MEASUREMENT","FINAL"],"witness order")
        row.update(row["behavior"]["outcome"]);row["final_observation"]=asdict(session.public());row["completed"]=True
    except BaseException as error:row["error"]={"type":type(error).__name__,"message":str(error)}
    finally:
        if session is not None:row.update(physical_rows=session.last_rows,host_attempts=session.attempts,host_returned=session.completed,policy_queries=session.policy_queries,captures=session.captures,restores=session.restores,partial_public_events=events)
        row["ledger_before_close"]=ledger.snapshot()
        if env is not None:
            try:env.close();row["environment_closed"]=True
            except BaseException as error:row["close_error"]={"type":type(error).__name__,"message":str(error)}
        row["ledger_after_close"]=ledger.snapshot();row["wall_ns"]=perf_counter_ns()-started
        fits=[e for e in events if e["kind"]=="FIT_RESULT"];row["c4_c8_fit_attempts"]=sum(e["kind"]=="FIT_INTENT" for e in events);row["c4_c8_fit_results"]=len(fits);row["c4_c8_optimizer_nfev"]=sum(e["payload"]["fit"].get("nfev",0) for e in fits)
    if row["error"] is not None or row["close_error"] is not None or not row["completed"]:raise CollectionFailure(normalize(row))
    return normalize(row)


def collect(manifest_path,split):
    io.clean();m=io.load(manifest_path);io.require(io.git("rev-parse","HEAD")==m["source_git_commit"],"frozen implementation HEAD required")
    root=manifest_path.parent;io.phase_gate(root,split)
    if split!="TRAIN":io.require(io.read(root/("train" if split=="CAL" else "cal")/"audit.json")["integrity"]=="PASSED","preceding records must be audited")
    folder=root/split.lower();folder.mkdir();specs=m["config"]["population"][split];identity={k:m[k] for k in io.IDENTITY};budget={"completed":0,"maximum":len(specs)*168}
    started=perf_counter_ns();models=io.read(io.ROOT/io.C8)["joint"];key={};last={};compact=[];failure=failed=None
    with gzip.open(folder/"events.jsonl.gz","xt",encoding="utf-8") as ef,gzip.open(folder/"cases.jsonl.gz","xt",encoding="utf-8") as cf,gzip.open(folder/"witnesses.jsonl.gz","xt",encoding="utf-8") as wf:
        journal=JsonJournal(ef,identity);private=JsonJournal(wf,identity)
        def emit(event,payload):
            nonlocal last
            if event=="LIFECYCLE_RESET_INTENT":io.require(ledger.counts.get("reset_attempts",0)<=51*len(specs),"all-reset cap")
            value=journal.emit(event,{**key,**payload});last={k:value[k] for k in ("sequence","saved_ns")};return value
        def emit_private(event,payload):return private.emit(event,{**key,**payload})
        ledger=LifecycleLedger(emit,len(specs)*(25500+168*5))
        import metaworld
        from metaworld.sawyer_xyz_env import SawyerXYZEnv
        from gymnasium.envs.mujoco import MujocoEnv
        try:
            with ledger.instrument(SawyerXYZEnv,MujocoEnv,metaworld):
                for spec in specs:
                    io.check_disk();key={k:spec[k] for k in ("case_id","split","group","unit","task","seed","variant")}
                    result={**identity,**execute_case(spec,models[spec["task"]],emit,emit_private,ledger,budget,lambda:deepcopy(last))}
                    cf.write(json.dumps(result,ensure_ascii=False,allow_nan=False)+"\n");cf.flush()
                    compact.append({k:result[k] for k in (*spec,"completed","success","total_steps","reposition_steps","measurement_steps","task_steps","stop_reason","c4_c8_fit_attempts","c4_c8_fit_results","c4_c8_optimizer_nfev")})
                    io.write(folder/"status.json",{**identity,"split":split,"status":"RUNNING","completed_executions":len(compact),"control_steps":budget["completed"],"lifecycle":ledger.snapshot()},exclusive=False)
                    print(json.dumps({"split":split,"completed":len(compact),"allocated":len(specs),"steps":budget["completed"]}),flush=True)
            io.require(len(compact)==len(specs) and private.sequence==5*len(specs),"complete allocated phase required")
        except BaseException as error:
            failure={"type":type(error).__name__,"message":str(error)}
            if isinstance(error,CollectionFailure):failed={**identity,**error.record};io.write(folder/"failed_execution.json",failed)
    summary={**identity,"split":split,"status":"COLLECTED_FOR_INDEPENDENT_AUDIT" if failure is None else "FAILED_PARTIAL","allocated_executions":len(specs),"executions":len(compact),
        "rows":compact,"lifecycle":ledger.snapshot(),"control_steps":budget["completed"],"control_step_attempts":sum(r["total_steps"] for r in compact)+(0 if failed is None else failed.get("host_attempts",0)),
        "events":journal.sequence,"witness_records":private.sequence,"failure":failure,"wall_ns":perf_counter_ns()-started,"new_api_calls":0,"new_response_model_fits":0,"new_policy_training":0}
    io.write(folder/"summary.json",summary);io.write(folder/"status.json",{k:v for k,v in summary.items() if k!="rows"},exclusive=False)
    io.write(folder/"completion.json",{**identity,"split":split,"status":summary["status"],"closed_ns":perf_counter_ns(),"artifact_sha256":{p.name:io.sha(p) for p in folder.iterdir() if p.is_file()}})
    if failure is not None:raise RuntimeError("one-shot collection stopped; partial record retained: "+str(failure))

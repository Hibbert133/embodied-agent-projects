"""Evaluator host: one reset, fixed saved C8 behavior, full physical and private records."""
from copy import deepcopy
from dataclasses import asdict
import gzip
import json
from time import perf_counter_ns

import numpy as np

from src.analysis import response_qualification_io_v1 as io
from src.analysis.capsule_record_json_v2 import JsonJournal, normalize
from src.analysis.paired_probe_host_v1 import ProbeSession
from src.analysis.stale_reprobe_context_v1 import install_context
from src.probe import response_qualification_behavior_v1 as behavior
from src.probe.cold_start_response import ColdPrefix
from src.probe.lifecycle_ledger import LifecycleLedger
from src.probe.local_reprobe_v1 import anchor_ready, control_update, selected_anchor
from src.probe.operator_identification import affine_controller, encode_controller
from src.probe.physical_reprobe_v1 import Start
from src.rollout.task_registry import create_task_environment, create_task_policy
from scripts.qualify_delayed_intervention_v2 import observe_state


class CollectionFailure(RuntimeError):
    def __init__(self,record):super().__init__(str(record.get("error")));self.record=record


def execute_case(spec,model,emit,emit_private,ledger,budget,position):
    row={**spec,"completed":False,"error":None,"close_error":None,"environment_closed":False,
        "fault_oracle":io.initial_fault(spec["split"]),"scheduled_fault_oracle":io.destination(spec),"fault_transition":None,
        "state_witnesses":[],"physical_rows":[],"ledger_before":ledger.snapshot()}
    env=session=None;events=[];pending_raw=None;move_start=None;move_obs=[];integral=[0.,0.];lifted=False;expected_move=None;controller=None
    labels=[];phase_start_ns=perf_counter_ns()
    def witness(label):
        value=session.witness()
        row["state_witnesses"].append(observe_state(session,label,value,position,emit_private));labels.append(label)

    try:
        emit("FACTORY_INTENT",{"ledger":ledger.snapshot()})
        with ledger.scope("FACTORY_SETUP"):env=create_task_environment(spec["task"],spec["seed"])
        emit("FACTORY_COMPLETE",{"ledger":ledger.snapshot()});before_reset=ledger.snapshot()
        with ledger.scope("CONTROLLED_RESET"):initial,_=env.reset(seed=spec["seed"])
        session=ProbeSession(env,create_task_policy(spec["task"]),initial,spec["task"],spec["seed"],row["fault_oracle"],emit,ledger,budget)
        session.ctx["noise_rows"]=io.noise(spec["seed"],spec["noise_namespace"])
        tape=session.ctx["noise_rows"];base=env.unwrapped;addresses=(base.model._address,base.data._address)
        reset_counts={k:ledger.counts.get(k,0) for k in ("reset_attempts","reset_completed","reset_errors")}
        start_clock=float(base.data.time);start_frames=ledger.counts.get("simulation_frames_completed",0);start_budget=budget["completed"]
        session.branch={"role":"RESPONSE_QUALIFICATION_FIXED_BEHAVIOR","future":0,"program":"C8_LOCAL_PID_C8_32"}
        row["initial"]=asdict(session.public());witness("INITIAL")
        emit("NOISE_COMMITMENT",{"at_calls":0,"namespace_oracle":spec["noise_namespace"],"tape_sha256_oracle":io.digest(tape.tolist())})
        def continuous():
            io.require(session.env.unwrapped is base and (base.model._address,base.data._address)==addresses,"environment replacement")
            io.require(session.ctx["noise_rows"] is tape and not tape.flags.writeable,"noise replacement")
            io.require(all(ledger.counts.get(k,0)==v for k,v in reset_counts.items()),"reset after initial reset")
            calls=session.ctx["calls"]
            io.require(calls==session.completed==session.attempts==len(session.last_rows)<=160,"physical control count")
            io.require(budget["completed"]-start_budget==calls and ledger.counts.get("simulation_frames_completed",0)-start_frames==5*calls,"control cost mismatch")
            io.require(np.isclose(float(base.data.time)-start_clock,.0125*calls,atol=1e-9,rtol=0),"physical clock discontinuity")
            io.require(not session.captures and not session.restores and not session._snapshots,"state copy / restore forbidden")
        def policy(observation):
            nonlocal pending_raw
            continuous();io.require(pending_raw is None and np.array_equal(observation,session.public().observation),"duplicate or stale policy query")
            pending_raw=session.policy_query(observation).tolist();return np.array(pending_raw,np.float32)
        def save(kind,payload):
            nonlocal move_start,move_obs,integral,lifted,expected_move,controller
            continuous();io.require(payload["at_calls"]==session.ctx["calls"] and session._pending is None,"stale public event")
            if kind=="FIT_INTENT":
                prefix=ColdPrefix.from_dict(payload["prefix"])
                io.require(prefix.initial_observation==tuple(initial) and np.array_equal(prefix.commands,session.ctx["commands"]) and np.array_equal(prefix.observations,session.ctx["observations"]),"fit uses non-observed prefix")
            if kind=="CHOICE" and payload["action"] in ("SAVE_C4_ONLY","RUN_C8"):
                source=events[payload["fit_sequence"]]
                io.require(source["kind"]=="FIT_RESULT" and source["payload"]["fit"]["valid"],"invalid fit used")
                fit=source["payload"]["fit"]
                io.require(io.digest(payload["controller"])==io.digest(affine_controller(fit["matrix_xy"],fit["bias_xy"])),"inverse mapping differs")
                if payload["action"]=="RUN_C8":controller=deepcopy(payload["controller"])
            if kind=="ACQUISITION_ENTRY":
                io.require(session.ctx["calls"]==spec["planned_boundary"] and session.alive() and controller==payload["controller"],"bad acquisition boundary")
                move_start=Start(spec["task"],session.ctx["calls"],session.public(),controller["matrix_xy"],controller["offset"][:2])
                io.require(list(selected_anchor(move_start,"LOCAL_PID"))==payload["anchor"],"anchor changed")
                move_obs=[session.public().observation];integral=[0.,0.];lifted=move_obs[-1][2]>=payload["anchor"][2]-.015
            if kind=="INTEGRAL_UPDATE":
                updated,expected_move=control_update(move_start,move_obs,lifted,integral,"LOCAL_PID")
                io.require(payload["integral_before"]==integral and payload["integral_after"]==updated,"PID update changed")
                integral=updated
            if kind=="COMMAND":
                io.require(payload["before"]==normalize(asdict(session.public())) and payload["decision_sequence"]<len(events),"unsaved command source")
                chosen=events[payload["decision_sequence"]]
                phase=payload["phase"]
                if phase=="FIXED_PROBE":
                    io.require(chosen["kind"]=="CHOICE" and chosen["payload"]["action"]=="PROBE_FOUR" and pending_raw is None,"bad probe choice")
                    index=session.ctx["calls"]-chosen["payload"]["at_calls"]
                    io.require(0<=index<4 and payload["command"]==behavior.PROGRAM[index],"probe changed")
                elif phase in ("POLICY","TASK_AFTER_MOVEMENT"):
                    io.require(pending_raw is not None and payload["raw_policy"]==pending_raw and controller is not None,"missing actual fixed-policy query")
                    expected=encode_controller(controller,pending_raw).tolist()
                    io.require(payload["command"]==expected,"saved C8 not used")
                elif phase=="REPOSITION":
                    io.require(chosen["kind"]=="ACQUISITION_ENTRY" and expected_move is not None and payload["raw_policy"] is None and payload["command"]==expected_move,"PID command not admitted")
                else:raise ValueError("unknown phase")
            if kind=="TASK_ENTRY":
                io.require(payload["controller"]==controller,"updated controller forbidden")
                anchor=selected_anchor(move_start,"LOCAL_PID")
                io.require(not session.alive() or len(move_obs)-1==64 or anchor_ready(move_obs,anchor),"premature movement stop")
            saved=session._agent_emit(kind,normalize(payload));events.append({"kind":kind,"payload":deepcopy(saved)})
            if kind=="ACQUISITION_ENTRY":
                witness("BOUNDARY")
                row["fault_transition"]=install_context(session,row["fault_oracle"],row["scheduled_fault_oracle"],planned_boundary=spec["planned_boundary"])
            if kind=="TASK_ENTRY":witness("POST_MOVEMENT")
            return saved
        def step(saved):
            nonlocal pending_raw,expected_move,lifted
            continuous();io.require(session.ctx["calls"]<160,"per-execution cap")
            io.require(saved==session._pending,"unsaved physical step")
            result=session._agent_step(saved)
            if saved["phase"] in ("POLICY","TASK_AFTER_MOVEMENT"):pending_raw=None
            if saved["phase"]=="REPOSITION":
                move_obs.append(result.observation);expected_move=None
                lifted=lifted or result.observation[2]>=selected_anchor(move_start,"LOCAL_PID")[2]-.015
            continuous();return result
        row["behavior"]=normalize(behavior.run(spec["task"],session.public(),model,spec["planned_boundary"],policy,step,save))
        continuous();io.require(pending_raw is None and session._pending is None,"unconsumed query/command")
        if "BOUNDARY" not in labels:witness("BOUNDARY")
        if "POST_MOVEMENT" not in labels:witness("POST_MOVEMENT")
        witness("FINAL");io.require(labels==["INITIAL","BOUNDARY","POST_MOVEMENT","FINAL"],"witness order")
        row.update(row["behavior"]["outcome"]);row["final_observation"]=asdict(session.public());row["completed"]=True
    except BaseException as error:
        row["error"]={"type":type(error).__name__,"message":str(error)}
    finally:
        if session is not None:
            row.update(physical_rows=session.last_rows,host_attempts=session.attempts,host_returned=session.completed,policy_queries=session.policy_queries,
                captures=session.captures,restores=session.restores,partial_public_events=events)
        row["ledger_before_close"]=ledger.snapshot()
        if env is not None:
            try:env.close();row["environment_closed"]=True
            except BaseException as error:row["close_error"]={"type":type(error).__name__,"message":str(error)}
        row["ledger_after_close"]=ledger.snapshot();row["wall_ns"]=perf_counter_ns()-phase_start_ns
        fits=[e for e in events if e["kind"]=="FIT_RESULT"]
        row["c4_c8_fit_attempts"]=sum(e["kind"]=="FIT_INTENT" for e in events);row["c4_c8_fit_results"]=len(fits)
        row["c4_c8_optimizer_nfev"]=sum(e["payload"]["fit"].get("nfev",0) for e in fits)
    if row["error"] is not None or row["close_error"] is not None or not row["completed"]:raise CollectionFailure(normalize(row))
    return normalize(row)


def collect(manifest_path,split):
    io.clean();manifest=io.load(manifest_path);io.require(io.git("rev-parse","HEAD")==manifest["source_git_commit"],"frozen implementation commit required")
    root=manifest_path.parent;io.phase_gate(root,split)
    if split!="TRAIN":io.require(io.read(root/("train" if split=="CAL" else "cal")/"audit.json")["integrity"]=="PASSED","preceding data audit required")
    folder=root/split.lower();folder.mkdir()
    specs=manifest["config"]["population"][split];identity={k:manifest[k] for k in io.IDENTITY}
    phase_frames=len(specs)*(25500+5*160);budget={"completed":0,"maximum":len(specs)*160}
    model_bank=io.read(io.ROOT/io.C8)["joint"];started=perf_counter_ns();failure=None;compact=[];key={};last={};failed=None
    with gzip.open(folder/"events.jsonl.gz","xt",encoding="utf-8") as f,gzip.open(folder/"cases.jsonl.gz","xt",encoding="utf-8") as cf,gzip.open(folder/"witnesses.jsonl.gz","xt",encoding="utf-8") as wf:
        journal=JsonJournal(f,identity);private=JsonJournal(wf,identity)
        def emit(event,payload):
            nonlocal last
            if event=="LIFECYCLE_RESET_INTENT":io.require(ledger.counts.get("reset_attempts",0)<=51*len(specs),"all-reset budget")
            saved=journal.emit(event,{**key,**payload});last={k:saved[k] for k in ("sequence","saved_ns")};return saved
        def emit_private(event,payload):return private.emit(event,{**key,**payload})
        ledger=LifecycleLedger(emit,phase_frames)
        import metaworld
        from metaworld.sawyer_xyz_env import SawyerXYZEnv
        from gymnasium.envs.mujoco import MujocoEnv
        try:
            with ledger.instrument(SawyerXYZEnv,MujocoEnv,metaworld):
                for spec in specs:
                    key={k:spec[k] for k in ("case_id","split","group","unit","task","seed","variant")}
                    result=execute_case(spec,model_bank[spec["task"]],emit,emit_private,ledger,budget,lambda:deepcopy(last))
                    result={**identity,**result};cf.write(json.dumps(result,ensure_ascii=False,allow_nan=False)+"\n");cf.flush()
                    compact.append({k:result[k] for k in (*spec,"completed","success","total_steps","reposition_steps","task_steps","stop_reason","c4_c8_fit_attempts","c4_c8_fit_results","c4_c8_optimizer_nfev")})
                    io.write(folder/"status.json",{**identity,"status":"RUNNING","split":split,"completed_executions":len(compact),"control_steps":budget["completed"],"lifecycle":ledger.snapshot()},exclusive=False)
                    print(json.dumps({"split":split,"completed":len(compact),"allocated":len(specs),"steps":budget["completed"]}),flush=True)
            io.require(len(compact)==len(specs) and private.sequence==4*len(specs),"incomplete phase")
        except BaseException as error:
            failure={"type":type(error).__name__,"message":str(error)}
            if isinstance(error,CollectionFailure):failed={**identity,**error.record};io.write(folder/"failed_execution.json",failed)
    summary={**identity,"status":"COLLECTED_FOR_INDEPENDENT_AUDIT" if failure is None else "FAILED_PARTIAL", "split":split,"allocated_executions":len(specs),
        "executions":len(compact),"rows":compact,"lifecycle":ledger.snapshot(),"control_steps":budget["completed"],
        "control_step_attempts":sum(r["total_steps"] for r in compact)+(0 if failed is None else failed.get("host_attempts",0)),
        "events":journal.sequence,"witness_records":private.sequence,
        "failure":failure,"wall_ns":perf_counter_ns()-started,"new_api_calls":0,"new_response_model_fits":0,"new_policy_training":0}
    io.write(folder/"summary.json",summary);io.write(folder/"status.json",{k:v for k,v in summary.items() if k!="rows"},exclusive=False)
    io.write(folder/"completion.json",{**identity,"status":summary["status"],"split":split,"closed_ns":perf_counter_ns(),
        "artifact_sha256":{p.name:io.sha(p) for p in folder.iterdir() if p.is_file()}})
    if failure is not None:raise RuntimeError("frozen collection stopped; partial record preserved: "+str(failure))

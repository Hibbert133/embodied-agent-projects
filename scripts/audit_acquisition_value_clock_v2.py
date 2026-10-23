"""Read-only clock repair of the frozen auditor; original experiments stay unchanged."""
import argparse
from collections import Counter, deque
from contextlib import contextmanager
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from scripts import run_acquisition_value as runner
from scripts.analyze_action_response import equal, verify_git_inputs
from src.probe.acquisition_value import METHODS, MID_METHODS, PRIOR_CACHE_METHODS, deadline_loss, repeat_consistency
from src.probe.forward_prediction import ForwardHistory
from src.probe.continuous import ContinuousTransition
from src.probe.operator_identification import OperatorSample, infer_operator, encode_controller, identity_controller


def statistics(m, rows, sources, pairings,update_pairs=None):
    c = m["config"]
    keys = ("stream", "task", "scenario", "replicate", "method")
    indexed = {tuple(r[k] for k in keys): r for r in rows}
    expected = {(s, t, z, r, p) for s in range(8) for t in runner.TASKS for z in runner.SCENARIOS for r in range(4) for p in METHODS}
    if set(indexed) != expected or len(rows) != 2304 or len(sources) != 24:
        raise ValueError("complete registered population required")
    expected_sources = {(s, t) for s in range(8) for t in runner.TASKS}
    if {(r["stream"], r["task"]) for r in sources} != expected_sources:
        raise ValueError("complete immutable cold-source bank required")
    paired = {(r["stream"], r["task"], r["scenario"], r["replicate"], r["method"]): r["reason"] for r in pairings}
    if set(paired) != {k for k in expected if k[-1] in MID_METHODS} or len(pairings) != 1536:
        raise ValueError("complete comparison eligibility required")
    source_steps = sum(r["total_steps"] for r in sources); source_resets = sum(r["environment_resets"] for r in sources)
    methods = {}; strata = {}
    def cell(part):
        n = len(part)
        return {"cases": n, "successes": sum(r["success"] for r in part), "stops": sum(r["stopped"] for r in part),
                "total_steps": sum(r["total_steps"] for r in part), "mean_steps": sum(r["total_steps"] for r in part)/n,
                "mean_deadline_loss": sum(r["deadline_loss"] for r in part)/n,
                "mean_probe_steps": sum(r["micro_steps"]+r["fixed_probe_steps"] for r in part)/n}
    for method in METHODS:
        part = [r for r in rows if r["method"] == method]; result = cell(part)
        offline = 0 if method == "NO_PROBE" else 21010
        cold = source_steps if method in PRIOR_CACHE_METHODS else 0
        result.update(point_fit_failures=sum(r["point_fit_failures"] for r in part),
                      offline_nominal_steps=offline, offline_nominal_controlled_resets=0 if method == "NO_PROBE" else 288,
                      cold_source_steps=cold, cold_source_controlled_resets=source_resets if method in PRIOR_CACHE_METHODS else 0,
                      mean_amortized_steps=result["mean_steps"]+(offline+cold)/192,
                      mean_amortized_deadline_loss=result["mean_deadline_loss"]+(offline+cold)/192)
        methods[method] = result
        strata[method] = {"by_task": {t: cell([r for r in part if r["task"]==t]) for t in runner.TASKS},
                          "by_scenario": {z: cell([r for r in part if r["scenario"]==z]) for z in runner.SCENARIOS},
                          "by_stream": {str(s): cell([r for r in part if r["stream"]==s]) for s in range(8)},
                          "by_replicate": {str(v): cell([r for r in part if r["replicate"]==v]) for v in range(4)}}
    contexts=[]; matched_details=[]
    for s in range(8):
        for t in runner.TASKS:
            for z in runner.SCENARIOS:
                signs=[]; reasons=[]
                for v in range(4):
                    a,b=indexed[s,t,z,v,"MID16_WIDE"],indexed[s,t,z,v,"CACHE_CONTINUE"]
                    why=paired[s,t,z,v,"MID16_WIDE"];reasons.append(why)
                    if why != "MATCHED": continue
                    sign=1 if a["deadline_loss"]<b["deadline_loss"] else -1 if a["deadline_loss"]>b["deadline_loss"] else 0
                    signs.append(sign)
                    matched_details.append({"stream":s,"task":t,"scenario":z,"replicate":v,"sign":sign,
                                            "target_loss":a["deadline_loss"],"reference_loss":b["deadline_loss"],
                                            "target_steps":a["total_steps"],"reference_steps":b["total_steps"],
                                            "target_success":a["success"],"reference_success":b["success"],"target_stop":a["stopped"]})
                item={"stream":s,"task":t,"scenario":z,"signs":signs,"reasons":reasons,"complete":len(signs)==4}
                if item["complete"]: item.update(repeat_consistency(signs))
                contexts.append(item)
    valid=[r for r in contexts if r["complete"]]; non_tie=[r for r in valid if r["has_non_tie"]]
    reversals=sum(r["sign_reversal"] for r in non_tie); checked=sum(r["leave_one_out_checked"] for r in valid)
    correct=sum(r["leave_one_out_correct"] for r in valid); abstained=sum(r["leave_one_out_abstained"] for r in valid)
    reversal_fraction=reversals/len(non_tie) if non_tie else None
    agreement=correct/checked if checked else None; coverage=checked/(checked+abstained) if checked+abstained else None
    gate={"contexts":48,"fully_matched_contexts":len(valid),"non_tie_contexts":len(non_tie),"sign_reversal_contexts":reversals,
          "sign_reversal_fraction":reversal_fraction,"leave_one_out_checked":checked,"leave_one_out_correct":correct,
          "leave_one_out_abstained":abstained,"leave_one_out_agreement":agreement,"leave_one_out_coverage":coverage,
          "passed":len(valid)==48 and len(non_tie)>=24 and reversal_fraction is not None and reversal_fraction<=.25
                   and agreement is not None and agreement>=.75 and coverage is not None and coverage>=.75}
    update_summary={}
    if update_pairs is not None:
        expected_updates={(s,t,z,v,p) for s in range(8) for t in runner.TASKS for z in runner.SCENARIOS for v in range(4) for p in ("MID8_WIDE","MID16_WIDE")}
        if len(update_pairs)!=384 or {tuple(r[k] for k in keys) for r in update_pairs}!=expected_updates:
            raise ValueError("complete matched update contrasts required")
        for method in ("MID8_WIDE","MID16_WIDE"):
            group=[r for r in update_pairs if r["method"]==method];eligible=[r for r in group if r["reason"]=="MATCHED_UPDATE"]
            for r in group:
                if r["update_loss_difference"]+r["probe_motion_loss_difference"]!=r["total_loss_difference"]:
                    raise ValueError("realized branch contrast decomposition differs")
            n=len(eligible)
            update_summary[method]={"original_pairs":len(group),"reasons":dict(Counter(r["reason"] for r in group)),"update_decisions":n,
                                    "updated_successes":sum(r["updated_success"] for r in eligible),"kept_successes":sum(r["kept_success"] for r in eligible),
                                    "updated_stops":sum(r["updated_stop"] for r in eligible),"kept_stops":sum(r["kept_stop"] for r in eligible),
                                    "mean_update_loss_difference":sum(r["update_loss_difference"] for r in eligible)/n if n else None,
                                    "mean_probe_motion_loss_difference":sum(r["probe_motion_loss_difference"] for r in eligible)/n if n else None,
                                    "mean_total_loss_difference":sum(r["total_loss_difference"] for r in eligible)/n if n else None,
                                    "pure_information_value_claim":False}
    return {"methods":methods,"strata":strata,"repeat_gate":gate,"primary_contexts":contexts,"primary_paired_cases":matched_details,
            "post_probe_update_contrasts":update_summary,
            "pairing_reason_counts":{method:dict(Counter(r["reason"] for r in pairings if r["method"]==method)) for method in MID_METHODS},
            "independent_stream_clusters":8,"nominal_contexts":48,"repetitions_per_context":4,
            "source_controlled_steps":source_steps,"source_controlled_resets":source_resets,
            "new_controlled_steps":source_steps+sum(r["total_steps"] for r in rows),
            "new_controlled_resets":source_resets+sum(r["environment_resets"] for r in rows),
            "probability_qualification":False,"selector_qualification":False,"publication_ready":False}


def verify_record(record, model, source_cache, operator, business_events):
    """Independent branch arithmetic; mathematical fitting/guards explicitly reused."""
    method=record["method"]; calibration=method=="CALIBRATE_OLD16"
    event_fields=(*runner.IDENTITY,"stream","task","scenario","replicate","seed","method","operator_id_oracle")
    def same_event(event):
        if any(event[k]!=record[k] for k in event_fields):raise ValueError("foreign branch event")
    if record["source_cache"] != source_cache: raise ValueError("foreign or future source cache")
    decisions={d["sequence"]:d for d in record["decisions"]}; trace=record["trace"]
    if len(trace)>500 or [r["host_calls"] for r in trace]!=list(range(1,len(trace)+1)):raise ValueError("branch budget or timeline differs")
    if record["initial"] is None:
        if source_cache is not None or method not in PRIOR_CACHE_METHODS or trace or len(decisions)!=1:raise ValueError("source stop substituted")
        d=next(iter(decisions.values()))
        if d["action"]!="STOP_NO_SOURCE_CACHE" or d["controller"] is not None:raise ValueError("unavailable source did not stop")
        event=business_events.popleft();same_event(event);equal(d,event)
        expected={"success":False,"stopped":True,"total_steps":0,"environment_resets":0,"prefix_steps":0,
                  "micro_steps":0,"fixed_probe_steps":0,"policy_steps":0,"point_fit_failures":0,"deadline_loss":500,"source_cache_unavailable":True}
        if record["outcome"]!=expected or record["new_cache"] is not None or record["ledger_before"]!=record["ledger_after"] or d["ledger"]!=record["ledger_before"]:
            raise ValueError("source failure outcome or cost substituted")
        return
    # Factory/reset envelopes are checked independently from their event ledger.
    start,factory=business_events.popleft(),business_events.popleft()
    same_event(start);same_event(factory)
    if start["event"]!="FACTORY_INTENT" or factory["event"]!="FACTORY_COMPLETE" or start["ledger"]!=record["ledger_before"]:raise ValueError("factory ordering differs")
    initial=business_events.popleft()
    same_event(initial)
    if initial["event"]!="CONTROLLED_INITIAL" or initial["initial"]!=record["initial"] or initial["physics_witness_oracle"]!=record["initial_physics_witness_oracle"]:
        raise ValueError("initial state declaration differs")
    history=ForwardHistory(record["initial"]["observation"]);samples=[];fixed_start=None;fixed_length=None;fixed_magnitude=None;fixed_position=0
    micro_program=None;micro_position=0;micro_count=0;current=record["initial"];calls=0;controller=None;new_cache=None
    rng=np.random.default_rng(runner.noise_seed(record["seed"],record["task"],record["replicate"]))
    def rng_hash():return hashlib.sha256(json.dumps(rng.bit_generator.state,sort_keys=True).encode()).hexdigest()
    if rng_hash()!=record["initial_rng_hash"]:raise ValueError("initial RNG differs")
    previous=runner.cached(source_cache)
    policy=runner.create_task_policy(record["task"])
    last_decision_sequence=None
    while business_events:
        event=business_events[0]
        if event.get("stream")!=record["stream"] or event.get("task")!=record["task"] or event.get("scenario")!=record["scenario"] or event.get("method")!=method or event.get("replicate")!=record["replicate"]:
            break
        business_events.popleft()
        same_event(event)
        kind=event["event"]
        if kind=="DECISION":
            if event["sequence"] not in decisions:raise ValueError("unsaved decision")
            equal(event,decisions[event["sequence"]]);action=event["action"]
            if event["at_host_calls"]!=calls or event["observation_sha256"]!=runner.state_hash(current["observation"]) or event["rng_hash"]!=rng_hash():raise ValueError("decision used future state")
            expected_controller=previous.controller if previous is not None else identity_controller()
            if action=="RUN_UNCORRECTED":
                if method!="NO_PROBE" or calls:raise ValueError("uncorrected branch changed")
                expected_controller=identity_controller()
            elif action=="RUN_OLD_POINT":
                if method!="CACHE_CONTINUE" or calls:raise ValueError("cache branch changed")
            elif action=="REQUEST_PREFIX":
                if method not in MID_METHODS or calls or event["prefix_steps"]!=6:raise ValueError("prefix program changed")
            elif action=="REQUEST_FIXED_PROBE":
                length,magnitude=event["probe_steps"],event["magnitude"]
                if calibration: allowed=(16,.2,0)
                elif method in ("G_OPTIMAL","RESPONSE_SET"): allowed=(16,.2,calls)
                else:
                    spec=runner.PROGRAMS[method];allowed=(spec.probe_steps,spec.magnitude,spec.prefix_steps)
                if (length,magnitude,calls)!=allowed or calls+length+32>500:raise ValueError("fixed probe or budget changed")
                fixed_start,fixed_length,fixed_magnitude,fixed_position=calls,length,magnitude,0
            elif action in ("RUN_NEW_POINT","STOP_POINT_FIT"):
                if not calibration and runner.PROGRAMS[method].keep_old:raise ValueError("keep branch consumed an unselected new estimate")
                if fixed_start is None or fixed_position!=fixed_length:raise ValueError("fit without completed probe")
                fit=infer_operator(model,tuple(s for s in samples if s.step>fixed_start));equal(fit,event["fit"])
                if action=="RUN_NEW_POINT" and fit["valid"]:
                    new_cache=runner.CachedPoint(fit["matrix_xy"],fit["bias_xy"]);expected_controller=new_cache.controller
                elif action=="STOP_POINT_FIT" and not fit["valid"]:expected_controller=None
                else:raise ValueError("fit validity substituted")
            elif action=="KEEP_MEASURED_OLD_POINT":
                if not runner.PROGRAMS[method].keep_old or fixed_position!=fixed_length:raise ValueError("unregistered post-probe keep choice")
            elif event.get("validation") is not None:
                if method not in ("G_OPTIMAL","RESPONSE_SET") or calls<6:raise ValueError("unregistered guard")
                sigma=verify_record.sigma
                decision=runner.agent_validation(method,model,previous,tuple(samples),sigma,micro_count,500-calls)
                equal(decision,event["validation"])
                if action!=decision["action"] or event["micro_steps"]!=micro_count:raise ValueError("guard choice substituted")
                if action.startswith("STOP"):expected_controller=None
                if action=="REQUEST_MICRO_PROBE":micro_program=runner.PRIMITIVES[decision["program_id"]];micro_position=0
            elif action=="STOP_BUDGET":
                raise ValueError("unexpected reachable budget stop in registered short programs")
            else:raise ValueError("unknown branch action")
            equal(expected_controller,event["controller"]);controller=event["controller"]
            last_decision_sequence=event["sequence"]
        elif kind=="STEP_INTENT":
            if calls>=len(trace) or event["decision_sequence"]!=last_decision_sequence or controller is None:raise ValueError("physical step without selected controller")
            row=trace[calls];phase=row["phase"]
            if event["command"]!=row["command"] or event["before"]!=current or event["rng_before"]!=rng_hash() or event["at_host_calls"]!=calls:
                raise ValueError("step intent changed")
            if row["intent_sequence"]!=event["sequence"] or row["decision_sequence"]!=event["decision_sequence"] or event["phase"]!=phase:
                raise ValueError("decision/intent association differs")
            if not (decisions[row["decision_sequence"]]["sequence"]<row["intent_sequence"] and row["intent_saved_ns"]<row["execution_started_ns"]<=row["completed_ns"]):
                raise ValueError("choice did not precede execution")
            if phase in ("POLICY","PREFIX_POLICY"):
                if phase=="PREFIX_POLICY" and (method not in MID_METHODS or calls>=6):raise ValueError("invalid prefix phase")
                raw=np.asarray(policy.get_action(np.asarray(current["observation"])),dtype=np.float32)
                if raw.tolist()!=row["raw_policy"] or encode_controller(controller,raw).tolist()!=row["command"]:raise ValueError("saved policy/controller not executed")
            elif phase=="FIXED_PROBE":
                if fixed_start is None or fixed_position>=fixed_length:raise ValueError("extra fixed probe")
                directions=((fixed_magnitude,0),( -fixed_magnitude,0),(0,fixed_magnitude),(0,-fixed_magnitude))
                xy=directions[fixed_position//(fixed_length//4)];command=np.asarray([*xy,0,0],dtype=np.float32).tolist()
                if row["command"]!=command or row["raw_policy"] is not None:raise ValueError("probe command changed")
                fixed_position+=1
            elif phase=="MICRO_PROBE":
                if micro_program is None or micro_position>=len(micro_program) or np.asarray(micro_program[micro_position],dtype=np.float32).tolist()!=row["command"]:raise ValueError("micro program changed")
                micro_position+=1;micro_count+=1
                if micro_count>16:raise ValueError("repeat probe cap exceeded")
            else:raise ValueError("unknown physical phase")
            query=history.request(row["command"])
            equal(runner.normal(asdict_query(query)),event["forward_query"])
            actual=np.asarray(row["command"],dtype=np.float32).copy()
            actual[:2]=np.asarray(operator["matrix_xy"],dtype=np.float32)@actual[:2]+np.asarray(operator["bias_xy"],dtype=np.float32)
            actual[:3]+=rng.normal(0,.05,3).astype(np.float32);actual=np.clip(actual,-1,1)
            if actual.tolist()!=row["executed_action_oracle"] or rng_hash()!=row["rng_after"]:raise ValueError("injected action or continuous RNG differs")
            target=history.observe(ContinuousTransition(tuple(row["command"]),current["observation"],row["after"]["observation"]));calls+=1
            if query is not None:samples.append(OperatorSample(calls,query,target))
            equal(list(target),row["target_xy"]);current=row["after"]
            if not np.isclose(row["simulation_time_after_oracle"]-row["simulation_time_before_oracle"],verify_record.expected_env_dt,atol=1e-10,rtol=1e-10):raise ValueError("physics clock discontinuity")
            complete=business_events.popleft()
            same_event(complete)
            if complete["event"]!="STEP_COMPLETE":raise ValueError("missing physical completion")
            for k,v in row.items():equal(v,complete[k])
        else:raise ValueError("unexpected business event")
    if calls!=len(trace):raise ValueError("missing actual steps")
    if not calibration and controller is not None and calls<500 and not any(current[k] for k in ("success","terminated","truncated")):
        raise ValueError("chosen task branch was truncated before completion")
    if calibration and (calls>16 or any(r["phase"]!="FIXED_PROBE" for r in trace)):
        raise ValueError("cold calibration program changed")
    expected_ledger=trace[-1]["ledger_after"] if trace else initial["ledger"]
    if record["ledger_after"]!=expected_ledger:raise ValueError("branch lifecycle cost changed")
    equal(runner.saved_cache(new_cache),record["new_cache"])
    phase=Counter(r["phase"] for r in trace);out=record["outcome"]
    result={"success":current["success"],"stopped":controller is None,"total_steps":len(trace),"environment_resets":1,
            "prefix_steps":phase["PREFIX_POLICY"],"micro_steps":phase["MICRO_PROBE"],"fixed_probe_steps":phase["FIXED_PROBE"],"policy_steps":phase["POLICY"],
            "point_fit_failures":sum(d.get("fit") is not None and not d["fit"]["valid"] for d in decisions.values()),
            "deadline_loss":len(trace) if current["success"] else 500,"source_cache_unavailable":False}
    if result!=out:raise ValueError("independent outcome cost differs")


def asdict_query(query):
    from dataclasses import asdict
    return asdict(query) if query is not None else None


def read_lines(path):
    with gzip.open(path,"rt",encoding="utf-8") as handle:
        for line in handle:yield json.loads(line)


def advance_ledger(before, phase, additions):
    result=json.loads(json.dumps(before))
    counts=result["counts"];section=result["by_phase"].setdefault(phase,{})
    for field,amount in additions.items():
        counts[field]=counts.get(field,0)+amount
        section[field]=section.get(field,0)+amount
    return result


class JournalAudit:
    def __init__(self, identity):
        self.identity=identity;self.sequence=0;self.pending=None;self.resets=0
        self.ledger={"counts":{},"by_phase":{}};self.step_pending=None
    def accept(self,event):
        self.sequence+=1
        if event["sequence"]!=self.sequence or any(event[k]!=v for k,v in self.identity.items()):
            raise ValueError("foreign or reordered event")
        kind=event["event"]
        if kind=="LIFECYCLE_RESET_INTENT":
            if self.pending is not None or self.step_pending is not None or event["before"]!=self.ledger:
                raise ValueError("reset ledger chronology differs")
            self.pending=event;return None
        if kind=="LIFECYCLE_RESET_COMPLETE":
            if self.pending is None or event["intent_sequence"]!=self.pending["sequence"]:
                raise ValueError("reset completion without intent")
            phase=event["phase"]
            if phase!=self.pending["phase"] or phase not in ("GOAL_GENERATION","CONTROLLED_RESET"):
                raise ValueError("reset phase differs")
            delta={"reset_attempts":1,"reset_completed":1,"simulation_attempts":100,"simulation_completed":100,
                   "simulation_frames_attempted":500,"simulation_frames_completed":500}
            if advance_ledger(self.ledger,phase,delta)!=event["after"]:
                raise ValueError("actual reset initialization cost differs")
            self.ledger=event["after"];self.pending=None;self.resets+=1;return None
        if self.pending is not None:raise ValueError("business event inside incomplete reset")
        if "ledger" in event and event["ledger"]!=self.ledger:raise ValueError("factory/initial ledger differs")
        if kind=="STEP_INTENT":
            if self.step_pending is not None or event["ledger_before"]!=self.ledger:
                raise ValueError("control intent ledger differs")
            self.step_pending=event["sequence"]
        elif kind=="STEP_COMPLETE":
            if event["intent_sequence"]!=self.step_pending:raise ValueError("physical completion without matching intent")
            delta={"simulation_attempts":1,"simulation_completed":1,"simulation_frames_attempted":5,"simulation_frames_completed":5}
            if event["ledger_before"]!=self.ledger or advance_ledger(self.ledger,"CONTROL",delta)!=event["ledger_after"]:
                raise ValueError("control completion ledger differs")
            self.ledger=event["ledger_after"];self.step_pending=None
        elif self.step_pending is not None:raise ValueError("business event inside incomplete physical step")
        return event
    def boundary(self):
        if self.pending is not None or self.step_pending is not None:
            raise ValueError("incomplete physical/lifecycle event at stream boundary")


def compiled_clock_units(manifest):
    """Compile bound XML into MjModel only; no MjData, reset or stepping."""
    import metaworld
    import mujoco
    from metaworld.asset_path_utils import full_V3_path_for
    files={"push-v3":"sawyer_xyz/sawyer_push_v3.xml", "reach-v3":"sawyer_xyz/sawyer_reach_v3.xml", "door-open-v3":"sawyer_xyz/sawyer_door_pull.xml"}
    package=Path(metaworld.__file__).parent
    result={}
    for task,name in files.items():
        path=Path(full_V3_path_for(name))
        key="metaworld/"+path.relative_to(package).as_posix()
        if runner.digest(path)!=manifest["library_source_sha256"][key]:raise ValueError("bound model XML changed")
        model=mujoco.MjModel.from_xml_path(str(path))
        timestep=float(model.opt.timestep)
        if not np.isfinite(timestep) or timestep<=0:raise ValueError("invalid compiled timestep")
        result[task]={"model_xml":key,"model_xml_sha256":runner.digest(path),"compiled_timestep_seconds":timestep,"env_step_frames":5,"env_step_seconds":5*timestep}
        del model
    return result


def analyze(path):
    m=runner.load(path);verify_git_inputs(m);output=path.parent
    clock_units=compiled_clock_units(m)
    models,_,_=runner.load_bank(m["config"])
    profile=json.loads((ROOT/m["config"]["nominal_profile_path"]).read_text(encoding="utf-8"))
    sources=iter(read_lines(output/"cold_sources.jsonl.gz"));rows=[];cold=[];pairings=[];update_pairs=[]
    journal=JournalAudit({k:m[k] for k in runner.IDENTITY});last_ledger={"counts":{},"by_phase":{}}
    for stream in range(8):
        business=deque()
        for event in read_lines(output/f"events_{stream:02}.jsonl.gz"):
            accepted=journal.accept(event)
            if accepted is not None:business.append(accepted)
        journal.boundary()
        cases=iter(read_lines(output/f"episodes_{stream:02}.jsonl.gz"));bank={p["id"]:p for p in m["operators_oracle"][stream]["states_oracle"]}
        for task in runner.TASKS:
            source=next(sources);expected={"stream":stream,"task":task,"scenario":"SOURCE_A","replicate":-1,"seed":runner.task_seed(stream,task,True),"method":"CALIBRATE_OLD16","operator_id_oracle":"A"}
            if any(source[k]!=v for k,v in expected.items()) or any(source[k]!=m[k] for k in runner.IDENTITY):raise ValueError("cold-source ordering/identity differs")
            verify_record.sigma=profile["rms_m"][task]
            verify_record.expected_env_dt=clock_units[task]["env_step_seconds"]
            verify_record(source,models[task],None,bank["A"],business)
            cold.append({**{k:source[k] for k in (*runner.IDENTITY,*expected)},**source["outcome"]});source_cache=source["new_cache"]
            for scenario in runner.SCENARIOS:
                label="A" if scenario=="UNCHANGED" else "B"
                for replicate in range(4):
                    branches={}
                    for method in METHODS:
                        record=next(cases);expected={"stream":stream,"task":task,"scenario":scenario,"replicate":replicate,"seed":runner.task_seed(stream,task),"method":method,"operator_id_oracle":label}
                        if any(record[k]!=v for k,v in expected.items()) or any(record[k]!=m[k] for k in runner.IDENTITY):raise ValueError("case ordering/identity differs")
                        verify_record(record,models[task],source_cache if method in PRIOR_CACHE_METHODS else None,bank[label],business)
                        rows.append({**{k:record[k] for k in (*runner.IDENTITY,*expected)},**record["outcome"]});branches[method]=record
                        for row in record["trace"]:
                            before,after=row["ledger_before"],row["ledger_after"]
                            for field,delta in (("simulation_attempts",1),("simulation_completed",1),("simulation_frames_attempted",5),("simulation_frames_completed",5)):
                                if after["counts"].get(field,0)-before["counts"].get(field,0)!=delta:raise ValueError("actual step frame cost differs")
                        last_ledger=record["ledger_after"]
                    for method in MID_METHODS:
                        pairings.append({**{k:expected[k] for k in ("stream","task","scenario","replicate","seed")},"method":method,
                                         "reason":runner.pairing_reason(branches[method],branches["CACHE_CONTINUE"])})
                    for method in ("MID8_WIDE","MID16_WIDE"):
                        update_pairs.append(runner.update_pair(branches[method],branches[method+"_KEEP"],branches["CACHE_CONTINUE"]))
        if next(cases,None) is not None or business:raise ValueError("extra raw case or event")
        print(f"Audited stream={stream}: {len(rows)}/2304",flush=True)
    if next(sources,None) is not None:raise ValueError("extra source")
    stats=statistics(m,rows,cold,pairings,update_pairs);summary=json.loads((output/"summary.json").read_text(encoding="utf-8"));status=json.loads((output/"status.json").read_text(encoding="utf-8"))
    equal(stats,summary["statistics"]);equal(pairings,summary["pairings"]);equal(cold,summary["cold_sources"]);equal(rows,summary["cases"])
    equal(update_pairs,summary["update_pairs"])
    expected_status="COMPLETED_TARGET_REPEAT_PASS" if stats["repeat_gate"]["passed"] else "COMPLETED_TARGET_REPEAT_FAILED"
    expected_counts={"episodes":2304,"cold_sources":24,"controlled_steps":stats["new_controlled_steps"],"controlled_resets":stats["new_controlled_resets"],"api_calls":0,"memory_writes":0}
    if any(status[k]!=v or summary[k]!=v for k,v in expected_counts.items()) or status["status"]!=expected_status or summary["status"]!=expected_status:raise ValueError("status/cost differs")
    equal(last_ledger,status["lifecycle"])
    equal(last_ledger,journal.ledger)
    lifecycle_resets=journal.resets
    counts=last_ledger["counts"]
    if counts.get("reset_completed")!=lifecycle_resets or counts.get("reset_attempts")!=lifecycle_resets or counts.get("simulation_errors",0) or counts.get("reset_errors",0):raise ValueError("incomplete lifecycle accounting")
    if counts["simulation_frames_completed"]!=500*lifecycle_resets+5*stats["new_controlled_steps"]:raise ValueError("complete simulator frame arithmetic differs")
    if lifecycle_resets!=51*stats["new_controlled_resets"] or stats["new_controlled_steps"]>1152384 or counts["simulation_frames_attempted"]>66000000:raise ValueError("factory/reset/frame cap differs")
    return {**{k:m[k] for k in runner.IDENTITY},**expected_counts,"status":expected_status,"integrity":"PASSED","statistics":stats,
            "clock_units_v2":clock_units,"original_frozen_clock_audit_passed":False,"clock_repair_new_robot_steps":0,
            "analysis_source_sha256":runner.digest(Path(__file__)),"analysis_git_commit":runner.git("rev-parse","HEAD"),
            "lifecycle":last_ledger,"events_checked":journal.sequence,"frozen_git_inputs_checked":len(m["input_sha256"]),
            "artifact_sha256":{p.name:runner.digest(p) for p in output.iterdir() if p.is_file()},
            "scope":"Recorded-observation replay; independent injected-action/RNG, event order, program/controller execution and reset/frame/step arithmetic. Registered guard/fit, pairing and repeat-summary helpers explicitly reused; no robot resimulation, complete hidden-state or probability qualification."}


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--manifest",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args()
    output=a.output.resolve();source=a.manifest.resolve()
    if output.exists() or source.parent in output.parents:raise FileExistsError("new external audit required")
    result=analyze(source);output.mkdir(parents=True,exist_ok=False);runner.write_json(output/"audit.json",result)
    print(json.dumps({k:result[k] for k in ("status","integrity","episodes","controlled_steps","controlled_resets")}))

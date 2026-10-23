"""Visible-only fixed continuation programs for an evaluator effect bank.

These are registered controls, not a learned selector or a value certificate.
No environment, snapshot, seed, actuator truth or future outcome is accepted.
"""
from dataclasses import asdict
import numpy as np
from src.analysis.capsule_record_json_v2 import normalize
from src.probe.cache_acquisition_evidence_v1 import CacheAcquisitionEvidenceV1, digest
from src.probe.chronological_cache_reference import BLOCK8
from src.probe.cold_start_response import ColdPrefix, infer_operator
from src.probe.continuous import StepObservation
from src.probe.forward_prediction import vector
from src.probe.operator_identification import affine_controller, encode_controller

PROGRAMS=("REUSE_OLD", "PROBE_KEEP", "PROBE_UPDATE", "PROBE_UPDATE_KEEP")


def ended(current):
    return current.success or current.terminated or current.truncated


def execute_warm(program, evidence, current, model, policy, step, emit):
    if program not in PROGRAMS or type(evidence) is not CacheAcquisitionEvidenceV1:
        raise ValueError("registered program and strict decision-time evidence required")
    if type(current) is not StepObservation or tuple(current.observation)!=evidence.prefix.observations[-1] or ended(current):
        raise ValueError("live four-step boundary required")
    theta=np.asarray(evidence.old_parameters).reshape(2,3)
    old=affine_controller(theta[:,:2],theta[:,2])
    return _execute(program,evidence.prefix.task,evidence.prefix.initial_observation,
        list(evidence.prefix.commands),list(evidence.prefix.observations),current,old,model,policy,step,emit)


def execute_cold(task, initial, model, policy, step, emit):
    if type(initial) is not StepObservation or ended(initial):raise ValueError("live controlled initial observation required")
    vector(initial.observation,39)
    return _execute("COLD8",task,initial.observation,[],[],initial,None,model,policy,step,emit)


def _execute(program,task,initial,commands,observations,current,old,model,policy,step,emit):
    calls=len(commands);start_calls=calls;trace=[];decisions=[];fit=None;fit_prefix=None;queries=0;stopped=False;last_sequence=-1
    controller=old;controller_kind="OLD" if old is not None else None
    def save(event,payload):
        nonlocal last_sequence
        declaration=normalize(payload);saved=emit(event,declaration)
        if (type(saved) is not dict or set(saved)!=set(declaration)|{"sequence","saved_ns"} or
            any(saved[k]!=v for k,v in declaration.items()) or type(saved["sequence"]) is not int or
            saved["sequence"]!=last_sequence+1 or type(saved["saved_ns"]) is not int):
            raise ValueError("saved public acknowledgement differs")
        last_sequence=saved["sequence"];return saved
    def choose(action,**payload):
        declaration=normalize({"action":action,"at_calls":calls,**payload})
        saved=save("CHOICE",declaration)
        decisions.append(saved)
        return saved
    def move(command,phase,decision,raw=None):
        nonlocal calls,current
        if ended(current) or calls>=500:raise ValueError("ended/exhausted program stepped")
        sent=np.asarray(command,np.float32)
        if sent.shape!=(4,) or not np.isfinite(sent).all() or np.any(abs(sent)>1):raise ValueError("bounded finite saved command required")
        payload={"at_calls":calls,"decision_sequence":decision["sequence"],"phase":phase,"command":sent.tolist(),
                 "before":asdict(current),"raw_policy":None if raw is None else np.asarray(raw,np.float32).tolist()}
        request=normalize(payload);saved=save("COMMAND",request)
        before=current;current=step(saved)
        if type(current) is not StepObservation:raise ValueError("public step observation required")
        vector(current.observation,39);calls+=1
        trace.append({"host_calls":calls,"phase":phase,"command":saved["command"],"raw_policy":request["raw_policy"],
            "decision_sequence":decision["sequence"],"command_sequence":saved["sequence"],"before":asdict(before),"after":asdict(current)})
        return current
    if program=="REUSE_OLD":
        decision=choose("RUN_OLD",controller=old)
    else:
        program_commands=BLOCK8 if program=="COLD8" else BLOCK8[4:]
        decision=choose("PROBE8",program=[list(c) for c in program_commands],prefix_steps=calls)
        for command in decision["program"]:
            if ended(current):break
            move(command,"FIXED_PROBE",decision)
            commands.append(tuple(trace[-1]["command"]));observations.append(current.observation)
        if not ended(current):
            if calls!=8:raise ValueError("exactly one complete eight-step open-loop prefix required")
            if program=="PROBE_KEEP":
                decision=choose("RUN_OLD",controller=old)
            else:
                fit_prefix=ColdPrefix(task,initial,tuple(commands),tuple(observations),True)
                fit=normalize(infer_operator(model,fit_prefix))
                if fit["valid"]:
                    selected=affine_controller(fit["matrix_xy"],fit["bias_xy"])
                    decision=choose("RUN_NEW",controller=selected,fit=fit,prefix_evidence_sha256=digest(asdict(fit_prefix)))
                    controller=decision["controller"];controller_kind="NEW"
                elif program=="PROBE_UPDATE_KEEP":
                    decision=choose("REJECT_KEEP_OLD",controller=old,fit=fit)
                    controller=decision["controller"];controller_kind="OLD"
                else:
                    decision=choose("STOP_INVALID_FIT",fit=fit);controller=None;controller_kind=None;stopped=True
    while not ended(current) and calls<500 and controller is not None:
        raw=np.asarray(policy(np.asarray(current.observation)),np.float32);queries+=1
        move(encode_controller(decision["controller"],raw),"POLICY",decision,raw)
    outcome={"success":bool(current.success),"stopped":stopped and not ended(current),"total_steps":calls,
        "suffix_steps":calls-start_calls,"deadline_loss":calls if current.success else 500,
        "fixed_probe_suffix_steps":sum(r["phase"]=="FIXED_PROBE" for r in trace),"policy_suffix_steps":sum(r["phase"]=="POLICY" for r in trace),
        "online_parameter_fits":int(fit is not None),"optimizer_nfev":int(fit.get("nfev",sum(v["nfev"] for v in fit.get("optimizer_trials",[])))) if fit else 0,
        "policy_queries":queries,"applied_new_controller":controller_kind=="NEW"}
    return {"program":program,"trace":normalize(trace),"decisions":normalize(decisions),"fit":fit,
            "fit_prefix":fit_prefix,"outcome":outcome}

"""Fixed visible C4/C8, continuous local PID, then at most 32 C8 task steps."""
from copy import deepcopy
from dataclasses import asdict

import numpy as np

from src.probe.cache_acquisition_evidence_v1 import digest
from src.probe.cold_start_response import ColdPrefix, infer_operator, validate_model
from src.probe.continuous import StepObservation
from src.probe.local_reprobe_v1 import anchor_ready, control_update, selected_anchor
from src.probe.operator_identification import affine_controller, encode_controller
from src.probe.physical_reprobe_v1 import Start
from src.probe.short_joint_reference_v1 import infer_four
from src.analysis.capsule_record_json_v2 import normalize

PROGRAM = np.asarray([[.4,0,0,0],[0,.4,0,0],[-.4,0,0,0],[0,-.4,0,0]],np.float32).tolist()


def ended(value):return value.success or value.terminated or value.truncated


def run(task, initial, nominal, boundary, policy, step, emit):
    if type(initial) is not StepObservation or ended(initial) or boundary not in (16,32,64):
        raise ValueError("live public initial state and registered boundary required")
    validate_model(nominal)
    if nominal["task"] != task:raise ValueError("matching frozen C8 model required")
    events=[];current=initial;calls=queries=0;prefix_commands=[];prefix_observations=[]
    controller=None;choice=None;move_count=task_count=0

    def save(kind,payload):
        expected=normalize(payload);saved=emit(kind,deepcopy(expected))
        if (set(saved)!=set(expected)|{"sequence","saved_ns"} or saved["sequence"]!=len(events)
                or digest({k:saved[k] for k in expected})!=digest(expected)):
            raise ValueError("saved acknowledgement differs")
        events.append({"kind":kind,"payload":deepcopy(saved)});return saved

    def act(command,phase,decision,raw=None):
        nonlocal current,calls
        if ended(current) or calls>=160:raise ValueError("ended or exhausted fixed window")
        sent=np.asarray(command,np.float32)
        if sent.shape!=(4,) or not np.isfinite(sent).all() or np.any(abs(sent)>1):raise ValueError("bounded command required")
        request=save("COMMAND",{"at_calls":calls,"phase":phase,"decision_sequence":decision["sequence"],
            "before":asdict(current),"command":sent.tolist(),"raw_policy":raw})
        supplied=deepcopy(request);after=step(supplied)
        if digest(supplied)!=digest(request) or type(after) is not StepObservation:raise ValueError("physical receipt differs")
        current=after;calls+=1
        save("STEP_RESULT",{"at_calls":calls,"command_sequence":request["sequence"],"after":asdict(current)})

    save("PROGRAM",{"at_calls":0,"task":task,"initial":asdict(initial),"boundary":boundary,
        "maximum_move":64,"maximum_task":32,"maximum_total":160,"nominal_sha256":digest(nominal)})
    reason="EARLY_PREFIX_END"
    for count in (4,8):
        probe=save("CHOICE",{"at_calls":calls,"action":"PROBE_FOUR","program":PROGRAM})
        for command in PROGRAM:
            if ended(current):break
            act(command,"FIXED_PROBE",probe)
            prefix_commands.append(command);prefix_observations.append(current.observation)
        if ended(current):break
        prefix=ColdPrefix(task,initial.observation,prefix_commands,prefix_observations,True)
        intent=save("FIT_INTENT",{"at_calls":calls,"prefix":asdict(prefix),"prefix_sha256":digest(asdict(prefix))})
        fit=infer_four(nominal,prefix) if count==4 else infer_operator(nominal,prefix)
        fitted=save("FIT_RESULT",{"at_calls":calls,"intent_sequence":intent["sequence"],"fit":fit})
        if not fit["valid"]:
            reason="INVALID_FOUR" if count==4 else "INVALID_EIGHT";break
        candidate=affine_controller(fit["matrix_xy"],fit["bias_xy"])
        selected=save("CHOICE",{"at_calls":calls,"action":"SAVE_C4_ONLY" if count==4 else "RUN_C8",
            "controller":candidate,"fit_sequence":fitted["sequence"]})
        if count==8:controller=candidate;choice=selected
    if choice is not None:
        while not ended(current) and calls<boundary:
            raw=np.asarray(policy(np.asarray(current.observation).copy()),np.float32).tolist();queries+=1
            act(encode_controller(controller,raw),"POLICY",choice,raw)
        reason="ENDED_BEFORE_BOUNDARY" if ended(current) else "WINDOW_COMPLETE"
        if not ended(current):
            start=Start(task,calls,current,controller["matrix_xy"],controller["offset"][:2])
            anchor=selected_anchor(start,"LOCAL_PID")
            entry=save("ACQUISITION_ENTRY",{"at_calls":calls,"before":asdict(current),"controller":controller,
                "source_choice_sequence":choice["sequence"],"anchor":list(anchor)})
            observations=[current.observation];integral=[0.,0.];lifted=current.observation[2]>=anchor[2]-.015
            while not ended(current) and move_count<64 and not anchor_ready(observations,anchor):
                updated,command=control_update(start,observations,lifted,integral,"LOCAL_PID")
                update=save("INTEGRAL_UPDATE",{"at_calls":calls,"integral_before":integral,"integral_after":updated})
                act(command,"REPOSITION",entry)
                move_count+=1;observations.append(current.observation);integral=updated
                lifted=lifted or current.observation[2]>=anchor[2]-.015
            task_choice=save("TASK_ENTRY",{"at_calls":calls,"controller":controller,"source_choice_sequence":choice["sequence"],
                "before":asdict(current),"movement_steps":move_count,"anchor_reached":anchor_ready(observations,anchor)})
            while not ended(current) and task_count<32:
                raw=np.asarray(policy(np.asarray(current.observation).copy()),np.float32).tolist();queries+=1
                act(encode_controller(task_choice["controller"],raw),"TASK_AFTER_MOVEMENT",task_choice,raw)
                task_count+=1
            reason="EARLY_SUCCESS_OR_ENV_END" if ended(current) else "WINDOW_COMPLETE"
    outcome={"total_steps":calls,"reposition_steps":move_count,"task_steps":task_count,"policy_queries":queries,
        "success":current.success,"terminated":current.terminated,"truncated":current.truncated,"stop_reason":reason,
        "task_utility_established":False,"new_response_model_fits":0}
    save("OUTCOME",{"at_calls":calls,"outcome":outcome,"final":asdict(current)})
    return {"events":events,"outcome":outcome}

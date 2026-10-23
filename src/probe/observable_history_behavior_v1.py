"""Fixed saved C8/PID behavior plus a prescribed real measurement program."""
from copy import deepcopy
from dataclasses import asdict
import numpy as np

from src.probe.cold_start_response import ColdPrefix,infer_operator,validate_model
from src.probe.short_joint_reference_v1 import infer_four
from src.probe.continuous import StepObservation
from src.probe.local_reprobe_v1 import selected_anchor,anchor_ready,control_update
from src.probe.operator_identification import affine_controller,encode_controller
from src.probe.physical_reprobe_v1 import Start
from src.probe.cache_acquisition_evidence_v1 import digest
from src.analysis.capsule_record_json_v2 import normalize

PROBE=np.array([[.4,0,0,0],[0,.4,0,0],[-.4,0,0,0],[0,-.4,0,0]],np.float32).tolist()


def ended(s):return s.success or s.terminated or s.truncated


def validate_program(kind,actions):
    if kind not in ("FEEDBACK8","BALANCED8"):raise ValueError("prescribed measurement program required")
    expected=np.array([[.4,0,0,-1],[0,.4,0,-1],[-.4,0,0,-1],[0,-.4,0,-1]]*2,np.float32).tolist()
    if type(actions) is not list or sorted(actions)!=sorted(expected):raise ValueError("exact balanced eight actions required")


def run(task,initial,nominal,boundary,kind,actions,policy,step,emit):
    if type(initial) is not StepObservation or ended(initial) or boundary not in (16,32,64):raise ValueError("live initial and registered boundary required")
    validate_program(kind,actions);validate_model(nominal)
    if nominal["task"]!=task:raise ValueError("matching frozen C8 model")
    events=[];current=initial;calls=queries=0;prefix_commands=[];prefix_observations=[]
    controller=choice=None;move_count=measure_count=task_count=0
    def save(name,payload):
        expected=normalize(payload);saved=emit(name,deepcopy(expected))
        if set(saved)!=set(expected)|{"sequence","saved_ns"} or saved["sequence"]!=len(events) or digest({k:saved[k] for k in expected})!=digest(expected):raise ValueError("durable acknowledgement differs")
        events.append({"kind":name,"payload":deepcopy(saved)});return saved
    def act(command,phase,decision,raw=None,desired=None):
        nonlocal current,calls
        if ended(current) or calls>=168:raise ValueError("ended/exhausted execution")
        sent=np.asarray(command,np.float32)
        if sent.shape!=(4,) or not np.isfinite(sent).all() or np.any(abs(sent)>1):raise ValueError("finite bounded command")
        request=save("COMMAND",{"at_calls":calls,"phase":phase,"decision_sequence":decision["sequence"],"before":asdict(current),
            "command":sent.tolist(),"raw_policy":raw,"measurement_desired":desired})
        supplied=deepcopy(request);current=step(supplied)
        if type(current) is not StepObservation or digest(supplied)!=digest(request):raise ValueError("physical acknowledgement differs")
        calls+=1;save("STEP_RESULT",{"at_calls":calls,"command_sequence":request["sequence"],"after":asdict(current)})
    def task_action(phase,decision):
        nonlocal queries
        raw=np.asarray(policy(np.array(current.observation)),np.float32).tolist();queries+=1
        act(encode_controller(controller,raw),phase,decision,raw)
    save("PROGRAM",{"at_calls":0,"task":task,"initial":asdict(initial),"boundary":boundary,"measurement_program":kind,"balanced_actions":actions,
        "maximum_move":64,"maximum_measurement":8,"maximum_task":32,"maximum_total":168,"nominal_sha256":digest(nominal)})
    reason="EARLY_PREFIX_END"
    for length in (4,8):
        probe=save("CHOICE",{"at_calls":calls,"action":"PROBE_FOUR","program":PROBE})
        for u in PROBE:
            if ended(current):break
            act(u,"FIXED_PROBE",probe);prefix_commands.append(u);prefix_observations.append(current.observation)
        if ended(current):break
        prefix=ColdPrefix(task,initial.observation,prefix_commands,prefix_observations,True)
        intent=save("FIT_INTENT",{"at_calls":calls,"prefix":asdict(prefix),"prefix_sha256":digest(asdict(prefix))})
        fitted=infer_four(nominal,prefix) if length==4 else infer_operator(nominal,prefix)
        result=save("FIT_RESULT",{"at_calls":calls,"intent_sequence":intent["sequence"],"fit":fitted})
        if not fitted["valid"]:reason="INVALID_FOUR" if length==4 else "INVALID_EIGHT";break
        selected=save("CHOICE",{"at_calls":calls,"action":"SAVE_C4_ONLY" if length==4 else "RUN_C8","fit_sequence":result["sequence"],
            "controller":affine_controller(fitted["matrix_xy"],fitted["bias_xy"])})
        if length==8:controller=selected["controller"];choice=selected
    if choice is not None:
        while not ended(current) and calls<boundary:task_action("POLICY",choice)
        reason="ENDED_BEFORE_BOUNDARY" if ended(current) else "WINDOW_COMPLETE"
        if not ended(current):
            start=Start(task,calls,current,controller["matrix_xy"],controller["offset"][:2]);anchor=selected_anchor(start,"LOCAL_PID")
            entry=save("ACQUISITION_ENTRY",{"at_calls":calls,"before":asdict(current),"controller":controller,"source_choice_sequence":choice["sequence"],"anchor":list(anchor)})
            observations=[current.observation];integral=[0.,0.];lifted=current.observation[2]>=anchor[2]-.015
            while not ended(current) and move_count<64 and not anchor_ready(observations,anchor):
                updated,u=control_update(start,observations,lifted,integral,"LOCAL_PID")
                save("INTEGRAL_UPDATE",{"at_calls":calls,"integral_before":integral,"integral_after":updated});act(u,"REPOSITION",entry)
                move_count+=1;observations.append(current.observation);integral=updated;lifted=lifted or current.observation[2]>=anchor[2]-.015
            measurement=save("MEASUREMENT_ENTRY",{"at_calls":calls,"before":asdict(current),"controller":controller,"source_choice_sequence":choice["sequence"],
                "measurement_program":kind,"balanced_actions":actions,"movement_steps":move_count,"anchor_reached":anchor_ready(observations,anchor)})
            while not ended(current) and measure_count<8:
                if kind=="FEEDBACK8":task_action("MEASURE_FEEDBACK",measurement)
                else:
                    desired=actions[measure_count];act(encode_controller(controller,desired),"MEASURE_BALANCED",measurement,desired=desired)
                measure_count+=1
            tail=save("TASK_ENTRY",{"at_calls":calls,"before":asdict(current),"controller":controller,"source_choice_sequence":choice["sequence"],"measurement_steps":measure_count})
            while not ended(current) and task_count<32:task_action("TASK_AFTER_MEASUREMENT",tail);task_count+=1
            reason="EARLY_SUCCESS_OR_ENV_END" if ended(current) else "WINDOW_COMPLETE"
    outcome={"total_steps":calls,"reposition_steps":move_count,"measurement_steps":measure_count,"task_steps":task_count,"policy_queries":queries,
        "success":current.success,"terminated":current.terminated,"truncated":current.truncated,"stop_reason":reason,"new_response_model_fits":0,"task_utility_established":False}
    save("OUTCOME",{"at_calls":calls,"outcome":outcome,"final":asdict(current)})
    return {"events":events,"outcome":outcome}

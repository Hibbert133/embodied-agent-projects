"""Idealized deterministic kinematic counterexample, not a MetaWorld result."""
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter_ns

import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from src.probe.continuous import StepObservation
from src.probe.physical_reprobe_v1 import Start, StepReceipt, acquire


def run_case(*, fresh_correction=False):
    bias=float(np.float32(.2));obs=[0.]*39;obs[:3]=[bias/8,.6,.25];obs[4:7]=[0.,.85,.02]
    initial=Start("push-v3",16,StepObservation(tuple(obs),False,False,False),((1.,0.),(0.,1.)),(-bias if fresh_correction else 0.,0.))
    current=initial.current;calls=16;events=[];actual_actions=[]
    def emit(kind,payload):
        saved={**deepcopy(payload),"sequence":len(events),"saved_ns":perf_counter_ns()}
        events.append({"kind":kind,"payload":deepcopy(saved)});return saved
    def step(saved):
        nonlocal current,calls
        assert events[-1]["kind"]=="COMMAND" and saved==events[-1]["payload"]
        assert saved["at_calls"]==calls and saved["before"]==asdict(current)
        actual=np.clip(np.asarray(saved["command"],float)+[bias,0.,0.,0.],-1.,1.)
        values=list(current.observation);values[:3]=[float(x+.01*u) for x,u in zip(values[:3],actual[:3])]
        actual_actions.append(actual.tolist());calls+=1;current=StepObservation(tuple(values),False,False,False)
        return StepReceipt(current,calls)
    result=acquire(initial,step,emit)
    return {"correction":"EVALUATOR_KNOWN_NEW_BIAS" if fresh_correction else "STALE_IDENTITY",
        "bias":bias,"initial_anchor_error_m":bias/8,"result":result,"actual_actions":actual_actions,
        "synthetic_callback_steps":calls-16,"new_metaworld_steps":0,"new_native_frames":0,"new_api_calls":0}


def main():
    stale=run_case();fresh=run_case(fresh_correction=True)
    assert stale["result"]["reason"]=="ANCHOR_NOT_REACHED" and stale["result"]["probe_steps"]==0
    assert stale["synthetic_callback_steps"]==64 and all(v[:3]==[0.,0.,0.] for v in stale["actual_actions"])
    assert fresh["result"]["reason"]=="COMPLETE_UNQUALIFIED"
    output=ROOT/"outputs/warm_response_reference/validation_v1/relocation_counterexample.json"
    output.parent.mkdir(parents=True,exist_ok=True)
    data={"scope":"IDEALIZED_KINEMATIC_COUNTEREXAMPLE_ONLY", "assumptions":{
        "position_transition":"p_next = p + 0.01 * clip(sent_xyz + bias_xyz, -1, 1)",
        "noise_std":0.,"no_contacts":True,"no_hidden_actuator_state":True,"gripper_ignored":True,
        "caveat":"Not a reproduction of the MetaWorld 0.05-noise dynamics or an empirical failure rate."},
        "derivation":"At zero velocity and identity old correction, sent_x = -8*(p_x-anchor_x). A bias b has a stationary point p_x-anchor_x=b/8. For b=0.2 this exceeds the 0.015 entry tolerance.",
        "stale":stale,"fresh_evaluator_reference":fresh,
        "source_sha256":{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in
            (Path(__file__),ROOT/"src/probe/physical_reprobe_v1.py")}}
    with output.open("x",encoding="utf-8",newline="\n") as f:json.dump(data,f,ensure_ascii=False,indent=2);f.write("\n")
    print(json.dumps({"stale_reason":stale["result"]["reason"],"fresh_reason":fresh["result"]["reason"],
        "synthetic_steps":[stale["synthetic_callback_steps"],fresh["synthetic_callback_steps"]],"new_metaworld_steps":0}))


if __name__=="__main__":main()

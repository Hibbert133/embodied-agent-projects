"""Same registered relocation with optional measurement; no simulator or fit API."""
from copy import deepcopy
from dataclasses import asdict
from src.analysis.capsule_record_json_v2 import normalize
from src.probe import local_reprobe_v1 as old
from src.probe.physical_reprobe_v1 import Start,StepReceipt
from src.probe.task_passive_pi_v1 import require,digest


def acquire(start,step,emit,*,method,measure=True):
    require(type(measure) is bool,'explicit measurement branch')
    if measure:return old.acquire(start,step,emit,method=method)
    require(type(start) is Start and method=='LOCAL_PID','registered no-probe strong reference')
    current=start.current;calls=start.completed_steps;history=[current.observation];anchor=old.selected_anchor(start,method)
    integral=[0.,0.];count=0;events=[];sequence=None
    def save(kind,payload):
        nonlocal sequence
        p=normalize(payload);ack=emit(kind,deepcopy(p))
        require(type(ack) is dict and set(ack)==set(p)|{'sequence','saved_ns'} and (sequence is None or ack['sequence']==sequence+1)
            and digest({k:ack[k] for k in p})==digest(p),'saved no-probe operation acknowledgement')
        sequence=ack['sequence'];events.append({'kind':kind,'payload':deepcopy(ack)});return ack
    choice=save('REACQUIRE_CHOICE',{'at_calls':calls,'start':asdict(start),'scope':'LOCAL_PID_RELOCATION_ONLY_V1','anchor':list(anchor),
        'maximum_reposition_steps':64,'task_reserve':100,'probe_program':[],'relocation_method':method,'integral_gain':.32,'integral_limit':.5})
    reason=None
    if old._ended(current):reason='ALREADY_ENDED'
    elif 500-calls<172:reason='ENTRY_BUDGET_INSUFFICIENT'
    else:
        lifted=current.observation[2]>=anchor[2]-.015
        while not old.anchor_ready(history,anchor) and count<64 and not old._ended(current):
            updated,command=old.control_update(start,history,lifted,integral,method)
            save('INTEGRAL_UPDATE',{'at_calls':calls,'integral_before':integral,'integral_after':updated})
            request=save('COMMAND',{'at_calls':calls,'decision_sequence':choice['sequence'],'phase':'REPOSITION','before':asdict(current),'command':command,'raw_policy':None})
            supplied=deepcopy(request);receipt=step(supplied)
            require(digest(supplied)==digest(request) and type(receipt) is StepReceipt and receipt.completed_steps==calls+1,'actual continuous no-probe relocation receipt')
            current,calls=receipt.current,receipt.completed_steps;history.append(current.observation);count+=1;integral=updated
            lifted=lifted or current.observation[2]>=anchor[2]-.015
            save('STEP_RESULT',{'at_calls':calls,'command_sequence':request['sequence'],'after':asdict(current)})
        reason='ENDED_DURING_REPOSITION' if old._ended(current) else 'RELOCATION_COMPLETE_UNQUALIFIED' if old.anchor_ready(history,anchor) else 'ANCHOR_NOT_REACHED'
    evidence=old.relocation_evidence(start,integral,old.anchor_ready(history,anchor))
    save('RELOCATION_EVIDENCE',{'at_calls':calls,**evidence})
    result={'reason':reason,'completed_steps':calls,'new_steps':calls-start.completed_steps,'reposition_steps':count,'probe_steps':0,'remaining_steps':500-calls,
        'final':asdict(current),'measurement_model_qualified':False,'parameter_fits':0,'relocation_method':method,'measurement_anchor':list(anchor),
        'relocation_evidence':evidence,'window':None}
    save('REACQUIRE_RESULT',{'at_calls':calls,**result});return {**result,'events':events}

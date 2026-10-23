"""Public, post-acquisition supplemental-trace release; no simulator or fitting.

The common view intentionally retains the real endpoint and task-controller
memory. MASKED means no *supplemental trace*, never absence of all information.
This module authenticates no physical world: a native host still has to bind
receipts, durable events, randomization and continuity before collection.
"""
from copy import deepcopy
from dataclasses import asdict,replace
import math
from src.probe.task_memory_option_v1 import TaskMemory,TaskMemoryMachine
from src.probe.continuous import StepObservation
from src.probe.task_passive_pi_v1 import digest,require
from src.analysis.capsule_record_json_v2 import normalize

ACTIONS=('CONTINUE','VALIDATE8','MOVE_MEASURE')
RATES=(.125,.5,2.,8.)
PHASES={'CONTINUE':(), 'VALIDATE8':('VALIDATION_TASK',), 'MOVE_MEASURE':('REPOSITION','MEASUREMENT')}
REASONS=('NO_ACQUISITION','COMPLETE','EARLY_END','PARTIAL','BUDGET_KEEP')


def numeric(value,low=None,high=None):
    require(type(value) in (int,float) and math.isfinite(value),'finite public number')
    require((low is None or value>=low) and (high is None or value<=high),'number outside registered range')
    return float(value)


def ended(memory):return any((memory.current.success,memory.current.terminated,memory.current.truncated))


def observations(value):
    require(type(value) is dict and set(value)=={'observation','terminated','truncated','success'},'strict public observation')
    require(all(type(value[k]) is bool for k in ('terminated','truncated','success')),'exact public stop flags')
    require(type(value['observation']) in (tuple,list) and len(value['observation'])==39,'39 actual public coordinates')
    for v in value['observation']:numeric(v)
    return normalize(asdict(StepObservation(**value)))


def memory(value):
    """Reject private/nonnumeric nested observation data, including stop flags."""
    require(type(value) is dict and 'current' in value,'saved public memory')
    observations(value['current'])
    result=TaskMemory.from_dict(value)
    require(digest(normalize(result.to_dict()))==digest(value),'canonical actual task memory')
    return result


def public_record(before,after,action,steps,reason):
    require(type(before) is TaskMemory and type(after) is TaskMemory,'actual public memory snapshots')
    memory(normalize(before.to_dict()));memory(normalize(after.to_dict()))
    require(action in ACTIONS and reason in REASONS and type(steps) in (tuple,list),'registered acquisition record')
    require(before.task==after.task and before.saved_controller==after.saved_controller and before.time_constant_s==after.time_constant_s,
            'acquisition must not change the saved task controller or its rate')
    require(after.completed_steps==before.completed_steps+len(steps)<=500,'actual consecutive acquisition cost')
    require(not steps or not ended(before),'no acquisition after task end')
    if action!='VALIDATE8':require(before.integral_xy==after.integral_xy,'movement suspends task integral')
    require(len(steps)<=(0 if action=='CONTINUE' else 8 if action=='VALIDATE8' else 72),'registered acquisition step cap')
    current=observations(normalize(asdict(before.current)));at=before.completed_steps;clean=[];previous_phase=-1;counts={p:0 for p in PHASES[action]}
    for step in steps:
        require(type(step) is dict and set(step)=={'at_calls','phase','command','before','after'},'unknown/private/extra trace field')
        require(type(step['at_calls']) is int and step['at_calls']==at,'acquisition clock, no future or repeated receipt')
        require(not any(current[k] for k in ('success','terminated','truncated')),'receipt after real end')
        require(step['phase'] in PHASES[action],'phase belongs to actual acquisition')
        phase=PHASES[action].index(step['phase']);require(phase>=previous_phase,'repeated/reversed acquisition phase');previous_phase=phase
        command=step['command'];require(type(command) in (tuple,list) and len(command)==4,'bounded actual send')
        command=[numeric(v,-1,1) for v in command]
        require(digest(observations(step['before']))==digest(current),'trace does not continue real observation')
        current=observations(step['after']);clean.append(dict(at_calls=at,phase=step['phase'],command=command,before=observations(step['before']),after=current))
        counts[step['phase']]+=1;at+=1
    require(counts.get('REPOSITION',0)<=64 and counts.get('MEASUREMENT',0)<=8,'movement/measurement caps')
    require(digest(current)==digest(observations(normalize(asdict(after.current)))),'returned memory is not actual final observation')
    if not steps:require(before==after,'zero-step acquisition cannot silently change memory')
    if reason=='EARLY_END':require(ended(after),'early-end reason requires real end')
    if action!='CONTINUE' and reason=='COMPLETE':
        require(len(steps)==8 if action=='VALIDATE8' else counts.get('MEASUREMENT',0)==8,'complete acquisition requires eight actual measurements')
    if reason=='BUDGET_KEEP':require(not steps,'budget refusal cannot conceal paid movement')
    if action=='CONTINUE':require(reason=='NO_ACQUISITION','zero acquisition reason')
    return dict(schema='PUBLIC_ACQUISITION_SIGNAL_RECORD_V1',before_memory=normalize(before.to_dict()),
        post_memory=normalize(after.to_dict()),action=action,steps=clean,reason=reason)


def seal(record,physical_finished_sequence):
    require(type(record) is dict and set(record)=={'schema','before_memory','post_memory','action','steps','reason'},'strict public record')
    require(record['schema']=='PUBLIC_ACQUISITION_SIGNAL_RECORD_V1','versioned public trace')
    checked=public_record(memory(record['before_memory']),memory(record['post_memory']),record['action'],record['steps'],record['reason'])
    require(digest(checked)==digest(record),'noncanonical or tampered public trace')
    require(type(physical_finished_sequence) is int and physical_finished_sequence>=0,'host physical return event')
    return dict(schema='ACQUISITION_SIGNAL_SEAL_V1',record=deepcopy(checked),record_sha256=digest(checked),physical_finished_sequence=physical_finished_sequence)


def common_view(record):
    steps=record['steps']
    return dict(schema='INFORMATION_RELEASE_COMMON_V1',before_memory=deepcopy(record['before_memory']),post_memory=deepcopy(record['post_memory']),
        action=record['action'],paid_acquisition_steps=len(steps),reason=record['reason'],
        phase_counts={p:sum(s['phase']==p for s in steps) for p in PHASES[record['action']]})


def validate_view(view):
    require(type(view) is dict and set(view)=={'common','signal'},'only common public state and supplemental signal are model inputs')
    c=view['common'];require(type(c) is dict and set(c)=={'schema','before_memory','post_memory','action','paid_acquisition_steps','reason','phase_counts'}
        and c['schema']=='INFORMATION_RELEASE_COMMON_V1','strict common-state model interface')
    before=memory(c['before_memory']);after=memory(c['post_memory']);action=c['action'];cost=c['paid_acquisition_steps']
    require(action in ACTIONS and c['reason'] in REASONS and type(cost) is int and cost>=0,'registered actual acquisition summary')
    require(type(c['phase_counts']) is dict and set(c['phase_counts'])==set(PHASES[action])
        and all(type(n) is int and n>=0 for n in c['phase_counts'].values()) and sum(c['phase_counts'].values())==cost,'actual phase counts')
    require(before.task==after.task and before.saved_controller==after.saved_controller and before.time_constant_s==after.time_constant_s
        and after.completed_steps==before.completed_steps+cost<=500,'common actual continuation state and controller')
    require(cost<=(0 if action=='CONTINUE' else 8 if action=='VALIDATE8' else 72),'registered actual cost')
    require(c['phase_counts'].get('REPOSITION',0)<=64 and c['phase_counts'].get('MEASUREMENT',0)<=8,'registered phase caps')
    require(not cost or not ended(before),'no acquisition after task end')
    if action!='VALIDATE8':require(before.integral_xy==after.integral_xy,'movement retains task integral')
    if not cost:require(before==after,'no unobserved zero-cost memory change')
    if action=='CONTINUE':require(c['reason']=='NO_ACQUISITION','registered continuation reason')
    if c['reason']=='EARLY_END':require(ended(after),'real common terminal state')
    if c['reason']=='BUDGET_KEEP':require(cost==0,'budget refusal cannot conceal costs')
    if c['reason']=='COMPLETE' and action!='CONTINUE':
        require(cost==8 if action=='VALIDATE8' else c['phase_counts'].get('MEASUREMENT',0)==8,'complete actual measurement')
    if view['signal'] is not None:
        require(cost>0,'empty trace must collapse both model views')
        record=public_record(before,after,action,view['signal'],c['reason'])
        require(digest(common_view(record))==digest(c),'supplemental trace and common view differ')
    return before,after


def release(saved,*,expose,release_sequence,receiver_version):
    require(type(saved) is dict and set(saved)=={'schema','record','record_sha256','physical_finished_sequence'}
            and saved['schema']=='ACQUISITION_SIGNAL_SEAL_V1','saved physical return before release')
    require(digest(saved)==digest(seal(saved['record'],saved['physical_finished_sequence'])),'changed or stale sealed acquisition')
    require(type(expose) is bool and type(release_sequence) is int and release_sequence>saved['physical_finished_sequence'],'release must follow physical completion')
    require(type(receiver_version) is str and len(receiver_version)==64 and all(c in '0123456789abcdef' for c in receiver_version),'frozen receiver identity')
    r=saved['record'];steps=r['steps']
    # Bindings are audit metadata and are deliberately absent from model_view.
    common=common_view(r)
    view=dict(common=common,signal=deepcopy(steps) if expose and steps else None)
    validate_view(view)
    return dict(schema='INFORMATION_RELEASE_RECEIPT_V1',model_view=view,
        binding=dict(record_sha256=saved['record_sha256'],physical_finished_sequence=saved['physical_finished_sequence'],
            release_sequence=release_sequence,assigned_exposure=expose,receiver_version=receiver_version,view_sha256=digest(view)),
        new_environment_steps=0,new_policy_queries=0,new_model_fits=0,physical_safety_guarantee=False)


def assign(saved,*,probability,uniform,release_sequence,receiver_version):
    """Consume a host's *post-return* draw; this cannot authenticate its RNG."""
    p=numeric(probability);u=numeric(uniform)
    require(0<p<1 and 0<=u<1,'positive exposure support and actual uniform draw')
    receipt=release(saved,expose=u<p,release_sequence=release_sequence,receiver_version=receiver_version)
    receipt['binding'].update(assignment_probability=p,random_uniform=u)
    return receipt


def validate_receipt(saved,receipt):
    require(type(receipt) is dict and type(receipt.get('binding')) is dict,'saved randomized-release receipt')
    b=receipt['binding']
    require(set(b)=={'record_sha256','physical_finished_sequence','release_sequence','assigned_exposure','receiver_version',
        'view_sha256','assignment_probability','random_uniform'},'strict randomized-release binding')
    expected=assign(saved,probability=b['assignment_probability'],uniform=b['random_uniform'],
        release_sequence=b['release_sequence'],receiver_version=b['receiver_version'])
    require(digest(expected)==digest(receipt),'changed release, receiver, propensity, view or random assignment')
    return validate_view(receipt['model_view'])


def validate_release(saved,receipt):
    require(type(receipt) is dict and type(receipt.get('binding')) is dict,'saved release receipt')
    b=receipt['binding']
    if 'assignment_probability' in b:return validate_receipt(saved,receipt)
    expected=release(saved,expose=b.get('assigned_exposure'),release_sequence=b.get('release_sequence'),receiver_version=b.get('receiver_version'))
    require(digest(expected)==digest(receipt),'changed deterministic deployment release')
    return validate_view(receipt['model_view'])


def choose_rate(view,base_risks,full_risks=None):
    _,after=validate_view(view)
    require(not ended(after) and after.completed_steps<500,'no receiving decision after actual task end')
    def scores(values):
        require(type(values) in (tuple,list) and len(values)==4,'four registered task-rate risks')
        return tuple(numeric(v,0,500) for v in values)
    base=scores(base_risks)
    if view['signal'] is None:
        require(full_risks is None,'empty/withheld signal must use the same common-state head');used=base
    else:require(full_risks is not None,'actual released signal requires explicit signal-conditioned risks');used=scores(full_risks)
    i=min(range(4),key=lambda j:(used[j],RATES[j]!=.5,j))
    return dict(time_constant_s=RATES[i],risk_vector=list(used),default_tie_prefers_half_second=True,
                input_view_sha256=digest(view),information_is_supplemental=view['signal'] is not None)


def receiver_plan(saved,receipt,base_risks,full_risks=None):
    _,after=validate_release(saved,receipt)
    chosen=choose_rate(receipt['model_view'],base_risks,full_risks)
    return dict(schema='SAVED_INFORMATION_RECEIVER_DECISION_V1',release_receipt_sha256=digest(receipt),
        receiver_version=receipt['binding']['receiver_version'],base_risks=list(base_risks),
        full_risks=None if full_risks is None else list(full_risks),choice=chosen,gain_plan=gain_plan(after,chosen['time_constant_s']))


def consume_receiver(machine,saved_decision,saved_return,receipt):
    require(type(saved_decision) is dict and 'base_risks' in saved_decision and 'full_risks' in saved_decision,'saved receiver decision before command')
    expected=receiver_plan(saved_return,receipt,saved_decision['base_risks'],saved_decision['full_risks'])
    require(digest(saved_decision)==digest(expected),'receiver decision changed after saving')
    return consume_gain(machine,saved_decision['gain_plan'])


def gain_plan(memory,rate):
    require(type(memory) is TaskMemory and not ended(memory) and memory.completed_steps<500,'live returned task memory')
    require(type(rate) in (int,float) and rate in RATES,'registered fixed-policy outer PI rate')
    after=replace(memory,time_constant_s=float(rate))
    return dict(schema='CARRIED_INTEGRAL_RATE_PLAN_V1',before_memory_sha256=memory.sha256,after_memory=normalize(after.to_dict()),
        new_environment_steps=0,new_policy_queries=0,integral_reset=False,controller_mapping_changed=False,
        physical_safety_guarantee=False,task_benefit_established=False)


def consume_gain(machine,saved):
    require(type(machine) is TaskMemoryMachine and machine.pending is None and machine.suspended is None,'no outstanding command or suspended controller')
    require(type(saved) is dict and type(saved.get('after_memory')) is dict,'saved carried-integral rate plan')
    rate=saved['after_memory'].get('time_constant_s');expected=gain_plan(machine.memory,rate)
    require(digest(saved)==digest(expected),'unknown, stale, future or changed gain plan')
    used=getattr(machine,'_information_rate_plans_used',frozenset());require(digest(saved) not in used,'rate plan already consumed, including a no-op rate')
    before=machine.memory;machine.memory=TaskMemory.from_dict(saved['after_memory']);machine._information_rate_plans_used=used|{digest(saved)}
    return dict(schema='CARRIED_INTEGRAL_RATE_COMMIT_V1',plan_sha256=digest(saved),before_memory_sha256=before.sha256,
        after_memory_sha256=machine.memory.sha256,integral_unchanged=machine.memory.integral_xy==before.integral_xy,
        new_environment_steps=0,new_policy_queries=0)

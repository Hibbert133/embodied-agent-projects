"""Constructed software/numerical verification only, never robot samples."""
from dataclasses import asdict,replace
import hashlib
from fractions import Fraction
import numpy as np
from src.analysis import response_qualification_io_v1 as io
from src.analysis.capsule_record_json_v2 import normalize
from src.probe.continuous import StepObservation
from src.probe.task_memory_option_v1 import TaskMemory,TaskMemoryMachine
from src.probe import information_release_v1 as r
from src.probe.information_release_features_v1 import encode
from src.analysis.information_release_targets_v1 import targets

VERSION='c'*64  # Constructed receiver marker; no model has been fitted.


def constructed_record(task,action,terminal):
    def current(i,end=False):
        v=[0.]*39;v[:3]=[.1+.001*i,.8,.25];return StepObservation(tuple(v),False,False,end)
    at=16;before=replace(TaskMemory.initial(task,current(at,terminal and action=='CONTINUE')),completed_steps=at,integral_xy=(.15,-.08))
    n=0 if action=='CONTINUE' else 8 if action=='VALIDATE8' else 10
    steps=[];obs=before.current
    for i in range(n):
        after=current(at+i+1,terminal and i==n-1)
        phase='VALIDATION_TASK' if action=='VALIDATE8' else 'REPOSITION' if i<2 else 'MEASUREMENT'
        steps.append(dict(at_calls=at+i,phase=phase,command=[.2,-.1,0.,-1.],before=normalize(asdict(obs)),after=normalize(asdict(after))))
        obs=after
    after=replace(before,current=obs,completed_steps=at+n)
    return r.public_record(before,after,action,steps,'NO_ACQUISITION' if action=='CONTINUE' else 'EARLY_END' if terminal else 'COMPLETE')


def tensor_receipt(view):
    x=encode(view);n=int(x['trace_mask'].sum())
    return dict(common=x['common'].tolist(),trace_present=x['trace'][:n].tolist(),valid_steps=n,
        trace_shape=list(x['trace'].shape),trace_sha256=hashlib.sha256(x['trace'].astype('<f8').tobytes()).hexdigest(),
        mask_sha256=hashlib.sha256(x['trace_mask'].tobytes()).hexdigest())


def generate():
    cases=[];math_rows=[]
    for task in io.TASKS:
        for action in r.ACTIONS:
            for terminal in (False,True):
                saved=r.seal(constructed_record(task,action,terminal),100);views=[]
                for expose in (False,True):
                    receipt=r.assign(saved,probability=.5,uniform=.25 if expose else .75,release_sequence=101,receiver_version=VERSION)
                    view=receipt['model_view'];plan=None;command=None
                    if not terminal:
                        plan=r.receiver_plan(saved,receipt,[180,140,160,200],[130,180,90,210] if view['signal'] else None)
                        machine=TaskMemoryMachine(r.memory(saved['record']['post_memory']));r.consume_receiver(machine,plan,saved,receipt)
                        command=machine.plan([.2,-.1,.3,-1.])
                    views.append(dict(receipt=receipt,tensors=tensor_receipt(view),receiver_decision=plan,next_command=command))
                cases.append(dict(task=task,action=action,terminal=terminal,saved_return=saved,views=views))
    saved=r.seal(constructed_record('push-v3','MOVE_MEASURE',False),100)
    for p in (Fraction(1,4),Fraction(1,2),Fraction(3,4)):
        for y0,y1 in ((40,200),(200,40),(200,200),(500,60)):
            for m0,m1 in ((0,0),(100,100),(120,320)):
                outcomes=[]
                for expose,y in ((False,y0),(True,y1)):
                    receipt=r.assign(saved,probability=float(p),uniform=float(p)/2 if expose else float(p)+(1-float(p))/2,
                        release_sequence=101,receiver_version=VERSION)
                    t=targets(saved_return=saved,release_receipt=receipt,cutoff_loss=y,mu_masked=m0,mu_full=m1,expected_receiver_version=VERSION,
                        independent_group='SYNTHETIC_A',nuisance_training_groups=['SYNTHETIC_B'],expected_probability=float(p))
                    outcomes.append(dict(release_receipt=receipt,cutoff_loss=y,target=t))
                math_rows.append(dict(probability=str(p),constructed_potential_losses=[y0,y1],nuisance=[m0,m1],outcomes=outcomes))
    return dict(schema='INFORMATION_RELEASE_CONSTRUCTED_VERIFICATION_V1',classification='SOFTWARE_ONLY_NOT_ROBOT_POPULATION',
        public_cases=cases,algebra_cases=math_rows,new_environment_steps=0,new_resets=0,new_physical_frames=0,
        new_scientific_model_fits=0,new_online_LLM_API_calls=0,task_benefit_established=False,publication_goal_complete=False)


def save(path):
    result=generate();io.write(path,result)
    return dict(public_constructed_cases=len(result['public_cases']),release_views=sum(len(c['views']) for c in result['public_cases']),
        algebra_settings=len(result['algebra_cases']),algebra_assignment_rows=sum(len(c['outcomes']) for c in result['algebra_cases']),
        sha256=io.sha(path),robot_population_size=0)

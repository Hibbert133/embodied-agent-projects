"""Explicit PI memory across acquisition receipts; no world/reset/fit capability.

Preserving an integrator is not a bumpless-transfer or physical safety guarantee.
The external host must authenticate physical receipts and durable commands.
"""
from copy import deepcopy
from dataclasses import dataclass,asdict,replace
import numpy as np
from src.probe.continuous import StepObservation
from src.probe.physical_reprobe_v1 import StepReceipt
from src.probe.task_passive_pi_v1 import PIQuery,PIPlan,controller,vector,require,digest,TIME_CONSTANTS,GAINS
from src.probe.operator_identification import identity_controller


@dataclass(frozen=True)
class TaskMemory:
    task:str
    completed_steps:int
    current:StepObservation
    saved_controller:tuple
    integral_xy:tuple
    time_constant_s:float

    def __post_init__(self):
        require(self.task in GAINS and type(self.completed_steps) is int and 0<=self.completed_steps<=500,'task and actual completed-step budget')
        require(type(self.current) is StepObservation and len(self.current.observation)==39,'current public observation')
        source,m,o=self.saved_controller;c=controller({'source':source,'matrix_xy':m,'offset':o})
        integral=vector(self.integral_xy,2);require(max(abs(x) for x in integral)<=2,'bounded command-coordinate task integral')
        require(type(self.time_constant_s) in (float,int) and self.time_constant_s in TIME_CONSTANTS,'registered PI rate')
        object.__setattr__(self,'saved_controller',c);object.__setattr__(self,'integral_xy',integral);object.__setattr__(self,'time_constant_s',float(self.time_constant_s))

    @classmethod
    def initial(cls,task,current):return cls(task,0,current,controller(identity_controller()),(0.,0.),.5)

    def base(self):
        source,m,o=self.saved_controller;return {'source':source,'matrix_xy':[list(r) for r in m],'offset':list(o)}

    def to_dict(self):return {'schema':'TASK_MEMORY_OPTION_V1','task':self.task,'completed_steps':self.completed_steps,
        'current':asdict(self.current),'controller':self.base(),'integral_xy':list(self.integral_xy),'time_constant_s':self.time_constant_s}

    @property
    def sha256(self):return digest(self.to_dict())

    @classmethod
    def from_dict(cls,value):
        require(type(value) is dict and set(value)=={'schema','task','completed_steps','current','controller','integral_xy','time_constant_s'}
            and value['schema']=='TASK_MEMORY_OPTION_V1','unknown/private/future memory field')
        c=value['current'];require(type(c) is dict and set(c)=={'observation','terminated','truncated','success'},'strict current observation')
        return cls(value['task'],value['completed_steps'],StepObservation(**c),controller(value['controller']),value['integral_xy'],value['time_constant_s'])


class TaskMemoryMachine:
    def __init__(self,memory):
        require(type(memory) is TaskMemory,'immutable public memory');self.memory=memory;self.pending=None;self.suspended=None

    def plan(self,raw):
        require(self.pending is None and self.suspended is None,'outstanding command or suspended task controller')
        m=self.memory;q=PIQuery.create(m.task,m.completed_steps,m.current,raw,m.base(),m.integral_xy,m.time_constant_s)
        p=PIPlan(q);saved={'schema':'TASK_MEMORY_COMMAND_V1','before_memory_sha256':m.sha256,'pi_plan':p.to_dict(),'pi_plan_sha256':p.sha256}
        self.pending=digest(saved);return deepcopy(saved)

    def commit(self,saved,receipt):
        require(self.pending is not None and digest(saved)==self.pending,'changed/unsaved/already-consumed task plan')
        require(type(saved) is dict and set(saved)=={'schema','before_memory_sha256','pi_plan','pi_plan_sha256'} and saved['schema']=='TASK_MEMORY_COMMAND_V1','strict saved task command')
        m=self.memory;require(saved['before_memory_sha256']==m.sha256,'stale memory plan')
        p=PIPlan.from_dict(saved['pi_plan']);require(p.sha256==saved['pi_plan_sha256'],'saved PI plan identity')
        require(type(receipt) is StepReceipt and receipt.completed_steps==m.completed_steps+1,'one actual consecutive task receipt')
        self.memory=replace(m,current=receipt.current,completed_steps=receipt.completed_steps,integral_xy=tuple(p.numbers()['integral_after_receipt']))
        self.pending=None;return self.memory

    def suspend(self):
        require(self.pending is None and self.suspended is None,'cannot suspend outstanding task operation')
        m=self.memory;require(m.completed_steps<500 and not any((m.current.success,m.current.terminated,m.current.truncated)),'live task controller')
        self.suspended={'schema':'TASK_MEMORY_SUSPEND_V1','memory_sha256':m.sha256,'at_completed_steps':m.completed_steps}
        return deepcopy(self.suspended)

    def resume(self,saved,receipts):
        require(self.pending is None and self.suspended is not None and digest(saved)==digest(self.suspended),'changed or reused suspension token')
        m=self.memory;require(saved['memory_sha256']==m.sha256,'memory altered during acquisition')
        require(type(receipts) in (list,tuple),'explicit consecutive acquisition receipts')
        current=m.current;step=m.completed_steps
        for receipt in receipts:
            require(not any((current.success,current.terminated,current.truncated)) and step<500,'acquisition advanced after end/budget')
            require(type(receipt) is StepReceipt and receipt.completed_steps==step+1,'skipped or reversed acquisition step')
            current,step=receipt.current,receipt.completed_steps
        self.memory=replace(m,current=current,completed_steps=step)
        require(self.memory.integral_xy==m.integral_xy and self.memory.saved_controller==m.saved_controller and self.memory.time_constant_s==m.time_constant_s,'silent task-memory reset')
        self.suspended=None;return self.memory

    def set_rate(self,time_constant_s,*,memory_mode):
        require(self.pending is None and self.suspended is None,'cannot change active/suspended memory')
        require(memory_mode in ('CARRY','EXPLICIT_RESET'),'explicit memory-handling arm required')
        before=self.memory;after=replace(before,time_constant_s=time_constant_s,
            integral_xy=before.integral_xy if memory_mode=='CARRY' else (0.,0.))
        self.memory=after
        return {'schema':'TASK_MEMORY_RATE_CHANGE_V1','at_completed_steps':before.completed_steps,'mode':memory_mode,
            'before':before.to_dict(),'after':after.to_dict(),'bumpless_transfer_established':False,'task_benefit_established':False}

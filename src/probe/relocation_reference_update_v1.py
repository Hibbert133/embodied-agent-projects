"""Standard bounded relocation reference adoption, not physical identification."""
from dataclasses import replace
from src.probe.task_memory_option_v1 import TaskMemory
from src.probe.task_passive_pi_v1 import controller,require,digest,vector


def propose(memory,evidence,*,mode):
    require(type(memory) is TaskMemory and mode in ('RESET','CARRY'),'exact current task memory and registered reference mode')
    require(memory.completed_steps<500 and not any((memory.current.success,memory.current.terminated,memory.current.truncated)),'live post-acquisition state')
    require(memory.saved_controller==controller({'source':'UNCORRECTED','matrix_xy':[[1.,0.],[0.,1.]],'offset':[0.,0.,0.,0.]}),'reference applies only to registered RAW history')
    require(type(evidence) is dict and set(evidence)=={'integral_xy','at_anchor','controller','parameter_estimate_qualified','task_utility_demonstrated'},'strict actual relocation evidence')
    require(type(evidence['at_anchor']) is bool and evidence['at_anchor'] and evidence['parameter_estimate_qualified'] is False and evidence['task_utility_demonstrated'] is False,'actual anchor entry; no unearned qualification flags')
    integral=vector(evidence['integral_xy'],2);require(max(abs(v) for v in integral)<=.5,'registered bounded relocation accumulator')
    expected={'source':'RELOCATION_INTEGRAL_REFERENCE','matrix_xy':[[1.,0.],[0.,1.]],'offset':[integral[0],integral[1],0.,0.]}
    require(digest(evidence['controller'])==digest(expected),'raw relocation reference mapping differs')
    mapped=controller({**expected,'source':'ESTIMATED_AFFINE'})
    after=replace(memory,saved_controller=mapped,integral_xy=(0.,0.) if mode=='RESET' else memory.integral_xy)
    return {'schema':'RELOCATION_REFERENCE_UPDATE_V1','mode':mode,'before_memory_sha256':memory.sha256,'after_memory':after.to_dict(),
        'evidence_sha256':digest(evidence),'parameter_identification_qualified':False,'task_benefit_established':False,'bumpless_transfer_established':False}


def consume(machine,saved,evidence):
    from src.probe.task_memory_option_v1 import TaskMemoryMachine
    require(type(machine) is TaskMemoryMachine and machine.pending is None and machine.suspended is None,'no outstanding command or acquisition')
    require(type(saved) is dict and 'mode' in saved,'saved registered reference plan')
    expected=propose(machine.memory,evidence,mode=saved['mode']);require(digest(saved)==digest(expected),'changed, stale or private-field reference plan')
    machine.memory=TaskMemory.from_dict(saved['after_memory']);return machine.memory

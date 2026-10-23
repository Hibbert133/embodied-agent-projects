"""Saved zero-step PI memory changes; cannot access or reset a physical world."""
from dataclasses import replace
from src.probe.task_memory_option_v1 import TaskMemory,TaskMemoryMachine
from src.probe.task_passive_pi_v1 import require,digest


def propose(memory,*,mode):
    require(type(memory) is TaskMemory and mode in ('NOOP','ZERO_INTEGRAL'),'exact current public task memory and registered transition')
    require(memory.completed_steps<500 and not any((memory.current.success,memory.current.terminated,memory.current.truncated)),
            'live current task memory before transition')
    after=memory if mode=='NOOP' else replace(memory,integral_xy=(0.,0.))
    return dict(schema='CONTROLLER_MEMORY_TRANSITION_V1',mode=mode,at_calls=memory.completed_steps,
        before_memory_sha256=memory.sha256,after_memory=after.to_dict(),new_control_steps=0,
        policy_queries=0,new_measurements=0,controller_mapping_changed=False,
        physical_reset_performed=False,bumpless_transfer_established=False,safety_guarantee=False,task_benefit_established=False)


def consume(machine,saved):
    require(type(machine) is TaskMemoryMachine and machine.pending is None and machine.suspended is None,
            'no pending command or suspended acquisition')
    require(type(saved) is dict and 'mode' in saved,'saved explicit memory plan required')
    expected=propose(machine.memory,mode=saved['mode'])
    require(digest(saved)==digest(expected),'mutated, unknown, stale or future memory transition')
    used=getattr(machine,'_memory_transition_used',frozenset())
    require(digest(saved) not in used,'memory transition already consumed, including zero/no-op plans')
    before=machine.memory;after=TaskMemory.from_dict(saved['after_memory'])
    require(after.current==before.current and after.completed_steps==before.completed_steps
            and after.saved_controller==before.saved_controller and after.time_constant_s==before.time_constant_s,
            'memory transition cannot change observation, clock, controller or gain')
    machine.memory=after
    machine._memory_transition_used=used|{digest(saved)}
    return dict(schema='CONTROLLER_MEMORY_TRANSITION_RECEIPT_V1',plan_sha256=digest(saved),
        before_memory_sha256=before.sha256,after_memory_sha256=after.sha256,mode=saved['mode'],
        at_calls=after.completed_steps,nonzero_integral_changed=after.integral_xy!=before.integral_xy,
        new_control_steps=0,new_policy_queries=0,new_measurements=0)

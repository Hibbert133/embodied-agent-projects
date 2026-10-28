"""Versioned deployment actor and isolated driver, preserving all historical sources."""
from pathlib import Path
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects')


def write(name,text):
    p=ROOT/name;p.parent.mkdir(parents=True,exist_ok=True)
    if p.exists():raise FileExistsError(name)
    compile(text,name,'exec');p.write_text(text,encoding='utf8',newline='\n')


header='''"""Fixed-reference actual deployment, not a new acquisition algorithm."""
from copy import deepcopy
from dataclasses import asdict
import numpy as np
from src.analysis.capsule_record_json_v2 import normalize
from src.probe.occam_performance_core_v1 import require,digest,RATES
from src.probe.task_memory_option_v1 import TaskMemory,TaskMemoryMachine
from src.probe.physical_reprobe_v1 import Start,StepReceipt
from src.probe import acquisition_reference_operation_v1 as macro
from src.probe import occam_window_cost_v1 as cost
from src.probe import task_passive_program_v1 as legacy

ACQUISITIONS=('CONTINUE','VALIDATE8','MOVE_MEASURE')
CONTROLLERS=('PI_0125','PI_0500','PI_2000','PI_8000','META_ADAPT','META_FROZEN','ERM_ADAPT','ERM_FROZEN')
PROGRAMS=tuple(c+'__'+a for a in ACQUISITIONS for c in CONTROLLERS)+('DIRECT_C8','MOVE_INTEGRAL')


def program_spec(program):
    require(type(program) is str and program in PROGRAMS,'one of26 frozen complete programs')
    if program in ('DIRECT_C8','MOVE_INTEGRAL'):return dict(kind='LEGACY',action=program,bank=None,adapt=False,rate=None)
    name,action=program.split('__')
    if name.startswith('PI_'):
        return dict(kind='FIXED',action=action,bank=None,adapt=False,rate=RATES[CONTROLLERS.index(name)])
    return dict(kind='TRAINED',action=action,bank='META_FINAL' if name.startswith('META_') else 'MATCHED_ERM_FINAL',adapt=name.endswith('_ADAPT'),rate=None)


def run_program(task,initial,boundary,program,nominal,provider,policy,step,emit):
    settings=program_spec(program)
    if settings['kind']=='LEGACY':
        require(provider is None and nominal is not None,'original C8 references retain their original data and fit')
        return legacy.run(task,initial,nominal,boundary,legacy.Program(program),policy,step,emit)
    require(nominal is None and provider is not None,'public-history provider receives no nominal response prior')
    return run(task,initial,boundary,settings['action'],provider,policy,step,emit,program_name=program)


'''
s=(ROOT/'src/probe/occam_training_program_v1.py').read_text(encoding='utf8');body=s[s.index('\ndef run(task,'):]
body=body.replace('*,window_steps=16):','*,window_steps=16,program_name=None):')
body=body.replace("bank_sha256=provider.bank_sha256,scope='PERFORMANCE_TRAIN_BEHAVIOR_NOT_QUALIFICATION'","bank_sha256=provider.bank_sha256,program=program_name,scope='STANDARD_REFERENCE_OWN_HISTORY_QUALIFICATION_NOT_NEW_ACQUISITION'")
body=body.replace('training_behavior=True','reference_qualification=True')
write('src/probe/occam_qualification_program_v1.py',header+body)

replacements={
 'occam_native_case_io_v1':'occam_qualification_case_io_v1',
 'occam_native_case_process_v1':'occam_qualification_case_process_v1',
 'occam_native_case_audit_v1':'occam_qualification_process_audit_v1',
 'occam_reference_train_io_v3':'occam_reference_qualification_io_v1',
 'occam_reference_train_host_v3':'occam_reference_qualification_host_v1',
 'occam_reference_train_case_v3':'occam_reference_qualification_case_v1',
 'occam_case_events_v2':'occam_qualification_events_v1',
 'occam_native_case_worker_v1':'occam_qualification_case_worker_v1',
 "('NATIVE','TRAIN')":"('NATIVE','QUAL')",
 "=='TRAIN'":"=='QUAL'",
 'OCCAM_NATIVE_CASE_REQUEST_V1':'OCCAM_QUALIFICATION_CASE_REQUEST_V1',
 'OCCAM_NATIVE_CASE_PROCESS_RESULT_V1':'OCCAM_QUALIFICATION_CASE_PROCESS_RESULT_V1',
 "'OCCAM_REFERENCE_TRAIN_V3'":"'OCCAM_REFERENCE_QUALIFICATION_V1'",
 "'occam_reference_train_v3_'":"'occam_reference_qualification_v1_'",
 "'outputs/occam_reference_train_v3'":"'outputs/occam_reference_qualification_v1'",
 "BASE/'development_v1'":"BASE/'qualification_v1'",
 "BASE/'freeze_validation_v1/complete.json'":"BASE/'freeze_validation_v1/complete.json'",
 'configs/movement_task/occam_reference_train_v3.json':'configs/movement_task/occam_reference_qualification_v1.json',
 "'frozen v3 config'":"'frozen independent deployment config'",
 "('cohort','group','task','seed','context','planned_boundary','acquisition_action','behavior')":"('cohort','group','task','seed','context','planned_boundary','program')",
 "'FROZEN_RANDOM_OR_BLOCK_TRAIN_BEHAVIOR'":"'FROZEN_STANDARD_REFERENCE_DEPLOYMENT'",
 'training_behavior_data_not_task_qualification=True':'standard_reference_deployment=True',
}
clones=[('src/analysis/occam_native_case_io_v1.py','src/analysis/occam_qualification_case_io_v1.py'),
 ('src/analysis/occam_native_case_process_v1.py','src/analysis/occam_qualification_case_process_v1.py'),
 ('src/analysis/occam_reference_train_case_v3.py','src/analysis/occam_reference_qualification_case_v1.py'),
 ('src/analysis/occam_native_case_audit_v1.py','src/analysis/occam_qualification_process_audit_v1.py'),
 ('src/analysis/occam_reference_train_collect_v3.py','src/analysis/occam_reference_qualification_collect_v1.py'),
 ('src/analysis/occam_case_events_v2.py','src/analysis/occam_qualification_events_v1.py'),
 ('src/analysis/occam_train_envelope_v2.py','src/analysis/occam_qualification_envelope_v1.py'),
 ('scripts/occam_native_case_worker_v1.py','scripts/occam_qualification_case_worker_v1.py')]
for old,new in clones:
    value=(ROOT/old).read_text(encoding='utf8')
    for before,after in replacements.items():value=value.replace(before,after)
    if old.endswith('occam_native_case_io_v1.py'):value=value.replace('occam_reference_train_v3 manifest directory','occam_reference_qualification_v1 manifest directory')
    write(new,value)
print(dict(created_actor=True,isolated_driver_modules=len(clones),old_sources_modified=False,new_physics=0),flush=True)

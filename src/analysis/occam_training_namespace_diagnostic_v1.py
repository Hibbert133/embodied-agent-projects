"""Read-only reproduction of the frozen collector's event ownership guard.

Only its small local `wrapped` function is extracted; collector/factory/native
reset code is not executed. Proposed headers are illustrative, not new records.
"""
from copy import deepcopy
from pathlib import Path
import ast,hashlib,io as streams
from src.analysis import response_qualification_io_v1 as io
from src.analysis.capsule_record_json_v2 import JsonJournal

COLLECTOR=io.ROOT/'src/analysis/occam_reference_train_collect_v1.py'
PHASES=('FACTORY_SETUP','GOAL_GENERATION','CONTROLLED_RESET','CONTROL','PREFIX_TASK','VALIDATION_TASK','REPOSITION','WARM_PROBE','TAIL_TASK')


def extract_guard(source,header):
    tree=ast.parse(source);collector=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='collect')
    functions=[n for n in ast.walk(collector) if isinstance(n,ast.FunctionDef) and n.name=='wrapped']
    io.require(len(functions)==1,'one exact frozen local ownership guard')
    module=ast.Module(body=functions,type_ignores=[]);ast.fix_missing_locations(module);namespace=dict(io=io,key=deepcopy(header))
    exec(compile(module,str(COLLECTOR)+'::ownership-guard-only','exec'),namespace)
    return namespace['wrapped']


def attempt(source,header,payload):
    output=streams.StringIO();journal=JsonJournal(output,dict(diagnostic_only=True));error=None;record=None
    try:record=extract_guard(source,header)(journal,'SYNTHETIC_EVENT',payload)
    except ValueError as ex:error=str(ex)
    return dict(rejected=error is not None,error=error,journal_emissions=journal.sequence,record=record)


def diagnose(manifest):
    manifest=Path(manifest).resolve();m=io.read(manifest);name=COLLECTOR.relative_to(io.ROOT).as_posix();source=COLLECTOR.read_bytes()
    io.require(hashlib.sha256(source).hexdigest()==m['source_sha256'][name],'exact frozen collector bytes')
    header=m['config']['populations']['NATIVE'][0];original=[];proposed=[]
    for owner in ('NATIVE','TRAIN'):
        h={**header,'phase':owner};new=dict(h);new['cohort']=new.pop('phase')
        for phase in PHASES:
            payload=dict(phase=phase,before=dict(counts={}))
            a=attempt(source,h,payload);b=attempt(source,new,payload)
            io.require(a['rejected'] and a['journal_emissions']==0,'original guard must fail before event persistence/delegation')
            io.require(not b['rejected'] and b['record']['phase']==phase and b['record']['cohort']==owner,'separate proposed namespaces preserve both values')
            original.append(dict(case_owner=owner,payload_phase=phase,error=a['error'],journal_emissions=0))
            proposed.append(dict(case_owner=owner,payload_phase=phase,journal_emissions=1,illustration_only_not_collected_data=True))
    bad=attempt(source,{**header,'cohort':header['phase']},dict(seed=-1,phase='GOAL_GENERATION'))
    io.require(bad['rejected'],'case ownership protection remains necessary')
    return dict(integrity='PASSED_DIAGNOSTIC_ONLY',frozen_collector_sha256=hashlib.sha256(source).hexdigest(),original_rejections=original,
        proposed_namespace_examples=proposed,protection_not_disabled=True,no_collector_factory_or_environment_executed=True,
        original_records_changed=False,scientific_method_result=False,new_environment_interactions=0,model_training=0,online_LLM_API_calls=0)

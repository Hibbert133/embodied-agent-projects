"""Closed-record sources only; no model loading, fitting or environment operations."""
from pathlib import Path
from src.analysis import response_qualification_io_v1 as io
ROOT=io.ROOT
OLD=ROOT/'outputs/task_passive/development_v1/task_passive_20261022T032948Z_67fefc4da922'
NEW=ROOT/'outputs/response_action/development_v1/response_action_20261022T073655Z_401a7f2427df'
BASE=ROOT/'outputs/acquisition_support'
PROTOCOL=ROOT/'docs/protocols/acquisition_support_audit_v1_zh.md'
SOURCES=(('PI_DEV',OLD,'DEV',720,6,20),('PI_QUAL',OLD,'QUAL',432,9,8),('RANK_DEV',NEW,'DEV',432,6,12))


def pid(case):
    value=case['style']
    if case.get('time_constant_s') is not None:value+='_T'+str(float(case['time_constant_s']))
    if case.get('regularization_weight') is not None:value+='_W'+str(float(case['regularization_weight']))
    return value


def paths():
    result={}
    for bank,root,cohort,n,groups,programs in SOURCES:
        folder=root/cohort.lower();completion=io.read(folder/'completion.json');audit=io.read(folder/'audit.json')
        io.require(completion['status']=='COLLECTED_FOR_INDEPENDENT_AUDIT' and audit['integrity']=='PASSED' and audit['executions']==n,'complete original cohort '+bank)
        io.require(audit['completion_sha256']==io.sha(folder/'completion.json'),'original audit binding '+bank)
        for name,h in completion['artifact_sha256'].items():io.require(io.sha(folder/name)==h,'original raw bytes changed '+bank+'/'+name)
        numeric=(root/'result_delivery'/('numeric_audit_'+cohort.lower()+'.json')) if root==OLD else root/'evaluation'/('independent_audit_'+cohort.lower()+'.json')
        num=io.read(numeric);stats=root/'evaluation'/(cohort.lower()+'.json')
        io.require(num['integrity']=='PASSED' and num['statistics_sha256']==io.sha(stats),'original numeric audit binding')
        for p in (root/'manifest.json',root/'selection.json',folder/'completion.json',folder/'audit.json',numeric,stats,
                  root/'result_delivery/costs_and_provenance.json',root/'result_delivery/closure.json',
                  *(folder/name for name in completion['artifact_sha256'])):result[p.relative_to(ROOT).as_posix()]=io.sha(p)
        if root==NEW:
            out=root/'result_delivery'
            guard=folder/'audit_interaction_guard.json';io.require(io.read(guard)['integrity']=='PASSED','new source audit guard')
            result[guard.relative_to(ROOT).as_posix()]=io.sha(guard)
            io.require(audit['effective_independent_rank_audit_version']=='V2_EXPLICIT_DOT_NORM_AMENDMENT','explicit v2 source audit')
            for key,name in (('effective_rank_auditor_sha256','rank_audit_v2.py'),('effective_wrapper_sha256','run_record_audit_v2.py'),('audit_amendment_sha256','audit_amendment_v2_zh.md')):
                io.require(audit[key]==io.sha(out/name),'effective source audit changed')
                result[(out/name).relative_to(ROOT).as_posix()]=io.sha(out/name)
    io.require(not (NEW/'qual').exists() and io.read(NEW/'selection.json')['development_gate']=='FAILED_STOP_NO_QUALIFICATION','new rank qualification remains unexecuted')
    return result


def validate_cases(cases,bank,n,groups,programs):
    io.require(len(cases)==n and len({c['case_id'] for c in cases})==n,'whole distinct source population '+bank)
    io.require({c['group'] for c in cases}==set(range(groups)),'whole independent groups')
    ids=list(dict.fromkeys(pid(c) for c in cases));io.require(len(ids)==programs,'all registered programs')
    units=list(dict.fromkeys(c['unit_id'] for c in cases));io.require(len(units)==6*groups,'whole task/condition population')
    for u in units:io.require({pid(c) for c in cases if c['unit_id']==u}==set(ids),'complete paired unit')
    for c in cases:
        io.require(c['completed'] and c['error'] is None and c['close_error'] is None,'uncompleted record cannot disappear')
        io.require(type(c['success']) is bool and type(c['total_steps']) is int and 0<=c['total_steps']<=500,'source result')
        io.require(c['deadline_loss']==(c['total_steps'] if c['success'] else 500),'complete cutoff cost')
        io.require(c['task'] in io.TASKS and c['context'] in ('UNCHANGED','CHANGED'),'all task/condition cells')
    return ids,units


def load_manifest(path):
    path=Path(path).resolve();io.require(path.name=='manifest.json' and path.parent.parent==(BASE/'analysis_v1').resolve(),'owned analysis manifest')
    value=io.read(path);body=dict(value);identifier=body.pop('manifest_id')
    io.require(io.digest(body)==identifier and value['config']==io.read(ROOT/'configs/movement_task/acquisition_support_audit_v1.json'),'manifest/config identity')
    for name,h in value['source_sha256'].items():io.require(io.sha(ROOT/name)==h,'analysis/source hash changed '+name)
    return value

"""Independent raw accounting checks; never call the compatibility adapter."""
import hashlib
from collections import Counter


def need(ok,message):
    if not ok:raise ValueError(message)


def verify(case,spec,accounting,parent,index,raw_case,raw_accounting,row):
    need(parent['case_index']==index==accounting['case_index'],'independent original case index')
    need(parent['cohort']==spec['cohort']==case['cohort']==accounting['cohort'],'independent cohort identity')
    need(parent['status']=='RETURNED' and parent['expected_status']=='RETURNED'
         and parent['expected_contract_observed'] is True and type(parent['returncode']) is int and parent['returncode']==0,'independent process contract')
    need(hashlib.sha256(raw_case).hexdigest()==parent['artifact_sha256']['case.json'],'independent original case hash')
    need(hashlib.sha256(raw_accounting).hexdigest()==parent['artifact_sha256']['accounting.json'],'independent original accounting hash')
    need(accounting['status']=='COMPLETE' and accounting['failure'] is None,'independent complete accounting')
    need(accounting['ledger_start']==case['ledger_before'] and accounting['ledger_after']==case['ledger_after_close'],'independent ledger linkage')
    a=accounting['control_steps_start'];b=accounting['control_steps_after']
    need(type(a) is int and type(b) is int and a>=0 and b-a==case['total_steps'],'independent control linkage')
    value=accounting['online_LLM_API_calls'];attempts=accounting['network_guard']['attempted_network_calls']
    need(type(value) is int and value==0 and type(attempts) is int and attempts==0,'independent explicit accounting API evidence')
    if 'online_LLM_API_calls' in case:
        need(type(case['online_LLM_API_calls']) is int and case['online_LLM_API_calls']==value,'independent optional case counter')
        source='CASE_AND_ACCOUNTING_EXPLICIT_ZERO'
    else:
        need(spec['program']=='DIRECT_C8' or spec['program']=='MOVE_INTEGRAL','independent registered legacy omission')
        source='LEGACY_ACCOUNTING_EXPLICIT_ZERO_CASE_FIELD_ABSENT'
    need(row['online_LLM_API_calls']==value and row['LLM_tokens']==0 and row['mean_API_call_latency_ns'] is None,'independent saved API costs')
    return source


def verify_phase(summary,audit,rows,sources,saved):
    need(saved['source_counts']==dict(Counter(sources)),'independent API source census')
    need(len(sources)==len(rows) and sum(row['online_LLM_API_calls'] for row in rows)==0,'all original case API costs')
    need(type(summary['online_LLM_API_calls']) is int and summary['online_LLM_API_calls']==0
         and type(audit['online_LLM_API_calls']) is int and audit['online_LLM_API_calls']==0,'independent complete-phase counters')
    need(audit['guard']['network']['attempted_network_calls']==0,'independent complete original audit guard')
    need(saved['case_API_field_absence_not_defaulted_to_zero'] is True
         and saved['case_API_costs_come_from_original_accounting_and_parent_hashes'] is True,'saved provenance, not missing-as-zero')

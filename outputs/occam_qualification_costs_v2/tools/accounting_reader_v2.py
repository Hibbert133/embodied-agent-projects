"""Compatibility for the two legacy case schemas, using explicit accounting."""
import hashlib
import costs_engine_v1 as e

LEGACY=('DIRECT_C8','MOVE_INTEGRAL')
API_SOURCES=('CASE_AND_ACCOUNTING_EXPLICIT_ZERO','LEGACY_ACCOUNTING_EXPLICIT_ZERO_CASE_FIELD_ABSENT')


def authenticate(case,spec,accounting,parent,*,index,case_bytes,accounting_bytes):
    e.require(type(index) is int and index>0,'literal allocated case index')
    e.require(parent['cohort']==accounting['cohort']==case['cohort']==spec['cohort']
              and parent['case_index']==accounting['case_index']==index,'same original cohort and case index')
    e.require(parent['status']==parent['expected_status']=='RETURNED'
              and parent['expected_contract_observed'] is True and type(parent['returncode']) is int
              and parent['returncode']==0,'original successful technical process, task failures retained')
    for name,data in (('case.json',case_bytes),('accounting.json',accounting_bytes)):
        e.require(parent['artifact_sha256'][name]==hashlib.sha256(data).hexdigest(),'original parent artifact hash '+name)
    e.require(accounting['status']=='COMPLETE' and accounting['failure'] is None,'complete original accounting')
    e.require(accounting['ledger_start']==case['ledger_before'] and accounting['ledger_after']==case['ledger_after_close'],'same original physical ledger')
    before=accounting['control_steps_start'];after=accounting['control_steps_after']
    e.require(type(before) is type(after) is int and 0<=before<=after
              and after-before==case['total_steps'],'same actual control increment')
    api=accounting['online_LLM_API_calls'];network=accounting['network_guard']['attempted_network_calls']
    e.require(type(api) is int and api==0 and type(network) is int and network==0,'explicit case accounting zero API and network attempts')
    if 'online_LLM_API_calls' in case:
        value=case['online_LLM_API_calls']
        e.require(type(value) is int and value==api,'optional original case counter agrees')
        return 'CASE_AND_ACCOUNTING_EXPLICIT_ZERO'
    e.require(spec['program'] in LEGACY,'only the two registered legacy schemas omit the case field')
    return 'LEGACY_ACCOUNTING_EXPLICIT_ZERO_CASE_FIELD_ABSENT'


def project(case,spec,accounting):
    # No default for a missing accounting counter. The raw case is never mutated.
    value=accounting['online_LLM_API_calls'];e.require(type(value) is int and value==0,'explicit counter, never absence-as-zero')
    view=dict(case)
    if 'online_LLM_API_calls' in view:e.require(type(view['online_LLM_API_calls']) is int and view['online_LLM_API_calls']==value,'case counter agreement')
    else:e.require(spec['program'] in LEGACY,'registered legacy-only compatibility')
    view['online_LLM_API_calls']=value
    return e.case_cost(view,spec)


def check_phase_api(summary,audit,rows,sources):
    e.require(set(sources)<=set(API_SOURCES) and all(type(v) is int and v>=0 for v in sources.values()),'registered explicit API sources')
    for record in (summary,audit):
        e.require(type(record['online_LLM_API_calls']) is int and record['online_LLM_API_calls']==0,'explicit complete-phase API counter')
    e.require(audit['guard']['network']['attempted_network_calls']==0,'original full-audit network guard')
    e.require(sum(sources.values())==len(rows) and sum(row['online_LLM_API_calls'] for row in rows)==0,'all case accounting counters, complete denominator')
    return dict(source_counts=dict(sources),case_API_field_absence_not_defaulted_to_zero=True,
        case_API_costs_come_from_original_accounting_and_parent_hashes=True,
        in_memory_compatibility_view_only_original_case_bytes_unchanged=True,
        phase_and_full_audit_explicit_API_calls=0,mean_API_call_latency_ns=None)

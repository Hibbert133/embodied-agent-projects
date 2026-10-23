"""Recorded native toy continuations plus adversarial mutations; no task Env."""
import copy
from dataclasses import asdict
import io
import unittest
from unittest.mock import patch
import numpy as np
from src.analysis.capsule_record_json_v2 import JsonJournal,normalize
from src.analysis.paired_probe_host_v1 import ProbeSession
from src.analysis.paired_probe_record_audit_v1 import CaseReplay
from src.probe.cache_acquisition_evidence_v1 import CacheAcquisitionEvidenceV1,digest
from src.probe.chronological_cache_reference import BLOCK8,VerifiedPoint
from src.probe.cold_cache_prediction import SourceBelief
from src.probe.cold_start_response import ColdPrefix
from src.probe.lifecycle_ledger import LifecycleLedger
from tests.test_paired_probe_host_v1 import TinyEnv,TinyPolicy


def synthetic_resets(emit,ledger):
    emit('FACTORY_INTENT',{'ledger':ledger.snapshot()})
    # Synthetic reset accounting only. No task factory or scientific task seed
    # is executed; physical continuation below uses a tiny hand-written XML.
    for index in range(51):
        phase='GOAL_GENERATION' if index<50 else 'CONTROLLED_RESET'
        if index==50:emit('FACTORY_COMPLETE',{'ledger':ledger.snapshot()})
        with ledger.scope(phase):
            start=emit('LIFECYCLE_RESET_INTENT',{'phase':phase,'before':ledger.snapshot()})
            for key,value in (('reset_attempts',1),('simulation_attempts',100),('simulation_completed',100),
                              ('simulation_frames_attempted',500),('simulation_frames_completed',500),('reset_completed',1)):ledger.add(key,value)
            emit('LIFECYCLE_RESET_COMPLETE',{'intent_sequence':start['sequence'],'phase':phase,'after':ledger.snapshot()})


def fixture(valid=True):
    events=[];writer=JsonJournal(io.StringIO(),{'manifest_id':'SOFTWARE_ONLY'})
    def emit(event,payload):
        value=writer.emit(event,payload);events.append(value);return value
    ledger=LifecycleLedger(emit,100000);initial_ledger=ledger.snapshot();synthetic_resets(emit,ledger)
    env=TinyEnv();policy=TinyPolicy();budget={'completed':0,'maximum':5000}
    fault={'matrix_xy':[[1,0],[0,1]],'bias_xy':[.1,-.06],'deadzone_xy':[0,0]}
    spec={'episode':1,'task':'push-v3','seed':700001,'fault_oracle':fault}
    theta=(1,0,.1,0,1,-.1);belief=SourceBelief('reach-v3',theta,tuple(map(tuple,np.eye(6))),'a'*64,False)
    cache=normalize(asdict(VerifiedPoint(theta,belief,0,'reach-v3','a'*64,True)))
    fit={'valid':valid,'matrix_xy':[[1,0],[0,1]],'bias_xy':[0,0],'nfev':1}
    references={name:{'action':'RUN_CACHED','reason':'SOFTWARE_ONLY'} for name in ('UNCERTAINTY4','TASK_IVR4')}
    row={'disposition':'WARM_ELIGIBLE','cache_before':cache,'evaluations':[],'sentinels':[]}
    original=TinyEnv.do_simulation
    with patch.object(TinyEnv,'do_simulation',lambda env,ctrl,n:ledger.simulation_call(original,env,ctrl,n)),patch('src.probe.probe_effect_program_v1.infer_operator',return_value=fit):
        s=ProbeSession(env,policy,np.zeros(39),'push-v3',spec['seed'],fault,emit,ledger,budget)
        s.prefix4(BLOCK8[:4]);c=s.ctx
        prefix=ColdPrefix('push-v3',tuple(c['initial_observation']),tuple(map(tuple,c['commands'])),tuple(map(tuple,c['observations'])),True)
        e=CacheAcquisitionEvidenceV1(prefix,theta,belief.covariance,'reach-v3',1,False,tuple(s.policy_query(c['observation'])),496)
        row.update(evidence=e.to_dict(),evidence_sha256=e.evidence_sha256,references=references)
        choice=emit('SOURCE_CHECK_CHOICE',{'evidence':e.to_dict(),'evidence_sha256':e.evidence_sha256,'references':references})
        row['source_choice_sequence']=choice['sequence'];before=s.snapshot('FOUR_STEP_SOURCE_BOUNDARY')
        source,_=s.execute('REUSE_OLD',{},e,role='SOURCE',future=0)
        row.update(source=source,cache_after=cache,cache_write_error=None)
        saved=emit('SOURCE_CACHE_AFTER_ACTUAL_OUTCOME',{'source':source,'cache_before':cache,'cache_after':cache,'cache_write_error':None})
        row['source_cache_sequence']=saved['sequence'];after=s.snapshot('ACTUAL_SOURCE_AFTER_OUTCOME')
        for j in (1,2):
            for program in ('REUSE_OLD','PROBE_KEEP','PROBE_UPDATE','PROBE_UPDATE_KEEP'):
                s.recover(before,'EVALUATOR_FORK');s.replace_future(j)
                result,_=s.execute(program,{},e,role='EVAL',future=j);row['evaluations'].append(result)
                if j==1 and program=='REUSE_OLD':
                    s.recover(before,'SENTINEL');s.replace_future(j)
                    repeat,_=s.execute(program,{},e,role='SENTINEL',future=j);row['sentinels'].append(repeat)
        s.recover(after,'RETURN_TO_ACTUAL_SOURCE')
        returned=emit('SOURCE_STATE_RETURNED',{'cache_after_sha256':digest(cache),'logical_step':s.ctx['calls'],**s.witness()})
        row['source_return_sequence']=returned['sequence']
        row['case_actual']={'completed_steps':s.completed,'attempted_steps':s.attempts,'policy_queries':s.policy_queries,
            'captures':s.captures,'restores':s.restores,'capture_ns':s.capture_ns,'restore_ns':s.restore_ns}
        emit('SOURCE_CASE_COMPLETE',{'disposition':'WARM_ELIGIBLE','ledger':ledger.snapshot()})
    return normalize(row),spec,events,cache,initial_ledger,fit,references


class PairedProbeRecordAuditTest(unittest.TestCase):
    def run_audit(self,parts):
        row,spec,events,cache,ledger,fit,references=parts
        with patch('src.analysis.paired_probe_record_audit_v1.create_task_policy',return_value=TinyPolicy()),\
             patch('src.analysis.paired_probe_record_audit_v1.infer_operator',return_value=fit),\
             patch('src.analysis.paired_probe_record_audit_v1.check_choice',side_effect=lambda method,*args:references[method]):
            return CaseReplay(row,spec,events,{},cache,ledger,2).audit()

    def test_native_toy_full_transaction_and_actual_costs(self):
        result=self.run_audit(fixture())
        self.assertTrue(result['warm']);self.assertEqual(result['source_returns'],1)
        self.assertEqual(result['matched_probe_prefixes'],4);self.assertEqual(result['valid_update_equalities'],2)
        self.assertEqual(result['sentinels'],1);self.assertEqual(result['actual']['restores'],10)
        self.assertEqual(result['ledger']['counts']['simulation_frames_completed'],25500+5*result['actual']['completed_steps'])

    def test_invalid_update_and_retained_control_really_differ(self):
        result=self.run_audit(fixture(False))
        self.assertEqual(result['invalid_fallback_equalities'],2)

    def test_cold_actual_new_fit_writes_cache_only_after_success(self):
        events=[];writer=JsonJournal(io.StringIO(),{'manifest_id':'SOFTWARE_ONLY'})
        def emit(event,payload):
            value=writer.emit(event,payload);events.append(value);return value
        ledger=LifecycleLedger(emit,100000);before=ledger.snapshot();synthetic_resets(emit,ledger)
        fault={'matrix_xy':[[1,0],[0,1]],'bias_xy':[.1,-.06],'deadzone_xy':[0,0]}
        spec={'task':'push-v3','seed':700002,'episode':0,'fault_oracle':fault}
        env=TinyEnv();original=TinyEnv.do_simulation;fit={'valid':True,'matrix_xy':[[1,0],[0,1]],'bias_xy':[0,0],'nfev':1}
        with patch.object(TinyEnv,'do_simulation',lambda env,ctrl,n:ledger.simulation_call(original,env,ctrl,n)),patch('src.probe.probe_effect_program_v1.infer_operator',return_value=fit):
            session=ProbeSession(env,TinyPolicy(),np.zeros(39),'push-v3',spec['seed'],fault,emit,ledger,{'completed':0,'maximum':1000})
            source,_=session.execute('COLD8',{},role='SOURCE',future=0)
        def belief(model,prefix,parameters):
            return SourceBelief('push-v3',parameters,tuple(map(tuple,np.eye(6))),digest(asdict(prefix)),False)
        b=belief({},ColdPrefix.from_dict(source['fit_prefix']),(1,0,0,0,1,0))
        cache=normalize(asdict(VerifiedPoint(b.parameters,b,0,'push-v3',b.evidence_sha256,True)))
        saved=emit('SOURCE_CACHE_AFTER_ACTUAL_OUTCOME',{'source':source,'cache_before':None,'cache_after':cache,'cache_write_error':None})
        row={'disposition':'COLD_SOURCE','cache_before':None,'cache_after':cache,'cache_write_error':None,'source':source,'source_cache_sequence':saved['sequence'],
            'evidence':None,'references':None,'evaluations':[],'sentinels':[],
            'case_actual':{'completed_steps':session.completed,'attempted_steps':session.attempts,'policy_queries':session.policy_queries,
                'captures':0,'restores':0,'capture_ns':0,'restore_ns':0}}
        emit('SOURCE_CASE_COMPLETE',{'disposition':'COLD_SOURCE','ledger':ledger.snapshot()})
        with patch('src.analysis.paired_probe_record_audit_v1.create_task_policy',return_value=TinyPolicy()),\
             patch('src.analysis.paired_probe_record_audit_v1.infer_operator',return_value=fit),\
             patch('src.probe.chronological_cache_reference.source_belief',side_effect=belief):
            result=CaseReplay(row,spec,events,{},None,before,2).audit()
        self.assertEqual(result['cache_after'],cache);self.assertEqual(result['cache_writes'],1)

    def test_tampered_actions_noise_leakage_and_costs_are_rejected(self):
        source=fixture()
        def step(parts):return next(e for e in parts[2] if e['event']=='STEP_COMPLETE')
        mutations=[lambda p:step(p)['command'].__setitem__(0,.99),
                   lambda p:step(p)['executed_action_oracle'].__setitem__(0,.99),
                   lambda p:p[0]['evidence'].__setitem__('seed',700001),
                   lambda p:p[0]['case_actual'].__setitem__('policy_queries',0),
                   lambda p:next(e for e in p[2] if e['event']=='FRESH_FUTURE_INSTALLED').__setitem__('full_sha256','0'*64),
                   lambda p:next(e for e in p[2] if e['event']=='RESTORE_COMPLETE').__setitem__('python_semantic_sha256','0'*64)]
        for mutate in mutations:
            parts=copy.deepcopy(source);mutate(parts)
            with self.subTest(mutation=mutate),self.assertRaises(ValueError):self.run_audit(parts)

    def test_future_cache_and_decision_after_execution_are_rejected(self):
        source=fixture();parts=copy.deepcopy(source);parts[0]['cache_before']['source_episode']=1
        with self.assertRaises(ValueError):self.run_audit(parts)
        parts=copy.deepcopy(source);event=next(e for e in parts[2] if e['event']=='STEP_COMPLETE')
        event['execution_started_ns']=0
        with self.assertRaises(ValueError):self.run_audit(parts)


if __name__=='__main__':unittest.main()

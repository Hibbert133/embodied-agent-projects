"""Pure arrays, saved records and fake process handles; no real worker/Env/fit."""
from contextlib import ExitStack,contextmanager
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import patch
import ast,gzip,inspect,json,tempfile
import numpy as np
from src.analysis import occam_reference_qualification_io_v1 as q
from src.analysis import occam_qualification_case_io_v1 as contract
from src.analysis import occam_qualification_case_process_v1 as process
from src.analysis import occam_reference_qualification_collect_v1 as collect
from src.analysis import occam_reference_qualification_case_v1 as native_case
from src.analysis import occam_qualification_process_audit_v1 as process_audit
from src.analysis import occam_reference_qualification_host_v1 as host
from src.analysis import occam_reference_qualification_audit_v1 as record_audit
from src.analysis import occam_qualification_math_audit_v1 as independent
from src.analysis import occam_qualification_statistics_v1 as stats
from src.analysis.occam_qualification_statistics_audit_v1 import verify
from src.probe import occam_qualification_program_v1 as actor
from src.probe import occam_performance_core_v1 as core
from src.probe import occam_window_cost_v1 as cost
from src.probe.occam_qualification_provider_v1 import TrainedProvider,FixedRateProvider
from src.probe.occam_training_program_v1 import constructed_bank
from src.probe.continuous import StepObservation
from src.probe.physical_reprobe_v1 import StepReceipt
from tests.test_occam_performance_core_v1 import query
from tests.test_occam_window_host_v1 import initial,rows
from tests import test_occam_isolated_collection_v1 as fixtures


def observation(q):return q['history'][-1]['after'] if q['history'] else q['initial']


def measured(q,count=16,**flags):
    value=rows(count,start=q['completed_steps'],before=observation(q),**flags)
    return value,cost.measure(q['task'],q['completed_steps'],observation(q),value,q['evaluation_steps'])


def run_arrays(provider,stop=50,action='CONTINUE',*,mutate=None):
    saved=[];commands=[];current=initial()
    def emit(kind,payload):
        ack=dict(sequence=len(saved),saved_ns=len(saved)+1,**deepcopy(payload))
        if mutate:mutate(kind,ack)
        saved.append(dict(agent_event=kind,public_payload=deepcopy(ack)));return ack
    def policy(obs):np.testing.assert_array_equal(obs,current['observation']);return np.array([.1,-.05,0.,0.],np.float32)
    def step(command):
        nonlocal current
        commands.append(deepcopy(command));after=deepcopy(current);after['observation'][0]+=.0001*command['command'][0]
        if len(commands)==stop:after['success']=True
        current=after;return StepReceipt(StepObservation(**after),len(commands))
    result=actor.run('push-v3',StepObservation(**current),16,action,provider,policy,step,emit,program_name='ARRAY_ONLY')
    return result,saved,commands


@contextmanager
def isolated_arrays(**kwargs):
    with tempfile.TemporaryDirectory() as tmp,ExitStack() as stack:
        Path(tmp).resolve().relative_to(Path(tempfile.gettempdir()).resolve())
        for name,obj in (('a',q),('c',contract),('p',process),('audit',process_audit),('core',native_case),('collector',collect),('host',host)):
            stack.enter_context(patch.object(fixtures,name,obj))
        f=fixtures.ArrayFixture(tmp,**kwargs);f.install(stack);yield f


class LiveArraySession:
    """No simulator object or native factory; accounting fields are synthetic."""
    def __init__(self,*,stop=50,mutate=None):
        self.current=initial();self.stop=stop;self.mutate=mutate;self.attempts=self.completed=self.policy_queries=0
        self.last_rows=[];self.run_budget={'completed':0};self.ledger=NS(counts={});self.events=[];self._pending=None
        tape=np.zeros((500,3),np.float32);tape.flags.writeable=False;self.ctx={'calls':0,'noise_rows':tape}
        self.env=NS(unwrapped=NS(model=NS(_address=11),data=NS(_address=12,time=0.)));self.fault=q.initial_fault()
        self.captures=self.restores=0;self._snapshots={}
    def public(self):return StepObservation(**deepcopy(self.current))
    def alive(self):return self.ctx['calls']<500 and not any(self.current[k] for k in ('success','terminated','truncated'))
    def policy_query(self,obs):
        np.testing.assert_array_equal(obs,self.current['observation']);self.policy_queries+=1;return np.array([.1,-.05,0.,0.],np.float32)
    def witness(self):return dict(at=self.ctx['calls'],time=self.env.unwrapped.data.time,addresses=[11,12])
    def emit(self,*args):pass
    def _agent_emit(self,kind,payload):
        ack=dict(**deepcopy(payload),sequence=len(self.events),saved_ns=len(self.events)+1)
        if self.mutate:self.mutate(kind,ack)
        self.events.append((kind,deepcopy(ack)))
        if kind=='COMMAND':self._pending=deepcopy(ack)
        return ack
    def _agent_step(self,command):
        assert command==self._pending
        self.ctx['calls']+=1;self.attempts+=1;self.completed+=1;self.last_rows.append(deepcopy(command));self.run_budget['completed']+=1
        self.env.unwrapped.data.time+=.0125;self.ledger.counts['simulation_frames_completed']=5*self.ctx['calls']
        self.current['observation'][0]+=.0001*command['command'][0]
        if self.ctx['calls']==self.stop:self.current['success']=True
        self._pending=None;return self.public()


class DeploymentProviderTests(TestCase):
    def test_four_factor_first_predictions_match_with_fixed_prior(self):
        bank=constructed_bank(1);left=TrainedProvider(bank,adapt=True);right=TrainedProvider(bank,adapt=False)
        self.assertEqual(left.declare(query(16)),right.declare(query(16)))
    def test_frozen_feedback_keeps_all_parameters_but_advances_real_history(self):
        p=TrainedProvider(constructed_bank(1),adapt=False);x=query(16);d=p.declare(x);before=core.digest([p.session.mean,p.session.cov,p.session.Q,p.session.R])
        values,m=measured(x,count=8);p.feedback(d,m,values[-1]['after'])
        self.assertEqual(p.session.completed_steps,24);self.assertEqual(p.session.version,0);self.assertEqual(p.update_attempts,0)
        self.assertEqual(before,core.digest([p.session.mean,p.session.cov,p.session.Q,p.session.R]))
    def test_adaptation_follows_actual_full_feedback_only(self):
        p=TrainedProvider(constructed_bank(1),adapt=True);x=query(16);d=p.declare(x);values,m=measured(x,count=8)
        f=p.feedback(d,m,values[-1]['after']);self.assertTrue(f['update_applied']);self.assertEqual(p.session.version,1);self.assertEqual(p.update_attempts,1)
    def test_terminal_short_feedback_keeps_label_and_skips_update(self):
        p=TrainedProvider(constructed_bank(1),adapt=True);x=query(16);d=p.declare(x);values,m=measured(x,count=3,success=True)
        f=p.feedback(d,m,values[-1]['after']);self.assertFalse(f['update_applied']);self.assertEqual(p.session.version,0);self.assertTrue(p.session.closed)
    def test_full_terminal_feedback_cannot_start_another_query(self):
        p=TrainedProvider(constructed_bank(1),adapt=True);x=query(16);d=p.declare(x);values,m=measured(x,count=8,success=True)
        p.feedback(d,m,values[-1]['after'])
        with self.assertRaises(ValueError):p.declare(query(24))
    def test_declared_horizon_remainder_is_full_not_an_imputed_16_step_window(self):
        p=TrainedProvider(constructed_bank(1),adapt=True);x=query(496);x['evaluation_steps']=4;d=p.declare(x)
        values,m=measured(x,count=4);p.feedback(d,m,values[-1]['after'])
        self.assertTrue(m['full_window']);self.assertTrue(m['terminal']);self.assertEqual(p.session.version,1);self.assertTrue(p.session.closed)
    def test_future_or_misplaced_feedback_rejected_before_update(self):
        for field,value in (('start_at',17),('end_at',25),('full_window',False),('private_fault',.2)):
            p=TrainedProvider(constructed_bank(1),adapt=True);x=query(16);d=p.declare(x);values,m=measured(x,count=8);m[field]=value
            with self.assertRaises(ValueError):p.feedback(d,m,values[-1]['after'])
            self.assertEqual(p.update_attempts,0)
    def test_changed_decision_and_duplicate_feedback_rejected(self):
        p=TrainedProvider(constructed_bank(1),adapt=True);x=query(16);d=p.declare(x);values,m=measured(x,count=8)
        bad=deepcopy(d);bad['selected_rate']=2.
        with self.assertRaises(ValueError):p.feedback(bad,m,values[-1]['after'])
        p.feedback(d,m,values[-1]['after'])
        with self.assertRaises(ValueError):p.feedback(d,m,values[-1]['after'])
    def test_oracle_query_and_future_history_are_rejected(self):
        for field,value in (('seed',175000),('future_result',{}),('true_fault',.2)):
            x=query(16);x[field]=value
            with self.assertRaises(ValueError):TrainedProvider(constructed_bank(1),adapt=True).declare(x)
        x=query(16);x['history'].append(deepcopy(x['history'][-1]))
        with self.assertRaises(ValueError):FixedRateProvider(.5).declare(x)
    def test_all_four_fixed_gains_are_distinct_and_consumed_once(self):
        for index,rate in enumerate(core.RATES):
            p=FixedRateProvider(rate);x=query(16);d=p.declare(x);self.assertEqual(d['selected_index'],index)
            values,m=measured(x,count=8);p.feedback(d,m,values[-1]['after'])
            with self.assertRaises(ValueError):p.feedback(d,m,values[-1]['after'])
    def test_legal_model_selections_change_actual_array_commands(self):
        left,_,a=run_arrays(TrainedProvider(constructed_bank(-1),adapt=False));right,_,b=run_arrays(TrainedProvider(constructed_bank(1),adapt=False))
        self.assertEqual([x['command'] for x in a[:16]],[x['command'] for x in b[:16]])
        self.assertNotEqual([x['command'] for x in a[16:]],[x['command'] for x in b[16:]])
    def test_early_success_is_kept_without_model_queries(self):
        p=TrainedProvider(constructed_bank(1),adapt=True);result,events,commands=run_arrays(p,stop=5)
        self.assertEqual(result['outcome']['deadline_loss'],5);self.assertIsNone(p.session);self.assertFalse(any(e['agent_event']=='WINDOW_DECISION' for e in events))
    def test_independent_scalar_and_batch_checks_with_main_math_disabled(self):
        bank=constructed_bank(1);_,events,_=run_arrays(TrainedProvider(bank,adapt=True))
        def denied(*args,**kwargs):raise AssertionError('primary math forbidden')
        with patch.object(core,'update',denied),patch.object(core,'forecast',denied),patch.object(core,'basis_forward',denied),patch.object(TrainedProvider,'declare',denied):
            result=independent.audit_windows('META_ADAPT__CONTINUE',events,bank,0.)
        self.assertEqual(result['windows'],3);self.assertEqual(result['updates'],2);self.assertEqual(result['batch_solves'],1)
    def test_independent_check_detects_wrong_basis_and_future_feedback(self):
        bank=constructed_bank(1);_,events,_=run_arrays(TrainedProvider(bank,adapt=True));bad=deepcopy(events)
        next(e for e in bad if e['agent_event']=='WINDOW_DECISION')['public_payload']['declaration']['bases'][0][0][0]+=1.
        with self.assertRaises(ValueError):independent.audit_windows('META_ADAPT__CONTINUE',bad,bank,0.)
        bad=deepcopy(events);i=next(i for i,e in enumerate(bad) if e['agent_event']=='WINDOW_RESULT');j=i+1;bad[i],bad[j]=bad[j],bad[i]
        with self.assertRaises(ValueError):independent.audit_windows('META_ADAPT__CONTINUE',bad,bank,0.)
    def test_legacy_command_clips_raw_policy_before_inverse_map(self):
        c={'source':'ESTIMATED_AFFINE','matrix_xy':[[.3,.5],[-.6,.8]],'offset':[.1,0.,0.,0.]}
        actual=record_audit.literal_legacy_command(c,[2.,-3.,.2,0.]);np.testing.assert_allclose(actual,[-.1,-1.,.2,0.],atol=1e-7)


class HostAndIsolationTests(TestCase):
    def test_host_uses_saved_model_choice_and_stays_continuous(self):
        spec=next(s for s in q.population('NATIVE') if s['program']=='META_ADAPT__CONTINUE');session=LiveArraySession();w=[]
        result=host.run_live(spec,session,lambda label:w.append((label,session.witness())),lambda:None,TrainedProvider(constructed_bank(1),adapt=True),None)
        self.assertEqual(result['total_steps'],50);self.assertEqual(session.run_budget['completed'],50);self.assertEqual(result['full_feedback_windows'],2)
        self.assertEqual(session.ledger.counts['simulation_frames_completed'],250);self.assertIn('FIRST_RATE_POST',[label for label,_ in w])
    def test_host_rejects_changed_saved_gain_before_tail_execution(self):
        spec=next(s for s in q.population('NATIVE') if s['program']=='META_FROZEN__CONTINUE')
        def mutate(kind,ack):
            if kind=='RATE_PLAN':ack['rate']=99.
        s=LiveArraySession(mutate=mutate)
        with self.assertRaises(ValueError):host.run_live(spec,s,lambda label:None,lambda:None,TrainedProvider(constructed_bank(1),adapt=False),None)
        self.assertEqual(s.ctx['calls'],16)
    def test_fake_complete_case_process_and_byte_audit(self):
        with isolated_arrays(cases=2) as f:
            root=collect.collect(f.manifest,'NATIVE');result=process_audit.audit_cohort(f.manifest,'NATIVE')
            self.assertEqual(result['executions'],2);self.assertEqual(len(f.launches),2)
            self.assertTrue(all('occam_qualification_case_worker_v1.py' in x[3] for x in f.launches));self.assertEqual(f.callbacks['cases'],2)
    def test_fake_failure_keeps_unstarted_null_and_never_retries(self):
        with isolated_arrays(cases=3,fail_case=1) as f:
            with self.assertRaises(RuntimeError):collect.collect(f.manifest,'NATIVE')
            s=contract.read(f.run/'native/summary.json');self.assertEqual(len(f.launches),1);self.assertEqual(s['unstarted'],2)
            self.assertTrue(all(row['task_metrics'] is None for row in s['outcomes']))
    def test_owned_handle_timeout_is_recorded_without_retry(self):
        with isolated_arrays(cases=1,hang=True) as f:
            r=f.request();ticks=[0]
            def clock():ticks[0]+=220*10**9;return ticks[0]
            result=process.attempt(f.run/'native/case_0001',r,spawn=f.spawn,observe=f.sample,clock=clock,sleep=lambda _:None)
            self.assertEqual(result['status'],'TIMEOUT_TERMINATED');self.assertEqual(len(f.launches),1);self.assertEqual(f.process.terminations,1)
    def test_array_fixture_cannot_open_a_real_science_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp).resolve().relative_to(Path(tempfile.gettempdir()).resolve())
            with self.assertRaises(ValueError):contract.check_manifest(Path(tmp)/'manifest.json')
    def test_clone_keeps_process_watchdog_and_classification_body(self):
        from src.analysis import occam_native_case_process_v1 as old
        for name in ('attempt','classify','_same_identity'):
            before=ast.parse(inspect.getsource(getattr(old,name)));after=ast.parse(inspect.getsource(getattr(process,name)));changes=0
            for node in ast.walk(before):
                if isinstance(node,ast.Constant) and node.value=='OCCAM_NATIVE_CASE_PROCESS_RESULT_V1':
                    node.value='OCCAM_QUALIFICATION_CASE_PROCESS_RESULT_V1';changes+=1
            self.assertEqual(changes,int(name=='attempt'));self.assertEqual(ast.dump(before),ast.dump(after))
    def test_whole_registered_population_and_costs_are_not_reduced(self):
        self.assertEqual([len(q.population(p)) for p in q.PHASES],[156,1404]);self.assertEqual(len(actor.PROGRAMS),26)
        c=q.config()['complete_limits'];self.assertEqual(c['all_resets'],1560*51);self.assertEqual(c['physical_frames'],1560*28000)
        self.assertEqual({s['planned_boundary'] for s in q.population('QUAL')},{16,32,64})
    def test_qualification_early_successes_do_not_become_contract_failures(self):
        self.assertTrue(record_audit.model_execution_coverage('QUAL',[]))
        with self.assertRaises(ValueError):record_audit.model_execution_coverage('NATIVE',[])
    def test_saved_fixed_behavior_arithmetic_and_noise_cursor_corruption(self):
        # Mechanical record-reader fixture only; ownership is deliberately not
        # relabeled or promoted as a new program execution/qualification.
        from src.analysis import occam_reference_train_io_v3 as old
        folder=q.TRAIN/'native/case_0002';case=q.io.read(folder/'case.json')
        def load(name):
            with gzip.open(folder/name,'rt',encoding='utf8') as f:return [json.loads(line) for line in f]
        events=load('events.jsonl.gz');private=load('witnesses.jsonl.gz');old_spec={k:case[k] for k in old.KEYS}
        rate=next(e for e in events if e.get('agent_event')=='WINDOW_DECISION')['public_payload']['declaration']['selected_rate']
        name=actor.CONTROLLERS[core.RATES.index(rate)]+'__CONTINUE';spec=next(s for s in q.population('NATIVE') if s['program']==name)
        tape=old.noise(old_spec)
        with patch.object(q,'noise',return_value=tape),patch.object(q,'registry',return_value=old.registry()):
            ledger,steps,public,w=record_audit.reconstruct(spec,case,events,private,case['ledger_before'])
            self.assertEqual(len(steps),case['total_steps']);self.assertEqual(ledger,case['ledger_after_close'])
            bad=deepcopy(events);step=next(e for e in bad if e['event']=='STEP_COMPLETE')
            step['executed_action_oracle']=record_audit.applied(step['command'],q.initial_fault(),tape[1])
            with self.assertRaises(ValueError):record_audit.reconstruct(spec,case,bad,private,case['ledger_before'])
        from src.analysis.occam_qualification_envelope_v1 import bind_case
        manifest={k:case[k] for k in q.IDENTITY}
        with self.assertRaises((KeyError,ValueError)):bind_case(manifest,spec,case,events,private,(events[0]['sequence'],private[0]['sequence'],-1,-1))
    def test_executor_noise_must_precede_final_clipping(self):
        fault=dict(matrix_xy=[[1.2,0.],[0.,1.]],bias_xy=[.1,0.],deadzone_xy=[0.,0.])
        actual=record_audit.applied([1.,0.,0.,0.],fault,np.array([-.6,0.,0.],np.float32))
        self.assertAlmostEqual(actual[0],.7,places=6);self.assertNotAlmostEqual(actual[0],.4,places=6)


def synthetic_panels():
    result=[]
    for spec in q.population('QUAL'):
        trained=actor.program_spec(spec['program'])['kind']=='TRAINED';primary=spec['program']=='META_ADAPT__CONTINUE';n=80 if primary else 100
        result.append({**spec,'success':True,'deadline_loss':n,'total_steps':n,'boundary_applied':True,'performance_windows':2,
            'filter_updates':int(trained and actor.program_spec(spec['program'])['adapt']),
            'mse':.05 if primary else .1 if trained else None,'constant_mse':.2 if trained else None,'prediction_missing_reason':None if trained else 'NOT_A_PREDICTOR'})
    return result


class GroupStatisticsTests(TestCase):
    @classmethod
    def setUpClass(cls):cls.panels=synthetic_panels();cls.indices=stats.draws();cls.summary=stats.summarize(cls.panels,cls.indices)
    def test_independent_statistics_accept_known_whole_group_effect(self):
        def denied(*args,**kwargs):raise AssertionError('main statistics forbidden')
        with patch.object(stats,'contrast',denied),patch.object(stats,'quantile',denied),patch.object(stats,'prediction_gate',denied):
            checked=verify(self.panels,self.indices.tolist(),self.summary)
        self.assertEqual(checked['integrity'],'PASSED');self.assertTrue(self.summary['task_qualified']);self.assertTrue(self.summary['prediction']['qualified'])
    def test_one_stronger_opponent_prevents_intersection_promotion(self):
        panels=deepcopy(self.panels)
        for row in panels:
            if row['program']=='DIRECT_C8':row['deadline_loss']=row['total_steps']=70
        result=stats.summarize(panels,self.indices);self.assertFalse(result['task_qualified']);self.assertEqual(len(result['primary']),7)
    def test_missing_early_predictions_are_null_not_zero(self):
        panels=deepcopy(self.panels)
        for row in panels:
            if row['program']=='META_ADAPT__CONTINUE':row.update(mse=None,constant_mse=None,performance_windows=0,total_steps=8,deadline_loss=8)
        result=stats.summarize(panels,self.indices);self.assertTrue(result['task_qualified']);self.assertFalse(result['prediction']['qualified'])
        self.assertEqual(result['prediction']['available_trajectories'],0);self.assertIsNone(result['prediction']['CI95'])
    def test_correlated_steps_cannot_replace_groups_or_cross_strata(self):
        indices=self.indices.copy();indices[0,0]=1
        with self.assertRaises(ValueError):stats.summarize(self.panels,indices)
        with self.assertRaises(ValueError):stats.summarize(self.panels[:-1],self.indices)
    def test_independent_statistics_detects_promotion_or_interval_tampering(self):
        result=deepcopy(self.summary);result['primary'][0]['CI95_exact'][1]='1'
        with self.assertRaises(ValueError):verify(self.panels,self.indices.tolist(),result)
    def test_zero_difference_does_not_pass_a_strict_loss_gate(self):
        panels=deepcopy(self.panels)
        for row in panels:row['deadline_loss']=row['total_steps']=100
        result=stats.summarize(panels,self.indices);self.assertFalse(result['task_qualified'])
        self.assertTrue(all(p['CI95_exact']==['0','0'] for p in result['primary']))

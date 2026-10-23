"""Synthetic state/command/RNG and numerical checks; no physical interaction."""
from copy import deepcopy
from dataclasses import asdict
from types import SimpleNamespace
from time import perf_counter_ns
import unittest
from unittest.mock import patch
import numpy as np
from src.analysis.capsule_record_json_v2 import normalize
from src.analysis import release_learning_io_v1 as a
from src.analysis import release_learning_host_v1 as host
from src.analysis import release_learning_regression_v1 as fit
from src.probe import release_learning_actor_v1 as actor
from src.probe import release_learning_features_v1 as features
from src.probe import release_learning_predictor_v1 as predictor
from src.probe import release_learning_programs_v1 as programs
from src.probe.continuous import StepObservation
from src.probe.physical_reprobe_v1 import StepReceipt
from src.probe.task_passive_pi_v1 import digest


def observation():
    v=[0.]*39;v[:3]=[.1,.8,.25];v[4:7]=[.8,0.,.05];return StepObservation(tuple(v),False,False,False)


def constant_model(n,y):return dict(schema='GROUP_WEIGHTED_RBF_RISK_V1',mean=[0.]*n,scale=[1.]*n,active=[False]*n,
    centers=[[0.]*n],width=1.,coefficients=[float(y),0.],training_groups=['TAIL_TRAIN/0'],training_rows=1)


def receiver():
    m=dict(feature_spec='PUBLIC_COMPLETE_PREFIX_AND_RETURN_V1',common=[constant_model(159,y) for y in (180,120,150,200)],
        common_residual=[constant_model(159,0.) for _ in range(4)],
        signal_residual=[constant_model(213,y) for y in (-100,20,-80,0)])
    return dict(schema='FROZEN_RELEASE_RECEIVER_V1',model=m,receiver_version=digest(m))


def fixture(program='GATE_MOVE_MEASURE',uniform=.25,end_at=80):
    current=observation();events=[];steps=[];queries=0;draws=[]
    def emit(kind,payload):
        p={**normalize(payload),'sequence':len(events),'saved_ns':perf_counter_ns()};events.append(dict(kind=kind,payload=p));return p
    def policy(o):
        nonlocal queries
        if tuple(o)!=current.observation:raise AssertionError('future/stale policy query')
        queries+=1;return np.array([.2,-.1,.3,-1.],np.float32)
    def step(saved):
        nonlocal current
        if events[-1]['kind']!='COMMAND' or events[-1]['payload']!=saved:raise AssertionError('command not saved before step')
        n=len(steps)+1;current=StepObservation(current.observation,False,False,n>=end_at)
        steps.append(deepcopy(saved));return StepReceipt(current,n)
    def draw(seq):
        if events[-1]['kind']!='SIGNAL_SEAL' or events[-1]['payload']['sequence']!=seq:raise AssertionError('exposure before seal')
        if events[-1]['payload']['saved_return']['record']['post_memory']['completed_steps']!=len(steps):raise AssertionError('unfinished real acquisition')
        draws.append((seq,len(steps)));return uniform
    runtime=dict(receiver=receiver(),policy=None,pre_bank=None)
    r=actor.run('push-v3',current,16,program,None,policy,step,emit,runtime=runtime,draw_exposure=draw)
    return r,events,steps,queries,draws


class PublicHostStub:
    """Array-only adapter exercises actual host ordering, without a simulator."""
    def __init__(self,end_at=80):
        self._base=SimpleNamespace(action_scale=.01,model=SimpleNamespace(_address=1),data=SimpleNamespace(_address=2,time=0.))
        self.env=SimpleNamespace(unwrapped=self._base);tape=np.zeros((500,3),np.float32);tape.flags.writeable=False;o=observation()
        self.ctx=dict(noise_rows=tape,initial_observation=np.array(o.observation),observation=np.array(o.observation),calls=0,
            success=False,terminated=False,truncated=False,commands=[],observations=[])
        self.ledger=SimpleNamespace(counts={});self.run_budget=dict(completed=0,maximum=500);self.end_at=end_at
        self.attempts=self.completed=self.policy_queries=self.captures=self.restores=self._local=0
        self.last_rows=[];self._snapshots={};self._pending=None;self._map={};self.events=[];self.fault=a.initial_fault()
    def public(self):return StepObservation(tuple(self.ctx['observation']),self.ctx['terminated'],self.ctx['truncated'],self.ctx['success'])
    def alive(self):return not any((self.ctx['success'],self.ctx['terminated'],self.ctx['truncated']))
    def emit(self,name,p):
        r={**normalize(p),'event':name,'sequence':len(self.events),'saved_ns':perf_counter_ns()};self.events.append(r);return r
    def witness(self):return dict(native_sha256=digest([self.ctx['calls'],self.ctx['observation'].tolist()]),python_semantic_sha256=digest(self.ctx['calls']),
        noise_past_sha256=digest(self.ctx['noise_rows'][:self.ctx['calls']].tolist()),simulation_time=self._base.data.time)
    def policy_query(self,o):self.policy_queries+=1;return np.array([.2,-.1,.3,-1.],np.float32)
    def _agent_emit(self,name,p):
        r={**normalize(p),'sequence':self._local,'saved_ns':perf_counter_ns()};self._local+=1
        outer=self.emit('AGENT_EVENT',dict(agent_event=name,public_payload=r));self._map[r['sequence']]=outer['sequence']
        if name=='COMMAND':self._pending=r
        return r
    def _agent_step(self,saved):
        if saved!=self._pending:raise AssertionError('changed send')
        self.attempts+=1;self.completed+=1;self.ctx['calls']+=1;self.run_budget['completed']+=1
        self.ledger.counts['simulation_frames_completed']=5*self.completed;self._base.data.time+=.0125
        self.ctx['success']=self.completed>=self.end_at
        self.last_rows.append(dict(command=saved['command'],phase=saved['phase'],raw_policy=saved['raw_policy'],after=normalize(asdict(self.public()))))
        self._pending=None;return self.public()


class ReleaseLearningContracts(unittest.TestCase):
    def test_real_actor_requests_draw_only_after_actual_acquisition(self):
        r,e,s,q,d=fixture()
        self.assertEqual(len(d),1);self.assertGreater(d[0][1],16);self.assertEqual(r['outcome']['policy_queries'],q)
        self.assertEqual(r['outcome']['total_steps'],len(s));self.assertEqual(r['outcome']['deadline_loss'],80)
        seal=next(v for v in e if v['kind']=='SIGNAL_SEAL');rel=next(v for v in e if v['kind']=='INFORMATION_RELEASE')
        self.assertLess(seal['payload']['sequence'],rel['payload']['sequence'])

    def test_learned_signal_changes_actual_saved_send_and_carries_integral(self):
        one=fixture(uniform=.25);two=fixture(uniform=.75)
        a1=one[0]['outcome']['learning'];a0=two[0]['outcome']['learning']
        self.assertEqual(a1['saved_return'],a0['saved_return'])
        self.assertEqual(a1['receiver_decision']['choice']['time_constant_s'],2.)
        self.assertEqual(a0['receiver_decision']['choice']['time_constant_s'],.5)
        n=a1['saved_return']['record']['post_memory']['completed_steps']
        self.assertNotEqual(one[2][n]['command'][:2],two[2][n]['command'][:2])
        for l in (a1,a0):self.assertEqual(l['receiver_decision']['gain_plan']['after_memory']['integral_xy'],l['saved_return']['record']['post_memory']['integral_xy'])

    def test_empty_trace_collapses_learned_receiver_with_same_prefix(self):
        one=fixture('GATE_CONTINUE',.25)[0]['outcome']['learning'];two=fixture('GATE_CONTINUE',.75)[0]['outcome']['learning']
        self.assertEqual(one['release_receipt']['model_view'],two['release_receipt']['model_view'])
        self.assertEqual(one['receiver_decision']['choice'],two['receiver_decision']['choice'])
        self.assertIsNone(one['receiver_decision']['full_risks'])

    def test_both_receivers_retain_identical_complete_prior_history(self):
        l=fixture()[0]['outcome']['learning'];view=l['release_receipt']['model_view'];prefix=l['prefix_history']
        c,f,p=features.after(view,prefix);self.assertEqual((len(c),len(f),len(prefix)),(159,213,16));self.assertTrue(p)
        masked=deepcopy(view);masked['signal']=None;c2,f2,p2=features.after(masked,prefix)
        self.assertTrue(np.array_equal(c,c2));self.assertTrue(np.array_equal(f[:159],f2[:159]));self.assertFalse(p2)

    def test_future_private_or_truncated_history_rejected(self):
        l=fixture()[0]['outcome']['learning'];h=deepcopy(l['prefix_history']);h[-1]['future_loss']=500
        with self.assertRaises(ValueError):features.before(l['pre_memory'],h)
        with self.assertRaises(ValueError):features.after(l['release_receipt']['model_view'],l['prefix_history'][1:])

    def test_early_end_does_not_fabricate_acquisition_or_receiving_decision(self):
        r,e,s,q,d=fixture(end_at=8);self.assertIsNone(r['outcome']['learning']);self.assertEqual(d,[])
        self.assertEqual(len(s),8);self.assertEqual(q,8)
        r,e,s,q,d=fixture(end_at=18);self.assertIsNone(r['outcome']['learning']['receiver_decision']);self.assertEqual(len(d),1)

    def test_validation_really_advances_task_integral_and_charges_eight_steps(self):
        r,e,s,q,d=fixture('GATE_VALIDATE8');l=r['outcome']['learning'];rec=l['saved_return']['record']
        self.assertEqual(len(rec['steps']),8);self.assertNotEqual(rec['before_memory']['integral_xy'],rec['post_memory']['integral_xy'])
        self.assertEqual(q,len(s));self.assertEqual(r['outcome']['warm_probe_steps'],8)

    def test_stopped_or_partial_acquisition_preserves_actual_prefix(self):
        r,e,s,q,d=fixture(end_at=18);l=r['outcome']['learning'];rec=l['saved_return']['record']
        self.assertEqual(rec['reason'],'EARLY_END');self.assertEqual(len(rec['steps']),2)
        self.assertEqual(rec['before_memory']['integral_xy'],rec['post_memory']['integral_xy'])

    def test_host_consumes_separate_rng_after_durable_seal(self):
        spec=next(s for s in a.population('SOFTWARE_NATIVE') if s['program']=='N_MOVE_RANDOM')
        session=PublicHostStub();witnesses=[];syncs=[]
        r=host.run_live(spec,None,session,lambda label:witnesses.append((label,session.ctx['calls'])),lambda:syncs.append(len(session.events)),dict(receiver=None,policy=None,pre_bank=None))
        draws=[v for v in session.events if v['event']=='RELEASE_RANDOM_ORACLE'];self.assertEqual(len(draws),1)
        d=draws[0];seal=session.events[d['seal_global_sequence']]
        self.assertEqual(seal['agent_event'],'SIGNAL_SEAL');self.assertLess(seal['saved_ns'],d['saved_ns'])
        self.assertEqual(d['physical_before'],d['physical_after']);self.assertIn(d['sequence'],syncs)
        rng=np.random.default_rng(np.random.SeedSequence(a.exposure_seed(spec)));self.assertEqual(float(rng.random()),d['uniform_oracle'])
        self.assertEqual(r['exposure_draws'],1);self.assertEqual(r['total_steps'],80)

    def test_all_fixed_programs_resolve_and_unknown_program_is_rejected(self):
        for cohort in a.COHORTS:
            for p in a.programs(cohort):programs.fixed(p)
        with self.assertRaises(ValueError):programs.fixed('UNREGISTERED')

    def test_population_and_all_physical_costs_are_explicit(self):
        c=a.config()['combined_limits'];self.assertEqual(c['executions'],5940);self.assertEqual(c['control_steps'],2970000)
        self.assertEqual(c['all_resets'],302940);self.assertEqual(c['physical_frames'],166320000)
        self.assertEqual(c['c4_c8_fit_attempts'],648);self.assertEqual(c['audit_c4_c8_refits'],648)
        self.assertEqual(a.config()['receiver']['main_closed_form_fits']+a.config()['precritic']['main_closed_form_fits'],198)

    def test_episode_seeds_are_disjoint_from_registered_reserve(self):
        seen=set()
        for cohort in a.COHORTS:
            values={s['seed'] for s in a.population(cohort)};self.assertFalse(values&seen);seen|=values
            self.assertTrue(max(values)<74700)
        self.assertEqual(a.registry()['reserved_episode_seed_range'],[74700,77999])

    def test_modified_allocation_rejected(self):
        s=deepcopy(a.population('SOFTWARE_NATIVE')[0]);s['seed']+=999
        with self.assertRaises(ValueError):a.validate_spec(s)

    def test_common_and_signal_model_versions_cannot_silently_change(self):
        l=fixture()[0]['outcome']['learning'];b=receiver();b['model']['common'][0]['coefficients'][0]+=1
        with self.assertRaises(ValueError):predictor.receiver(b,l['release_receipt']['model_view'],l['prefix_history'])

    def test_group_weighted_fit_matches_different_augmented_solver(self):
        x=[[0.,0.],[1.,0.],[2.,0.],[3.,0.]];y=[-200.,50.,600.,300.];g=['A','A','B','B'];ledger=[]
        m=fit.fit(x,y,g,1.,.01,3,ledger,role='SYNTHETIC_TEST')
        audit=[];v=fit.independent_refit(m,x,y,g,.01,audit,role='SYNTHETIC_AUDIT')
        self.assertEqual(v['integrity'],'PASSED');self.assertEqual(len(ledger),1);self.assertEqual(len(audit),1)
        self.assertEqual(m['active'],[True,False]);self.assertTrue(np.isfinite([predictor.predict(m,z) for z in x]).all())

    def test_group_weights_do_not_reward_duplicated_long_groups(self):
        w=fit.weights(['A','A','A','B']);self.assertAlmostEqual(float(w[:3].sum()),.5);self.assertEqual(w[-1],.5)

    def test_independent_memory_trace_and_rate_audit(self):
        from src.analysis.release_learning_record_audit_v1 import numerical
        r,events,sends,_,_=fixture();after={e['payload']['command_sequence']:e['payload']['after'] for e in events if e['kind']=='STEP_RESULT'}
        steps=[dict(command=s['command'],phase=s['phase'],raw_policy=s['raw_policy'],after=after[s['sequence']]) for s in sends]
        public=[dict(agent_event=e['kind'],public_payload=e['payload']) for e in events]
        spec=next(s for s in a.population('GATE_TRAIN') if s['program']=='GATE_MOVE_MEASURE')
        case={**r['outcome'],'initial':normalize(asdict(observation()))};c=numerical(spec,case,public,steps,dict(receiver=receiver()))
        self.assertGreater(c['pi_plans'],0);self.assertEqual(c['rate_transitions'],1)
        corrupt=deepcopy(public)
        for e in corrupt:
            if e['agent_event']=='MEMORY_TRANSITION_PLAN':e['public_payload']['plan']['after_memory']['integral_xy']=[0.,0.]
        with self.assertRaises(ValueError):numerical(spec,case,corrupt,steps,dict(receiver=receiver()))

    def test_independent_randomizer_audit_rejects_changed_draw(self):
        from src.analysis.release_learning_record_audit_v1 import randomness
        spec=next(s for s in a.population('SOFTWARE_NATIVE') if s['program']=='N_MOVE_RANDOM');session=PublicHostStub();witnesses=[]
        def observe(label):witnesses.append(dict(label=label,source_witness=deepcopy(session.witness())))
        r=host.run_live(spec,None,session,observe,lambda:None,dict(receiver=None,policy=None,pre_bank=None))
        public=[e for e in session.events if e['event']=='AGENT_EVENT']
        self.assertEqual(randomness(spec,r,session.events,public,witnesses)['actual_exposure_draws'],1)
        corrupt=deepcopy(session.events)
        for e in corrupt:
            if e['event']=='RELEASE_RANDOM_ORACLE':e['uniform_oracle']=1-e['uniform_oracle']
        with self.assertRaises(ValueError):randomness(spec,r,corrupt,public,witnesses)

    def test_both_no_probe_strong_controls_reach_the_actual_host(self):
        for program in ('REFERENCE_NO_PROBE','PURE_MOVE_KEEP'):
            spec=next(s for s in a.population('DEV') if s['program']==program);session=PublicHostStub()
            original=actor.macro.acquire
            r=host.run_live(spec,None,session,lambda label:None,lambda:None,dict(receiver=None,policy=None,pre_bank=None))
            self.assertIs(actor.macro.acquire,original);self.assertEqual(r['warm_probe_steps'],0);self.assertGreater(r['movement_steps'],0)
            self.assertEqual(r['reference_update_applied'],program=='REFERENCE_NO_PROBE');self.assertEqual(r['exposure_draws'],0)

    def test_common_receiver_has_matched_residual_capacity(self):
        l=fixture()[0]['outcome']['learning'];b=receiver();b['model']['common_residual'][0]['coefficients'][0]=-150.
        b['receiver_version']=digest(b['model']);base,full=predictor.receiver(b,l['release_receipt']['model_view'],l['prefix_history'])
        self.assertEqual(base[0],30.);self.assertEqual(full[0],80.)
        view=deepcopy(l['release_receipt']['model_view']);view['signal']=None
        base2,full2=predictor.receiver(b,view,l['prefix_history']);self.assertEqual(base,base2);self.assertIsNone(full2)

    def test_risk_resolution_removes_spurious_roundoff_rate_choice(self):
        l=fixture()[0]['outcome']['learning'];b=receiver()
        for j,m in enumerate(b['model']['common']):m['coefficients'][0]=100.+(3-j)*1e-8
        b['receiver_version']=digest(b['model']);v,_=predictor.receiver(b,l['release_receipt']['model_view'],l['prefix_history'])
        self.assertEqual(v,[100.,100.,100.,100.])

    def test_registered_center_locations_cannot_be_replaced(self):
        ledger=[];x=[[0.],[1.],[2.],[3.]];y=[0.,10.,20.,30.];g=['A','A','B','B'];m=fit.fit(x,y,g,1.,.01,3,ledger,role='SYNTHETIC_CENTER_TEST')
        m['centers'][0][0]+=.1
        with self.assertRaises(ValueError):fit.independent_refit(m,x,y,g,.01,[],role='SYNTHETIC_CORRUPTION',expected_centers=3)

    def test_effect_and_standard_dr_heads_are_the_same_linear_estimator(self):
        from src.analysis.release_learning_equivalence_v1 import check
        r=check()
        self.assertEqual(r['integrity'],'PASSED_EQUIVALENCE_CONFIRMED')
        self.assertEqual(len(r['synthetic_fit_ledger']),3)
        self.assertLess(r['max_prediction_identity_error'],1e-8)
        self.assertEqual(r['new_scientific_model_fits'],0)

    def test_closed_draft_preparation_rejects_before_any_manifest_io(self):
        self.assertEqual(a.config()['collection_status'],'CLOSED_BEFORE_COLLECTION')
        with patch.object(a.io,'read',side_effect=AssertionError('must reject before reading or allocating a manifest')):
            with self.assertRaisesRegex(ValueError,'standard DR'):a.prepare()

    def test_closed_draft_collection_rejects_before_directory_or_environment(self):
        from src.analysis.release_learning_collect_v1 import collect
        with patch.object(a.io,'read',side_effect=AssertionError('must reject before reading a manifest')):
            with self.assertRaisesRegex(ValueError,'rejected before any physical collection'):
                collect(a.OUTPUT/'never_created'/'manifest.json','SOFTWARE_NATIVE')


if __name__=='__main__':unittest.main()

from copy import deepcopy
from importlib.util import spec_from_file_location,module_from_spec
from time import perf_counter_ns
import unittest
import numpy as np
from src.analysis import correction_scope_io_v1 as a
from src.analysis import correction_scope_host_v1 as host
from src.analysis import correction_scope_independent_v1 as independent
from src.analysis.release_learning_guard_v1 import read_only
from src.probe import correction_scope_model_v1 as model
from src.probe import correction_scope_program_v1 as actor
from src.probe.continuous import StepObservation
from src.probe.task_memory_option_v1 import TaskMemory
from src.probe.physical_reprobe_v1 import StepReceipt
from src.analysis.capsule_record_json_v2 import normalize


def initial():
    o=[0.]*39;o[:3]=[.1,.8,.25];o[4:7]=[.5,.1,.05]
    return StepObservation(tuple(o),False,False,False)


def fixture(action='CONTINUE',rate=.5,end_at=50,bank=None):
    current=initial();events=[];steps=[]
    def emit(name,p):
        r={**normalize(p),'sequence':len(events),'saved_ns':perf_counter_ns()};events.append(dict(kind=name,payload=r));return r
    def policy(o):
        if list(o)!=list(current.observation):raise AssertionError('stale policy observation')
        return np.asarray([.2,-.1,.3,-1.],np.float32)
    def step(saved):
        nonlocal current
        if events[-1]['kind']!='COMMAND' or events[-1]['payload']!=saved:raise AssertionError('unsaved command')
        n=len(steps)+1;o=list(current.observation);o[:3]=[o[i]+.005*saved['command'][i] for i in range(3)]
        current=StepObservation(tuple(o),False,False,n>=end_at);steps.append(deepcopy(saved));return StepReceipt(current,n)
    result=actor.run('push-v3',current,16,action,rate,policy,step,emit,bank=bank)
    return result,events,steps


def input_view():
    _,events,_=fixture();return next(e['payload']['value'] for e in events if e['kind']=='FORECAST_INPUT')


class CorrectionScopeContracts(unittest.TestCase):
    def test_frozen_bank_forecasts_are_saved_before_outcomes(self):
        v=input_view();models={}
        for stage in model.STAGES:
            models[stage]={}
            for kind in model.KINDS:
                n=len(model.features(v,kind));rows=1+n+(0 if kind=='FULL_LINEAR' else 1)
                c=np.zeros((rows,model.TARGETS));c[0]=np.linspace(0,1,model.TARGETS)
                models[stage][kind]=dict(kind=kind,mean=[0.]*n,scale=[1.]*n,centers=[[0.]*n],coefficients=c.tolist())
        bank=dict(schema='CORRECTION_SCOPE_BANK_V1',models=models);bank['bank_id']=a.io.digest(bank)
        r,events,steps=fixture(bank=bank)
        forecasts=[e['payload'] for e in events if e['kind']=='FORECAST'];self.assertEqual(len(forecasts),2)
        self.assertTrue(all(f['forecast']['bank_id']==bank['bank_id'] for f in forecasts))
        self.assertLess(forecasts[-1]['sequence'],steps[16]['sequence'])
        wrong=deepcopy(bank);wrong['models']['PRE']['FULL_LINEAR']['coefficients'][0][0]+=1
        with self.assertRaises(ValueError):model.predict(wrong,v)

    def test_host_detects_midtask_reset_before_rate_commit(self):
        sp=spec_from_file_location('old_release_fixture_reset',a.ROOT/'tests/test_release_learning_v1.py');module=module_from_spec(sp);sp.loader.exec_module(module)
        session=module.PublicHostStub(end_at=100)
        def witness(name):
            if name=='RATE_PRE':session.ledger.counts['reset_attempts']=1
        with self.assertRaisesRegex(ValueError,'mid-task reset'):host.run_live(a.population('NATIVE')[0],session,witness,lambda:None,None)

    def test_independent_persistence_moments(self):
        v=input_view();np.testing.assert_allclose(model.project(model.persistence(v)),independent.persistence(v),atol=2e-13,rtol=2e-13)

    def test_direction_allocation_and_exact_costs(self):
        self.assertEqual([len(a.population(c)) for c in a.COHORTS],[108,648,216,648])
        self.assertEqual(a.config()['combined_limits'],dict(executions=1620,control_steps=810000,controlled_resets=1620,all_resets=82620,physical_frames=45360000))
        with self.assertRaises(ValueError):a.validate_spec({**a.population('TRAIN')[0],'seed':73000})

    def test_pre_prediction_precedes_acquisition_and_tail(self):
        r,events,steps=fixture('MOVE_MEASURE',end_at=120)
        names=[e['kind'] for e in events];self.assertLess(names.index('FORECAST'),names.index('ACQUISITION_CHOICE'))
        post=next(e['payload'] for e in events if e['kind']=='FORECAST_INPUT' and e['payload']['value']['stage']=='POST')
        self.assertGreater(post['at_calls'],16);first=next(s for s in steps if s['phase']=='TAIL_TASK');self.assertGreater(first['sequence'],post['sequence'])
        self.assertEqual(r['outcome']['total_steps'],len(steps))

    def test_rate_changes_actual_commands_carry_same_integral(self):
        one=fixture(rate=.125);two=fixture(rate=8.)
        self.assertEqual([x['command'] for x in one[2][:16]],[x['command'] for x in two[2][:16]])
        self.assertNotEqual(one[2][16]['command'][:2],two[2][16]['command'][:2])
        for _,events,_ in (one,two):
            p=next(e['payload'] for e in events if e['kind']=='RATE_COMMIT');self.assertEqual(p['receipt']['before']['integral_xy'],p['receipt']['after']['integral_xy'])

    def test_validation_eight_is_actual_task_history(self):
        r,events,steps=fixture('VALIDATE8');self.assertEqual(r['outcome']['measurement_steps'],8)
        self.assertEqual(sum(s['phase']=='VALIDATION_TASK' for s in steps),8);self.assertEqual(r['outcome']['policy_queries'],len(steps))

    def test_early_end_retains_no_fabricated_forecasts(self):
        r,e,s=fixture(end_at=8);self.assertIsNone(r['outcome']['pre_forecast']);self.assertFalse(any(x['kind']=='RATE_COMMIT' for x in e))
        r,e,s=fixture('VALIDATE8',end_at=18);self.assertIsNotNone(r['outcome']['pre_forecast']);self.assertIsNone(r['outcome']['post_forecast'])

    def test_private_nested_and_future_fields_fail_closed(self):
        v=input_view()
        for mutate in (lambda x:x.update(seed=1),lambda x:x['history'][0].update(noise_oracle=[0,0,0]),lambda x:x['memory'].update(future_loss=0)):
            bad=deepcopy(v);mutate(bad)
            with self.assertRaises(ValueError):model.validate(bad)

    def test_future_missing_reversed_history_rejected(self):
        v=input_view()
        for h in (v['history'][:-1],list(reversed(v['history'])),v['history']+[v['history'][-1]]):
            bad=deepcopy(v);bad['history']=h
            with self.assertRaises(ValueError):model.validate(bad)

    def test_rate_blind_cannot_recover_memory_rate(self):
        v=input_view();v['stage']='POST';v['memory']['time_constant_s']=.125;v['time_constant_s']=.125
        w=deepcopy(v);w['memory']['time_constant_s']=8.;w['time_constant_s']=8.
        np.testing.assert_array_equal(model.features(v,'RATE_BLIND_RBF'),model.features(w,'RATE_BLIND_RBF'))
        self.assertFalse(np.array_equal(model.features(v,'FULL_RBF'),model.features(w,'FULL_RBF')))

    def test_independent_feature_math(self):
        v=input_view()
        for kind in model.KINDS:np.testing.assert_allclose(model.features(v,kind),independent.features(v,kind),atol=1e-14,rtol=1e-14)

    def test_known_model_and_noise_algebra(self):
        r=deepcopy(input_view()['history'][0]);b=r['before']['observation'];r['command']=[.25,-.5,0.,0.]
        after=deepcopy(r['before']);after['observation'][:2]=[b[0]+.0025,b[1]-.005];r['after']=after
        self.assertAlmostEqual(model.query_vector(r)[1],0.,25)
        r['after']['observation'][0]+=.001;self.assertAlmostEqual(model.query_vector(r)[1],.01,12);self.assertAlmostEqual(independent.row_values(r)[1],.01,12)

    def test_mismatched_model_leaves_error(self):
        r=deepcopy(input_view()['history'][0]);r['after']=deepcopy(r['before']);r['command']=[1.,0.,0.,0.];self.assertEqual(model.query_vector(r)[1],1.)

    def test_short_and_zero_length_not_padded(self):
        v=input_view();m=v['memory'];y,reason=model.target(v['history'],len(v['history'])-2,m)
        self.assertIsNone(reason);self.assertEqual(y[49],2/8);self.assertEqual(y[99],2/32)
        self.assertEqual(model.target(v['history'],len(v['history']),m),(None,'NO_EXECUTED_TAIL'))
        np.testing.assert_allclose(y,independent.target(v['history'],len(v['history'])-2,m),atol=1e-13)

    def test_projection_same_constraints_all_models(self):
        y=np.linspace(-2,3,model.TARGETS);p=model.project(y)
        for o in (0,50):
            self.assertAlmostEqual(sum(p[o:o+24]),1.);self.assertAlmostEqual(sum(p[o+24:o+48]),p[o+48]);self.assertTrue(0<=p[o+49]<=1)
        np.testing.assert_allclose(p,independent.project(y),atol=1e-14)

    def test_correlated_joint_not_product(self):
        y=np.zeros(model.TARGETS);y[0]=y[1]=.5;y[24]=1.;y[48]=1.;y[49]=1.;y[50:100]=y[:50]
        e=model.family_errors(y,y);self.assertEqual(e['joint_32'],0.);self.assertGreater(e['factorized_joint_32'],0.);self.assertEqual(e,independent.errors(y.tolist(),y.tolist()))

    def test_fit_independent_augmented_refit(self):
        v=input_view();rows=[]
        for i in range(8):
            w=deepcopy(v);w['time_constant_s']=model.RATES[i%4];y=model.project(np.linspace(0,1,model.TARGETS)+i*.01);rows.append(dict(view=w,target=y,spec=dict(group=i//4)))
        m=model.fit([model.features(e['view'],'FULL_RBF') for e in rows],[e['target'] for e in rows],[e['spec']['group'] for e in rows],'FULL_RBF')
        self.assertEqual(independent.refit(rows,'FULL_RBF',m).shape[1],model.TARGETS)

    def test_illegal_action_rate_budget_rejected(self):
        with self.assertRaises(ValueError):fixture('AGAIN')
        with self.assertRaises(ValueError):fixture(rate=.25)
        with self.assertRaises(ValueError):a.validate_spec({**a.population('TRAIN')[0],'planned_boundary':499})

    def test_saved_records_literal_targets_compatible(self):
        folder=a.ROOT/'outputs/memory_reset/qualification_v1/memory_reset_20261022T224151Z_814c7dbd2ce7/software_native'
        w=next(a.io.rows(folder/'witnesses.jsonl.gz'))
        from src.analysis.continuous_state_witness_v1 import verify_witness
        verify_witness(w['witness'],full_sha256=w['source_witness']['python_semantic_sha256'],native_sha256=w['source_witness']['native_sha256'])
        h=[];prior=None
        for r in a.io.rows(folder/'events.jsonl.gz'):
            if r['event']=='CONTROLLED_INITIAL':prior=dict(observation=r['observation'],success=False,terminated=False,truncated=False)
            if r['event']=='STEP_COMPLETE':
                h.append(dict(at_calls=r['logical_step'],before=prior,command=r['command'],after=r['after']));prior=r['after']
                if len(h)==8:break
        m=TaskMemory.initial('push-v3',StepObservation(**prior)).to_dict();m['completed_steps']=8
        y,_=model.target(h,0,m);np.testing.assert_allclose(y,independent.target(h,0,m),atol=2e-12,rtol=2e-12)

    def test_actual_host_array_adapter_continuity(self):
        sp=spec_from_file_location('old_release_fixture',a.ROOT/'tests/test_release_learning_v1.py');module=module_from_spec(sp);sp.loader.exec_module(module)
        session=module.PublicHostStub(end_at=100);s=a.population('NATIVE')[0];w=[];syncs=[]
        r=host.run_live(s,session,lambda name:w.append((name,session.ctx['calls'])),lambda:syncs.append(session.ctx['calls']),None)
        self.assertEqual(r['total_steps'],100);self.assertTrue(r['boundary_applied']);self.assertEqual(session.run_budget['completed'],100)
        self.assertIn(('RATE_PRE',16),w);self.assertIn(('RATE_POST',16),w);self.assertGreaterEqual(len(syncs),100)

    def test_statistics_quantile_literal_order(self):
        from src.analysis.correction_scope_statistics_v1 import quantile
        v=[-4.,3.,1.,8.,2.];self.assertEqual(quantile(v,.025),float(np.quantile(v,.025)));self.assertEqual(quantile(v,.975),float(np.quantile(v,.975)))

    def test_readonly_guard_denies_network(self):
        receipt={}
        with read_only(receipt):
            import socket
            with self.assertRaises(RuntimeError):socket.create_connection(('127.0.0.1',9))
        self.assertEqual(receipt['network']['attempted_network_calls'],1);self.assertTrue(receipt['zero_new_physical_interactions'])


if __name__=='__main__':unittest.main()

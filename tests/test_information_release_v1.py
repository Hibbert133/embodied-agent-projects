"""Array/synthetic contracts only; no environment, new scientific fit or API."""
from copy import deepcopy
from dataclasses import asdict,replace
import unittest
import numpy as np
from src.probe.continuous import StepObservation
from src.probe.task_memory_option_v1 import TaskMemory,TaskMemoryMachine
from src.probe import information_release_v1 as m
from src.probe import information_release_features_v1 as f
from src.probe import information_release_acquisition_v1 as a
from src.analysis.information_release_targets_v1 import targets,complete_program_score
from src.analysis.capsule_record_json_v2 import normalize

VERSION='a'*64


def obs(i=0,end=False):
    v=[0.]*39;v[:3]=[.1+i*.0001,.8,.25];return StepObservation(tuple(v),False,False,end)


def initial(at=16):return replace(TaskMemory.initial('push-v3',obs(at)),completed_steps=at,integral_xy=(.15,-.08))


def record(action='MOVE_MEASURE',n=10,end=False):
    before=initial();steps=[];current=before.current
    for i in range(n):
        after=obs(17+i,end and i==n-1)
        phase='VALIDATION_TASK' if action=='VALIDATE8' else 'REPOSITION' if i<max(0,n-8) else 'MEASUREMENT'
        steps.append(dict(at_calls=16+i,phase=phase,command=[.2,-.1,0.,-1.],before=normalize(asdict(current)),after=normalize(asdict(after))))
        current=after
    after=replace(before,current=current,completed_steps=16+n)
    reason='NO_ACQUISITION' if action=='CONTINUE' else 'EARLY_END' if end else 'COMPLETE' if n==(8 if action=='VALIDATE8' else 10) else 'PARTIAL'
    return m.public_record(before,after,action,steps,reason)


def pair(action='MOVE_MEASURE',n=10,end=False,p=.5):
    saved=m.seal(record(action,n,end),100)
    receipts=[m.assign(saved,probability=p,uniform=u,release_sequence=101,receiver_version=VERSION) for u in (p+(1-p)*.5,.25*p)]
    return saved,receipts


def target(saved,r,y=120,m0=100,m1=110,**kw):
    args=dict(saved_return=saved,release_receipt=r,cutoff_loss=y,mu_masked=m0,mu_full=m1,expected_receiver_version=VERSION,
        independent_group='G02',nuisance_training_groups=['G00','G01'],expected_probability=r['binding'].get('assignment_probability',.5))
    args.update(kw);return targets(**args)


def history(at=16):
    return [dict(at_calls=i,command=[.2,-.1,0.,-1.],before=normalize(asdict(obs(i))),after=normalize(asdict(obs(i+1)))) for i in range(at)]


def risks():return {x:dict(masked_risk=100.,information_effect=0.) for x in a.ACTIONS}


class InformationReleaseContracts(unittest.TestCase):
    def test_masked_and_full_share_actual_return_state(self):
        saved,(masked,full)=pair()
        self.assertEqual(masked['model_view']['common'],full['model_view']['common'])
        self.assertIsNone(masked['model_view']['signal']);self.assertEqual(full['model_view']['signal'],saved['record']['steps'])
        self.assertEqual(masked['model_view']['common']['post_memory']['integral_xy'],[.15,-.08])

    def test_empty_signal_collapses_model_inputs(self):
        saved,(masked,full)=pair('CONTINUE',0)
        self.assertEqual(masked['model_view'],full['model_view'])
        self.assertNotEqual(masked['binding'],full['binding'])
        self.assertEqual(target(saved,full)['supplemental_information_effect'],0.)

    def test_release_is_strictly_after_physical_return(self):
        saved,_=pair()
        for seq in (99,100,True):
            with self.assertRaises(ValueError):m.assign(saved,probability=.5,uniform=.1,release_sequence=seq,receiver_version=VERSION)

    def test_release_transport_rejects_changed_record(self):
        saved,_=pair();saved['record']['steps'][0]['command'][0]=.9
        with self.assertRaises(ValueError):m.assign(saved,probability=.5,uniform=.1,release_sequence=101,receiver_version=VERSION)

    def test_unknown_nested_oracle_and_future_fields_rejected(self):
        _,(_,full)=pair()
        for field in ('oracle','noise','seed','future_loss'):
            x=deepcopy(full['model_view']);x['common']['post_memory'][field]=0
            with self.assertRaises(ValueError):f.encode(x)
            x=deepcopy(full['model_view']);x['signal'][0][field]=0
            with self.assertRaises(ValueError):f.encode(x)

    def test_public_observation_flags_and_coordinates_are_strict(self):
        _,(_,r)=pair()
        for bad in (float('nan'),float('inf'),True):
            x=deepcopy(r['model_view']);x['common']['post_memory']['current']['observation'][0]=bad
            with self.assertRaises(ValueError):f.encode(x)
        x=deepcopy(r['model_view']);x['common']['post_memory']['current']['success']=1
        with self.assertRaises(ValueError):f.encode(x)

    def test_skipped_clock_and_discontinuous_observation_rejected(self):
        saved,_=pair()
        for key in ('clock','state'):
            x=deepcopy(saved['record'])
            if key=='clock':x['steps'][1]['at_calls']+=1
            else:x['steps'][1]['before']['observation'][0]+=.01
            with self.assertRaises(ValueError):m.seal(x,100)

    def test_phase_reversal_and_over_cap_rejected(self):
        saved,_=pair();x=deepcopy(saved['record']);x['steps'][-1]['phase']='REPOSITION'
        with self.assertRaises(ValueError):m.seal(x,100)
        with self.assertRaises(ValueError):record('VALIDATE8',9)
        with self.assertRaises(ValueError):record('MOVE_MEASURE',73)

    def test_empty_and_budget_refusal_preserve_memory(self):
        before=initial();r=m.public_record(before,before,'MOVE_MEASURE',[],'BUDGET_KEEP')
        self.assertEqual(r['before_memory'],r['post_memory'])
        with self.assertRaises(ValueError):m.public_record(before,replace(before,integral_xy=(0.,0.)),'MOVE_MEASURE',[],'BUDGET_KEEP')

    def test_partial_and_early_end_are_not_zero_filled(self):
        saved,(_,full)=pair(n=2,end=True)
        self.assertEqual(len(full['model_view']['signal']),2)
        self.assertEqual(full['model_view']['common']['paid_acquisition_steps'],2)
        self.assertEqual(target(saved,full,y=18)['supplemental_information_effect'],0.)
        with self.assertRaises(ValueError):target(saved,full,y=500)

    def test_no_receiving_decision_after_terminal(self):
        saved,(_,full)=pair(n=2,end=True)
        with self.assertRaises(ValueError):m.receiver_plan(saved,full,[1.,2.,3.,4.],[1.,2.,3.,4.])

    def test_assignment_support_and_draw_are_strict(self):
        saved,_=pair()
        for p,u in ((0,.1),(1,.1),(True,.1),(.5,1),(.5,-.1),(.5,float('nan'))):
            with self.assertRaises(ValueError):m.assign(saved,probability=p,uniform=u,release_sequence=101,receiver_version=VERSION)

    def test_assignment_and_view_binding_cannot_disagree(self):
        saved,(_,full)=pair()
        for key in ('assignment','signal'):
            x=deepcopy(full)
            if key=='assignment':x['binding']['assigned_exposure']=False
            else:x['model_view']['signal']=None
            with self.assertRaises(ValueError):m.validate_receipt(saved,x)

    def test_receiver_choice_changes_saved_actual_next_send(self):
        saved,(masked,full)=pair();plans=[m.receiver_plan(saved,masked,[100,10,100,100]),
            m.receiver_plan(saved,full,[100,10,100,100],[10,100,100,100])]
        commands=[]
        for receipt,p in zip((masked,full),plans):
            machine=TaskMemoryMachine(m.memory(saved['record']['post_memory']));m.consume_receiver(machine,p,saved,receipt)
            q=machine.plan([.2,-.1,.3,-1.]);commands.append(q['pi_plan']['numbers']['sent_command'])
            self.assertEqual(machine.memory.integral_xy,(.15,-.08))
        self.assertNotEqual(commands[0][:2],commands[1][:2]);self.assertEqual(commands[0][2:],commands[1][2:])

    def test_empty_view_cannot_invent_signal_head(self):
        _,(_,full)=pair('CONTINUE',0)
        with self.assertRaises(ValueError):m.choose_rate(full['model_view'],[1,2,3,4],[4,3,2,1])
        self.assertEqual(m.choose_rate(full['model_view'],[7,7,7,7])['time_constant_s'],.5)

    def test_changed_saved_choice_and_replay_rejected(self):
        saved,(masked,_)=pair();p=m.receiver_plan(saved,masked,[100,10,100,100]);machine=TaskMemoryMachine(m.memory(saved['record']['post_memory']))
        x=deepcopy(p);x['choice']['time_constant_s']=8.
        with self.assertRaises(ValueError):m.consume_receiver(machine,x,saved,masked)
        m.consume_receiver(machine,p,saved,masked)
        with self.assertRaises(ValueError):m.consume_receiver(machine,p,saved,masked)

    def test_rate_plan_rejects_outstanding_and_stale_state(self):
        saved,(masked,_)=pair();p=m.receiver_plan(saved,masked,[10,100,100,100]);machine=TaskMemoryMachine(m.memory(saved['record']['post_memory']))
        machine.plan([.2,-.1,.3,-1.])
        with self.assertRaises(ValueError):m.consume_receiver(machine,p,saved,masked)
        machine=TaskMemoryMachine(replace(m.memory(saved['record']['post_memory']),integral_xy=(0.,0.)))
        with self.assertRaises(ValueError):m.consume_receiver(machine,p,saved,masked)

    def test_deterministic_deployment_is_not_randomized_training(self):
        saved,_=pair();r=m.release(saved,expose=True,release_sequence=101,receiver_version=VERSION)
        self.assertIn('gain_plan',m.receiver_plan(saved,r,[1,2,3,4],[4,3,2,1]))
        with self.assertRaises(ValueError):target(saved,r,expected_probability=.5)

    def test_feature_shape_masks_real_history_and_excludes_metadata(self):
        saved,(masked,full)=pair(n=2)
        x=f.encode(full['model_view']);z=f.encode(masked['model_view'])
        self.assertEqual(x['common'].shape,(123,));self.assertEqual(x['trace'].shape,(72,86))
        self.assertEqual(x['trace_mask'].sum(),2);self.assertEqual(z['trace_mask'].sum(),0)
        self.assertTrue(np.array_equal(x['common'],z['common']))
        self.assertTrue(np.array_equal(x['trace'][0,5:44],saved['record']['steps'][0]['before']['observation']))
        self.assertTrue(np.all(x['trace'][2:]==0));self.assertNotIn('binding',x)

    def test_empty_feature_views_are_exactly_equal(self):
        _,(masked,full)=pair('CONTINUE',0)
        for k,v in f.encode(masked['model_view']).items():self.assertTrue(np.array_equal(v,f.encode(full['model_view'])[k]))

    def test_entire_group_is_excluded_and_receiver_is_fixed(self):
        saved,(_,r)=pair()
        for kw in (dict(nuisance_training_groups=['G02']),dict(expected_receiver_version='b'*64),dict(nuisance_training_groups=['G00','G00']),
                   dict(expected_probability=.75)):
            with self.assertRaises(ValueError):target(saved,r,**kw)

    def test_aipw_targets_keep_signed_out_of_range_values(self):
        saved,(_,r)=pair(p=.1)
        x=target(saved,r,y=500,m0=100,m1=0)
        self.assertEqual(x['released_full_program_risk'],5000)
        self.assertEqual(x['supplemental_information_effect'],4900)
        self.assertFalse(x['pseudo_targets_clipped'])

    def test_both_directions_of_information_effect_are_retained(self):
        saved,(masked,full)=pair()
        negative=target(saved,full,y=20,m0=100,m1=100)
        positive=target(saved,full,y=200,m0=100,m1=100)
        self.assertLess(negative['supplemental_information_effect'],0);self.assertGreater(positive['supplemental_information_effect'],0)
        self.assertEqual(target(saved,masked,y=200,m0=100,m1=100)['supplemental_information_effect'],-200)

    def test_complete_program_cost_is_not_added_twice(self):
        self.assertEqual(complete_program_score(140,-10,True),130)
        self.assertEqual(complete_program_score(140,-10,False),140)

    def test_predecision_cannot_read_future_or_fake_old_history(self):
        r=risks();h=history()
        self.assertEqual(a.plan(normalize(initial().to_dict()),h,r)['action'],'CONTINUE')
        h[0]['future_return_state']=[0.]*39
        with self.assertRaises(ValueError):a.plan(normalize(initial().to_dict()),h,r)
        with self.assertRaises(ValueError):a.plan(normalize(initial().to_dict()),history()[1:],r)
        h=history();h[-1]['after']['observation'][0]+=.01
        with self.assertRaises(ValueError):a.plan(normalize(initial().to_dict()),h,r)

    def test_predecision_uses_signed_total_effect_and_can_keep_movement(self):
        r=risks();r['MOVE_MEASURE']=dict(masked_risk=80,information_effect=30)
        p=a.plan(normalize(initial().to_dict()),history(),r)
        self.assertEqual((p['action'],p['expose_supplemental_trace'],p['complete_program_risk']),('MOVE_MEASURE',False,80))
        r['MOVE_MEASURE']['information_effect']=-10
        self.assertEqual(a.plan(normalize(initial().to_dict()),history(),r)['complete_program_risk'],70)
        self.assertEqual(p['predicted']['MOVE_MEASURE']['information_effect'],30)

    def test_budget_refuses_acquisition_without_rewinding_state(self):
        at=470;r=risks();r['MOVE_MEASURE']['masked_risk']=0;r['VALIDATE8']['masked_risk']=0
        p=a.plan(normalize(initial(at).to_dict()),history(at),r)
        self.assertEqual(p['action'],'CONTINUE');self.assertEqual(p['before_memory_sha256'],initial(at).sha256)

    def test_all_registered_gains_are_numerically_admissible_without_utility_claim(self):
        for rate in m.RATES:
            p=m.gain_plan(initial(),rate)
            self.assertFalse(p['physical_safety_guarantee']);self.assertFalse(p['task_benefit_established'])
        for bad in (0,1,True,float('nan')):
            with self.assertRaises(ValueError):m.gain_plan(initial(),bad)

    def test_independent_audit_detects_duplicate_and_broken_commands(self):
        from src.analysis.information_release_census_v1 import generate
        from src.analysis.information_release_independent_audit_v1 import audit_value
        v=generate();self.assertEqual(audit_value(v)['integrity'],'PASSED')
        x=deepcopy(v);x['public_cases'][1]=deepcopy(x['public_cases'][0])
        with self.assertRaises(ValueError):audit_value(x)
        x=deepcopy(v);x['public_cases'][0]['views'][0]['next_command']['pi_plan']['numbers']['sent_command'][0]+=.01
        with self.assertRaises(ValueError):audit_value(x)

    def test_independent_audit_detects_clipped_pseudo_targets(self):
        from src.analysis.information_release_census_v1 import generate
        from src.analysis.information_release_independent_audit_v1 import audit_value
        v=generate();found=False
        for c in v['algebra_cases']:
            for o in c['outcomes']:
                t=o['target'];x=t['released_full_program_risk']
                if x<0 or x>500:t['released_full_program_risk']=min(500,max(0,x));found=True;break
            if found:break
        self.assertTrue(found)
        with self.assertRaises(ValueError):audit_value(v)


if __name__=='__main__':unittest.main()

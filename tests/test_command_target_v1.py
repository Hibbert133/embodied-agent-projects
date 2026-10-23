"""Pure arrays and saved files only: no environment, reset, simulation or fit."""
from copy import deepcopy
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
import numpy as np
from src.probe.nominal_command_target_v1 import PublicNominalTarget,INITIAL,LOW,HIGH,target_update
from src.analysis import command_target_diagnostic_v1 as main,command_target_audit_v1 as audit,command_target_sources_v1 as source

FAULT={'matrix_xy':[[1.,0.],[0.,1.]],'bias_xy':[0.,0.],'deadzone_xy':[0.,0.]}


def fixture(n=4,phase='WARM_PROBE',entry=False):
    initial=[0.,.6,.2]+[0.]*36;history=[initial];events=[]
    for k in range(n):
        after=initial.copy();after[0]+=.001*(k+1);history.append(after)
        events.append({'event':'STEP_COMPLETE','sequence':k+1,'logical_step':k,'noise_cursor_after':k+1,'phase':phase,
            'command':[.2,-.1,0.,0.],'executed_action_oracle':[.21,-.08,0.,0.],'after':{'observation':after}})
        if entry and k==2:events.append({'event':'AGENT_EVENT','agent_event':'PROBE_ENTRY','sequence':100,'public_payload':{'at_calls':3,'entry_history':deepcopy(history[-4:])}})
    c={'group':0,'seed':987654,'context':'UNCHANGED','program':'LOCAL_PID_KEEP','planned_boundary':16,
        'initial_fault_oracle':FAULT,'task':'push-v3','total_steps':n,'success':True,'stop_reason':'SUCCESS'}
    return c,events,initial


class CommandTargetTests(TestCase):
    def test_explicit_reset_prior_and_limits(self):
        with self.assertRaises(ValueError):PublicNominalTarget.initial('push-v3',controlled_reset_declared=False)
        with self.assertRaises(ValueError):PublicNominalTarget.initial('unknown',controlled_reset_declared=True)
        state=PublicNominalTarget.initial('push-v3',controlled_reset_declared=True)
        self.assertEqual(state.target,INITIAL);self.assertFalse(state.to_dict()['physical_state_qualified'])
        with self.assertRaises(ValueError):PublicNominalTarget('push-v3',501,INITIAL)

    def test_saved_plan_changes_only_public_accumulator(self):
        state=PublicNominalTarget.initial('reach-v3',controlled_reset_declared=True);plan=state.propose([.4,0.,0.,0.]);new=state.consume(plan)
        self.assertGreater(new.target[0],0);self.assertEqual(new.completed_commands,1)
        self.assertEqual(state.target,INITIAL)
        with self.assertRaises(ValueError):new.consume(plan)

    def test_private_future_and_unearned_qualification_rejected(self):
        state=PublicNominalTarget('door-open-v3',0,INITIAL)
        for key,value in (('fault_oracle',FAULT),('future_result',True),('physical_state_qualified',True),('target',[True,.6,.2])):
            d=state.to_dict();d[key]=value
            with self.assertRaises(ValueError):PublicNominalTarget.from_dict(d)
        p=state.propose([0.,0.,0.,0.]);p['noise_oracle']=[0.,0.,0.]
        with self.assertRaises(ValueError):state.consume(p)

    def test_malformed_actions_and_exhausted_budget(self):
        state=PublicNominalTarget('push-v3',500,INITIAL)
        with self.assertRaises(ValueError):state.propose([0.,0.,0.,0.])
        state=PublicNominalTarget('push-v3',0,INITIAL)
        for u in ([0.,0.,0.],[True,0.,0.,0.],[float('nan'),0.,0.,0.],[1.01,0.,0.,0.],np.zeros(4)):
            with self.assertRaises(ValueError):state.propose(u)

    def test_installed_array_method_exact_conformance(self):
        # Invoke an unbound arithmetic method on a fake namespace, never an Env.
        from metaworld.sawyer_xyz_env import SawyerXYZEnv
        import ast
        from pathlib import Path
        import metaworld
        package=Path(metaworld.__file__).parent
        for task in ('push','reach','door'):
            tree=ast.parse((package/'envs'/f'sawyer_{task}_v3.py').read_text(encoding='utf-8'))
            assignments={t.id:node.value for node in ast.walk(tree) if isinstance(node,ast.Assign) for t in node.targets if isinstance(t,ast.Name)}
            self.assertEqual(tuple(ast.literal_eval(assignments['hand_low'])),LOW)
            self.assertEqual(tuple(ast.literal_eval(assignments['hand_high'])),HIGH)
            initializers=[v for node in ast.walk(tree) if isinstance(node,ast.Dict) for k,v in zip(node.keys,node.values) if isinstance(k,ast.Constant) and k.value=='hand_init_pos']
            self.assertEqual(len(initializers),1);self.assertEqual(tuple(ast.literal_eval(initializers[0].args[0])),INITIAL)
            super_calls=[node for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='__init__']
            self.assertTrue(super_calls)
            self.assertTrue(all(k.arg not in ('mocap_low','mocap_high','action_scale') for node in super_calls for k in node.keywords))
        fake=SimpleNamespace(data=SimpleNamespace(mocap_pos=np.array([INITIAL]),mocap_quat=None),action_scale=.01,
            mocap_low=np.array(LOW),mocap_high=np.array(HIGH))
        q=list(INITIAL)
        commands=([[.123456789,-.234567891,.345678912,0.]]*40+[[1.,1.,1.,0.]]*70+[[-1.,-1.,-1.,0.]]*100)
        for u in commands:
            SawyerXYZEnv.set_xyz_action(fake,np.array(u[:3],dtype=np.float32))
            q=target_update(q,u)['target'];np.testing.assert_array_equal(q,fake.data.mocap_pos[0])

    def test_float64_scale_mutant_is_detected(self):
        u=[.123456789,0.,0.,0.];got=target_update(INITIAL,u)['target'][0]
        wrong=float(np.float32(u[0]))*.01
        self.assertNotEqual(got,wrong);self.assertEqual(got,float(np.float32(np.float32(u[0])*np.float32(.01))))

    def test_per_step_workspace_clip_is_not_clip_at_end(self):
        start=[.499,.6,.2];a=target_update(start,[1.,0.,0.,0.])['target'];b=target_update(a,[-1.,0.,0.,0.])['target']
        self.assertLess(b[0],start[0]);self.assertTrue(target_update(start,[1.,0.,0.,0.])['workspace_clip_axes'][0])

    def test_zero_noise_mapping_not_inverse_or_early_clip(self):
        f={'matrix_xy':[[1.2,.3],[-.2,.9]],'bias_xy':[.3,-.2],'deadzone_xy':[.1,.2]};u=[.8,-.4,.2,0.]
        expected=main.applied(u,f,np.zeros(3,dtype=np.float32));audit.same(audit.noiseless(u,f),expected)
        inverse=np.linalg.solve(np.array(f['matrix_xy']),np.array(u[:2])-f['bias_xy'])
        self.assertFalse(np.allclose(expected[:2],inverse))
        before=np.array([.95,-.95,0.,0.],dtype=np.float32);noise=np.array([.2,-.2,0.],dtype=np.float32)
        actual=main.applied(before,FAULT,noise);wrong=np.clip(before,-1,1);wrong[:3]+=noise
        self.assertNotEqual(actual,wrong.tolist())

    def test_noise_transform_vector_decomposition_with_clipping(self):
        f=deepcopy(FAULT);f['bias_xy']=[.2,-.1]
        r=main.arithmetic([.499,.6,.2],[.499,.6,.2],[.499,.6,.2],[.9,.1,0.,0.],[-.4,.3,0.,0.],f,[0.,.6,.2],[.001,.6,.2],np.zeros(3))
        left=np.array(r['applied_target_after'])-r['sent_target_after']
        np.testing.assert_allclose(left,np.array(r['noise_input_component_xyz'])+r['transform_input_component_xyz'],rtol=0,atol=1e-16)
        self.assertTrue(r['sent_workspace_clipped']);self.assertLess(r['decomposition_roundoff_m'],1e-15)

    def test_future_entry_and_fabricated_history_rejected(self):
        c,events,initial=fixture(entry=True)
        for key in ('clock','history'):
            changed=deepcopy(events);p=changed[3]['public_payload']
            if key=='clock':p['at_calls']=4
            else:p['entry_history'][0][0]=999.
            with self.assertRaises(ValueError):main.trace('RECENT_QUAL',c,changed,initial)

    def test_noise_cursor_shift_rejected(self):
        c,events,initial=fixture();events[1]['noise_cursor_after']+=1
        with self.assertRaises(ValueError):main.trace('RECENT_QUAL',c,events,initial)

    def test_zero_length_and_early_success_keep_null_bins(self):
        c,events,initial=fixture(0);rows,summary,stages,entries=main.trace('RECENT_QUAL',c,events,initial)
        self.assertEqual(rows,[]);self.assertEqual(entries,[]);self.assertIsNone(summary['applied_hand_gap_mm'])
        self.assertTrue(all(r['steps']==0 and r['applied_hand_gap_mm'] is None for r in stages))
        c,events,initial=fixture(2,phase='PREFIX_TASK');_,summary,_,_=main.trace('RECENT_QUAL',c,events,initial)
        self.assertEqual(summary['missing_measurement_reason'],'SUCCESS');self.assertTrue(summary['source_success'])

    def test_short_window_and_movement_stage_bins(self):
        c,events,initial=fixture(4,'REPOSITION');events[-1]['phase']='WARM_PROBE';events[0]['after']['observation'][2]=.24
        _,summary,stages,_=main.trace('RECENT_QUAL',c,events,initial)
        self.assertEqual(summary['missing_measurement_reason'],'SHORT_EXECUTED_WINDOW')
        lift=next(r for r in stages if r['stage']=='LIFT' and r['bin_lo']==1)
        post=next(r for r in stages if r['stage']=='POST_LIFT' and r['bin_lo']==1)
        self.assertEqual((lift['steps'],post['steps']),(1,2))

    def test_independent_audit_with_main_disabled_and_tamper(self):
        c,events,initial=fixture(entry=True);rows,summary,stages,entries=main.trace('RECENT_QUAL',c,events,initial)
        with patch.object(main,'arithmetic',side_effect=RuntimeError('disabled')):
            s,ss,es,n=audit.audit_trace('RECENT_QUAL',c,events,initial,iter(rows))
        audit.same(s,summary);audit.same(ss,stages);audit.same(es,entries);self.assertGreater(n,100)
        changed=deepcopy(rows);changed[1]['applied_target_after'][0]+=.01
        with self.assertRaises(ValueError):audit.audit_trace('RECENT_QUAL',c,events,initial,iter(changed))

    def test_trajectory_then_group_weighting_no_time_or_move_duplication(self):
        base={k:0. for k in main.METRICS}|{'cohort':'X','task':'push-v3','context':'C','program':'LOCAL_PID_KEEP','phase':'REPOSITION',
            'stage':'ALL','bin_lo':1,'bin_hi':500,'steps':1,'missing_reason':None}
        rows=[base|{'group':0,'applied_hand_gap_mm':2.},base|{'group':0,'steps':500,'applied_hand_gap_mm':6.},
            base|{'group':1,'applied_hand_gap_mm':10.},base|{'group':2,'steps':0,'missing_reason':'EMPTY','applied_hand_gap_mm':None}]
        g=main.grouped(rows);audit.same(g,audit.group_tables(rows))
        self.assertEqual(g[0]['applied_hand_gap_mm'],7.);self.assertEqual(g[0]['available_groups'],2)
        other=base|{'group':0,'program':'DIRECT_C8','applied_hand_gap_mm':100.}
        self.assertEqual(len(main.grouped(rows+[other])),2)

    def test_grouped_source_journal_rejects_duplicates_and_omissions(self):
        def event(sequence,unit):return {'sequence':sequence,'saved_ns':sequence,'unit':unit,'run':'r'}
        j=source.GroupedJournal([event(0,0),event(1,1)],('unit',),{'run':'r'})
        self.assertEqual(len(j.take_case({'unit':0})),1);self.assertEqual(len(j.take_case({'unit':1})),1);j.finish()
        j=source.GroupedJournal([event(1,0)],('unit',),{'run':'r'})
        with self.assertRaises(ValueError):j.take_case({'unit':0})
        j=source.GroupedJournal([event(0,1)],('unit',),{'run':'r'})
        with self.assertRaises(ValueError):j.take_case({'unit':0})

    def test_saved_native_case_and_original_population(self):
        label,folder,_,n,steps=source.cohorts()[1];c,events,initial=next(source.cases(label,folder))
        rows,summary,stages,es=main.trace(label,c,events,initial)
        s,t,e,fields=audit.audit_trace(label,c,events,initial,iter(rows));audit.same(summary,s);audit.same(stages,t);audit.same(es,e)
        self.assertEqual(len(rows),c['total_steps']);self.assertGreater(fields,1000)
        self.assertEqual(sum(v[3] for v in source.cohorts()),1752);self.assertEqual(sum(v[4] for v in source.cohorts()),152128)

    def test_legacy_labels_preserved_without_semantic_remapping(self):
        from itertools import islice
        label,folder,*_=source.cohorts()[1]
        for c,events,initial in islice(source.cases(label,folder),1,3):
            rows,summary,stages,es=main.trace(label,c,events,initial)
            expected=[e['phase'] for e in events if e['event']=='STEP_COMPLETE']
            self.assertEqual([r['phase'] for r in rows],expected)
            s,t,e,_=audit.audit_trace(label,c,events,initial,iter(rows));audit.same(s,summary);audit.same(t,stages);audit.same(e,es)
            self.assertIn('TASK',summary['source_phase_counts'])
            if c['program']=='MOVE_INTEGRAL':self.assertIn('APPROACH',summary['source_phase_counts'])

"""Array/synthetic diagnostics: no environment, fits, thresholds or API changes."""
from copy import deepcopy
from unittest.mock import patch
import unittest
import numpy as np
from src.analysis import acquisition_anchor_diagnosis_v1 as d
from src.analysis import acquisition_anchor_diagnosis_audit_v1 as a


def fixture(empty=False):
    obs=[0.]*39;obs[:3]=[0.,.6,.25];obs[4:7]=[1.,0.,0.]
    current={'observation':obs,'success':empty,'terminated':False,'truncated':False}
    fault={'matrix_xy':[[1.,0.],[0.,1.]],'bias_xy':[0.,0.],'deadzone_xy':[0.,0.]}
    case={'group':0,'task':'push-v3','seed':0,'context':'UNCHANGED','planned_boundary':16,'action':'MOVE_MEASURE8',
        'success':empty,'deadline_loss':0 if empty else 500,'total_steps':0 if empty else 11,'option_reason':None if empty else 'COMPLETE_UNQUALIFIED',
        'boundary_reached':not empty,'movement_steps':0 if empty else 3,'warm_probe_steps':0 if empty else 8,'complete_warm_window':not empty,
        'initial':current,'initial_fault_oracle':fault,'destination_oracle':fault,'boundary_applied':False}
    tape=np.zeros((500,3),np.float32);events=[]
    commands=[[0.,0.,0.,-1.]]*3+[[.4,0,0,0],[0,.4,0,0],[-.4,0,0,0],[0,-.4,0,0]]*2
    if empty:commands=[]
    for n,command in enumerate(commands):
        sent=np.asarray(command,np.float32).astype(float).tolist();phase='REPOSITION' if n<3 else 'WARM_PROBE'
        events.append({'event':'AGENT_EVENT','agent_event':'COMMAND','sequence':100+n,'public_payload':{'decision_sequence':0,'command':sent}})
        events.append({'event':'STEP_COMPLETE','logical_step':n,'noise_cursor_after':n+1,'global_command_sequence':100+n,
            'phase':phase,'command':sent,'raw_policy':None,'executed_action_oracle':sent,'after':deepcopy(current)})
    return case,events,tape


class AnchorDiagnosisTests(unittest.TestCase):
    def test_readiness_uses_three_actual_displacements(self):
        case,_,_=fixture();h=[case['initial']['observation']]
        self.assertIsNone(d.gates(h)['recent_motion_inf_m']);self.assertFalse(d.gates(h)['ready'])
        self.assertTrue(d.gates(h*4)['ready']);self.assertEqual(d.gates(h*4),a.conditions(h*4))

    def test_position_clearance_and_motion_fail_separately(self):
        c,_,_=fixture();h=[list(c['initial']['observation']) for _ in range(4)]
        h[-1][0]=.03;self.assertIn('position',d.gates(h)['failed_conditions']);self.assertIn('motion',d.gates(h)['failed_conditions'])
        h=[list(c['initial']['observation']) for _ in range(4)];h[-1][4:7]=h[-1][:3]
        self.assertEqual(d.gates(h)['failed_conditions'],['clearance'])

    def test_float32_noise_before_final_clip_is_distinct_from_early_clip(self):
        c,_,_=fixture();f=deepcopy(c['initial_fault_oracle']);f['bias_xy']=[.4,0.]
        x=d.chain([.9,0,0,0],f,[-.5,0,0]);self.assertAlmostEqual(x['applied_action_oracle'][0],.8,places=6)
        self.assertNotEqual(x['applied_action_oracle'][0],.5);a.same(x,a.independent_chain([.9,0,0,0],f,[-.5,0,0]))

    def test_forward_affine_is_not_an_inverse_parameter_mapping(self):
        c,_,_=fixture();f=deepcopy(c['initial_fault_oracle']);f['matrix_xy']=[[2.,0.],[0.,1.]];f['bias_xy']=[.1,0.]
        self.assertAlmostEqual(d.chain([.3,0,0,0],f,[0,0,0])['applied_action_oracle'][0],.7,places=6)

    def test_noise_cursor_misalignment_is_detected(self):
        c,events,tape=fixture();tape[1,0]=.2;events[1]['executed_action_oracle'][0]=.2
        with self.assertRaisesRegex(ValueError,'float32 source execution'):d.case_analysis(c,events,tape)

    def test_invalid_noise_and_unbounded_send_are_rejected(self):
        c,_,_=fixture()
        for command,noise in (([1.1,0,0,0],[0,0,0]),([0,0,0,0],[float('nan'),0,0]),([0,0,0,0],[0,0])):
            with self.assertRaises(ValueError):d.chain(command,c['initial_fault_oracle'],noise)

    def test_fraction_balance_matches_closed_form_but_is_not_physics(self):
        c,_,_=fixture();f=deepcopy(c['initial_fault_oracle']);f['bias_xy']=[.12,-.08]
        x=d.balance_reference(f);a.same(x,a.rational_reference(f));self.assertTrue(x['not_a_physical_equilibrium_or_noise_free_response'])
        np.testing.assert_allclose(x['error_xy_m'],[-.015,.01],atol=1e-9)

    def test_balance_outside_support_and_deadzone_are_missing_not_zero(self):
        c,_,_=fixture();f=deepcopy(c['initial_fault_oracle']);f['bias_xy']=[2.,0.]
        self.assertIsNone(d.balance_reference(f)['error_xy_m']);f['bias_xy']=[0.,0.];f['deadzone_xy']=[.1,0.]
        self.assertIn('NONZERO',d.balance_reference(f)['missing_reason'])
        f['deadzone_xy']=[0.,0.];f['matrix_xy']=[[0.,0.],[0.,1.]]
        self.assertIn('SINGULAR',d.balance_reference(f)['missing_reason'])

    def test_first_relocation_derivative_is_explicitly_unmeasured(self):
        c,e,t=fixture();r,s,st=d.case_analysis(c,e,t)
        self.assertIsNone(r[0]['relocation']['controller_velocity_xyz_m']);self.assertIn('NOT_A_MEASURED',r[0]['relocation']['controller_velocity_missing_reason'])
        self.assertEqual(r[1]['relocation']['controller_velocity_xyz_m'],[0.,0.,0.]);self.assertTrue(s['final_relocation_gates']['ready'])

    def test_later_saved_observation_cannot_change_earlier_diagnostic(self):
        c,e,t=fixture();r,_,_=d.case_analysis(c,e,t);changed=deepcopy(e)
        third=next(v for v in changed if v['event']=='STEP_COMPLETE' and v['logical_step']==2)
        third['after']['observation'][0]+=.04
        later,_,_=d.case_analysis(c,changed,t)
        self.assertEqual(r[:2],later[:2]);self.assertNotEqual(r[2]['relocation']['after_gates'],later[2]['relocation']['after_gates'])

    def test_empty_and_zero_length_stages_keep_missing_reasons(self):
        c,e,t=fixture(empty=True);r,s,st=d.case_analysis(c,e,t)
        self.assertEqual(r,[]);self.assertIsNone(s['final_relocation_gates']);self.assertEqual(len(st),8)
        self.assertTrue(all(x['position_error_mean_m'] is None and x['missing_reason'] for x in st))

    def test_independent_full_synthetic_export_audit_disables_main_functions(self):
        c,e,t=fixture();r,s,st=d.case_analysis(c,e,t)
        with patch.object(d,'gates',side_effect=AssertionError),patch.object(d,'case_analysis',side_effect=AssertionError),patch.object(d,'chain',side_effect=AssertionError):
            self.assertGreater(a.audit_case(c,e,r,s,st,t),300)

    def test_cost_decomposition_preserves_failure_penalty_and_known_zero_cost(self):
        c,_,_=fixture();c.update(movement_steps=24,warm_probe_steps=8,deadline_loss=500,success=False)
        direct={**c,'action':'CONTINUE','deadline_loss':100,'success':True}
        p=d.paired_cost([direct,c])[0];self.assertEqual((p['L_move_minus_continue'],p['actual_movement_and_probe_steps'],p['remaining_loss_difference_after_paid_acquisition']),(400,32,368))
        self.assertTrue(p['success_to_failure']);c.update(movement_steps=0,warm_probe_steps=0,boundary_reached=False,deadline_loss=100,success=True)
        p=d.paired_cost([direct,c])[0];self.assertEqual(p['actual_movement_and_probe_steps'],0);self.assertTrue(p['both_ended_before_decision'])


if __name__=='__main__':unittest.main()

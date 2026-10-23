"""Synthetic observations/commands and menu records only; zero fitting or physics."""
from copy import deepcopy
from unittest import TestCase
from unittest.mock import patch
import numpy as np
from src.analysis import latent_response_diagnosis_io_v1 as a,latent_response_diagnosis_math_v1 as m,latent_response_diagnosis_audit_v1 as audit
from src.analysis.latent_response_diagnosis_v1 import main_windows,components
from src.probe.nominal_command_target_v1 import PublicNominalTarget
from src.probe.latent_response_query_v1 import ForecastQuery


def fixture(packet_steps=11):
    entry=3;commands=np.tile(np.array([.25,-.25,0.,0.],np.float32),(entry+packet_steps,1)).tolist();initial=[0.]*39;initial[:3]=[0.,.6,.2];initial[4:7]=[.2,.7,.1]
    p={'schema':'PUBLIC_COMMAND_WITNESS_TRAJECTORY_V1','task':'push-v3','initial_observation':initial,'steps':[]};reference=PublicNominalTarget.initial('push-v3',controlled_reset_declared=True);before=initial
    for i,u in enumerate(commands):
        after=before.copy();after[0]+=.001;after[1]-=.0005;reference=reference.consume(reference.propose(u))
        p['steps'].append({'logical_step':i,'command':u,'observation_before':before,'observation_after':after,'reference_after':reference.to_dict()});before=after
    meta={'schema':'PUBLIC_PACKET_METADATA_V1','entry_at_calls':entry,'packet_commands':np.tile(np.array([.25,-.25,0.,0.],np.float32),(32,1)).tolist(),'reason':'ENDED_DURING_PACKET'}
    case={'split':'TRAIN','task':'push-v3','total_steps':entry+packet_steps,'packet_steps':packet_steps}
    private=[{'label':'INITIAL','at_calls':0,'mocap_pos_oracle':[[0.,.6,.2]]}]+[{'label':'AFTER_STEP','at_calls':i+1,'mocap_pos_oracle':[[.002*(i+1),.6,.2]]} for i in range(entry+packet_steps)]
    return case,p,meta,private


def case_metadata(group=0):return {'split':'TRAIN','group':group,'task':'push-v3','seed':1,'initial_kind':'NOMINAL','context':'UNCHANGED','boundary':16,'packet_kind':'RANDOM32'}


def sample(value=1.):
    return m.metrics(np.full((8,2),value),np.zeros((8,2)),[True]*8,np.zeros((8,2)),np.zeros((8,2)))


def menu(losses=None):
    result={};losses=losses or {}
    for program in a.reference.PROGRAMS:
        loss=losses.get(program,100);result[program]={'group':0,'task':'push-v3','seed':1,'context':'UNCHANGED','planned_boundary':16,
            'success':True,'total_steps':loss,'deadline_loss':loss,'program':program}
    return result


class LatentResponseDiagnosisTests(TestCase):
    def test_config_has_zero_new_physics_fits_and_no_new_population(self):
        c=a.config();self.assertEqual(c['new_control_steps'],0);self.assertEqual(c['new_model_fits'],0);self.assertEqual(c['new_optimizer_updates'],0)
        self.assertEqual(c['each_pass_maximum_new_model_query_forwards'],100464);self.assertEqual(c['expected_prediction_rows_each_pass'],103888)

    def test_known_zero_error(self):
        v=sample(0.);self.assertEqual(v['masked_H8_objective_m2'],0.);self.assertEqual(v['H8_rmse_m'],0.)

    def test_known_constant_error_and_independent_equations(self):
        p=np.full((8,2),.002);y=np.zeros((8,2));mask=[True]*8;z=np.zeros((8,2));v=m.metrics(p,y,mask,z,z)
        self.assertAlmostEqual(v['masked_H8_objective_m2'],.002**2);audit.compare(v,audit.scalar_metrics(p.tolist(),y.tolist(),mask,z.tolist(),z.tolist()))

    def test_coherent_increment_energy_includes_all_cross_terms(self):
        p=np.tile(np.arange(1,9)[:,None]*.001,(1,2));v=m.metrics(p,np.zeros((8,2)),[True]*8,np.zeros((8,2)),np.zeros((8,2)))
        self.assertAlmostEqual(v['increment_diagonal_energy_m2'],8e-6);self.assertAlmostEqual(v['increment_cross_energy_m2'],56e-6);self.assertAlmostEqual(v['terminal_error_m2'],64e-6)

    def test_cancellation_has_negative_cross_energy(self):
        p=np.tile(np.array([1.,-1.]*4)[:,None]*.001,(1,2));v=m.metrics(p,np.zeros((8,2)),[True]*8,np.zeros((8,2)),np.zeros((8,2)))
        self.assertLess(v['increment_cross_energy_m2'],0);self.assertAlmostEqual(v['terminal_error_m2'],v['increment_diagonal_energy_m2']+v['increment_cross_energy_m2'])

    def test_component_norms_cannot_be_added_without_signed_crosses(self):
        p=np.full((8,2),.001);sent=np.full((8,2),.1);native=np.full((8,2),.05);y=np.zeros((8,2));v=m.metrics(p,y,[True]*8,sent,native)
        fields=('model_minus_nominal_m2','nominal_minus_native_m2','native_minus_hand_m2','twice_model_nominal_cross_m2','twice_model_hand_cross_m2','twice_nominal_hand_cross_m2')
        self.assertAlmostEqual(sum(v[k] for k in fields),v['masked_H8_objective_m2']);self.assertGreater(sum(v[k] for k in fields[:3]),100*v['masked_H8_objective_m2'])

    def test_masked_future_placeholders_never_affect_error(self):
        p=np.ones((8,2));y=np.zeros((8,2));mask=[True]*3+[False]*5;v=m.metrics(p,y,mask,np.zeros((8,2)),np.zeros((8,2)));y[3:]=1e30
        self.assertEqual(v,m.metrics(p,y,mask,np.zeros((8,2)),np.zeros((8,2))));self.assertIsNone(v['H8_rmse_m']);self.assertIsNone(v['H8_terminal_error_m2'])

    def test_invalid_noncontiguous_or_empty_actual_masks_rejected(self):
        for mask in ([False]*8,[True,False,True]+[False]*5):
            with self.assertRaises(ValueError):m.metrics(np.ones((8,2)),np.zeros((8,2)),mask,np.zeros((8,2)),np.zeros((8,2)))

    def test_single_step_model_does_not_get_fake_H8_zero(self):
        v=m.metrics([[.001,0]],np.zeros((8,2)),[True]*8,np.zeros((8,2)),np.zeros((8,2)))
        self.assertIsNone(v['masked_H8_objective_m2']);self.assertIsNone(v['H8_rmse_m']);self.assertTrue(all(x is None for x in v['horizon_mse_m2'][1:]))

    def test_nonfinite_prediction_rejected(self):
        with self.assertRaises(ValueError):m.metrics(np.full((8,2),np.nan),np.zeros((8,2)),[True]*8,np.zeros((8,2)),np.zeros((8,2)))

    def test_regime_bins_partition_actual_training_starts(self):
        counts={k:0 for k in a.REGIMES}
        for i in range(25):
            for k in m.regimes(i,'TRAIN'):counts[k]+=1
        self.assertEqual(counts,{'ALL_WINDOWS':25,'ENTRY_ONLY':1,'START_01_08':8,'START_09_16':8,'START_17_24':8})

    def test_empty_late_segment_has_reason_and_none(self):
        rs=m.trajectory_rows(case_metadata(),'SS_SENT',5000,[sample()]*11,None);last=next(r for r in rs if r['regime']=='START_17_24')
        self.assertEqual(last['windows'],0);self.assertIsNone(last['metrics']);self.assertEqual(last['reason'],'NO_ACTUAL_WINDOW_IN_BIN')

    def test_unavailable_software_and_invalid_forecasts_are_distinct(self):
        c=case_metadata()|{'split':'SOFTWARE'};r=m.trajectory_rows(c,'SS_SENT',5000,[],None)[0];self.assertEqual(r['reason'],'NO_MODEL_BY_SOFTWARE_PROTOCOL')
        r=m.trajectory_rows(case_metadata()|{'_diagnostic_missing_reason':'INVALID_SAVED_FORECAST'},'SS_SENT',5000,[],None)[0];self.assertEqual(r['reason'],'INVALID_SAVED_FORECAST')

    def test_short_trajectory_not_outweighed_by_long_trajectory(self):
        arow=m.trajectory_rows(case_metadata(),'SS_SENT',5000,[sample(1.)]*25,None)[0]
        brow=m.trajectory_rows(case_metadata(),'SS_SENT',5000,[sample(3.)],None)[0]
        self.assertAlmostEqual(m.means([arow['metrics'],brow['metrics']])['H1_mse_m2'],5.)

    def test_independent_groups_not_weighted_by_available_case_count(self):
        first=m.trajectory_rows(case_metadata(0),'SS_SENT',5000,[sample(1.)],None)[0];second=m.trajectory_rows(case_metadata(1),'SS_SENT',5000,[sample(3.)],None)[0]
        result=m.grouped([deepcopy(first) for _ in range(5)]+[second])[0];self.assertAlmostEqual(result['metrics']['H1_mse_m2'],5.);audit.compare([result],audit.independent_groups([deepcopy(first) for _ in range(5)]+[second]))

    def test_wholly_missing_group_is_reported_not_zero_filled(self):
        row=m.trajectory_rows(case_metadata(),'SS_SENT',5000,[],None)[0];v=m.grouped([row])[0];self.assertIsNone(v['metrics']);self.assertEqual(v['available_groups'],0);self.assertEqual(v['allocated_trajectories'],1)

    def test_causal_query_does_not_read_future_observation(self):
        c,p,meta,private=fixture();ws,*_=audit.rebuilt_source(c,p,meta,[],private);changed=deepcopy(p);changed['steps'][meta['entry_at_calls']+1]['observation_after'][0]+=.02
        other,*_=audit.rebuilt_source(c,changed,meta,[],private);self.assertEqual(ws[0]['query'],other[0]['query']);self.assertNotEqual(ws[0]['targets'],other[0]['targets'])

    def test_private_native_values_do_not_enter_queries(self):
        c,p,meta,private=fixture();ws,*_=audit.rebuilt_source(c,p,meta,[],private);changed=deepcopy(private)
        for r in changed:r['mocap_pos_oracle'][0][0]+=99.
        other,*_=audit.rebuilt_source(c,p,meta,[],changed);self.assertEqual(ws,other)

    def test_short_actual_training_packet_keeps_masks_and_real_history(self):
        c,p,meta,private=fixture(4);ws,*_=audit.rebuilt_source(c,p,meta,[],private);self.assertEqual(len(ws),4);self.assertEqual(ws[0]['mask'],[True]*4+[False]*4)
        self.assertEqual(ws[-1]['mask'],[True]+[False]*7);self.assertEqual(ws[0]['query']['observations'][0],p['initial_observation'])

    def test_no_oracle_keys_in_rebuilt_query(self):
        c,p,meta,private=fixture();ws,*_=audit.rebuilt_source(c,p,meta,[],private);ForecastQuery.from_dict(ws[0]['query'])
        with self.assertRaises(ValueError):ForecastQuery.from_dict(ws[0]['query']|{'native_target':1})

    def test_CAL_reads_saved_entry_only_without_any_model_forward(self):
        c,p,meta,private=fixture(8);ws,*_=audit.rebuilt_source(c,p,meta,[],private);c['split']='CAL';saved={method:{'valid':True,'displacements':np.zeros((1 if method in a.METHODS[-2:] else 8,2)).tolist()} for method in a.METHODS}
        q=ws[0]['query'];events=[{'agent_event':'FORECAST_RESULT','public_payload':{'result':{'query':q,'query_sha256':a.io.digest(q),'forecasts':saved}}}]
        from src.analysis import latent_response_diagnosis_v1 as main
        with patch.object(main,'predict',side_effect=RuntimeError('CAL may not recompute model')):actual,forecasts=main_windows(c,p,meta,events,{}, {})
        self.assertEqual(len(actual),1);self.assertEqual(forecasts,saved)

    def test_no_C8_external_program_in_same_prefix_oracle(self):
        v=m.menu_unit(menu({'DIRECT_C8':1,'RAW_CONTINUE':100,'LOCAL_PID_KEEP':150}));self.assertEqual(v['oracle_recorded_minimum_loss'],100);self.assertNotIn('DIRECT_C8',v['all_tied_minimizers']);self.assertEqual(v['direct_C8_external_whole_program_loss'],1)

    def test_oracle_preserves_all_ties(self):
        v=m.menu_unit(menu());self.assertEqual(v['all_tied_minimizers'],list(a.MENU));self.assertEqual(v['optimistic_raw_saving'],0);audit.compare(v,audit.independent_menu(menu()))

    def test_full_cost_decomposition_does_not_add_acquisition_twice(self):
        v=m.menu_unit(menu({'RAW_CONTINUE':90,'LOCAL_PID_KEEP':150,'LOCAL_PID_REFERENCE_RESET':130}));d=v['decompositions']['LOCAL_PID_REFERENCE_RESET']
        self.assertEqual(d,{'whole_minus_raw':40,'acquisition_keep_minus_raw':60,'reference_minus_keep':-20})

    def test_early_stop_failure_cost_is_500_not_four(self):
        c=menu();c['LOCAL_PID_REFERENCE_RESET'].update(success=False,total_steps=4,deadline_loss=500);v=m.menu_unit(c);self.assertEqual(v['menu_losses']['LOCAL_PID_REFERENCE_RESET'],500)
        c['LOCAL_PID_REFERENCE_RESET']['deadline_loss']=4
        with self.assertRaises(ValueError):m.menu_unit(c)

    def test_incomplete_program_population_rejected(self):
        v=menu();del v['FIXED_PD_KEEP']
        with self.assertRaises(ValueError):m.menu_unit(v)

    def test_independent_arithmetic_works_with_main_disabled(self):
        with patch.object(m,'metrics',side_effect=RuntimeError('disabled')),patch.object(m,'means',side_effect=RuntimeError('disabled')):
            value=audit.scalar_metrics(np.zeros((8,2)).tolist(),np.zeros((8,2)).tolist(),[True]*8,np.zeros((8,2)).tolist(),np.zeros((8,2)).tolist())
        self.assertEqual(value['H8_rmse_m'],0.)

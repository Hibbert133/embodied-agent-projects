"""Pure arrays, synthetic records and exact arithmetic; no Env, fits or model calls."""
from collections import Counter
from copy import deepcopy
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest,json
from unittest.mock import patch
import numpy as np
from src.analysis import packet_structure_math_v1 as m,packet_structure_independent_v1 as independent,packet_structure_diagnosis_v1 as main,packet_structure_sources_v1 as source
from src.analysis.short_probe_journal_audit_v1 import applied
from src.analysis.native_command_witness_audit_v1 import target


def compare(test,actual,expected):
    for key,v in expected.items():
        if isinstance(v,list):np.testing.assert_allclose(actual[key],[float(x) for x in v],atol=2e-15,rtol=2e-11)
        else:test.assertAlmostEqual(actual[key],float(v),places=16)


def family(length=3,entry=24,split='CAL',amplitude=1.):
    spec=source.original.population(split)[0];out=[];noise=np.zeros((500,3),np.float32);noise[:,0]=np.float32(-.3);noise[:,1]=np.float32(.02)
    fault=dict(matrix_xy=[[1.2,.1],[0.,.8]],bias_xy=[.2,-.1],deadzone_xy=[0.,0.])
    for role,u in zip(source.ROLES,([0.,0.,0.,0.],[amplitude,0.,0.,0.],[-amplitude,0.,0.,0.])):
        before={};after={};packet=[];q=[.499,.6,.2]
        for k in range(length if entry is not None else 0):
            n=entry+k;command=np.asarray(u,np.float32).tolist();actual=applied(command,fault,noise[n]);before[n]=dict(mocap_pos_oracle=[q]);q=target(q,actual)['target'];after[n+1]=dict(mocap_pos_oracle=[q]);obs=[0.]*39;obs[:3]=q
            packet.append(dict(logical_step=n,noise_cursor_after=n+1,command=command,executed_action_oracle=actual,after=dict(observation=obs)))
        rec=None if entry is None else dict(forecasts={},forecast_error=None)
        c=dict(spec,packet_kind=role,total_steps=0 if entry is None else entry+length,entry_at_calls=entry,packet_steps=len(packet),reason='SYNTHETIC_SHORT_PACKET',success_at_response_horizon=False,
            boundary_applied=entry is not None,destination_oracle=fault,forecast_record=rec)
        out.append(dict(case=c,packet=packet,before=before,after=after))
    return out,noise


class StructureTests(unittest.TestCase):
    def test_linear_symmetric_response_has_zero_even_floor(self):
        z=[.2,.7];p=[.21,.72];n=[.19,.68];r=m.response(z,p,n,z,p,n)
        self.assertLess(r['linear_command_class_floor_m2'],1e-30);compare(self,r,independent.observed(z,p,n,z,p,n))
    def test_known_even_response_leaves_exact_representation_floor(self):
        z=[0.,0.];p=[.03,.04];n=p;r=m.saved_error(z,p,n,[[0.,0.]]*3)
        self.assertAlmostEqual(r['saved_pair_mse_m2'],(.03**2+.04**2)/3);self.assertEqual(r['saved_odd_component_error_m2'],0.)
        compare(self,r,independent.prediction(z,p,n,[[0.,0.]]*3))
    def test_odd_error_and_even_error_have_distinct_coefficients(self):
        z=[.2,.7];p=[.25,.73];n=[.19,.69];pred=[[.01,.01],[-.01,-.01],[-.02,-.02]];r=m.saved_error(z,p,n,pred)
        self.assertGreater(r['linear_command_class_floor_m2'],0.);self.assertGreater(r['saved_odd_component_error_m2'],0.);compare(self,r,independent.prediction(z,p,n,pred))
    def test_inconsistent_saved_forecasts_keep_signed_cross_correction(self):
        z=[0.,0.];p=[.1,.1];n=p;pred=[[.1,.1],[.1,.1],[0.,0.]];r=m.saved_error(z,p,n,pred)
        self.assertEqual(r['saved_pair_mse_m2'],0.);self.assertLess(r['saved_nonclass_correction_m2'],0.);compare(self,r,independent.prediction(z,p,n,pred))
    def test_native_and_tracking_even_cross_term_can_cancel(self):
        z=[0.,0.];p=[.1,0.];n=[-.1,0.];r=m.response(z,p,n,z,[.2,0.],[0.,0.])
        self.assertEqual(r['linear_command_class_floor_m2'],0.);self.assertLess(r['native_tracking_cross_m2'],0.);compare(self,r,independent.observed(z,p,n,z,[.2,0.],[0.,0.]))
    def test_common_translation_does_not_change_response_contrasts(self):
        y=np.array([[.2,.7],[.21,.72],[.19,.68]]);n=y+.03;first=m.response(*y,*n);second=m.response(*(y+10),*(n+10))
        for key in first:np.testing.assert_allclose(first[key],second[key],atol=5e-14)
    def test_shared_action_independent_feedback_cancels_at_same_entry(self):
        absolute=np.array([[.3,.7],[.4,.8],[.2,.6]]);shift=np.array([.17,-.23])
        before=absolute[[1,2,2]]-absolute[[0,0,1]];after=(absolute+shift)[[1,2,2]]-(absolute+shift)[[0,0,1]]
        np.testing.assert_allclose(before,after,atol=1e-16)
    def test_action_dependent_feedback_need_not_cancel(self):
        absolute=np.zeros((3,2));changed=absolute.copy();changed[1]=[.1,0.]
        self.assertFalse(np.array_equal(absolute[1]-absolute[0],changed[1]-changed[0]))
    def test_malformed_or_nonfinite_vectors_are_rejected(self):
        for value in ([0.], [0.,float('nan')]):
            with self.subTest(value=value),self.assertRaises(ValueError):m.response(value,[0.,0.],[0.,0.],[0.,0.],[0.,0.],[0.,0.])
    def test_applied_parity_records_small_float32_asymmetry(self):
        u=np.zeros((3,2,4));u[1,:,0]=.4;u[2,:,0]=-.4;u[2,0,0]+=1e-8
        r=m.actuator_parity(u,[0,0,0],[0,1,0]);self.assertGreater(r['applied_even_max_abs_xyz_command'],0.);self.assertEqual(r['native_workspace_clip_axes'],1)
    def test_whole_source_and_all_horizons_are_registered(self):
        c=source.config();self.assertEqual(c['source_executions'],864);self.assertEqual(c['source_families']*len(c['horizons']),4608);self.assertFalse(c['new_collection_unlocked'])
    def test_jsonl_reader_is_plain_utf8_not_gzip(self):
        with TemporaryDirectory() as folder:
            p=Path(folder)/'test.jsonl';p.write_bytes(b'{"h":1}\n{"h":2}\n');self.assertEqual(list(source.plain_rows(p)),[dict(h=1),dict(h=2)])
    def test_blank_jsonl_rows_are_rejected(self):
        with TemporaryDirectory() as folder:
            p=Path(folder)/'test.jsonl';p.write_bytes(b'\n')
            with self.assertRaises(ValueError):list(source.plain_rows(p))


class RecordAndWeightTests(unittest.TestCase):
    def test_no_entry_keeps_all_slots_and_nulls(self):
        trio,_=family(0,None);counts=Counter();register,rows,preds=main.family_values(0,trio,counts)
        self.assertEqual((len(register),len(rows),len(preds)),(3,16,80));self.assertTrue(all(r['response'] is None and r['missing_reason']=='NO_COMMON_PACKET_ENTRY' for r in rows));self.assertTrue(all(p['saved_pair_mse_m2'] is None for p in preds))
    def test_short_actual_sequence_does_not_invent_future(self):
        trio,noise=family(3);counts=Counter()
        with patch.object(source.original,'noise',lambda v:noise):reg,rows,preds=main.family_values(0,trio,counts)
        self.assertEqual(sum(r['available'] for r in rows),3);self.assertFalse(rows[3]['available']);self.assertEqual(counts['saved_packet_actions_checked'],9)
        self.assertEqual(counts['saved_prediction_arithmetic_decompositions'],0);self.assertTrue(all(p['missing_reason']=='NO_SAVED_NUMERIC_PREDICTION' for p in preds[:15]))
    def test_noise_cursor_misalignment_rejected(self):
        trio,noise=family();trio[0]['packet'][0]['noise_cursor_after']+=1
        with patch.object(source.original,'noise',lambda v:noise),self.assertRaises(ValueError):main.family_values(0,trio,Counter())
    def test_preclip_then_noise_order_is_detected(self):
        trio,noise=family();trio[1]['packet'][0]['executed_action_oracle'][0]=float(np.float32(.7))
        with patch.object(source.original,'noise',lambda v:noise),self.assertRaises(ValueError):main.family_values(0,trio,Counter())
    def test_native_target_clip_and_action_clip_are_separate(self):
        trio,noise=family(amplitude=.4);counts=Counter()
        with patch.object(source.original,'noise',lambda v:noise):_,rows,_=main.family_values(0,trio,counts)
        self.assertEqual(rows[0]['actuator']['actuator_final_clip_axes'],0);self.assertGreater(rows[0]['actuator']['native_workspace_clip_axes'],0)
    def test_family_and_group_weights_do_not_reward_longer_records(self):
        rows=[]
        for group,family_id,values in ((0,0,[1.,1.,1.,1.]),(0,1,[3.]),(1,2,[10.])):
            for h,v in enumerate(values,1):
                rows.append(dict(split='QUAL',group=group,task='push-v3',context='UNCHANGED',acquisition_action='MOVE',boundary=16,horizon=h,horizon_band=1,family_index=family_id,available=True,
                    response=dict(linear_command_class_floor_m2=v,native_even_term_m2=0.,tracking_even_term_m2=v,native_tracking_cross_m2=0.)))
        panel=next(p for p in main.summarize(rows) if p['level']==['split']);self.assertEqual(panel['mean']['linear_command_class_floor_m2'],6.)
    def test_unavailable_panel_is_null_not_zero(self):
        row=dict(split='SOFTWARE',group=0,task='push-v3',context='UNCHANGED',acquisition_action='MOVE',boundary=16,horizon=1,horizon_band=1,family_index=0,available=False,response=None)
        panel=main.summarize([row])[0];self.assertIsNone(panel['mean']['linear_command_class_floor_m2']);self.assertEqual(panel['available_groups'],0)
    def test_independent_group_reader_reconstructs_complete_panel_grid(self):
        rows=[]
        for group,family_id,values in ((0,0,[1.,1.,1.]),(0,1,[3.]),(1,2,[10.])):
            for h,v in enumerate(values,1):
                rows.append(dict(split='QUAL',group=group,task='push-v3',context='UNCHANGED',acquisition_action='MOVE',boundary=16,horizon=h,horizon_band=1,family_index=family_id,available=True,
                    response=dict(linear_command_class_floor_m2=v,native_even_term_m2=0.,tracking_even_term_m2=v,native_tracking_cross_m2=0.)))
        with TemporaryDirectory() as folder:
            p=Path(folder)/'panels.json';source.io.write(p,main.summarize(rows));r=independent.verify_panels(p,rows,False)
            self.assertGreater(r['panels'],0);self.assertGreater(r['scalar_means_reconstructed'],0)


if __name__=='__main__':unittest.main()

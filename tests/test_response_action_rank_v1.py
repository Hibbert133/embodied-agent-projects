"""Array-only control interface checks; no environment or fitted models."""
from copy import deepcopy
import unittest
import numpy as np
from src.probe.continuous import StepObservation
from src.probe.operator_identification import identity_controller
from src.probe.linear_command_preflight_v1 import LinearCommandModel
from src.probe.response_action_rank_v1 import RankQuery,RankPlan,RankConsumer
from src.analysis.response_action_rank_audit_v1 import audit_rank


def fixture(sign=1.,weight=.1,base=None):
    states=np.zeros((3,39));states[:,4:7]=[.1,.7,.02];states[:,-3:]=[.2,.8,.1]
    states[:,0]=[0.,.0001,.0003]
    cur=StepObservation(states[-1].tolist(),False,False,False)
    q=RankQuery.create('push-v3',8,cur,states,[.5,0.,0.,0.],identity_controller() if base is None else base,weight)
    c=np.zeros((21,2));c[10,0]=sign*.002;c[11,1]=.002
    model=LinearCommandModel('push-v3','F20',np.zeros(20),np.ones(20),c)
    return q,('FEEDBACK8/push-v3/LINEAR_F20','a'*64,model),states


class RankKernelTests(unittest.TestCase):
    def test_model_predictions_change_actual_saved_choice(self):
        a,ma,_=fixture(1);b,mb,_=fixture(-1)
        pa=RankPlan.build(a,'F20_RANK',ma);pb=RankPlan.build(b,'F20_RANK',mb)
        self.assertEqual(pa.numbers()['selected_action_id'],'X_PLUS');self.assertEqual(pb.numbers()['selected_action_id'],'X_MINUS')
        self.assertNotEqual(RankConsumer(pa).consume(a,492)['command'],RankConsumer(pb).consume(b,492)['command'])
    def test_known_scores_have_metre_squared_units(self):
        q,m,_=fixture();p=RankPlan.build(q,'F20_RANK',m);row=p.numbers()['candidates'][1]
        self.assertAlmostEqual(row['tracking_squared_m2'],(.0015-.005)**2)
        self.assertAlmostEqual(row['regularization_m2'],.1*.01**2*.25**2)
    def test_regularization_changes_selection_without_changing_policy(self):
        q,m,_=fixture(weight=.1);a=RankPlan.build(q,'F20_RANK',m)
        q2,m2,_=fixture(weight=10.);b=RankPlan.build(q2,'F20_RANK',m2)
        self.assertEqual(a.numbers()['selected_action_id'],'X_PLUS');self.assertEqual(b.numbers()['selected_action_id'],'BASELINE')
        self.assertEqual(q.raw_policy,q2.raw_policy)
    def test_same_candidate_interface_and_exact_tie_keep_baseline(self):
        q,_,_=fixture();p=RankPlan.build(q,'KINEMATIC_RANK');self.assertEqual(p.numbers()['selected_action_id'],'BASELINE')
        self.assertEqual(len(p.numbers()['candidates']),5)
    def test_all_commands_float32_before_prediction_and_keep_z_grip(self):
        q,m,_=fixture();p=RankPlan.build(q,'F20_RANK',m)
        for row in p.numbers()['candidates']:
            u=row['sent_command'];self.assertEqual(tuple(np.asarray(u,np.float32).astype(float)),tuple(u));self.assertEqual(u[2:],[0.,0.])
    def test_clipped_duplicate_labels_are_preserved(self):
        q,_,_=fixture(base={'source':'ESTIMATED_AFFINE','matrix_xy':[[1.,0.],[0.,1.]],'offset':[.5,0.,0.,0.]})
        p=RankPlan.build(q,'KINEMATIC_RANK');r=p.numbers()['candidates'];self.assertEqual(r[0]['sent_command'],r[1]['sent_command']);self.assertEqual(len(r),5)
    def test_f20_input_is_actual_sent_command_not_inverse_or_forward_fault_map(self):
        q,m,_=fixture(base={'source':'ESTIMATED_AFFINE','matrix_xy':[[.5,0.],[0.,.5]],'offset':[0.,0.,0.,0.]})
        p=RankPlan.build(q,'F20_RANK',m)
        self.assertEqual(q.baseline()[0],.25);self.assertAlmostEqual(p.predictions[0][0],.0005)
        self.assertEqual(p.numbers()['reference_displacement_xy_m'],[.005,0.])
    def test_saved_payload_is_recomputed_and_rejects_tampering(self):
        q,m,_=fixture();p=RankPlan.build(q,'F20_RANK',m);v=p.to_dict();self.assertEqual(RankPlan.from_dict(v,m),p)
        for path in ('choice','prediction','score','oracle'):
            x=deepcopy(v)
            if path=='choice':x['numbers']['selected_action_id']='BASELINE'
            elif path=='prediction':x['predictions_xy_m'][0][0]+=.1
            elif path=='score':x['numbers']['candidates'][0]['score_m2']+=1
            else:x['true_fault']={}
            with self.assertRaises(ValueError):RankPlan.from_dict(x,m)
    def test_current_query_rejects_unknown_nested_private_future_fields(self):
        q,_,_=fixture()
        for key in ('seed','future_outcome','executed_action_oracle','noise','destination'):
            x=q.to_dict();x[key]=0
            with self.assertRaises(ValueError):RankQuery.from_dict(x)
        x=q.to_dict();x['controller']['oracle']=1
        with self.assertRaises(ValueError):RankQuery.from_dict(x)
    def test_real_history_and_no_future_timestamps(self):
        q,_,_=fixture();x=q.to_dict();x['observation_steps'][-1]+=1
        with self.assertRaises(ValueError):RankQuery.from_dict(x)
        x=q.to_dict();x['observations'][-1][0]+=1
        with self.assertRaises(ValueError):RankQuery.from_dict(x)
        x=q.to_dict();x['observations']=x['observations'][-2:]
        with self.assertRaises(ValueError):RankQuery.from_dict(x)
    def test_immutable_snapshot_not_alias(self):
        q,m,states=fixture();p=RankPlan.build(q,'F20_RANK',m);v=p.to_dict();states[:]=900
        self.assertEqual(p.to_dict(),v)
    def test_budget_staleness_reuse_and_ended_rejected(self):
        q,m,_=fixture();p=RankPlan.build(q,'F20_RANK',m)
        with self.assertRaises(ValueError):RankConsumer(p).consume(q,0)
        c=RankConsumer(p);c.consume(q,492)
        with self.assertRaises(ValueError):c.consume(q,492)
        other,_,_=fixture(weight=1.)
        with self.assertRaises(ValueError):RankConsumer(p).consume(other,492)
        x=q.to_dict();x['current']['success']=True
        with self.assertRaises(ValueError):RankQuery.from_dict(x)
    def test_wrong_model_kind_task_scale_and_descriptor_rejected(self):
        q,m,_=fixture()
        with self.assertRaises(ValueError):RankPlan.build(q,'KINEMATIC_RANK',m)
        with self.assertRaises(ValueError):RankPlan.build(q,'F20_RANK',None)
        with self.assertRaises(ValueError):RankPlan.build(q,'F20_RANK',('BALANCED8/push-v3/LINEAR_F20',m[1],m[2]))
    def test_independent_raw_coefficient_audit_and_command_override(self):
        q,m,_=fixture();p=RankPlan.build(q,'F20_RANK',m);spec={'task':q.task,'style':'F20_RANK','regularization_weight':q.weight}
        # Supply the actual full prefix as a history list; only its last three
        # observations are queried, without fabricating displacements in a run.
        history=[q.observations[0]]*6+list(q.observations)
        audit_rank(p.to_dict(),p.numbers()['selected_command'],spec,q.to_dict()['current'],[list(v) for v in history],list(q.raw_policy),m)
        with self.assertRaises(ValueError):audit_rank(p.to_dict(),[0.,0.,0.,0.],spec,q.to_dict()['current'],[list(v) for v in history],list(q.raw_policy),m)


if __name__=='__main__':unittest.main()

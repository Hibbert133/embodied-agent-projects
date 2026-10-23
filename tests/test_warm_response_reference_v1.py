"""Algebraic fixtures only; no MetaWorld, scientific seed allocation or API."""
from copy import deepcopy
from dataclasses import asdict
import unittest

import numpy as np

from src.probe import warm_response_reference_v1 as warm
from src.probe.cold_start_response import ColdPrefix, clipped_normal_mean
from src.probe.physical_reprobe_v1 import PROGRAM, WarmWindow


def history(rng, x=None):
    current=np.array([0.,.6,.25])+rng.uniform(-.009,.009,3)
    if x is not None:current[0]=x
    positions=[current]
    for _ in range(3):positions.insert(0,positions[0]-rng.uniform(-.001,.001,3))
    rows=[]
    for pos in positions:
        obs=np.zeros(39);obs[:3]=pos;obs[4:7]=[0.,.85,.02];rows.append(tuple(float(v) for v in obs))
    return tuple(rows)


def truth():
    impulse=np.eye(16)*.008
    for t in range(8):
        impulse[2*t,2*t+1]=.0005;impulse[2*t+1,2*t]=-.0004
        if t:impulse[2*t:2*t+2,2*t-2:2*t]=np.eye(2)*.003
    drift=np.zeros((16,12));drift[::2,0]=.12;drift[1::2,1]=-.10
    drift[::2,3]=.06;drift[1::2,4]=.04
    return impulse,impulse@drift


def observations(entry,commands,parameters=None,noise=None):
    impulse,initial_response=truth()
    effective=np.array(commands)[:,:2]
    if parameters is not None:effective=np.c_[effective,np.ones(8)]@np.array(parameters).reshape(2,3).T
    delta=(impulse@clipped_normal_mean(effective)[0].ravel()+initial_response@warm.entry_features(entry)).reshape(8,2)
    if noise is not None:delta+=noise
    xyz=np.array(entry[-1]);rows=[]
    for move in delta:
        xyz=xyz.copy();xyz[:2]+=move;rows.append(tuple(float(v) for v in xyz))
    return tuple(rows)


def training(*,count=96,confounded=False,fixed=False):
    rng=np.random.default_rng(601)
    rows=[]
    for _ in range(count):
        commands=np.c_[rng.uniform(-.8,.8,(8,2)),np.zeros((8,2))] if not fixed else np.array(PROGRAM)
        tied=clipped_normal_mean(commands[:,:2])[0][0,0]*.01
        if confounded=="near":tied+=rng.normal(0,1e-12)
        entry=history(rng,x=tied if confounded else None)
        commands=tuple(tuple(v) for v in commands)
        rows.append(warm.NominalWarmTrajectory("push-v3",30,entry,commands,
            observations(entry,commands,noise=rng.normal(0,1e-6,(8,2)))))
    return rows


class WarmResponseReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.samples=training();cls.model=warm.fit_response(cls.samples,"push-v3")
        cls.ablation=warm.fit_response(cls.samples,"push-v3",history_conditioned=False)
        cls.parameters=np.array([[1.15,.12,.13],[-.08,.91,-.09]])
        entry=history(np.random.default_rng(987),x=.008)
        cls.window=WarmWindow("push-v3",50,entry,PROGRAM,observations(entry,PROGRAM,cls.parameters))

    def test_independent_held_entry_history_recovers_known_operator(self):
        fitted=warm.infer_operator(self.model,self.window)
        self.assertTrue(fitted["valid"]);self.assertEqual(fitted["response_design_rank"],6)
        np.testing.assert_allclose(fitted["matrix_xy"],self.parameters[:,:2],atol=2e-3,rtol=0)
        np.testing.assert_allclose(fitted["bias_xy"],self.parameters[:,2],atol=2e-3,rtol=0)
        self.assertFalse(fitted["physical_response_qualified"]);self.assertFalse(fitted["probability_guarantee"])

    def test_same_data_history_ablation_exposes_initial_motion_bias(self):
        conditioned=warm.infer_operator(self.model,self.window);ablated=warm.infer_operator(self.ablation,self.window)
        error=lambda r:np.linalg.norm(np.array(r["bias_xy"])-self.parameters[:,2])
        self.assertGreater(error(ablated),.03);self.assertLess(error(conditioned),error(ablated)/20)
        np.testing.assert_array_equal(self.ablation["history_response"],np.zeros((16,12)))

    def test_real_entry_history_affects_fit_without_fabricated_zero_motion(self):
        altered=asdict(self.window)
        altered["entry_history"]=tuple(altered["entry_history"][-1] for _ in range(4))
        no_motion=warm.infer_operator(self.model,WarmWindow(**altered))
        original=warm.infer_operator(self.model,self.window)
        self.assertGreater(np.linalg.norm(np.array(no_motion["bias_xy"])-original["bias_xy"]),.001)

    def test_analytic_jacobian_matches_clipped_mean_finite_difference(self):
        problem=warm.WarmResponseProblem(self.model,self.window)
        p=np.array([1.9,.15,.29,-.1,1.8,-.29]);eps=1e-6
        actual=problem.predict(p,jacobian=True)[1]
        numeric=np.column_stack([(problem.predict(p+eps*np.eye(6)[i])-problem.predict(p-eps*np.eye(6)[i]))/(2*eps) for i in range(6)])
        np.testing.assert_allclose(actual,numeric,atol=1e-10,rtol=1e-7)

    def test_causal_impulse_and_zero_ablation_coefficients_are_enforced(self):
        model=deepcopy(self.model);model["impulse"][0][2]=1e-30
        with self.assertRaises(ValueError):warm.validate_model(model)
        model=deepcopy(self.ablation);model["history_response"][0][0]=1e-30
        with self.assertRaises(ValueError):warm.validate_model(model)

    def test_repeated_probes_do_not_identify_nominal_causal_response(self):
        with self.assertRaisesRegex(ValueError,"repeated fixed probes"):
            warm.fit_response(training(fixed=True),"push-v3")

    def test_input_history_confounding_rejected_despite_input_rank(self):
        samples=training(confounded=True)
        inputs=np.array([np.array(s.commands)[:,:2].ravel() for s in samples])
        self.assertEqual(np.linalg.matrix_rank(np.c_[np.ones(len(samples)),inputs]),17)
        for sample in (samples,training(confounded="near")):
            with self.assertRaisesRegex(ValueError,"confounded"):
                warm.fit_response(sample,"push-v3")

    def test_rank_deficient_learned_response_stops_before_optimizer(self):
        model=deepcopy(self.model)
        for row in model["impulse"]:
            for index in range(1,16,2):row[index]=0.
        result=warm.infer_operator(model,self.window)
        self.assertFalse(result["valid"]);self.assertEqual(result["nfev"],0)
        self.assertEqual(result["reason"],"INSUFFICIENT_LEARNED_RESPONSE_SUPPORT")

    def test_training_and_inference_types_cannot_substitute_for_each_other(self):
        with self.assertRaises(ValueError):warm.fit_response([self.window]*96,"push-v3")
        with self.assertRaises(ValueError):warm.infer_operator(self.model,self.samples[0])
        cold=ColdPrefix("push-v3",self.window.entry_history[-1],PROGRAM,self.window.observations,True)
        with self.assertRaises(ValueError):warm.infer_operator(self.model,cold)
        with self.assertRaises(ValueError):warm.fit_response(self.samples[:63],"push-v3")
        with self.assertRaises(ValueError):warm.fit_response(self.samples,"reach-v3")

    def test_private_fields_qualification_labels_and_invalid_scope_rejected(self):
        for field in ("seed","fault_oracle","executed_action_oracle","rng","future_result"):
            data=asdict(self.samples[0]);data[field]={}
            with self.assertRaises(ValueError):warm.NominalWarmTrajectory.from_mapping(data)
        data=asdict(self.samples[0]);data["split"]="QUALIFY"
        with self.assertRaises(ValueError):warm.NominalWarmTrajectory.from_mapping(data)
        for field,value in (("physical_response_qualified",True),("sigma",True),("training_input_rank",True),
                            ("training_conditional_input_rank",15),("training_joint_rmse_m",float("nan"))):
            model=deepcopy(self.model);model[field]=value
            with self.assertRaises(ValueError):warm.validate_model(model)
        model=deepcopy(self.model);model["covariance"][0][0]=-1
        with self.assertRaises(ValueError):warm.validate_model(model)
        data=asdict(self.samples[0]);data["observations"]=list(data["observations"])
        obs=list(data["observations"][0]);obs[2]=.1;data["observations"][0]=obs
        with self.assertRaises(ValueError):warm.NominalWarmTrajectory.from_mapping(data)

    def test_fit_is_read_only_and_serializable(self):
        import json
        model=deepcopy(self.model);window=deepcopy(self.window)
        result=warm.infer_operator(model,window)
        self.assertEqual(model,self.model);self.assertEqual(window,self.window)
        json.dumps(result,allow_nan=False);json.dumps(model,allow_nan=False)

    def test_stale_relocation_can_block_before_any_new_measurement(self):
        from docs.paper.check_relocation_stale_equilibrium_20261019 import run_case
        stale=run_case();fresh=run_case(fresh_correction=True)
        self.assertEqual(stale["result"]["reason"],"ANCHOR_NOT_REACHED")
        self.assertEqual((stale["synthetic_callback_steps"],stale["result"]["probe_steps"]),(64,0))
        self.assertTrue(all(a[:3]==[0.,0.,0.] for a in stale["actual_actions"]))
        self.assertEqual(fresh["result"]["reason"],"COMPLETE_UNQUALIFIED")
        self.assertEqual(stale["new_metaworld_steps"]+fresh["new_metaworld_steps"],0)


if __name__ == "__main__":unittest.main()

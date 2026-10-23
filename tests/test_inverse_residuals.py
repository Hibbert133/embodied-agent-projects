from dataclasses import replace
import unittest
import numpy as np

from src.analysis.inverse_residuals import OracleActuation, decompose_oracle_prefix
from src.probe.continuation_selector import ContinuationEvidence
from src.probe.forward_prediction import ForwardQuery
from src.probe.operator_identification import ForwardOperatorProblem, OperatorSample
from tests.test_acquisition_value import model


def block(noise=0.,mismatch=0.,constant=False):
    oracle=OracleActuation(((.9,.1),(-.05,1.1)),(.05,-.03))
    commands=[(-.4,0.,0.,0.)]*2+[(0.,.4,0.,0.)]*2+[(0.,-.4,0.,0.)]*2
    if constant: commands=[(.4,0.,0.,0.)]*6
    rng=np.random.default_rng(12); samples=[]; actions=[]
    for i,command in enumerate(commands,3):
        sent=np.asarray(command,np.float32); actual=np.asarray(oracle.noiseless_host_action(sent),np.float32)
        actual[:3]+=rng.normal(0,noise,3).astype(np.float32); actual=np.clip(actual,-1,1)
        target=np.array((.006*float(actual[0]),.008*float(actual[1])))
        target+=mismatch*np.array((sent[0]+.2*sent[1]+.1,-.3*sent[0]+sent[1]-.2))
        query=ForwardQuery((0.,)*39,(0.,)*3,(0.,)*3,tuple(sent))
        samples.append(OperatorSample(i,query,tuple(target))); actions.append(actual.tolist())
    problem=ForwardOperatorProblem(model(),samples)
    saved=problem.linear_start() if not constant else oracle.host_parameters+np.array((.1,0.,-.04,0.,.2,0.))
    return oracle,tuple(samples),actions,saved


class InverseResidualTest(unittest.TestCase):
    def test_exact_reference_and_no_noise_have_no_applied_input_residual(self):
        oracle,samples,actions,_=block()
        result=decompose_oracle_prefix(model(),samples,actions,oracle,oracle.host_parameters)
        self.assertAlmostEqual(result["component_mse"]["applied_input_prediction_residual"],0.,places=20)
        self.assertEqual(result["component_mse"]["propagated_input_noise"],0.)
        self.assertEqual(result["scaled_parameter_error_norm"],0.)
        self.assertFalse(result["controller_returned"])

    def test_known_input_noise_and_forward_mismatch_remain_separate(self):
        oracle,samples,actions,saved=block(noise=.015,mismatch=.0007)
        result=decompose_oracle_prefix(model(),samples,actions,oracle,saved)
        self.assertGreater(result["component_mse"]["applied_input_prediction_residual"],0.)
        self.assertGreater(result["component_mse"]["propagated_input_noise"],0.)
        total=sum(result["component_mse"].values())+sum(result["cross_mse"].values())
        self.assertAlmostEqual(total,result["residual_rmse_m"]**2,places=18)
        np.testing.assert_allclose(sum(np.asarray(v) for v in result["parameter_components"].values()),result["parameter_error"],rtol=0,atol=1e-10)
        self.assertAlmostEqual(sum(result["signed_scaled_error_contributions"].values()),result["scaled_parameter_error_norm"],places=10)

    def test_clipping_and_bound_active_fit_require_the_fit_residual_adjustment(self):
        oracle,samples,actions,_=block(noise=.02,mismatch=.0002)
        saved=np.array((2.,1.,.3,-1.,1.8,-.3))
        result=decompose_oracle_prefix(model(),samples,actions,oracle,saved)
        self.assertTrue(result["saved_parameter_bound_active"])
        self.assertGreater(result["saved_noiseless_xy_clipped_samples"],0)
        self.assertGreater(np.linalg.norm(result["parameter_components"]["fit_residual_adjustment"]),0.)
        self.assertLess(result["identity_errors"]["parameter_max_abs"],1e-8)

    def test_unidentified_parameter_difference_is_retained_in_nullspace(self):
        oracle,samples,actions,saved=block(constant=True)
        result=decompose_oracle_prefix(model(),samples,actions,oracle,saved)
        self.assertLess(result["secant_rank"],6)
        self.assertGreater(np.linalg.norm(result["parameter_components"]["secant_nullspace"]),.1)
        self.assertLess(result["identity_errors"]["parameter_max_abs"],1e-8)

    def test_privileged_diagnostic_cannot_be_loaded_as_agent_evidence(self):
        oracle,samples,actions,saved=block(noise=.01)
        result=decompose_oracle_prefix(model(),samples,actions,oracle,saved)
        with self.assertRaises(ValueError): ContinuationEvidence.from_dict(result)
        with self.assertRaises(ValueError): decompose_oracle_prefix(model(),samples,actions,{"matrix_xy":oracle.matrix_xy},saved)
        with self.assertRaises(ValueError): decompose_oracle_prefix({**model(),"method":"QUADRATIC_STATE"},samples,actions,oracle,saved)

    def test_missing_actions_reordered_history_and_changed_gripper_are_rejected(self):
        oracle,samples,actions,saved=block()
        with self.assertRaises(ValueError): decompose_oracle_prefix(model(),samples,actions[:-1],oracle,saved)
        with self.assertRaises(ValueError): decompose_oracle_prefix(model(),samples[::-1],actions,oracle,saved)
        changed=np.asarray(actions); changed[0,3]=1.
        with self.assertRaises(ValueError): decompose_oracle_prefix(model(),samples,changed,oracle,saved)
        with self.assertRaises(ValueError): decompose_oracle_prefix(model(),samples,actions,oracle,(3.,0.,0.,0.,1.,0.))

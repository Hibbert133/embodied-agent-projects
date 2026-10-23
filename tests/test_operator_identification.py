import copy
import json
from dataclasses import replace
import unittest
import numpy as np
from src.probe.continuous import ContinuousTransition,symmetric_program
from src.probe.forward_prediction import ForwardQuery,Predictors
from src.probe.operator_identification import OperatorSample,ForwardOperatorProblem,visible_samples,infer_operator,affine_controller,encode_controller,identity_controller
from src.operator_perturbations_v1 import AffineNoisePerturbation


def model(kind):
    size=10 if kind=="LINEAR_ARX" else 20;coefficient=np.zeros((11 if size==10 else 231,2))
    coefficient[1 if size==10 else 4,0]=.5;coefficient[2 if size==10 else 5,1]=.5
    coefficient[7 if size==10 else 10,0]=.006;coefficient[8 if size==10 else 11,1]=.008
    if size==20:
        a,b=np.triu_indices(20);index=next(i for i,pair in enumerate(zip(a,b),21) if pair==(9,9));coefficient[index,0]=.001
    return {"method":kind,"training_samples":100,"mean":[0.]*size,"scale":[1.]*size,
        "physical_response_qualified":False,"probability_guarantee":False,"coefficients":coefficient.tolist(),
        "ridge":.001,"feature_count":len(coefficient),"training_rmse":0.}


def generated_samples(kind,parameters):
    rng=np.random.default_rng(11);samples=[];empty=(0.,)*39
    for step,sent in enumerate(symmetric_program(),3):
        query=ForwardQuery(empty,tuple(rng.normal(0,.001,3)),tuple(rng.normal(0,.001,3)),sent)
        samples.append(OperatorSample(step,query,(0.,0.)))
    problem=ForwardOperatorProblem(model(kind),samples);targets=problem.predictions(np.array(parameters).ravel())
    return tuple(replace(s,displacement=tuple(y)) for s,y in zip(samples,targets))


class OperatorIdentificationTest(unittest.TestCase):
    def test_composed_predictions_match_independent_nominal_equations(self):
        parameters=np.array([[-.8,.2,0.],[.15,.9,-.198]])
        for kind in ("LINEAR_ARX","QUADRATIC_STATE"):
            samples=generated_samples(kind,parameters);problem=ForwardOperatorProblem(model(kind),samples);expected=[]
            for s in samples:
                effective=np.clip(parameters@np.array([*s.query.command[:2],1.]),-1,1)
                expected.append(.5*np.array(s.query.last_displacement[:2])+np.array([.006*effective[0]+(.001*effective[0]**2 if kind=="QUADRATIC_STATE" else 0),.008*effective[1]]))
            np.testing.assert_allclose(problem.predictions(parameters.ravel()),expected,atol=1e-14)

    def test_linear_fit_recovers_unknown_general_affine_from_visible_data(self):
        parameters=np.array([[-.8,.2,0.],[.15,.9,-.198]])
        samples=generated_samples("LINEAR_ARX",parameters);fit=infer_operator(model("LINEAR_ARX"),samples)
        self.assertTrue(fit["valid"]);np.testing.assert_allclose(np.column_stack((fit["matrix_xy"],fit["bias_xy"])),parameters,atol=1e-12)
        self.assertFalse(fit["physical_response_qualified"])

    def test_quadratic_fit_and_analytic_jacobian_without_true_parameter_argument(self):
        parameters=np.array([[.75,.25,.14],[-.15,1.2,-.14]])
        samples=generated_samples("QUADRATIC_STATE",parameters);problem=ForwardOperatorProblem(model("QUADRATIC_STATE"),samples)
        p=np.array([[.8,.1,.1],[.1,1.,-.1]]).ravel();epsilon=1e-6
        numerical=np.column_stack([(problem.residual(p+epsilon*np.eye(6)[i])-problem.residual(p-epsilon*np.eye(6)[i]))/(2*epsilon) for i in range(6)])
        np.testing.assert_allclose(problem.jacobian(p),numerical,rtol=1e-7,atol=1e-8)
        fit=infer_operator(model("QUADRATIC_STATE"),samples);self.assertTrue(fit["valid"])
        np.testing.assert_allclose(np.column_stack((fit["matrix_xy"],fit["bias_xy"])),parameters,atol=1e-7)
        self.assertEqual(len(fit["optimizer_trials"]),4)
        with self.assertRaises(TypeError):infer_operator(model("QUADRATIC_STATE"),samples,true_operator=parameters)

    def test_warmup_continuity_unknown_fields_and_incomplete_design_reject(self):
        position=(0.,)*39;transitions=[]
        for index,sent in enumerate(symmetric_program(steps_per_direction=2),1):
            after=(.001*index,)+(0.,)*38;transitions.append(ContinuousTransition(sent,position,after));position=after
        samples=visible_samples(transitions);self.assertEqual((len(samples),samples[0].step),(6,3))
        bad=list(transitions);bad[3]=replace(bad[3],before=(9.,)*39)
        with self.assertRaisesRegex(ValueError,"continuity"):visible_samples(bad)
        with self.assertRaisesRegex(ValueError,"visible"):infer_operator(model("LINEAR_ARX"),[{"operator_oracle":[]}])
        poisoned=copy.deepcopy(model("LINEAR_ARX"));poisoned["true_operator"]=[]
        with self.assertRaisesRegex(ValueError,"registered"):infer_operator(poisoned,samples)
        self.assertEqual(infer_operator(model("LINEAR_ARX"),samples[:5])["reason"],"INSUFFICIENT_SAMPLES")
        fixed=tuple(replace(s,query=replace(s.query,command=(.2,0.,0.,0.))) for s in samples)
        self.assertFalse(infer_operator(model("LINEAR_ARX"),fixed)["valid"])
        empty=tuple(replace(s,query=replace(s.query,command=(0.,)*4)) for s in samples)
        json.dumps(infer_operator(model("LINEAR_ARX"),empty),allow_nan=False)

    def test_saved_correction_changes_executed_input_and_clips_common_interface(self):
        raw=(.2,-.1,.8,1.)
        self.assertFalse(np.array_equal(encode_controller(identity_controller(),raw),encode_controller(affine_controller([[0.,-1.],[1.,0.]],[.1,-.1]),raw)))
        controller=affine_controller([[.25,0.],[0.,.25]],[.3,-.3]);sent=encode_controller(controller,(1.,-1.,2.,-2.))
        self.assertTrue(np.all(np.abs(sent)<=1));np.testing.assert_array_equal(sent[2:],[1.,-1.])
        poisoned=identity_controller();poisoned["future_success"]=True
        with self.assertRaisesRegex(ValueError,"schema"):encode_controller(poisoned,raw)

    def test_evaluator_injection_preserves_noise_stream_and_gripper(self):
        fault=AffineNoisePerturbation([[0.,-1.],[1.,0.]],[.1,-.1]);fault.reset(71)
        rng=np.random.default_rng(71);noise=rng.normal(0,.05,3).astype(np.float32);sent=np.array([.2,.1,.3,.7],dtype=np.float32)
        expected=sent.copy();expected[:2]=np.array([[0.,-1.],[1.,0.]],dtype=np.float32)@sent[:2]+np.array([.1,-.1],dtype=np.float32);expected[:3]+=noise
        np.testing.assert_array_equal(fault.apply(sent),expected);np.testing.assert_array_equal(sent,[np.float32(.2),np.float32(.1),np.float32(.3),np.float32(.7)])


if __name__=="__main__":unittest.main()

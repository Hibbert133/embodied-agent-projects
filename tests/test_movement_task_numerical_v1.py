from copy import deepcopy
import unittest
from unittest.mock import patch
import numpy as np

from src.analysis.movement_task_numerical_v1 import check_fit
from src.probe.movement_history_reference_v1 import estimate_movement
from src.probe.movement_history_reference_v1 import MovementHistoryV1, MovementTransitionV1
from src.probe.continuous import StepObservation
from tests.test_movement_history_reference_v1 import synthetic_history
from tests.test_operator_identification import model


class MovementTaskNumericalTests(unittest.TestCase):
    def test_independent_reconstruction_uses_all_responses_and_no_production_fitter(self):
        history, _ = synthetic_history();nominal = model("LINEAR_ARX")
        result = estimate_movement(nominal, history)
        with patch("src.probe.operator_identification.infer_operator", side_effect=AssertionError("no production fit")), patch(
                "src.probe.movement_history_reference_v1.operator_samples", side_effect=AssertionError("no production samples")), patch(
                "src.probe.operator_identification.ForwardOperatorProblem", side_effect=AssertionError("no production forward problem")):
            checked = check_fit(nominal, history.to_dict(), result)
        self.assertTrue(checked["valid"]);self.assertEqual(checked["responses"],12)

    def test_real_short_and_unexcited_inputs_keep_rejections_and_zero_optimizer_cost(self):
        for history in (synthetic_history(count=5)[0], synthetic_history(fixed=True)[0]):
            nominal = model("LINEAR_ARX");result = estimate_movement(nominal, history)
            checked = check_fit(nominal, history.to_dict(), result)
            self.assertFalse(checked["valid"]);self.assertEqual(checked["audit_nfev"],0)

    def test_changed_parameters_trials_sources_and_discarded_response_are_rejected(self):
        history, _ = synthetic_history();nominal = model("LINEAR_ARX");original = estimate_movement(nominal, history)
        for mode in ("matrix","bias","residual","sample","model","history","cost","trial"):
            estimate = deepcopy(original)
            if mode == "matrix":estimate["fit"]["matrix_xy"][0][0] += .01
            elif mode == "bias":estimate["fit"]["bias_xy"][1] += .01
            elif mode == "residual":estimate["fit"]["residual_rmse_m"] += .01
            elif mode == "sample":estimate["fit"]["sample_digest"] = "0"*64
            elif mode in ("model","history"):estimate[mode+"_sha256"] = "0"*64
            elif mode == "cost":estimate["optimizer_nfev"] += 1
            else:estimate["fit"]["optimizer_trials"][0]["parameters"][0] += .01
            with self.subTest(mode=mode), self.assertRaises(ValueError):check_fit(nominal, history.to_dict(), estimate)

    def test_saturated_noisy_responses_check_bounded_nonlinear_refinement(self):
        empty,_=synthetic_history(count=0);context=empty.context;rows=[]
        current=context[-1];velocity=np.array(current.observation[:2])-context[-2].observation[:2]
        actual=np.array([[1.4,.2,.1],[-.15,1.2,-.05]])
        program=((1.,1.),(-1.,-1.),(.2,-.3),(-.4,.2),(.5,.5),(-.2,-.6))
        for i in range(30):
            command=(*program[i%len(program)],.12,-1.)
            effective=np.clip(actual@np.array([*command[:2],1.]),-1.,1.)
            velocity=.5*velocity+np.array([.006,.008])*effective+1e-6*np.array([np.sin(i),np.cos(i)])
            position=np.array(current.observation);position[:2]+=velocity
            after=StepObservation(position,False,False,False)
            rows.append(MovementTransitionV1(17+i,command,current,after));current=after
        history=MovementHistoryV1("push-v3",16,46,context,tuple(rows));nominal=model("LINEAR_ARX")
        result=estimate_movement(nominal,history)
        self.assertTrue(result["fit"]["valid"]);self.assertGreater(result["optimizer_nfev"],1)
        checked=check_fit(nominal,history.to_dict(),result)
        self.assertTrue(checked["valid"]);self.assertGreater(checked["audit_nfev"],1)


if __name__ == "__main__":unittest.main()

"""Independent numerical audit checks on arrays; no world or fitting."""
import unittest
import numpy as np
from tests.test_passive_response_diagnostic_v1 import sequence
from src.analysis.passive_response_diagnostic_v1 import forecast_batch
from src.analysis.task_passive_diagnosis_audit_v1 import independent_forecasts


class IndependentResponseAuditTests(unittest.TestCase):
    def test_full_four_channel_increment_and_constant_bias_arithmetic(self):
        s,u,bank,_=sequence(full=True);target,pred=forecast_batch(s,u,bank);actual=independent_forecasts(s,u,bank)
        for k,v in pred.items():np.testing.assert_allclose(actual[k],np.mean((v-target)**2,axis=1),rtol=1e-10,atol=1e-18)
    def test_variable_bias_is_not_mistaken_for_a_correct_model(self):
        s,u,bank,_=sequence(vary=True);actual=independent_forecasts(s,u,bank)
        np.testing.assert_allclose(actual['SYNTHETIC/F20/LAST_RESIDUAL'],np.full(len(u)-3,.0001**2/2),atol=1e-19)
    def test_changed_future_does_not_rewrite_prior_prediction_errors(self):
        s,u,bank,_=sequence();a=independent_forecasts(s,u,bank);s[8:]+=20.;u[8:]*=-1.;b=independent_forecasts(s,u,bank)
        for k in a:np.testing.assert_array_equal(a[k][:4],b[k][:4])


if __name__=='__main__':unittest.main()

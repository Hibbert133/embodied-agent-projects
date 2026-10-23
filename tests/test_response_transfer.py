from fractions import Fraction
import unittest
from src.probe.action_support import CommandSupport
from src.probe.response_transfer import verify_cached_response,weights


class ResponseTransferTest(unittest.TestCase):
    def test_silent_y_change_requires_measurement_then_rejects_stale_cache(self):
        old=[[1.,0.,0.],[0.,1.,0.]]
        x=CommandSupport(([.2,0.,0.,0.],[-.2,0.,0.,0.]))
        response=[[.2,0.],[-.2,0.]]
        q=[0.,.5,0.,0.]
        result=verify_cached_response(x,q,response,old,assumed_componentwise_error_bound=0.)
        self.assertEqual(result["action"],"REACQUIRE_INPUT_SUPPORT")
        complete=CommandSupport(x.commands+((0.,.2,0.,0.),))
        changed=response+[[0.,.4]]
        result=verify_cached_response(complete,q,changed,old,assumed_componentwise_error_bound=0.)
        self.assertEqual(result["action"],"REJECT_CACHE_FOR_QUERY")
        self.assertEqual(result["minimum_conditional_cache_discrepancy"],.5)
        self.assertFalse(result["model_validity_qualified"])

    def test_qualified_analytic_unchanged_response_can_propose_conditional_reuse(self):
        rows=([.5,0.,0.,0.],[-.5,0.,0.,0.],[0.,.5,0.,0.])
        evidence=CommandSupport(rows); q=[0.,.25,0.,0.];old=[[1.,0.,0.],[0.,1.,0.]]
        y=[[.5,0.],[-.5,0.],[0.,.5]]
        result=verify_cached_response(evidence,q,y,old,assumed_componentwise_error_bound=.01,maximum_response_discrepancy=.02)
        self.assertEqual(result["action"],"REUSE_CONDITIONAL_PREDICTION")
        self.assertTrue(result["proposal_only"])
        self.assertFalse(result["task_success_guarantee"])
        self.assertFalse(result["probability_guarantee"])
        self.assertEqual(verify_cached_response(evidence,q,y,old)["action"],"UNQUALIFIED_RESPONSE_MODEL")

    def test_exact_interpolation_envelope_covers_adversarial_measurement_errors(self):
        evidence=CommandSupport(([.5,0.,0.,0.],[-.5,0.,0.,0.],[0.,.5,0.,0.]))
        q=[.8,.7,0.,0.]; model=[[1.,0.,0.],[0.,1.,0.]]
        indices,w=weights(evidence,q)
        epsilon=Fraction.from_float(.01)
        y=[]
        for i,c in enumerate(evidence.commands):
            weight=w[indices.index(i)]
            error=.01 if weight>=0 else -.01
            y.append([c[0]+error,c[1]-error])
        result=verify_cached_response(evidence,q,y,model,assumed_componentwise_error_bound=.010000000000001)
        for axis in range(2):
            self.assertLessEqual(result["response_interval_lower"][axis],q[axis])
            self.assertGreaterEqual(result["response_interval_upper"][axis],q[axis])
        self.assertEqual(sum(w),1)
        self.assertGreater(float(epsilon*sum(abs(v) for v in w)),.01)

    def test_tiny_missing_direction_and_invalid_error_envelope_fail_closed(self):
        evidence=CommandSupport(([.2,0.,0.,0.],[-.2,0.,0.,0.]))
        old=[[1.,0.,0.],[0.,1.,0.]];y=[[.2,0.],[-.2,0.]]
        result=verify_cached_response(evidence,[0.,1e-12,0.,0.],y,old,assumed_componentwise_error_bound=0.)
        self.assertEqual(result["action"],"REACQUIRE_INPUT_SUPPORT")
        for value in (-1.,True,float("nan")):
            with self.assertRaises(ValueError):
                verify_cached_response(evidence,[0.,0.,0.,0.],y,old,assumed_componentwise_error_bound=value)
        with self.assertRaises(TypeError):
            verify_cached_response(evidence,[0.,0.,0.,0.],y,old,true_current_model=old)

    def test_fresh_x_measurements_do_not_revalidate_aged_y(self):
        commands=([.5,0.,0.,0.],[-.5,0.,0.,0.],[0.,.5,0.,0.],[.5,0.,0.,0.],[-.5,0.,0.,0.])
        evidence=CommandSupport(commands);y=[[c[0],c[1]] for c in commands];old=[[1.,0.,0.],[0.,1.,0.]]
        options=dict(assumed_componentwise_error_bound=0.,maximum_response_discrepancy=.02,
                     maximum_coefficient_drift_per_step=.001,observation_steps=[0,0,0,100,100],query_step=100)
        self.assertEqual(verify_cached_response(evidence,[.25,0.,0.,0.],y,old,**options)["action"],"REUSE_CONDITIONAL_PREDICTION")
        self.assertEqual(verify_cached_response(evidence,[0.,.5,0.,0.],y,old,**options)["action"],"REACQUIRE_TEMPORAL_VALIDITY")
        expanded=CommandSupport(evidence.commands+((0.,.5,0.,0.),))
        options["observation_steps"]+=[100]
        self.assertEqual(verify_cached_response(expanded,[0.,.5,0.,0.],y+[[0.,.525]],old,**options)["action"],"REJECT_CACHE_FOR_QUERY")

    def test_contradictory_measurements_falsify_declared_drift_contract(self):
        commands=([.5,0.,0.,0.],[-.5,0.,0.,0.],[0.,.5,0.,0.],[.5,0.,0.,0.],[-.5,0.,0.,0.],[0.,.5,0.,0.])
        y=[[c[0],c[1]] for c in commands];y[-1]=[0.,1.]
        result=verify_cached_response(CommandSupport(commands),[0.,.5,0.,0.],y,[[1.,0.,0.],[0.,1.,0.]],
            assumed_componentwise_error_bound=0.,maximum_coefficient_drift_per_step=.001,
            observation_steps=[0,0,0,100,100,100],query_step=100)
        self.assertEqual(result["action"],"REJECT_DECLARED_RESPONSE_CONTRACT")
        self.assertFalse(result["model_validity_qualified"])

    def test_future_measurement_times_and_missing_time_contract_are_rejected(self):
        evidence=CommandSupport(([.5,0.,0.,0.],[-.5,0.,0.,0.],[0.,.5,0.,0.]))
        y=[[.5,0.],[-.5,0.],[0.,.5]];old=[[1.,0.,0.],[0.,1.,0.]]
        self.assertEqual(verify_cached_response(evidence,[.1,.1,0.,0.],y,old,
            assumed_componentwise_error_bound=0.,maximum_coefficient_drift_per_step=.001)["action"],"UNQUALIFIED_TIME_CONTRACT")
        with self.assertRaisesRegex(ValueError,"precede"):
            verify_cached_response(evidence,[.1,.1,0.,0.],y,old,assumed_componentwise_error_bound=0.,
                maximum_coefficient_drift_per_step=.001,observation_steps=[0,1,101],query_step=100)


if __name__=="__main__": unittest.main()

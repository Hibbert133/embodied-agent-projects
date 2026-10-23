import unittest
import numpy as np
from scripts.analyze_action_response_scope import hull,inside,implied_interval,case_scope
from src.probe.action_response_validity import ResidualDesign,set_intervals,hypothetical_extension,PRIMITIVES


class ActionResponseScopeTest(unittest.TestCase):
    def test_clipped_corner_image_can_miss_actual_interior_policy_command(self):
        matrix=np.array([[2.,2.],[-2.,2.]])
        corners=[np.clip(matrix@np.array(a),-1,1) for a in ((-1,-1),(-1,1),(1,-1),(1,1),(0,0))]
        boundary=hull(corners)
        actual=np.clip(matrix@np.array([.5,0.]),-1,1)
        self.assertFalse(inside(boundary,actual))
        self.assertTrue(all(inside(boundary,q) for q in corners))

    def test_exact_hull_rejects_tiny_outside_component_and_handles_degeneracy(self):
        boundary=hull([(0.,0.),(1.,0.),(0.,1.)])
        self.assertTrue(inside(boundary,(.5,.5)))
        self.assertFalse(inside(boundary,(.5,.500000000000001)))
        self.assertTrue(inside(hull([(0.,0.),(1.,0.)]),(.5,0.)))
        self.assertFalse(inside(hull([(0.,0.),(1.,0.)]),(.5,1e-12)))
        self.assertFalse(inside((),(0.,0.)))

    def test_implied_interval_uses_only_saved_design_and_realized_mean_command(self):
        validation={"residual_groups":{"commands_xy":[[-.4,0.],[.4,0.],[0.,-.4],[0.,.4],[0.,0.]],
            "mean_residual_mm":[[0.,0.]]*5,"counts":[8]*5,"evidence_digest":"predecision"},
            "assessment":{"noise_reference_rms_m":1e-6,"mode":"SET"}}
        interval=implied_interval(validation,[(0.,0.,0.,0.)]*4)
        self.assertEqual(interval["status"],"FINITE")
        self.assertTrue(all(x<=0 for x in interval["lower_mm"]))
        self.assertTrue(all(x>=0 for x in interval["upper_mm"]))
        self.assertEqual(interval["future_mean_sent_xy"],[0.,0.])

    def test_scope_uses_only_policy_steps_of_the_saved_reuse_decision(self):
        validation={"residual_groups":{"commands_xy":[[-.4,0.],[.4,0.],[0.,-.4],[0.,.4],[0.,0.]],
            "mean_residual_mm":[[0.,0.]]*5,"counts":[8]*5,"evidence_digest":"predecision"},
            "assessment":{"noise_reference_rms_m":1e-6,"mode":"SET"},
            "envelope":{"sent_xy":[[-1.,0.],[0.,-1.],[1.,0.],[0.,1.],[0.,0.]]}}
        record={"episode_index":1,"stream":0,"task":"push-v3","scenario":"MIXED","episode_in_stream":1,
            "method":"RESPONSE_SET","seed":10801,
            "decisions":[{"action":"REUSE_CACHE","sequence":12,"validation":validation}],
            "trace":[{"phase":"PREFIX_POLICY","decision_sequence":12,"host_calls":6,"command":[1.,-1.,0.,1.]},
                     {"phase":"POLICY","decision_sequence":11,"host_calls":7,"command":[1.,-1.,0.,1.]}]+
                    [{"phase":"POLICY","decision_sequence":12,"host_calls":k,"command":[1.,-1.,0.,1.],
                      "target_xy":[0.,0.],"forecast_xy":[0.,0.]} for k in range(8,12)]}
        result=case_scope(record)
        self.assertEqual(result["policy_queries"],4)
        self.assertEqual(result["outside_listed_query_hull"],4)
        self.assertEqual(result["first_outside_step"],8)
        self.assertTrue(result["first_four_policy_mean_covered"])
        self.assertFalse(result["prediction_scope_qualified"])
        record["trace"]=record["trace"][:-1]
        result=case_scope(record)
        self.assertIsNone(result["first_four_policy_mean_covered"])
        self.assertTrue(result["incomplete_future_block"])

    def test_regrouping_narrower_interval_need_not_be_nested(self):
        original=ResidualDesign(((0.,0.),),((0.,0.),),(1,),"analytic_original")
        predicted=hypothetical_extension(original,PRIMITIVES["ZERO4"])
        observed=ResidualDesign(((0.,0.),),((.16,0.),),(5,),"analytic_updated")
        def interval(design):
            result=set_intervals(design,((0.,0.),),.0001)
            self.assertEqual(result["status"],"FINITE")
            return result["intervals_mm"][0]
        old,guess,new=map(interval,(original,predicted,observed))
        self.assertAlmostEqual(old["upper"][0],.2)
        self.assertGreater(new["upper"][0],old["upper"][0])
        self.assertLess(new["upper"][0]-new["lower"][0],old["upper"][0]-old["lower"][0])
        self.assertLess(guess["upper"][0],old["upper"][0])
        for bounds in (old,new):
            self.assertLessEqual(bounds["lower"][0],.1)
            self.assertGreaterEqual(bounds["upper"][0],.1)


if __name__=="__main__":unittest.main()

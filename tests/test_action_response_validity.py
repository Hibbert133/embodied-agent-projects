from dataclasses import replace
import unittest
import numpy as np
from src.probe.action_response_validity import (CachedPoint,ResidualDesign,assess,choose_primitive,
    hypothetical_extension,residual_design,action_envelope,PRIMITIVES)
from src.probe.operator_identification import OperatorSample
from src.probe.forward_prediction import ForwardQuery
from scripts.run_action_response import agent_validation
from tests.test_operator_identification import model


class ActionResponseValidityTest(unittest.TestCase):
    def envelope(self):
        return {"sent_xy":[(-.4,0.),(.4,0.)],"thresholds_mm":[.01,.01]}

    def design(self):
        return ResidualDesign(((-.4,0.),(.4,0.)),((0.,0.),(0.,0.)),(8,8),"past")

    def test_query_specific_reuse_and_new_direction_requirement(self):
        design=self.design()
        result=assess(design,self.envelope(),1e-6)
        self.assertEqual(result["status"],"COMPATIBLE")
        self.assertFalse(result["physical_response_qualified"])
        y={"sent_xy":[(0.,.4)],"thresholds_mm":[.01]}
        self.assertEqual(assess(design,y,1e-6)["status"],"UNRESOLVED")
        measured=ResidualDesign(design.commands_xy+((0.,-.4),(0.,.4)),design.mean_residual_mm+((-1.,0.),(1.,0.)),(8,)*4,"more_past")
        self.assertEqual(assess(measured,y,1e-6)["status"],"INCOMPATIBLE")

    def test_point_ablation_can_approve_an_unmeasured_direction(self):
        y={"sent_xy":[(0.,.4)],"thresholds_mm":[.01]}
        self.assertEqual(assess(self.design(),y,1e-6,"POINT")["status"],"COMPATIBLE")
        self.assertEqual(assess(self.design(),y,1e-6,"SET")["status"],"UNRESOLVED")

    def test_inconsistent_observations_reject_model_without_cause_label(self):
        bad=ResidualDesign(((0.,0.),),((100.,0.),),(4,),"past")
        r=assess(bad,self.envelope(),1e-6)
        self.assertEqual(r["status"],"CONTRACT_REJECTED")
        self.assertNotIn("actuator_changed",r)

    def test_budget_exhaustion_cannot_request_a_program(self):
        choice=choose_primitive(self.design(),self.envelope(),1e-6,remaining_steps=35,reserved_task_steps=32)
        self.assertEqual(choice["action"],"STOP_BUDGET")
        self.assertIsNone(choice["program_id"])

    def test_registered_program_completes_query_uncertainty(self):
        y={"sent_xy":[(0.,.4)],"thresholds_mm":[.01]}
        choice=choose_primitive(self.design(),y,1e-6,remaining_steps=100)
        self.assertEqual(choice["program_id"],"WIDE_Y4")
        self.assertTrue(choice["prospective_score_is_not_observed_evidence"])
        expanded=hypothetical_extension(ResidualDesign(((float(np.float32(.4)),0.),),((0.,0.),),(2,),"old"),PRIMITIVES["WIDE_X4"])
        self.assertEqual(expanded.counts[0],4)

    def test_visible_residuals_and_response_mask_are_separate(self):
        q=ForwardQuery((0.,)*39,(0.,)*3,(0.,)*3,(.2,0.,0.,0.))
        samples=(OperatorSample(3,q,(.004,0.)),OperatorSample(4,q,(.004,0.)))
        point=CachedPoint(((1.,0.),(0.,1.)),(0.,0.))
        actual=residual_design(model("LINEAR_ARX"),point,samples)
        hidden=residual_design(model("LINEAR_ARX"),point,samples,mask_responses=True)
        self.assertEqual(actual.counts,hidden.counts)
        self.assertNotEqual(actual.mean_residual_mm,hidden.mean_residual_mm)
        self.assertEqual(hidden.mean_residual_mm,((0.,0.),))

    def test_future_samples_and_invalid_cached_point_are_rejected(self):
        q=ForwardQuery((0.,)*39,(0.,)*3,(0.,)*3,(.2,0.,0.,0.))
        samples=(OperatorSample(9,q,(.001,0.)),)
        point=CachedPoint(((1.,0.),(0.,1.)),(0.,0.))
        with self.assertRaisesRegex(ValueError,"future"):
            agent_validation("RESPONSE_SET",model("LINEAR_ARX"),point,samples,1e-4,0,494)
        with self.assertRaises(ValueError):CachedPoint(((True,0.),(0.,1.)),(0.,0.))
        with self.assertRaises(ValueError):CachedPoint(((.1,0.),(0.,1.)),(0.,0.))
        poisoned={**model("LINEAR_ARX"),"seed":10800}
        with self.assertRaises(ValueError):action_envelope(poisoned,point)

    def test_no_cost_ablation_does_not_stop_at_compatibility(self):
        point=CachedPoint(((1.,0.),(0.,1.)),(0.,0.))
        q=ForwardQuery((0.,)*39,(0.,)*3,(0.,)*3,(0.,0.,0.,0.))
        samples=tuple(OperatorSample(i,q,(0.,0.)) for i in range(3,7))
        result=agent_validation("RESPONSE_NO_COST",model("LINEAR_ARX"),point,samples,1e-6,0,494)
        self.assertEqual(result["action"],"REQUEST_MICRO_PROBE")


if __name__=="__main__":unittest.main()

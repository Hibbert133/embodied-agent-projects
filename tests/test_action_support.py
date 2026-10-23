from fractions import Fraction
import unittest
import numpy as np
from src.probe.action_support import CommandSupport,assess_query,recommend_completion
from src.probe.continuous import symmetric_program
from scripts.analyze_action_support import RankReplay,episode


class ActionSupportTest(unittest.TestCase):
    def test_affine_bias_requires_reverse_input_and_y_requires_y_support(self):
        full=symmetric_program()
        repeated=CommandSupport(full[:4]*2); reverse=CommandSupport(full[:8]); complete=CommandSupport(full)
        self.assertEqual((repeated.rank,reverse.rank,complete.rank),(1,2,3))
        self.assertTrue(assess_query(repeated,full[0])["structurally_supported"])
        self.assertFalse(assess_query(repeated,full[4])["structurally_supported"])
        self.assertTrue(assess_query(reverse,[.9,0.,0.,0.])["structurally_supported"])
        self.assertFalse(assess_query(reverse,[.9,.01,0.,0.])["structurally_supported"])
        self.assertTrue(assess_query(complete,[.9,.01,.5,1.])["structurally_supported"])

    def test_tiny_unobserved_component_is_not_rounded_into_support(self):
        support=CommandSupport(symmetric_program()[:8])
        result=assess_query(support,[.1,1e-12,0.,0.])
        self.assertFalse(result["structurally_supported"])
        self.assertTrue(result["numerically_near_span"])
        numerator,denominator=result["nullspace_witness"]["query_first_output_difference_exact"]
        self.assertNotEqual(Fraction(int(numerator),int(denominator)),0)

    def test_nullspace_witness_preserves_all_observed_inputs_but_changes_query(self):
        support=CommandSupport(symmetric_program()[:8]); query=[.1,.3,0.,0.]
        result=assess_query(support,query); witness=result["nullspace_witness"]
        delta=np.asarray(witness["delta_operator"])
        x=np.array([[r[0],r[1],1.] for r in support.commands])
        np.testing.assert_array_equal(x@delta.T,np.zeros((8,2)))
        original=np.array([[1.,0.,-.1],[0.,1.,.1]])
        np.testing.assert_array_equal(x@original.T,x@(original+delta).T)
        self.assertFalse(np.array_equal(original@np.array([.1,.3,1.]),(original+delta)@np.array([.1,.3,1.])))
        self.assertFalse(result["model_validity_qualified"])
        self.assertFalse(result["probability_guarantee"])
        self.assertFalse(result["task_success_guarantee"])

    def test_query_specific_support_does_not_require_full_identification(self):
        support=CommandSupport(([.2,.2,0.,0.],[-.2,-.2,0.,0.]))
        self.assertEqual(support.rank,2)
        result=assess_query(support,[.5,.5,0.,0.])
        self.assertTrue(result["structurally_supported"])
        self.assertFalse(assess_query(support,[.5,.4,0.,0.])["structurally_supported"])
        weights=np.array(result["interpolation_weights"])
        x=np.array([[r[0],r[1],1.] for r in support.commands])
        np.testing.assert_allclose(weights@x,[.5,.5,1.],atol=1e-12)
        self.assertGreater(result["numerical_interpolation_amplification_l1"],1)

    def test_completion_uses_cheapest_listed_program_and_preserves_task_budget(self):
        support=CommandSupport(symmetric_program()[:8]); q=[0.,.2,0.,0.]
        options={"repeat_x":symmetric_program()[:8],"full_xy":symmetric_program(),"positive_y":symmetric_program()[8:12]}
        result=recommend_completion(support,q,options,remaining_budget=488,task_reserve=484)
        self.assertEqual((result["action"],result["program_id"],result["probe_steps"]),("REQUEST_SUPPORT_COMPLETION","positive_y",4))
        self.assertTrue(result["qualification_required"])
        self.assertEqual(recommend_completion(support,q,options,remaining_budget=487,task_reserve=484)["action"],"ABSTAIN_INPUT_SCOPE")
        self.assertEqual(recommend_completion(support,[.2,0.,0.,0.],options,remaining_budget=0,task_reserve=0)["action"],"INPUT_SUPPORT_PRESENT")

    def test_invalid_and_oracle_inputs_fail_closed(self):
        support=CommandSupport(())
        self.assertFalse(assess_query(support,[0.,0.,0.,0.])["structurally_supported"])
        for value in ([True,0.,0.,0.],[float("nan"),0.,0.,0.],[2.,0.,0.,0.],{"true_bias":[.1,0.]}):
            with self.assertRaises(ValueError): assess_query(support,value)
        with self.assertRaises(TypeError): assess_query(support,[0.,0.,0.,0.],true_operator=np.eye(2))
        with self.assertRaises(ValueError): CommandSupport({"future_commands":[[0.,0.,0.,0.]]})
        with self.assertRaises(ValueError): recommend_completion(support,[0.,0.,0.,0.],{},remaining_budget=True,task_reserve=0)

    def test_independent_elimination_agrees_on_full_and_partial_support(self):
        for rows in ((),symmetric_program()[:4],symmetric_program()[:8],symmetric_program()):
            reference=RankReplay(rows); actual=CommandSupport(rows)
            self.assertEqual(len(reference.rows),actual.rank)
            for q in ([.2,0.,0.,0.],[-.2,0.,0.,0.],[.1,1e-12,0.,0.],[.5,.5,0.,0.]):
                self.assertEqual(reference.contains(q),assess_query(actual,q)["structurally_supported"])

    def test_causal_prefix_does_not_credit_current_or_future_command(self):
        probe=symmetric_program()[:8]
        queries=[[0.,.2,0.,0.],[.1,.4,0.,0.],[.8,.9,0.,0.]]
        record={"episode_index":1,"seed":0,"context_oracle":"synthetic","method":"synthetic",
            "declaration":{"evidence":{"transitions":[{"command":list(q)} for q in probe]}},
            "outcome":{"probe_steps":8,"success":True},
            "steps":[{"command":list(q),"host_calls":i+1} for i,q in enumerate([*probe,*queries])]}
        result=episode(record)
        self.assertEqual(result["frozen_probe_scope_gaps"],3)
        self.assertEqual(result["causal_prefix_scope_gaps"],1)
        self.assertEqual(result["first_causal_scope_gap"]["task_step"],1)
        self.assertEqual(result["first_causal_scope_gap"]["previous_command_count"],8)
        self.assertEqual(result["final_causal_input_rank"],3)


if __name__=="__main__": unittest.main()

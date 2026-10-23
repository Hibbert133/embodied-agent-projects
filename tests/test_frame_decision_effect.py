import copy
import unittest
from scripts.analyze_frame_decision_effect import execution_hash,matched_effect


class FrameDecisionEffectTest(unittest.TestCase):
    def test_only_explanation_hash_is_excluded_from_execution_equivalence(self):
        first=[{"command":[.1,0.,0.,0.],"before":{"observation":[1.,2.]},"rng_before":"a","choice_hash":"inferred"}]
        second=copy.deepcopy(first); second[0]["choice_hash"]="fixed"
        self.assertEqual(execution_hash(first),execution_hash(second))
        second[0]["command"][0]+=.01
        self.assertNotEqual(execution_hash(first),execution_hash(second))
        second=copy.deepcopy(first); second[0]["before"]["observation"][0]+=1
        self.assertNotEqual(execution_hash(first),execution_hash(second))

    def test_equivalent_method_follows_saved_choice_and_rejects_different_execution(self):
        def record(controller,success,command):
            return {"seed":9800,"context_oracle":"FRAME0","declaration":{"choice":{"controller":{"id":controller}}},
                    "steps":[{"command":command,"choice_hash":controller}],"outcome":{"success":success,"task_steps":1}}
        group={"MODEL_REVERSE8":record("FRAME_B",True,[0.,.1,0.,0.]),
               "FIXED_A_REVERSE8":record("FRAME_A",False,[.1,0.,0.,0.]),
               "FIXED_B_REVERSE8":record("FRAME_B",True,[0.,.1,0.,0.])}
        effect=matched_effect(group)
        # The evaluator context says FRAME0, but matching uses saved FRAME_B.
        self.assertEqual(effect["matched_fixed_method"],"FIXED_B_REVERSE8")
        self.assertEqual(effect["effects"]["FIXED_A_REVERSE8"],{"changed":True,"difference":1})
        group["FIXED_B_REVERSE8"]["steps"][0]["command"][1]+=.01
        with self.assertRaisesRegex(ValueError,"execution differs"):
            matched_effect(group)


if __name__=="__main__": unittest.main()

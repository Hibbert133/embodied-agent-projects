import unittest
from src.stochastic_recovery import choose_value_aware_recovery,derive_retry_seed
class StochasticRecoveryTest(unittest.TestCase):
 def test_retry_seed_is_deterministic_independent_and_not_episode_seed(self):
  first=derive_retry_seed(310,1);self.assertEqual(first,derive_retry_seed(310,1));self.assertNotEqual(first,derive_retry_seed(310,2));self.assertNotEqual(first,310)
 def test_value_decision_uses_only_consistency_score(self):
  self.assertEqual(choose_value_aware_recovery(.2,.1).strategy,"stochastic_retry")
  self.assertEqual(choose_value_aware_recovery(.0,.1).strategy,"bias_compensation")
if __name__=="__main__":unittest.main()

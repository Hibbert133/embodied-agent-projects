import unittest
from scripts.evaluate_probe_consistency import evaluate_fixed_threshold,select_threshold
class ProbeConsistencySelectionTest(unittest.TestCase):
 def test_oracle_tuning_threshold_uses_only_score_and_class(self):
  rows=[{"estimated_bias_std_norm":.01,"is_stochastic_ood":False},{"estimated_bias_std_norm":.02,"is_stochastic_ood":False},
        {"estimated_bias_std_norm":.08,"is_stochastic_ood":True},{"estimated_bias_std_norm":.10,"is_stochastic_ood":True}]
  selected=select_threshold(rows)
  self.assertEqual(selected["balanced_accuracy"],1.0);self.assertGreater(selected["threshold"],.02);self.assertLess(selected["threshold"],.08)
 def test_fixed_threshold_is_evaluated_without_retuning(self):
  rows=[{"estimated_bias_std_norm":.01,"is_stochastic_ood":False},{"estimated_bias_std_norm":.09,"is_stochastic_ood":True}]
  result=evaluate_fixed_threshold(rows,.05)
  self.assertEqual(result["threshold"],.05);self.assertEqual(result["balanced_accuracy"],1.0)
if __name__=="__main__":unittest.main()

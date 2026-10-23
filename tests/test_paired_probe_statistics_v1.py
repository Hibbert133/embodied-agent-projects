import unittest
import numpy as np
from src.analysis.paired_probe_statistics_v1 import contrasts,nested_summary,stream_bootstrap


class PairedProbeStatisticsTest(unittest.TestCase):
    def test_exact_controlled_program_decomposition(self):
        losses=[[100,120,70,70],[500,90,500,90]]
        c=contrasts(losses)
        np.testing.assert_array_equal(c[:,0],c[:,1]+c[:,2])
        np.testing.assert_array_equal(c[:,4],[0,410])

    def test_noise_subtraction_retains_negative_estimates(self):
        a=[[10,10,20,20],[30,10,20,20]]
        result=nested_summary([a,a])
        self.assertEqual(result['mean_contrast'][0],0)
        self.assertLess(result['noise_corrected_finite_source_covariance'][0][0],0)
        self.assertEqual(result['observed_context_mean_covariance'][0][0],0)

    def test_finite_source_covariance_identity_and_pure_signal(self):
        result=nested_summary([[[10,11,4,4]]*3,[[40,45,9,9]]*3])
        v=np.asarray(result['noise_corrected_finite_source_covariance'])
        self.assertAlmostEqual(v[0,0],v[1,1]+v[2,2]+2*v[1,2])
        self.assertEqual(np.max(np.abs(result['mc_mean_noise_covariance'])),0)

    def test_incomplete_unbounded_or_nonfinite_tables_rejected(self):
        for table in ([[1,2,3]],[[1,2,3,4]],[[1,2,3,501]]*2,[[1,2,np.nan,4]]*2):
            with self.assertRaises(ValueError):contrasts(table)
        with self.assertRaises(ValueError):nested_summary([[[1,2,3,4]]*2])

    def test_stream_resampling_recomputes_state_weighted_denominator(self):
        # One stream contributes one state, another three: weighting stream
        # means equally would give 15, whereas the registered state mean is 20.
        a=[[5,0,0,0]]*2;b=[[25,0,0,0]]*2
        value=stream_bootstrap([a,b,b,b],[0,1,1,1],{0:('F','S'),1:('F','S')},samples=1000,seed=11)
        self.assertEqual(value['point'][0],20)
        self.assertEqual(value['percentile_95'][0],[5,25])
        self.assertEqual(value['undefined_draws'],0)

    def test_empty_source_streams_are_kept_and_undefined_draws_disclosed(self):
        value=stream_bootstrap([[[5,0,0,0]]*2],[0],{0:('F','S'),1:('F','S')},samples=100,seed=3)
        self.assertEqual(value['source_streams'],2)
        self.assertGreater(value['undefined_draws'],0)
        self.assertIsNone(value['percentile_95'])
        with self.assertRaises(ValueError):stream_bootstrap([[[5,0,0,0]]*2],[2],{0:('F','S')})


if __name__=='__main__':unittest.main()

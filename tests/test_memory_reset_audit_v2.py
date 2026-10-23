"""Exact terminal wall-clock projection, no simulation or model fitting."""
from copy import deepcopy
import unittest
from src.analysis.memory_reset_streaming_audit_v2 import compare_info,project_info,same


def terminal():return dict(noise_cursor_after=500,after=dict(terminated=False,truncated=True,success=False),
    info=dict(success=0.,episode=dict(r=1.25,l=500,t=2.5)))


class WallDurationTests(unittest.TestCase):
    def test_only_finite_terminal_wall_duration_may_differ_and_raw_record_is_retained(self):
        a=terminal();b=deepcopy(a);b['info']['episode']['t']=8.125;old=deepcopy(b)
        self.assertEqual(compare_info(a,b),1);self.assertEqual(b,old)

    def test_physical_time_and_other_task_information_still_compare_exactly(self):
        a=terminal();b=deepcopy(a);a['simulation_time_after']=6.25;b['simulation_time_after']=6.26
        with self.assertRaises(ValueError):same(a['simulation_time_after'],b['simulation_time_after'])
        for key,value in (('success',1.),('other_unknown_field',1)):
            b=deepcopy(a);b['info'][key]=value
            with self.assertRaises(ValueError):compare_info(a,b)

    def test_episode_reward_length_shape_or_nonfinite_duration_cannot_be_hidden(self):
        a=terminal()
        for key,value in (('r',1.3),('l',499),('extra',0),('t',float('nan')),('t',-1.)):
            b=deepcopy(a);b['info']['episode'][key]=value
            with self.assertRaises(ValueError):compare_info(a,b)

    def test_nonterminal_or_missing_episode_cannot_receive_projection(self):
        a=terminal();a['after']['truncated']=False
        with self.assertRaises(ValueError):project_info(a)
        a=terminal();b=deepcopy(a);del b['info']['episode']
        with self.assertRaises(ValueError):compare_info(a,b)
        del a['info']['episode'];self.assertEqual(compare_info(a,b),0)


if __name__=='__main__':unittest.main()

import unittest
import numpy as np
from src.task_metrics import compute_push_step_metrics,summarize_push_episode
def observation(grip,obj,goal):
    x=np.zeros(39); x[:3]=grip; x[4:7]=obj; x[-3:]=goal; return x
class MetricsTest(unittest.TestCase):
    def test_known_geometry(self):
        initial=observation((0,0,0),(0,0,0),(1,0,0)); current=observation((.5,0,0),(.5,.2,0),(1,0,0)); m=compute_push_step_metrics(current,initial)
        self.assertAlmostEqual(m.object_goal_distance,np.hypot(.5,.2)); self.assertAlmostEqual(m.object_displacement_from_start,np.hypot(.5,.2)); self.assertAlmostEqual(m.progress_to_goal,1-np.hypot(.5,.2)); self.assertAlmostEqual(m.lateral_drift,.2)
        s=summarize_push_episode([m]); self.assertEqual(s.final_object_goal_distance,m.object_goal_distance)
if __name__=='__main__': unittest.main()

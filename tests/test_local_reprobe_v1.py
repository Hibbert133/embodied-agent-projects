"""Observable selected targets and estimator incompatibility, synthetic only."""
from copy import deepcopy
from dataclasses import asdict
import unittest
from src.probe import local_reprobe_v1 as m
from src.probe import integral_reprobe_v1 as previous
from src.probe.physical_reprobe_v1 import WarmWindow
from src.probe.cold_start_response import ColdPrefix
from src.probe.warm_response_reference_v1 import WarmResponseProblem
from tests.test_physical_reprobe_v1 import Host, start, observation


class LocalReprobeTests(unittest.TestCase):
    def test_fixed_methods_preserve_previous_actual_commands_and_outcomes(self):
        for position in ((0.,.6,.25),(.03,.62,.23),(.1,.7,.1)):
            initial=start(position)
            for method in ("PD","PID"):
                left,right=Host(initial),Host(initial)
                a=previous.acquire(initial,left.step,left.emit,method=method)
                b=m.acquire(initial,right.step,right.emit,method="FIXED_"+method)
                for key in ("reason","completed_steps","reposition_steps","probe_steps","final"):
                    self.assertEqual(a[key],b[key])
                self.assertEqual([x["command"] for x in left.executed],[x["command"] for x in right.executed])
                if b["window"] is not None:self.assertEqual(a["window"],{k:v for k,v in b["window"].items() if k!="anchor"})

    def test_local_anchor_changes_saved_choice_and_actual_motion(self):
        initial=start((.2,.8,.25));fixed,local=Host(initial),Host(initial)
        a=m.acquire(initial,fixed.step,fixed.emit,method="FIXED_PD")
        b=m.acquire(initial,local.step,local.emit,method="LOCAL_PD")
        self.assertNotEqual(fixed.executed[0]["command"],local.executed[0]["command"])
        self.assertEqual(b["reason"],"COMPLETE_UNQUALIFIED")
        self.assertLess(b["reposition_steps"],a["reposition_steps"])
        self.assertEqual(b["measurement_anchor"],[.2,.8,.25])
        self.assertEqual(b["probe_steps"],8)

    def test_target_uses_visible_object_height_and_declared_interior_bounds(self):
        initial=m.Start("push-v3",16,observation((.6,1.1,.3),obj=(0.,.8,.3)),((1.,0.),(0.,1.)),(0.,0.))
        self.assertEqual(m.selected_anchor(initial,"LOCAL_PID"),(.45,.95,.42))
        high=m.Start("push-v3",16,observation((-.6,.2,.3),obj=(0.,.8,.49)),((1.,0.),(0.,1.)),(0.,0.))
        self.assertEqual(m.selected_anchor(high,"LOCAL_PID"),(-.45,.45,.45))
        self.assertEqual(m.selected_anchor(high,"FIXED_PID"),(0.,.6,.25))

    def test_selected_target_cannot_follow_later_hand_or_object_observations(self):
        initial=start((.2,.8,.25));host=Host(initial)
        m.acquire(initial,host.step,host.emit,method="LOCAL_PID")
        choice=host.events[0]["payload"]
        self.assertEqual(choice["anchor"],[.2,.8,.25])
        self.assertEqual(choice["start"],asdict(initial))
        self.assertEqual(m.selected_anchor(initial,"LOCAL_PID"),(.2,.8,.25))

    def test_local_window_is_rejected_by_both_previous_estimator_contracts(self):
        initial=start((.2,.8,.25));host=Host(initial)
        result=m.acquire(initial,host.step,host.emit,method="LOCAL_PID")
        window=m.SelectedAnchorWindow.from_mapping(result["window"])
        with self.assertRaises(ValueError):WarmWindow.from_mapping(result["window"])
        with self.assertRaises(ValueError):ColdPrefix.from_dict(result["window"])
        with self.assertRaises(ValueError):WarmResponseProblem({"task":"push-v3"},window)
        self.assertFalse(result["measurement_model_qualified"])

    def test_anchor_and_window_reject_unknown_private_fields_or_false_geometry(self):
        initial=start((.2,.8,.25));host=Host(initial)
        original=m.acquire(initial,host.step,host.emit,method="LOCAL_PD")["window"]
        for field in ("seed","fault_oracle","controlled_reset_completed"):
            value=deepcopy(original);value[field]=True
            with self.assertRaises(ValueError):m.SelectedAnchorWindow.from_mapping(value)
        for anchor in ((.3,.8,.25),(float("nan"),.8,.25),(.6,.8,.25)):
            value=deepcopy(original);value["anchor"]=anchor
            with self.assertRaises(ValueError):m.SelectedAnchorWindow.from_mapping(value)

    def test_journal_target_mutation_prevents_any_command(self):
        initial=start((.2,.8,.25));host=Host(initial)
        def changed(kind,payload):
            saved=host.emit(kind,payload)
            if kind=="REACQUIRE_CHOICE":saved["anchor"][0]=0.
            return saved
        with self.assertRaises(ValueError):m.acquire(initial,host.step,changed,method="LOCAL_PID")
        self.assertEqual(host.used,0)

    def test_budget_and_terminal_guards_apply_to_local_methods(self):
        for initial in (start(steps=329),start(success=True)):
            host=Host(initial);result=m.acquire(initial,host.step,host.emit,method="LOCAL_PID")
            self.assertEqual(host.used,0);self.assertIsNone(result["window"])

    def test_stationary_unreachable_height_keeps_sixty_four_step_limit(self):
        initial=start((.2,.8,.1));host=Host(initial,stationary=True)
        result=m.acquire(initial,host.step,host.emit,method="LOCAL_PID")
        self.assertEqual(result["reason"],"ANCHOR_NOT_REACHED")
        self.assertEqual((host.used,result["probe_steps"]),(64,0))

    def test_position_stability_and_clearance_thresholds_remain_unchanged(self):
        anchor=(.2,.8,.25);o=observation(anchor).observation
        self.assertTrue(m.anchor_ready([o]*4,anchor))
        self.assertFalse(m.anchor_ready([o]*3,anchor))
        bad=observation((.216,.8,.25)).observation
        self.assertFalse(m.anchor_ready([bad]*4,anchor))
        self.assertFalse(m.anchor_ready([o,o,observation((.19,.8,.25)).observation,o],anchor))
        close=observation(anchor,obj=anchor).observation
        self.assertFalse(m.anchor_ready([close]*4,anchor))


if __name__=="__main__":unittest.main()

"""Synthetic behavioral checks, no new scientific MetaWorld cases."""
from copy import deepcopy
import unittest
import numpy as np
from src.probe import integral_reprobe_v1 as m
from src.probe import physical_reprobe_v1 as old
from tests.test_physical_reprobe_v1 import Host, start, observation


class IntegralReprobeTests(unittest.TestCase):
    def test_pd_preserves_original_behavior_on_actual_callback(self):
        for initial in (start(),start((.03,.62,.23)),start((.1,.6,.1)),start(steps=329)):
            a,b=Host(initial),Host(initial)
            first=old.acquire(initial,a.step,a.emit)
            second=m.acquire(initial,b.step,b.emit,method="PD")
            for key in ("reason","completed_steps","reposition_steps","probe_steps","final","window"):
                self.assertEqual(first[key],second[key])
            self.assertEqual([c["command"] for c in a.executed],[c["command"] for c in b.executed])

    def test_integral_breaks_idealized_stale_equilibrium_both_signs(self):
        for bias in (-.2,.2):
            initial=start((bias/8,.6,.25))
            def biased(host):return observation((host.current.observation[0]+.01*bias,*host.current.observation[1:3]))
            a,b=Host(initial,transform=biased),Host(initial,transform=biased)
            pd=m.acquire(initial,a.step,a.emit,method="PD")
            pid=m.acquire(initial,b.step,b.emit,method="PID")
            self.assertEqual(pd["reason"],"ANCHOR_NOT_REACHED")
            self.assertEqual(pid["reason"],"COMPLETE_UNQUALIFIED")
            self.assertLess(pid["relocation_evidence"]["integral_xy"][0]*bias,0)
            self.assertEqual(pid["parameter_fits"],0)

    def test_integral_is_bounded_and_rejects_outward_saturated_increment(self):
        initial=start((-.3,.6,.25));history=[initial.current.observation]
        state,command=m.control_update(initial,history,True,[.1,0.],"PID")
        self.assertEqual(state,[.1,0.])
        for value in ([.501,0.],[float("nan"),0.],[True,0.]):
            with self.assertRaises(ValueError):m.control_update(initial,history,True,value,"PID")
        with self.assertRaises(ValueError):m.control_update(initial,history,True,[.1,0.],"PD")

    def test_actuator_clipping_rejects_increments_pushing_farther_outward(self):
        initial=m.Start("push-v3",16,observation((-.01,.6,.25)),((1.,0.),(0.,1.)),(1.,0.))
        state,_=m.control_update(initial,[initial.current.observation],True,[0.,0.],"PID")
        self.assertEqual(state,[0.,0.])

    def test_missing_budget_and_ended_source_do_not_create_compensation(self):
        for initial in (start(steps=329),start(success=True)):
            host=Host(initial);r=m.acquire(initial,host.step,host.emit,method="PID")
            self.assertEqual(host.used,0);self.assertIsNone(r["relocation_evidence"])

    def test_integral_choice_is_saved_before_every_executed_move(self):
        initial=start((.03,.6,.25));host=Host(initial)
        r=m.acquire(initial,host.step,host.emit,method="PID")
        events=host.events
        for i,event in enumerate(events):
            if event["kind"]=="COMMAND" and event["payload"]["phase"]=="REPOSITION":
                self.assertEqual(events[i-1]["kind"],"INTEGRAL_UPDATE")
                self.assertEqual(events[i-1]["payload"]["at_calls"],event["payload"]["at_calls"])
        self.assertEqual(r["events"],events)

    def test_mutated_integral_journal_stops_before_physical_command(self):
        initial=start((.03,.6,.25));host=Host(initial)
        def corrupt(kind,payload):
            saved=host.emit(kind,payload)
            if kind=="INTEGRAL_UPDATE":saved["integral_after"][0]+=.1
            return saved
        with self.assertRaises(ValueError):m.acquire(initial,host.step,corrupt,method="PID")
        self.assertEqual(host.used,0)

    def test_unregistered_method_is_rejected(self):
        initial=start();host=Host(initial)
        with self.assertRaises(ValueError):m.acquire(initial,host.step,host.emit,method="TUNED_ON_TEST")
        self.assertEqual(host.events,[])

    def test_idealized_unclipped_linearization_is_schur_stable(self):
        # State: position error, previous displacement, integral; g=.01.
        matrix=np.array([[.9168,.16,-.01],[.0832,-.16,.01],[.32,0.,1.]])
        self.assertLess(max(abs(np.linalg.eigvals(matrix))),1.)


if __name__=="__main__":unittest.main()

"""Public state-machine checks using a synthetic kinematic callback, no simulator."""
from copy import deepcopy
from dataclasses import asdict
import unittest

import numpy as np

from src.probe.continuous import StepObservation
from src.probe.cold_start_response import ColdPrefix
from src.probe import physical_reprobe_v1 as m


def observation(position=m.ANCHOR, obj=(0., .8, .02), **flags):
    values = [0.] * 39
    values[:3] = position;values[4:7] = obj
    return StepObservation(tuple(values), flags.get("terminated", False),
                           flags.get("truncated", False), flags.get("success", False))


def start(position=m.ANCHOR, steps=16, **kwargs):
    return m.Start("push-v3", steps, observation(position, **kwargs), ((1., 0.), (0., 1.)), (0., 0.))


class Host:
    def __init__(self, initial, transform=None, stationary=False):
        self.current=initial.current;self.calls=initial.completed_steps;self.used=0
        self.events=[];self.executed=[];self.transform=transform;self.stationary=stationary

    def emit(self, kind, payload):
        saved={**deepcopy(payload), "sequence":37+len(self.events), "saved_ns":100+len(self.events)}
        self.events.append({"kind":kind,"payload":deepcopy(saved)})
        return saved

    def step(self, saved):
        assert saved==self.events[-1]["payload"]
        assert saved["at_calls"]==self.calls
        assert saved["before"]==asdict(self.current)
        assert saved["decision_sequence"]==37
        assert len(saved["command"])==4 and all(-1<=v<=1 for v in saved["command"])
        values=list(self.current.observation)
        if not self.stationary:
            values[:3]=[x+.01*u for x,u in zip(values[:3],saved["command"][:3])]
        self.calls+=1;self.used+=1
        self.current=StepObservation(tuple(values),False,False,False)
        if self.transform:self.current=self.transform(self)
        self.executed.append(deepcopy(saved))
        return m.StepReceipt(self.current,self.calls)


class PhysicalReprobeTests(unittest.TestCase):
    def run_acquisition(self, initial=None, **kwargs):
        initial=initial or start();host=Host(initial,**kwargs)
        return m.acquire(initial,host.step,host.emit),host

    def test_actual_relocation_then_eight_saved_probe_commands(self):
        result,host=self.run_acquisition()
        self.assertEqual(result["reason"],"COMPLETE_UNQUALIFIED")
        self.assertEqual((result["reposition_steps"],result["probe_steps"],result["new_steps"]),(3,8,11))
        self.assertEqual([tuple(x["command"]) for x in host.executed[3:]],list(m.PROGRAM))
        self.assertEqual(result["events"],host.events)
        self.assertFalse(result["measurement_model_qualified"])
        self.assertEqual(result["parameter_fits"],0)
        self.assertEqual(m.WarmWindow.from_mapping(result["window"]).probe_start_step,19)

    def test_visible_feedback_moves_nearby_hand_to_anchor(self):
        result,host=self.run_acquisition(start((.03,.62,.23)))
        self.assertEqual(result["reason"],"COMPLETE_UNQUALIFIED")
        self.assertGreater(result["reposition_steps"],3)
        self.assertTrue(m.anchor_ready(result["window"]["entry_history"]))
        self.assertEqual(result["new_steps"],host.used)

    def test_motion_and_geometry_need_three_actual_displacements(self):
        pos=observation().observation
        self.assertFalse(m.anchor_ready([pos]*3))
        self.assertTrue(m.anchor_ready([pos]*4))
        changed=observation((.01,.6,.25)).observation
        self.assertFalse(m.anchor_ready([pos,pos,pos,changed]))
        self.assertFalse(m.anchor_ready([observation(obj=m.ANCHOR).observation]*4))

    def test_far_stationary_hand_stops_at_relocation_cap(self):
        result,host=self.run_acquisition(start((.1,.6,.1)),stationary=True)
        self.assertEqual(result["reason"],"ANCHOR_NOT_REACHED")
        self.assertEqual((host.used,result["probe_steps"]),(64,0))
        self.assertIsNone(result["window"])

    def test_insufficient_budget_causes_no_step(self):
        result,host=self.run_acquisition(start(steps=329))
        self.assertEqual(result["reason"],"ENTRY_BUDGET_INSUFFICIENT")
        self.assertEqual(host.used,0)

    def test_exact_maximum_operation_preserves_one_hundred_steps(self):
        def motion(host):
            if host.used<=60:return observation((.1,.6,.25))
            if host.used<=64:return observation()
            return host.current
        result,host=self.run_acquisition(start((.1,.6,.25),steps=328),transform=motion)
        self.assertEqual(result["reason"],"COMPLETE_UNQUALIFIED")
        self.assertEqual((host.used,result["reposition_steps"],result["remaining_steps"]),(72,64,100))

    def test_success_termination_and_truncation_stop_during_relocation(self):
        for flag in ("success","terminated","truncated"):
            with self.subTest(flag=flag):
                def ended(host):return observation(**{flag:host.used==2})
                result,host=self.run_acquisition(transform=ended)
                self.assertEqual(result["reason"],"ENDED_DURING_REPOSITION")
                self.assertEqual((host.used,result["probe_steps"]),(2,0))

    def test_already_ended_does_not_consume_budget(self):
        result,host=self.run_acquisition(start(success=True))
        self.assertEqual(result["reason"],"ALREADY_ENDED")
        self.assertEqual(host.used,0)

    def test_end_during_probe_keeps_partial_costs_and_no_complete_window(self):
        def ended(host):return observation(host.current.observation[:3],success=host.used==6)
        result,host=self.run_acquisition(transform=ended)
        self.assertEqual((result["reason"],result["probe_steps"],host.used),("ENDED_DURING_PROBE",3,6))
        self.assertIsNone(result["window"])

    def test_scope_exit_stops_probe_after_the_actual_bad_step(self):
        for kind in ("near_object","low_height"):
            with self.subTest(kind=kind):
                def leave(host):
                    if host.used==4:
                        return observation(obj=m.ANCHOR) if kind=="near_object" else observation((0.,.6,.2))
                    return host.current
                result,host=self.run_acquisition(transform=leave)
                self.assertEqual((result["reason"],result["probe_steps"],host.used),("PROBE_SCOPE_EXIT",1,4))
                self.assertIsNone(result["window"])

    def test_saved_choices_cannot_be_rewritten_by_journal(self):
        initial=start();host=Host(initial)
        def changed(kind,payload):
            result=host.emit(kind,payload)
            if kind=="COMMAND":result["command"][0]=.9
            return result
        with self.assertRaisesRegex(ValueError,"journal"):
            m.acquire(initial,host.step,changed)
        self.assertEqual(host.used,0)

    def test_journal_order_and_time_must_be_monotone(self):
        for field in ("sequence","saved_ns"):
            initial=start();host=Host(initial)
            def changed(kind,payload):
                result=host.emit(kind,payload)
                if kind=="COMMAND":result[field]=999 if field=="sequence" else 0
                return result
            with self.assertRaisesRegex(ValueError,"journal"):
                m.acquire(initial,host.step,changed)
            self.assertEqual(host.used,0)

    def test_host_may_not_mutate_saved_command(self):
        initial=start();host=Host(initial)
        def mutate(saved):
            receipt=host.step(saved);saved["command"][0]=.8
            return receipt
        with self.assertRaisesRegex(ValueError,"host changed"):
            m.acquire(initial,mutate,host.emit)

    def test_host_receipt_must_advance_exactly_one_step(self):
        for increment in (0,2):
            initial=start();host=Host(initial)
            def bad_count(saved):return m.StepReceipt(host.current,host.calls+increment)
            with self.assertRaisesRegex(ValueError,"skipped"):
                m.acquire(initial,bad_count,host.emit)

    def test_mapping_rejects_private_keys_nested_flags_and_nonfinite_values(self):
        original=asdict(start())
        bad=[]
        for key in ("seed","rng_state","fault_oracle","future_outcome","controlled_reset_completed"):
            value=deepcopy(original);value[key]=0;bad.append(value)
        value=deepcopy(original);value["current"]["fault"]=0;bad.append(value)
        value=deepcopy(original);value["current"]["observation"]=list(value["current"]["observation"])
        value["current"]["observation"][0]=True;bad.append(value)
        value=deepcopy(original);value["offset_xy"]=(float("nan"),0.);bad.append(value)
        value=deepcopy(original);value["completed_steps"]=True;bad.append(value)
        for value in bad:
            with self.assertRaises(ValueError):m.Start.from_mapping(value)

    def test_warm_window_is_not_a_controlled_reset_prefix(self):
        result,_=self.run_acquisition()
        with self.assertRaises(ValueError):ColdPrefix.from_dict(result["window"])
        for key in ("controlled_reset_completed","oracle","seed"):
            value=deepcopy(result["window"]);value[key]=True
            with self.assertRaises(ValueError):m.WarmWindow.from_mapping(value)

    def test_complete_window_rejects_changed_commands_and_missing_observations(self):
        result,_=self.run_acquisition()
        value=deepcopy(result["window"]);value["commands"]=list(value["commands"])
        value["commands"][0]=(0.,0.,0.,0.)
        with self.assertRaises(ValueError):m.WarmWindow.from_mapping(value)
        value=deepcopy(result["window"]);value["observations"]=value["observations"][:-1]
        with self.assertRaises(ValueError):m.WarmWindow.from_mapping(value)

    def test_saved_correction_changes_relocation_command_only(self):
        first=start((.01,.6,.25))
        second=m.Start(first.task,first.completed_steps,first.current,((2.,0.),(0.,1.)),(.1,0.))
        history=[first.current.observation]
        a=m.relocation_command(first,history,True);b=m.relocation_command(second,history,True)
        self.assertAlmostEqual(a[0],-.08,places=6)
        self.assertAlmostEqual(b[0],-.06,places=6)
        self.assertEqual(a[2:],b[2:])
        self.assertEqual(len(m.PROGRAM),8)


if __name__=="__main__":unittest.main()

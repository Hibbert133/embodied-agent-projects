from collections import deque
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np

from scripts import run_cold_start_task_bridge as run
from scripts import audit_cold_start_task_bridge as audit
from scripts.audit_cold_start_task_bridge_statistics import check_statistics
from src.analysis.cold_start_task_bridge import statistics
from src.probe.lifecycle_ledger import LifecycleLedger
from src.probe.cold_start_task_bridge import point_fit, source_hash
from tests.test_acquisition_value import FakeEnv, FakeSimulator, FixedPolicy, model
from tests.test_cold_start_response import trained


class VisibleResetEnv(FakeEnv):
    def reset(self,seed=None):
        super().reset(seed=seed)
        self.observation[:3]=[0.,.6,.2];self.observation[4:7]=[.1,.7,.02]
        return self.observation.copy(),{}


def full_population():
    rows=[];pairs=[];repeats=[]
    for s in range(56):
        for t in run.TASKS:
            for f in range(2):
                for m in run.METHODS:
                    steps=40 if m=="JOINT8" else 80 if m=="NO_PROBE" else 50
                    rows.append(dict(stream=s,task=t,replicate=f,method=m,success=True,stopped=False,total_steps=steps,deadline_loss=steps,
                                     fixed_probe_steps=0 if m=="NO_PROBE" else 16 if m=="OLD_POINT16_CYCLE" else 8))
                for m in run.PORTFOLIO:pairs.append(dict(stream=s,task=t,replicate=f,method=m,reference="JOINT8",boundary=8,reason="MATCHED_ACTIVE_PREFIX_8"))
            for m in run.METHODS:repeats.append(dict(stream=s,task=t,replicate=1,method=m,reason="MATCHED_ACTIVE_PREFIX_8"))
    return rows,pairs,repeats


class ColdStartTaskBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        joint,_=trained();cls.response={"joint":{"push-v3":joint},"same_data_arx":{"push-v3":model()}}

    def setUp(self):
        self.events=[]
        def emit(kind,payload):
            item={"event":kind,"sequence":len(self.events)+1,"saved_ns":run.perf_counter_ns(),**run.normal(payload)}
            self.events.append(item);return item
        self.emit=emit;self.ledger=LifecycleLedger(emit,1000000);self.factory=SimpleNamespace(_make_tasks=lambda:None)
        self.key=dict(experiment_run_id="fixture",manifest_id="fixture",source_git_commit="fixture",stream=0,task="push-v3",replicate=0,seed=14600,operator_id_oracle="A")
        self.operator={"matrix_xy":[[1.1,.1],[0,1.2]],"bias_xy":[.03,-.02]}

    @contextmanager
    def fixtures(self):
        witness=lambda e:{"fixture":True,"time":e.data.time,"observation":e.observation.tolist()}
        with self.ledger.instrument(FakeEnv,FakeSimulator,self.factory),patch.object(run,"create_task_environment",side_effect=lambda *a:VisibleResetEnv()),patch.object(run,"create_task_policy",return_value=FixedPolicy()),patch.object(run,"physics_witness",side_effect=witness):
            yield

    def branch(self,method):
        return run.normal(run.execute({**self.key,"method":method},self.operator,model(),self.response,.0001,self.emit,self.ledger))

    def replay(self,record):
        events=deque(e for e in self.events if not e["event"].startswith("LIFECYCLE"))
        audit.verify_record(record,model(),self.response,.0001,self.operator,events,.01)
        self.assertFalse(events)

    def test_all_eight_programs_execute_saved_controllers_and_replay(self):
        with self.fixtures():
            for method in run.METHODS:
                self.events.clear();record=self.branch(method);self.replay(record)
                self.assertEqual(record["outcome"]["environment_resets"],1)
                expected=0 if method=="NO_PROBE" else 16 if method=="OLD_POINT16_CYCLE" else 8
                self.assertEqual(record["outcome"]["fixed_probe_steps"],expected)
                self.assertTrue(all(d["model_bundle_sha256"]==source_hash(method) for d in record["decisions"]))

    def test_same_actual_prefix_different_estimates_change_executed_task_commands(self):
        with self.fixtures():
            joint=self.branch("JOINT8");old=self.branch("OLD_POINT8")
            self.assertEqual(run.prefix_match(joint,old),"MATCHED_ACTIVE_PREFIX_8")
            self.assertNotEqual(joint["trace"][8]["command"],old["trace"][8]["command"])
            future=self.branch("JOINT8")
            self.assertEqual(run.prefix_match(joint,future),"MATCHED_ACTIVE_PREFIX_8")

    def test_saved_source_controller_command_and_repeated_probe_forgery_fail(self):
        with self.fixtures():
            record=self.branch("JOINT8");self.replay(record)
            original=deepcopy(self.events)
            for mode in ("source","controller","repeat_probe"):
                changed=deepcopy(record);self.events=deepcopy(original)
                d=next(v for v in changed["decisions"] if v["action"]=="RUN_POINT")
                if mode=="source":d["model_bundle_sha256"]="foreign"
                elif mode=="controller":d["controller"]["offset"][0]+=.1
                else:d["action"]="REQUEST_FIXED_PROBE";d["probe_steps"]=8
                e=next(v for v in self.events if v["sequence"]==d["sequence"]);e.update(deepcopy(d))
                with self.assertRaises(ValueError):self.replay(changed)

    def test_failed_joint_fit_stops_at_eight_and_no_fit_controls_do_not_substitute(self):
        with self.fixtures(),patch.object(run,"point_fit",return_value={"valid":False,"reason":"OUTSIDE_CONTROLLED_RESET_SCOPE"}):
            record=self.branch("JOINT8")
        self.assertEqual((record["outcome"]["stopped"],record["outcome"]["total_steps"],record["outcome"]["deadline_loss"]),(True,8,500))
        with self.fixtures(),patch.object(run,"point_fit",side_effect=AssertionError("unexpected point fit")),patch.object(run.GaussianReference,"from_visible",side_effect=AssertionError("unexpected Gaussian fit")):
            for method in ("NO_PROBE","IDENTITY_AFTER8"):self.assertFalse(self.branch(method)["outcome"]["stopped"])

    def test_visible_point_boundary_and_private_field_checks_fail_closed(self):
        with self.assertRaises(ValueError):point_fit("JOINT8",model(),self.response["joint"]["push-v3"],model(),None,())
        with self.assertRaises(ValueError):point_fit("OLD_POINT16_CYCLE",model(),None,None,None,())
        with self.assertRaises(ValueError):source_hash("ORACLE")

    def test_point_agent_receives_only_visible_completed_prefix_and_history(self):
        original=run.point_fit;seen=[]
        def visible_only(method,old,joint,arx,prefix,samples):
            payload=dict(prefix=asdict(prefix) if prefix is not None else None,samples=[asdict(s) for s in samples])
            serialized=json.dumps(payload)
            for forbidden in ("seed","oracle","replicate","operator_id","future_outcome","executed_action"):
                self.assertNotIn(forbidden,serialized)
            self.assertEqual(max(s.step for s in samples),16 if method=="OLD_POINT16_CYCLE" else 8)
            seen.append(method);return original(method,old,joint,arx,prefix,samples)
        with self.fixtures(),patch.object(run,"point_fit",side_effect=visible_only):
            for method in ("JOINT8","JOINT_DROP2_8","SAME_DATA_POINT8","OLD_POINT8","OLD_POINT16_CYCLE"):self.branch(method)
        self.assertEqual(len(seen),5)

    def test_power_plan_and_fresh_reservations_are_fixed(self):
        c=json.loads(run.CONFIG.read_text(encoding="utf-8"));run.validate(c);plan=run.planning(c)
        self.assertEqual(plan["normal_approximation_required_streams"],52);self.assertEqual(len(run.operators(c)),56)
        self.assertEqual({run.task_seed(s,t) for s in range(56) for t in run.TASKS},set(range(14600,14768)))
        for change in ({"streams":16},{"seed_start":14384},{"response_source_steps":3072},{"api_calls":1}):
            with self.assertRaises(ValueError):run.validate({**c,**change})

    def test_complete_statistics_independent_rebuild_stops_and_tampering(self):
        rows,pairs,repeats=full_population();s=statistics(rows,pairs,repeats);self.assertTrue(s["component_gate"]["passed"])
        result=check_statistics(dict(cases=rows,statistics=s));self.assertEqual(result["integrity"],"PASSED")
        bad=deepcopy(s);bad["contrasts"][0]["statistics"]["deadline_loss"]["paired_stream_percentile_95"][1]+=.01
        with self.assertRaises(ValueError):check_statistics(dict(cases=rows,statistics=bad))
        bad=deepcopy(s);bad["methods"]["JOINT8"]["source_steps"]=0
        with self.assertRaises(ValueError):check_statistics(dict(cases=rows,statistics=bad))
        row=next(r for r in rows if r["method"]=="JOINT8");row.update(success=False,stopped=True,total_steps=8,deadline_loss=500)
        s=statistics(rows,pairs,repeats);self.assertEqual(s["methods"]["JOINT8"]["cases"],336);self.assertEqual(s["methods"]["JOINT8"]["stops"],1)
        self.assertFalse(s["component_gate"]["passed"]);check_statistics(dict(cases=rows,statistics=s))
        with self.assertRaises(ValueError):statistics(rows[:-1],pairs,repeats)
        row["deadline_loss"]=8
        with self.assertRaises(ValueError):statistics(rows,pairs,repeats)

    def test_global_lifecycle_rejects_mid_control_resets_and_hidden_simulation(self):
        ledger=dict(counts=dict(reset_completed=137088,simulation_frames_completed=68549000),
                    by_phase=dict(CONTROL=dict(simulation_completed=1000,simulation_frames_completed=5000),CONTROLLED_RESET=dict(reset_completed=2688)))
        audit.verify_lifecycle(ledger,1000)
        for change in (dict(reset_attempts=1),dict(simulation_frames_completed=5005)):
            bad=deepcopy(ledger);bad["by_phase"]["CONTROL"].update(change)
            with self.assertRaises(ValueError):audit.verify_lifecycle(bad,1000)


if __name__ == "__main__":unittest.main()

import copy
from dataclasses import replace
import gzip
import itertools
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np
from scripts import run_frame_evidence as runner
from scripts import analyze_frame_evidence as audit
from src.probe.continuous import StepObservation, collect_continuous, symmetric_program
from src.probe.response_calibration import known_offset_program, fit_response
from src.probe.frame_identification import (fit_nominal_arx, select_frame, registered_controller,
    encode_command, program, transcript_hash, canonical_hash, METHODS)


def synthetic_evidence(commands, rotation=None, bias=(0.,0.)):
    position, velocity = np.zeros(39), np.zeros(2)
    response = np.array([[.012,.003],[-.002,.015]])
    rotation = np.eye(2) if rotation is None else rotation
    def step(command):
        nonlocal velocity
        effective = np.asarray(rotation,dtype=np.float32)@np.asarray(command[:2],dtype=np.float32)+np.asarray(bias,dtype=np.float32)
        velocity = .6*velocity + response@effective
        position[:2] += velocity
        return StepObservation(tuple(position),False,False,False)
    return collect_continuous(step,StepObservation(tuple(position),False,False,False),commands,
                              remaining_budget=len(commands),task_reserve=0)


def priors():
    training = [(offset,synthetic_evidence(known_offset_program(offset)))
                for offset in itertools.product((-.2,0.,.2),repeat=2)]
    return fit_nominal_arx([e for _,e in training]), fit_response(training)


class FrameIdentificationTest(unittest.TestCase):
    def test_constant_prefix_alias_is_resolved_by_reverse_commands(self):
        arx, _ = priors()
        r90 = np.array([[0.,-1.],[1.,0.]])
        for method in ("FIXED_A_PREFIX4","MODEL_REPEAT8"):
            first = synthetic_evidence(program(method),bias=(-.1,.1))
            second = synthetic_evidence(program(method),rotation=r90,bias=(.1,-.1))
            self.assertEqual(transcript_hash(first),transcript_hash(second))
            self.assertFalse(select_frame(arx,first)["informative_input"])
            self.assertEqual(select_frame(arx,first)["controller_id"],"FRAME_A")
            self.assertEqual(select_frame(arx,second)["controller_id"],"FRAME_A")
        first = synthetic_evidence(program("MODEL_REVERSE8"),bias=(-.1,.1))
        second = synthetic_evidence(program("MODEL_REVERSE8"),rotation=r90,bias=(.1,-.1))
        self.assertNotEqual(transcript_hash(first),transcript_hash(second))
        self.assertEqual(select_frame(arx,first)["controller_id"],"FRAME_A")
        self.assertEqual(select_frame(arx,second)["controller_id"],"FRAME_B")
        self.assertFalse(select_frame(arx,second)["confidence_certificate"])

    def test_training_only_arx_reconstructs_the_nominal_linear_system(self):
        arx, _ = priors()
        self.assertEqual(arx.training_trials,9)
        self.assertEqual(arx.samples,135)
        np.testing.assert_allclose(arx.inertia,.6*np.eye(2),atol=1e-7)
        np.testing.assert_allclose(arx.response,[[.012,.003],[-.002,.015]],atol=1e-7)
        self.assertEqual(arx.design_rank,5)

    def test_evaluator_truth_cannot_enter_the_estimator(self):
        arx, legacy = priors()
        evidence = synthetic_evidence(program("MODEL_REVERSE8"))
        with self.assertRaises(TypeError):
            select_frame(arx,evidence,true_context="FRAME90")
        with self.assertRaises(TypeError):
            runner.choose("MODEL_REVERSE8",evidence,arx,legacy,fault=runner.FrameFault("FRAME90"))
        raw = evidence.to_dict(); raw["true_bias"]=[.1,-.1]
        with self.assertRaisesRegex(ValueError,"invalid frame"):
            runner.choose("MODEL_REVERSE8",raw,arx,legacy)
        with self.assertRaisesRegex(ValueError,"probe size"):
            runner.choose("MODEL_REVERSE8",replace(evidence,requested_steps=500),arx,legacy)
        rows = list(evidence.transitions); rows[2]=replace(rows[2],before=(0.,)*39)
        with self.assertRaisesRegex(ValueError,"discontinuous"):
            select_frame(arx,replace(evidence,transitions=tuple(rows)))

    def test_legal_selections_change_actual_bounded_commands(self):
        raw = np.array([.4,-.3,.2,1.],dtype=np.float32)
        a = encode_command(registered_controller("FRAME_A"),raw)
        b = encode_command(registered_controller("FRAME_B"),raw)
        self.assertFalse(np.array_equal(a,b))
        for context, command in (("FRAME0",a),("FRAME90",b)):
            fault=runner.FrameFault(context); fault.reset(15)
            # Remove the same sampled noise independently to inspect the transform.
            noise=np.random.default_rng(15).normal(0,.05,3).astype(np.float32)
            np.testing.assert_allclose(fault.apply(command)[:3]-noise,raw[:3],atol=1e-7)
        for name in ("FRAME_A","FRAME_B","UNCORRECTED"):
            self.assertLessEqual(float(np.max(np.abs(encode_command(registered_controller(name),[100.,-100.,3.,9.])))),1)
        changed=registered_controller("FRAME_A"); changed["matrix_xy"]=[[0.,0.],[0.,0.]]
        with self.assertRaisesRegex(ValueError,"changed"):
            encode_command(changed,raw)
        with self.assertRaisesRegex(ValueError,"unknown"):
            registered_controller("ORACLE")
        with self.assertRaisesRegex(ValueError,"bounded"):
            fault.apply([2.,0.,0.,0.])

    def test_common_noise_coupling_and_probe_budget(self):
        first, second = runner.FrameFault("FRAME0"), runner.FrameFault("FRAME90")
        first.reset(55); second.reset(55)
        for _ in range(8):
            np.testing.assert_array_equal(first.apply([.2,0.,0.,0.]),second.apply([.2,0.,0.,0.]))
        self.assertFalse(np.array_equal(first.apply([-.2,0.,0.,0.]),second.apply([-.2,0.,0.,0.])))
        called=[]
        with self.assertRaisesRegex(ValueError,"reserved"):
            collect_continuous(lambda command:called.append(command),StepObservation((0.,)*39,False,False,False),
                               program("MODEL_REVERSE8"),remaining_budget=499,task_reserve=492)
        self.assertFalse(called)
        with self.assertRaisesRegex(ValueError,"input rank"):
            fit_nominal_arx([synthetic_evidence(symmetric_program()[:4])])


class FrameRunnerAuditTest(unittest.TestCase):
    def test_monotonic_counter_orders_events_even_if_wall_clock_steps(self):
        events=[{"event_index":1,"perf_counter_ns":100,"utc":"2026-10-14T10:00:01+00:00"},
                {"event_index":2,"perf_counter_ns":200,"utc":"2026-10-14T10:00:00+00:00"}]
        self.assertEqual(audit.verify_event_order(events),1)
        events[1]["perf_counter_ns"]=99
        with self.assertRaisesRegex(ValueError,"timestamp order"):
            audit.verify_event_order(events)

    def test_complete_mocked_population_and_adversarial_replay(self):
        arx, legacy = priors()
        c = json.loads(runner.CONFIG.read_text())
        m = {"experiment_run_id":"synthetic", "source_git_commit":"test", "config":c,
             "nominal_arx":arx.to_dict(), "arx_model_sha256":canonical_hash(arx.to_dict()),
             "legacy_model_sha256":"legacy", "input_sha256":{}}
        m["manifest_id"]=runner.manifest_digest(m)
        created=[]; resets=[]; case=self
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"manifest.json"; path.write_text(json.dumps(m))
            (path.parent/"nominal_arx.json").write_text(json.dumps({**runner.identity(m),"model":m["nominal_arx"],"arx_model_sha256":m["arx_model_sha256"]}))
            class Env:
                action_space=SimpleNamespace(low=-np.ones(4),high=np.ones(4))
                def __init__(self):
                    self.index=len(created)+1; self.method=METHODS[len(created)%11]; created.append(self)
                def reset(self,**kwargs):
                    resets.append(kwargs); self.calls=0; self.position=np.zeros(39); self.velocity=np.zeros(2)
                    return self.position.copy(),{}
                def step(self,command):
                    self.calls+=1
                    if self.calls==len(program(self.method))+1:
                        saved=json.loads((path.parent/"decisions.jsonl").read_text().splitlines()[-1])
                        case.assertEqual(saved["episode_index"],self.index)
                        case.assertEqual(saved["choice_hash"],canonical_hash(saved["choice"]))
                    self.velocity=.6*self.velocity+np.array([[.012,.003],[-.002,.015]])@command[:2]
                    self.position[:2]+=self.velocity
                    return self.position.copy(),0.,False,False,{"success":self.calls==19}
                def close(self): pass
            policy=SimpleNamespace(get_action=lambda observation:np.array([.04,-.03,0.,0.]))
            with patch.object(runner,"check_clean"), patch.object(runner,"git",return_value="test"), \
                 patch.object(runner,"load_priors",return_value=(arx,legacy,"legacy")), \
                 patch.object(runner,"create_push_environment",side_effect=lambda seed:Env()), \
                 patch.object(runner,"create_push_policy",return_value=policy),patch("builtins.print"):
                runner.run(path)
                with self.assertRaisesRegex(FileExistsError,"cannot restart"):
                    runner.run(path)
            self.assertEqual(len(resets),176)
            with patch.object(audit,"load_priors",return_value=(arx,legacy,"legacy")), \
                 patch.object(audit,"create_push_policy",return_value=policy):
                result=audit.analyze(path)
            self.assertEqual(result["physical_steps"],3344)
            self.assertEqual(result["verified_probe_steps"],1472)
            self.assertEqual(result["integrity"],"PASSED")
            self.assertFalse(result["statistics"]["gate_passed"])
            self.assertEqual(result["statistics"]["methods"]["MODEL_REVERSE8"]["mean_amortized_steps"],163)
            with gzip.open(path.parent/"episodes.jsonl.gz","rt",encoding="utf-8") as handle:
                record=json.loads(next(handle))
            declaration=json.loads((path.parent/"decisions.jsonl").read_text().splitlines()[0])
            events=[json.loads(line) for line in (path.parent/"events.jsonl").read_text().splitlines()[:5]]
            def replay(row, ev=events):
                return audit.verify_episode(m,row,declaration,ev,arx,legacy,policy)
            changed=copy.deepcopy(record); changed["steps"][4]["rng_before"]="reset"
            with self.assertRaisesRegex(ValueError,"RNG reseed"):
                replay(changed)
            changed=copy.deepcopy(record); changed["steps"][4]["choice_hash"]="other"
            with self.assertRaisesRegex(ValueError,"saved fixed-policy"):
                replay(changed)
            changed=copy.deepcopy(record); changed["steps"][4]["before"]["observation"][0]+=1
            with self.assertRaisesRegex(ValueError,"handoff discontinuity"):
                replay(changed)
            changed=copy.deepcopy(record); changed["steps"][4]["executed_action_oracle"][0]+=.1
            with self.assertRaisesRegex(ValueError,"frame/noise"):
                replay(changed)
            changed=copy.deepcopy(record); changed["outcome"]["environment_resets"]=2
            with self.assertRaisesRegex(ValueError,"cost reconstruction"):
                replay(changed)
            changed=copy.deepcopy(record)
            changed["declaration"]["evidence"]["true_bias"]=[.1,-.1]
            hidden_declaration=changed["declaration"]
            with self.assertRaisesRegex(ValueError,"evidence schema"):
                audit.verify_episode(m,changed,hidden_declaration,events,arx,legacy,policy)
            wrong=copy.deepcopy(events); wrong[2]["kind"]="TASK_STARTED"
            with self.assertRaisesRegex(ValueError,"chronology"):
                replay(record,wrong)


if __name__ == "__main__":
    unittest.main()

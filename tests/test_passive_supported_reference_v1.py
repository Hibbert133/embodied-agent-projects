import copy
from time import perf_counter_ns
import unittest
import numpy as np
from src.probe.passive_supported_reference_v1 import (run_passive_reference, OwnedPassiveCacheV1, PassiveReferenceFailure)
from src.probe.chronological_cache_reference import VerifiedPoint
from src.probe.continuous import StepObservation
from src.probe.operator_identification import encode_controller
from tests.test_operator_identification import model
from scripts.audit_passive_supported_reference_v1 import verify


def prior(mode="PASSIVE8_KEEP", episode=0):
    return OwnedPassiveCacheV1(mode, VerifiedPoint((1., 0., .1, 0., 1., 0.), None, episode, "push-v3", "a"*64, True))


class ToyHost:
    """Deterministic test callback, not a MetaWorld research observation."""
    def __init__(self, end=26, varied=16, success=True):
        self.calls, self.events, self.sent = 0, [], []
        self.position, self.velocity = np.zeros(39), np.zeros(3)
        self.end, self.varied, self.success = end, varied, success

    def persist(self, kind, payload):
        event = {"event": kind, "payload": copy.deepcopy(payload), "sequence": len(self.events)+1, "saved_ns": perf_counter_ns()}
        self.events.append(event)
        return copy.deepcopy(event)

    def policy(self, observation):
        index = int(observation[-1])
        program = ((.3, 0.), (-.3, 0.), (0., .3), (0., -.3))
        xy = program[index % 4] if index < self.varied else (.2, .1)
        return [*xy, 0., 0.]

    def step(self, command):
        assert self.events[-1]["event"] == "STEP_INTENT"
        assert self.events[-1]["saved_ns"] <= perf_counter_ns()
        np.testing.assert_array_equal(command, np.array(self.events[-1]["payload"]["command"], np.float32))
        self.sent.append(command.copy())
        # Test-only unknown-to-the-adapter actuation and nominal AR2 dynamics.
        effective = np.clip(np.array([.8*command[0]+.06, 1.1*command[1]-.03]), -1, 1)
        self.velocity[:2] = .5*self.velocity[:2]+np.array([.006, .008])*effective
        self.position[:3] += self.velocity
        self.calls += 1
        self.position[-1] = self.calls
        ended = self.calls == self.end
        return StepObservation(tuple(self.position), False, ended and not self.success, ended and self.success)

    def run(self, mode="PASSIVE8_KEEP", previous=None, episode=1):
        return run_passive_reference(mode=mode, task="push-v3", episode=episode, initial=StepObservation((0.,)*39, False, False, False),
            previous=previous, model=model("LINEAR_ARX"), policy=self.policy, step=self.step, persist=self.persist)


class SupportedPassiveReferenceTest(unittest.TestCase):
    def test_independent_saved_control_flow_replay_covers_accept_reject_and_rolling_updates(self):
        for mode, varied, end in (("PASSIVE8_KEEP", 16, 26), ("PASSIVE8_KEEP", 0, 26),
                                 ("PASSIVE64_PERIODIC16_KEEP", 16, 100)):
            host = ToyHost(end=end, varied=varied)
            record = host.run(mode=mode)
            result = verify(record, model("LINEAR_ARX"), host.policy)
            self.assertEqual(result["events_checked"], len(record["events"]))
            self.assertIs(result["physical_host_qualified"], False)

    def test_independent_replay_rejects_changed_command_fit_or_renewed_old_cache(self):
        host = ToyHost(varied=0)
        record = host.run(previous=prior(), episode=4)
        for kind in ("command", "fit", "cache"):
            changed = copy.deepcopy(record)
            if kind == "command": changed["trace"][8]["command"][0] += .1
            elif kind == "fit":
                next(e for e in changed["events"] if e["event"] == "DECISION" and e["payload"]["fit"])["payload"]["fit"]["valid"] = True
            else: changed["state_after"]["point"]["source_episode"] = 4
            with self.subTest(kind=kind), self.assertRaises(ValueError): verify(changed, model("LINEAR_ARX"), host.policy)

    def test_valid_actual_fit_changes_sent_commands_and_only_then_enters_verified_cache(self):
        host = ToyHost()
        record = host.run()
        decisions = [e for e in host.events if e["event"] == "DECISION"]
        self.assertEqual([d["payload"]["action"] for d in decisions], ["START_IDENTITY", "ACCEPT_UPDATE"])
        self.assertEqual(decisions[1]["payload"]["at_host_calls"], 8)
        self.assertEqual(decisions[1]["payload"]["fit"]["samples"], 6)
        row = record["trace"][8]
        np.testing.assert_array_equal(host.sent[8], encode_controller(decisions[1]["payload"]["controller"], row["raw_policy"]))
        self.assertFalse(np.allclose(row["command"], row["raw_policy"]))
        self.assertTrue(record["outcome"]["success"])
        self.assertEqual(record["state_after"]["point"]["source_episode"], 1)
        self.assertEqual(record["state_after"]["point"]["evidence_sha256"], decisions[1]["payload"]["fit"]["sample_digest"])
        self.assertEqual(host.events[-1]["event"], "TASK_OUTCOME_AND_CACHE")

    def test_unsupported_new_fit_really_continues_identity_without_making_a_cache(self):
        host = ToyHost(varied=0)
        record = host.run()
        decision = [e for e in host.events if e["event"] == "DECISION"][-1]
        self.assertEqual(decision["payload"]["action"], "REJECT_UPDATE_KEEP")
        self.assertEqual(decision["payload"]["fit"]["reason"], "MISSING_OR_ILL_CONDITIONED_INPUT_SUPPORT")
        self.assertEqual(len(host.sent), 26)
        self.assertIsNone(record["state_after"])
        np.testing.assert_array_equal(host.sent[8], np.array([.2, .1, 0., 0.], np.float32))

    def test_unsupported_update_keeps_own_cache_and_does_not_renew_source_age(self):
        old = prior()
        host = ToyHost(varied=0)
        record = host.run(previous=old, episode=4)
        self.assertEqual(record["state_after"], old.to_dict())
        for row in record["trace"]:
            np.testing.assert_array_equal(np.array(row["command"], np.float32), encode_controller(old.point.controller, row["raw_policy"]))

    def test_later_rejection_keeps_latest_applied_update_instead_of_reverting_to_initial(self):
        host = ToyHost(end=100, varied=16)
        record = host.run(mode="PASSIVE64_PERIODIC16_KEEP")
        choices = [e for e in host.events if e["event"] == "DECISION"]
        updates = [d for d in choices if d["payload"]["action"] == "ACCEPT_UPDATE"]
        rejects = [d for d in choices if d["payload"]["action"] == "REJECT_UPDATE_KEEP"]
        self.assertTrue(updates and rejects)
        for d in rejects:
            self.assertEqual(d["payload"]["controller"], updates[-1]["payload"]["controller"])
        self.assertEqual(record["outcome"]["last_applied_fit_decision_sequence"], updates[-1]["sequence"])
        self.assertEqual(record["state_after"]["point"]["evidence_sha256"], updates[-1]["payload"]["fit"]["sample_digest"])
        self.assertEqual([d["payload"]["at_host_calls"] for d in choices[1:]], [16, 32, 48, 64, 80, 96])
        self.assertEqual([d["payload"]["fit"]["samples"] for d in choices[1:]], [14, 30, 46, 62, 64, 64])

    def test_failure_clears_old_cache_and_retains_the_500_deadline_loss(self):
        host = ToyHost(end=12, varied=0, success=False)
        record = host.run(previous=prior())
        self.assertIsNone(record["state_after"])
        self.assertFalse(record["outcome"]["success"])
        self.assertEqual(record["outcome"]["deadline_loss"], 500)
        self.assertEqual(record["outcome"]["total_steps"], 12)

    def test_early_ending_does_not_request_a_fit_after_the_episode(self):
        host = ToyHost(end=8)
        record = host.run(previous=prior())
        self.assertEqual(record["outcome"]["fit_attempts"], 0)
        self.assertEqual(record["state_after"], prior().to_dict())

    def test_total_budget_caps_the_rolling_reference_at_500_actual_steps(self):
        host = ToyHost(end=999, varied=0)
        record = host.run(mode="PASSIVE64_PERIODIC16_KEEP")
        self.assertEqual((host.calls, len(host.sent), record["outcome"]["total_steps"]), (500, 500, 500))
        self.assertEqual(record["outcome"]["fit_attempts"], 31)
        self.assertEqual(record["outcome"]["deadline_loss"], 500)
        self.assertIsNone(record["state_after"])

    def test_foreign_future_and_nested_evaluator_cache_data_are_rejected_before_stepping(self):
        for old in (prior("PASSIVE64_PERIODIC16_KEEP"), prior(episode=1)):
            host = ToyHost()
            with self.assertRaises(ValueError): host.run(previous=old, episode=1)
            self.assertEqual(host.calls, 0)
        packet = prior().to_dict()
        packet["point"]["fault_oracle"] = "hidden"
        with self.assertRaises(ValueError): OwnedPassiveCacheV1.from_dict(packet)

    def test_saved_decision_or_command_tampering_is_rejected_before_execution(self):
        for kind in ("DECISION", "STEP_INTENT"):
            host = ToyHost()
            persist = host.persist
            def tamper(event, payload):
                saved = persist(event, payload)
                if event == kind:
                    if event == "DECISION": saved["payload"]["controller"]["offset"][0] = .5
                    else: saved["payload"]["command"][0] = .5
                return saved
            host.persist = tamper
            with self.subTest(kind=kind), self.assertRaises(PassiveReferenceFailure) as error:
                host.run()
            self.assertEqual(host.calls, 0)
            self.assertEqual(error.exception.record["step_attempts"], 0)

    def test_step_exception_preserves_partial_actual_execution_without_promoting_a_cache(self):
        host = ToyHost()
        actual = host.step
        def failed_step(command):
            if host.calls == 8: raise RuntimeError("test callback failed")
            return actual(command)
        host.step = failed_step
        with self.assertRaises(PassiveReferenceFailure) as error:
            host.run()
        self.assertEqual(error.exception.record["completed_steps"], 8)
        self.assertEqual(error.exception.record["step_attempts"], 9)
        self.assertNotIn("state_after", error.exception.record)
        self.assertNotEqual(host.events[-1]["event"], "TASK_OUTCOME_AND_CACHE")

    def test_no_oracle_reset_or_future_parameter_is_accepted_by_the_adapter(self):
        with self.assertRaises(TypeError): run_passive_reference(fault_oracle={})
        packet = prior().to_dict()
        self.assertEqual(OwnedPassiveCacheV1.from_dict(packet).to_dict(), packet)
        host = ToyHost()
        bad = model("LINEAR_ARX")
        bad["true_parameters"] = [1.]*6
        with self.assertRaises(ValueError):
            run_passive_reference(mode="PASSIVE8_KEEP", task="push-v3", episode=1,
                initial=StepObservation((0.,)*39, False, False, False), previous=None, model=bad,
                policy=host.policy, step=host.step, persist=host.persist)
        self.assertEqual(host.calls, 0)


if __name__ == "__main__": unittest.main()

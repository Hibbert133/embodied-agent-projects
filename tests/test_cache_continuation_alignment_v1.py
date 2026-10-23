import copy
from dataclasses import asdict
import unittest
from unittest.mock import patch
import numpy as np
from tests.test_chronological_cache_reference import cache_fixture
from src.analysis.cache_continuation_alignment_v1 import (process_unit, query_purity, describe, METHODS)
from src.probe.cache_acquisition_evidence_v1 import CacheAcquisitionEvidenceV1
from src.probe.chronological_cache_reference import BLOCK8
from scripts.audit_cache_continuation_alignment_v1 import reconstruct, counts


def fixture():
    _, cached = cache_fixture()
    cache = asdict(cached)
    witness = {"state_spec": 8191, "integration": [0.], "body_pos": [[0., 0., 0.]], "site_pos": [[0., 0., 0.]],
               "task_fields": {"curr_path_length": 4}, "complete_hidden_state_qualification": False}
    def obs(i, success=False):
        return {"observation": [i*.001]*39, "success": success, "terminated": False, "truncated": False}
    def record(method, reuse=False):
        n = 6 if reuse else 10
        trace = []
        for i in range(1, n+1):
            probe = i <= (4 if reuse else 8)
            command = np.array(BLOCK8[i-1] if probe else [0., 0., 0., 0.], np.float32).astype(float).tolist()
            trace.append({"host_calls": i, "phase": "FIXED_PROBE" if probe else "POLICY", "command": command,
                "raw_policy": None if probe else [0.]*4, "before": obs(i-1), "after": obs(i, i == n),
                "noise_before_hash": f"noise{i-1}", "noise_after_hash": f"noise{i}", "target_xy": [0., 0.],
                "executed_action_oracle": command, "simulation_time_before_oracle": (i-1)*.0125,
                "simulation_time_after_oracle": i*.0125, "decision_sequence": 1 if probe else (2 if reuse else 3)})
        fit = None if reuse else {"valid": True, "model": "JOINT_FULL8", "matrix_xy": [[1., 0.], [0., 1.]], "bias_xy": [0., 0.]}
        warm = method != "ALWAYS8"
        decisions = [{"sequence": 1, "at_host_calls": 0, "action": "CHECK4" if warm else "PROBE8",
                      "program": list(map(list, BLOCK8[:4] if warm else BLOCK8)), "controller": None}]
        if warm:
            decisions.append({"sequence": 2, "at_host_calls": 4, "action": "RUN_CACHED" if reuse else "REFRESH8",
                "program": [] if reuse else list(map(list, BLOCK8[4:])), "controller": cached.controller if reuse else None,
                "noise_hash": "noise4", "raw_policy_for_check": [0.]*4})
        if not reuse:
            decisions.append({"sequence": 3, "at_host_calls": 8, "action": "RUN_POINT", "program": [], "controller": cached.controller, "fit": fit})
        return {"experiment_run_id": "synthetic", "manifest_id": "m", "source_git_commit": "c", "phase": "MAIN",
            "stream": 0, "episode": 1, "seed": 17001, "task": "push-v3", "method": method,
            "initial": obs(0), "initial_physics_witness_oracle": copy.deepcopy(witness), "initial_noise_hash": "noise0",
            "noise_commitment_oracle": {"full_sha256": "private"}, "clock_contract": {"frame_skip": 5},
            "boundary_physics_witness_oracle": {"4": copy.deepcopy(witness)}, "state_before": {"cache": copy.deepcopy(cache)},
            "state_after": {"cache": copy.deepcopy(cache)}, "fit": fit, "trace": trace, "decisions": decisions,
            "outcome": {"success": True, "total_steps": n, "deadline_loss": n, "stopped": False,
                        "environment_resets": 1, "noise_rows_consumed": n, "fixed_probe_steps": 4 if reuse else 8,
                        "online_parameter_fits": 0 if reuse else 1}}
    records = [record("ALWAYS8"), record("CUSUM4", True), record("PLUGIN4", True), record("UNCERTAINTY4"), record("TASK_IVR4")]
    past = {(m, 0): {"task": "push-v3", "success": True, "new_fit": True, "cache": copy.deepcopy(cache)} for m in ("ALWAYS8", *METHODS)}
    return records, past


class CacheContinuationAlignmentTest(unittest.TestCase):
    def test_reuse_and_actual_refresh_remain_different_kinds_of_evidence(self):
        records, past = fixture()
        result = process_unit(records, past, check_policy=False)
        self.assertEqual(len(result["reuse_pairs"]), 2)
        self.assertEqual(len(result["unique_reuse_pairs"]), 1)
        self.assertEqual(result["unique_reuse_pairs"][0]["behavior_methods"], ["CUSUM4", "PLUGIN4"])
        self.assertEqual(len(result["refresh_controls"]), 2)
        self.assertEqual(result["reuse_pairs"][0]["realized_loss_difference_under_source_contract"], -4)
        self.assertEqual(len(result["evidence"]), 1)
        self.assertTrue(all(r["complete_hidden_state_qualified"] is False for r in result["dispositions"]))

    def test_independent_reconstruction_matches_without_calling_main_extractor(self):
        records, past = fixture()
        result = process_unit(copy.deepcopy(records), copy.deepcopy(past), check_policy=False)
        with patch("src.analysis.cache_continuation_alignment_v1.process_unit", side_effect=AssertionError("main extractor called")):
            d, p, u, c, e = reconstruct(records, past)
        for key, value in (("dispositions", d), ("reuse_pairs", p), ("unique_reuse_pairs", u), ("refresh_controls", c), ("evidence", e)):
            self.assertEqual(result[key], value)
        self.assertEqual(counts(u)["mean_realized_reuse_minus_fresh_loss"], -4)

    def test_another_actual_unit_is_not_deduplicated_even_with_identical_visible_input(self):
        records, past = fixture()
        first = process_unit(copy.deepcopy(records), copy.deepcopy(past), check_policy=False)
        for row in records:
            row["stream"] = 1
        second = process_unit(records, past, check_policy=False)
        a, b = first["unique_reuse_pairs"][0], second["unique_reuse_pairs"][0]
        self.assertEqual(a["public_evidence_sha256"], b["public_evidence_sha256"])
        self.assertNotEqual(a["decision_id"], b["decision_id"])

    def test_prefix_state_noise_and_reset_mismatches_fail_instead_of_being_dropped(self):
        changes = [lambda r: r["trace"][1]["command"].__setitem__(0, .3),
                   lambda r: r["trace"][2].__setitem__("noise_after_hash", "future"),
                   lambda r: r["initial_physics_witness_oracle"]["integration"].__setitem__(0, 1.),
                   lambda r: r["clock_contract"].__setitem__("frame_skip", 6),
                   lambda r: r["initial"]["observation"].__setitem__(0, .01)]
        for change in changes:
            records, past = fixture()
            records = copy.deepcopy(records)
            change(records[1])
            with self.subTest(change=change), self.assertRaises(ValueError):
                process_unit(records, past, check_policy=False)

    def test_refresh_tail_and_fits_are_actual_negative_controls(self):
        for kind in ("trace", "fit", "program"):
            records, past = fixture()
            if kind == "trace": records[3]["trace"][8]["command"][0] = .1
            elif kind == "fit": records[3]["fit"]["bias_xy"][0] = .01
            else: records[3]["decisions"][1]["program"][0][1] = .3
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                process_unit(records, past, check_policy=False)

    def test_future_foreign_unverified_and_renewed_cache_sources_rejected(self):
        for kind in ("future", "unverified", "renewed", "no_new_fit"):
            records, past = fixture()
            if kind == "future": records[1]["state_before"]["cache"]["source_episode"] = 1
            elif kind == "unverified": past["CUSUM4", 0]["success"] = False
            elif kind == "renewed": past["CUSUM4", 0]["cache"]["evidence_sha256"] = "0"*64
            else: past["CUSUM4", 0]["new_fit"] = False
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                process_unit(records, past, check_policy=False)

    def test_identical_same_unit_evidence_requires_same_actual_reuse_tail(self):
        records, past = fixture()
        records[2]["trace"][4]["command"][0] = .1
        with self.assertRaises(ValueError):
            process_unit(records, past, check_policy=False)

    def test_failures_keep_deadline_penalty_and_do_not_become_missing_data(self):
        records, past = fixture()
        for r in records[1:3]:
            r["trace"][-1]["after"]["success"] = False
            r["trace"][-1]["after"]["truncated"] = True
            r["outcome"].update(success=False, deadline_loss=500)
        result = process_unit(records, past, check_policy=False)
        self.assertEqual(result["unique_reuse_pairs"][0]["realized_loss_difference_under_source_contract"], 490)
        self.assertEqual(result["unique_reuse_pairs"][0]["realized_success_difference"], -1)

    def test_stopped_check_cannot_be_written_as_executed_reuse(self):
        records, past = fixture()
        r = records[1]
        r["trace"] = r["trace"][:4]
        r["decisions"][1].update(action="STOP_CHECK_SCOPE_OR_NUMERICS", controller=None)
        r["outcome"].update(success=False, total_steps=4, deadline_loss=500, stopped=True, noise_rows_consumed=4)
        result = process_unit(records, past, check_policy=False)
        self.assertEqual(result["dispositions"][1]["status"], "EXCLUDED_CHECK_STOP")
        self.assertEqual([p["method"] for p in result["reuse_pairs"]], ["PLUGIN4"])

    def test_public_packet_rejects_top_level_and_nested_evaluator_information(self):
        records, past = fixture()
        result = process_unit(records, past, check_policy=False)
        public = next(iter(result["evidence"].values()))
        for key in ("seed", "stream", "method", "fault_oracle", "future_success", "noise_hash", "source_episode"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                CacheAcquisitionEvidenceV1.from_dict({**public, key: 0})
        nested = copy.deepcopy(public)
        nested["prefix"]["physical_witness_oracle"] = {}
        with self.assertRaises(ValueError): CacheAcquisitionEvidenceV1.from_dict(nested)
        self.assertEqual(CacheAcquisitionEvidenceV1.from_dict(public).to_dict(), public)

    def test_visible_age_covariance_program_and_budget_are_checked(self):
        records, past = fixture()
        public = next(iter(process_unit(records, past, check_policy=False)["evidence"].values()))
        for field, value in (("source_age", 0), ("source_age", True), ("remaining_budget", 500),
                             ("source_covariance", np.zeros((6, 6)).tolist()), ("current_policy_command", [float("nan")]*4)):
            with self.subTest(field=field), self.assertRaises((ValueError, np.linalg.LinAlgError)):
                CacheAcquisitionEvidenceV1.from_dict({**public, field: value})
        wrong = copy.deepcopy(public)
        wrong["prefix"]["commands"][0][0] = .2
        with self.assertRaises(ValueError): CacheAcquisitionEvidenceV1.from_dict(wrong)

    def test_purity_checks_detect_policy_internal_state_and_random_consumption(self):
        class Stateful:
            def get_action(self, observation):
                self.calls = getattr(self, "calls", 0)+1
                return [0.]*4
        class Random:
            def get_action(self, observation):
                np.random.random()
                return [0.]*4
        for policy in (Stateful(), Random()):
            state = np.random.get_state()
            try:
                with patch("src.analysis.cache_continuation_alignment_v1.create_task_policy", return_value=policy):
                    with self.assertRaises(ValueError): query_purity("push-v3", [0.]*39, [0.]*4)
            finally:
                np.random.set_state(state)

    def test_successful_checks_do_not_promote_conditional_expectation_or_novelty(self):
        records, past = fixture()
        r = process_unit(records, past, check_policy=False)
        s = describe(r["dispositions"], r["reuse_pairs"], r["unique_reuse_pairs"], r["refresh_controls"], 0)
        for key in ("conditional_expectation_identified", "unconditional_causal_transport_qualified", "whole_stream_counterfactual_identified", "new_algorithm_established"):
            self.assertIs(s[key], False)


if __name__ == "__main__":
    unittest.main()

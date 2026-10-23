import copy
from dataclasses import asdict, replace
import unittest
from time import perf_counter_ns
import numpy as np
from src.probe.cache_acquisition_evidence_v1 import digest
from src.probe.history_query_reference_v1 import (PastPolicyQueryV1, HistoryQueryMeasureV1, OwnedQueryHistoryV1, history_ivr, history_check)
from src.probe.chronological_cache_reference import BLOCK8, ivr_reference
from tests.test_chronological_cache_reference import cache_fixture, visible_prefix
from src.analysis.strong_chronological_reference_v1 import METHODS, population, statistics
from src.probe.continuous import StepObservation
from src.probe.cold_start_response import clipped_normal_mean
from src.probe.history_query_execution_v1 import run_history_query_reference
from scripts.audit_history_query_execution_v1 import verify
from scripts.audit_strong_reference_statistics_v1 import reconstruct
from scripts import run_strong_chronological_reference_v1 as runner


class HistoryQueryReferenceTest(unittest.TestCase):
    def test_config_rejects_changed_population_budget_and_query_rules(self):
        config = runner.read(runner.CONFIG); runner.validate(config)
        for key, value in (("query_history_cap_per_task", 65), ("history_ivr_threshold", .3), ("api_calls", 1)):
            bad = copy.deepcopy(config); bad[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): runner.validate(bad)
        for key in ("seed_start", "maximum_environment_steps", "maximum_controlled_resets"):
            bad = copy.deepcopy(config); bad["main"][key] -= 1
            with self.subTest(key=key), self.assertRaises(ValueError): runner.validate(bad)

    def test_cold_and_warm_saved_execution_pass_independent_control_and_ivr_replay(self):
        model, cached = cache_fixture(); _, prefix = visible_prefix(BLOCK8)
        for previous in (None, cached):
            events, calls = [], [0]
            position = np.array(prefix.initial_observation)
            def persist(kind, payload):
                value = {"event": kind, "sequence": len(events)+1, "saved_ns": perf_counter_ns(), "payload": copy.deepcopy(payload)}
                events.append(value)
                return copy.deepcopy(value)
            def policy(observation): return np.array([.3, .2, 0., 0.])
            def step(command):
                position[:2] += .01*clipped_normal_mean(np.array(command[:2]))[0]
                calls[0] += 1
                return StepObservation(tuple(position), False, False, calls[0] == 14)
            past = (PastPolicyQueryV1("push-v3", 0, 1, (.4, 0., 0., 0.), "a"*64),) if previous else ()
            result = run_history_query_reference(task="push-v3", episode=1, initial=StepObservation(prefix.initial_observation, False, False, False),
                previous=previous, past_queries=past, model=model, policy=policy, step=step, persist=persist)
            audited = verify(result, model, previous, past, policy)
            self.assertEqual(audited["integrity"], "PASSED")
            self.assertEqual(audited["events_checked"], len(events))
            self.assertEqual(result["outcome"]["total_steps"], 14)
            changed = copy.deepcopy(result)
            changed["trace"][-1]["command"][0] += .1
            with self.assertRaises(ValueError): verify(changed, model, previous, past, policy)

    def test_no_prior_queries_exactly_matches_the_current_query_ivr(self):
        model, cache = cache_fixture(); _, prefix = visible_prefix(BLOCK8[:4]); raw = (.3, .4, 0., 0.)
        got = history_ivr(model, prefix, cache, HistoryQueryMeasureV1(prefix.task, 1, (), raw))
        expected = ivr_reference(model, prefix, cache, raw)
        for key in ("variance_after4", "expected_variance_after8", "relative_variance_reduction"):
            self.assertAlmostEqual(got[key], expected[key], places=12)
        self.assertEqual(got["total_measure_queries"], 1)
        self.assertIs(got["task_value_estimate"], False)

    def test_task_measure_averages_variances_before_computing_relative_reduction(self):
        model, cache = cache_fixture(); _, prefix = visible_prefix(BLOCK8[:4])
        commands = ((.1, -.2, 0., 0.), (.7, .8, 0., 0.), (.3, .4, 0., 0.))
        past = tuple(PastPolicyQueryV1(prefix.task, 0, i+1, raw, "a"*64) for i, raw in enumerate(commands[:2]))
        measure = HistoryQueryMeasureV1(prefix.task, 1, past, commands[2])
        result = history_ivr(model, prefix, cache, measure)
        references = [ivr_reference(model, prefix, cache, raw) for raw in commands]
        for key in ("variance_after4", "expected_variance_after8"):
            self.assertAlmostEqual(result[key], sum(r[key] for r in references)/3, places=12)
        self.assertEqual(HistoryQueryMeasureV1.from_dict(measure.to_dict()).to_dict(), measure.to_dict())

    def test_future_foreign_duplicate_and_hidden_queries_fail_closed(self):
        q = PastPolicyQueryV1("push-v3", 0, 1, (.1, .2, 0., 0.), "a"*64)
        for values in ((replace(q, source_episode=1),), (replace(q, task="reach-v3"),), (q, q)):
            with self.assertRaises(ValueError): HistoryQueryMeasureV1("push-v3", 1, values, (0.,)*4)
        packet = HistoryQueryMeasureV1("push-v3", 1, (q,), (0.,)*4).to_dict()
        for key in ("seed", "future_policy_commands", "fault_oracle", "outcome"):
            with self.assertRaises(ValueError): HistoryQueryMeasureV1.from_dict({**packet, key: 0})
        packet["past_queries"][0]["executed_action_oracle"] = [0.]*4
        with self.assertRaises(ValueError): HistoryQueryMeasureV1.from_dict(packet)

    def test_owned_history_retains_actual_failure_queries_and_has_a_fixed_cap(self):
        history = OwnedQueryHistoryV1("PASSIVE8_KEEP")
        rows = [{"host_calls": i, "phase": "POLICY", "raw_policy": [.1, .2, 0., 0.], "before": {"observation": [float(i)]*39}} for i in range(1, 71)]
        record = {"method": "PASSIVE8_KEEP", "episode": 0, "task": "push-v3", "trace": rows, "outcome": {"total_steps": 70, "success": False}}
        before = history.sha256
        history.append_record(record)
        part = history.for_task("push-v3", 1)
        self.assertEqual(len(part), 64)
        self.assertEqual((part[0].host_calls, part[-1].host_calls), (7, 70))
        self.assertNotEqual(before, history.sha256)
        self.assertEqual(part[-1].observation_sha256, digest(rows[-1]["before"]["observation"]))
        for changed in ({**record, "method": "ALWAYS8", "episode": 1}, record):
            with self.assertRaises(ValueError): history.append_record(changed)
        with self.assertRaises(ValueError): history.for_task("push-v3", 0)

    def test_source_bound_guard_still_forces_refresh(self):
        model, cache = cache_fixture(); _, prefix = visible_prefix(BLOCK8[:4])
        cache = replace(cache, belief=replace(cache.belief, active_parameter_bound=True))
        result = history_check(model, prefix, cache, HistoryQueryMeasureV1(prefix.task, 1, (), (0.,)*4))
        self.assertEqual(result["action"], "REFRESH8")

    def test_new_physical_population_does_not_use_old_or_reserved_seeds(self):
        smoke, main = population("SMOKE"), population("MAIN")
        self.assertEqual({c["seed"] for s in smoke for c in s["cases"]}, set(range(18000, 18012)))
        self.assertEqual({c["seed"] for s in main for c in s["cases"]}, set(range(18100, 18316)))
        self.assertEqual(len(main), 18)
        self.assertEqual(sum(len(s["cases"])*len(METHODS) for s in main), 1944)
        self.assertEqual({s["generation_seed_oracle"] for s in main}, set(range(63001, 63019)))
        for task in ("push-v3", "reach-v3", "door-open-v3"):
            self.assertEqual(sum(c["task"] == task for s in main for c in s["cases"]), 72)

    def test_full_statistics_keep_stops_and_complete_per_method_source_fees(self):
        rows = []
        for stream in population("MAIN"):
            for case in stream["cases"]:
                for method in METHODS:
                    row = {"stream": stream["stream"], "episode": case["episode"], "method": method, "task": case["task"],
                        "family_oracle": stream["family_oracle"], "schedule_oracle": stream["schedule_oracle"],
                        "success": method == "NO_PROBE", "stopped": method == "PASSIVE_RECENT8", "deadline_loss": 50 if method == "NO_PROBE" else 500,
                        "total_steps": 8 if method == "PASSIVE_RECENT8" else 50, "fixed_probe_steps": 0}
                    for key in ("online_parameter_fits", "optimizer_nfev", "policy_queries", "cache_writes", "cache_clears", "stale_cached_policy_steps_oracle",
                                "accepted_passive_updates", "rejected_passive_updates", "history_queries_used_at_check"): row[key] = 0
                    rows.append(row)
        got = statistics(rows, "MAIN")
        independently = reconstruct(rows, {"population_oracle": {"MAIN": population("MAIN")}, "config": {"methods": list(METHODS)}}, "MAIN")
        self.assertEqual(got, independently)
        stopped = got["methods"]["PASSIVE_RECENT8"]
        self.assertEqual((stopped["cases"], stopped["stops"], stopped["mean_deadline_loss"], stopped["mean_total_steps"]), (216, 216, 500, 8))
        self.assertAlmostEqual(stopped["mean_amortized_actual_steps"], 8+21010/216)
        self.assertEqual(got["methods"]["ALWAYS8"]["offline_source_steps"], 3840)
        with self.assertRaises(ValueError): statistics(rows[:-1], "MAIN")


if __name__ == "__main__": unittest.main()

import unittest
from copy import deepcopy
from scripts import run_chronological_cache_reference as run
from scripts.audit_chronological_cache_statistics import reconstruct, compare
from src.analysis.chronological_cache_reference import statistics
from src.probe.chronological_cache_reference import METHODS
from src.rollout.chronological_faults import population


def fixture(phase):
    specs = population(phase); records = []; rows = []
    for stream in specs:
        for case in stream["cases"]:
            for method in METHODS:
                failed = method == "UNCERTAINTY4" and stream["stream"] == 0 and case["episode"] == 0
                steps = 8 if failed else 56 if method == "UNCERTAINTY4" else 60
                outcome = {"success": not failed, "stopped": failed, "total_steps": steps, "environment_resets": 1,
                           "fixed_probe_steps": 4 if method == "UNCERTAINTY4" else 8, "policy_measure_steps": 0,
                           "policy_steps": steps-4, "deadline_loss": 500 if failed else steps, "noise_rows_consumed": steps,
                           "online_parameter_fits": 0, "optimizer_nfev": 0}
                record = {"experiment_run_id": "fixture", "manifest_id": "fixture", "source_git_commit": "fixture", "phase": phase,
                          "stream": stream["stream"], "episode": case["episode"], "task": case["task"], "seed": case["seed"], "method": method,
                          "state_before": {"cache": None}, "state_after": {"cache": None}, "decisions": [], "trace": [], "outcome": outcome}
                records.append(record); rows.append(run.compact_case(record, stream))
    manifest = {"config": {"methods": list(METHODS), "tasks": ["push-v3", "reach-v3", "door-open-v3"]}, "population_oracle": {phase: specs}}
    return manifest, records, rows


class ChronologicalStatisticsTest(unittest.TestCase):
    def test_all_methods_failures_and_stream_intervals_match_independent_arithmetic(self):
        manifest, records, rows = fixture("MAIN")
        independently_built, expected = reconstruct(manifest, "MAIN", iter(records))
        self.assertEqual(independently_built, rows)
        count, error = compare(statistics(rows, "MAIN"), expected)
        self.assertGreater(count, 1000); self.assertLess(error, 1e-10)
        self.assertEqual(expected["methods"]["UNCERTAINTY4"]["cases"], 432)
        self.assertEqual(expected["methods"]["UNCERTAINTY4"]["stops"], 1)
        self.assertEqual(expected["methods"]["UNCERTAINTY4"]["successes"], 431)

    def test_smoke_has_no_performance_promotion_and_missing_rows_are_rejected(self):
        manifest, records, rows = fixture("SMOKE")
        _, independently_built = reconstruct(manifest, "SMOKE", records)
        compare(statistics(rows, "SMOKE"), independently_built)
        self.assertEqual(independently_built["contrasts"], [])
        self.assertFalse(independently_built["algorithm_novelty_established"])
        with self.assertRaises(ValueError): statistics(rows[:-1], "SMOKE")

    def test_registered_configuration_sources_and_reservations_are_exact(self):
        config = run.read(run.CONFIG); run.validate(config)
        for key in ("source_bridge_manifest", "source_bridge_audit"):
            self.assertEqual(len(bytes.fromhex(config[key+"_sha256"])), 32)
            self.assertEqual(run.sha(run.ROOT/config[key]), config[key+"_sha256"])
        changed = deepcopy(config); changed["main"]["reserved"] = [17431, 17999]
        with self.assertRaises(ValueError): run.validate(changed)


if __name__ == "__main__": unittest.main()

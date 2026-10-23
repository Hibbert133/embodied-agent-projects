import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np

from src.probemem.probe_support import CONTEXTS, CORRECTIONS, ProbeNullPerturbation, candidate_plan, summarize_support
from src.probe.directional import PROBE_DIRECTIONS, ProbeResult
from scripts import run_probe_support as runner


class ProbeSupportTest(unittest.TestCase):
    def test_original_probe_support_is_exactly_indistinguishable(self):
        for _, vector in PROBE_DIRECTIONS:
            command = vector * np.float32(.2)
            for coefficient in CONTEXTS.values():
                np.testing.assert_array_equal(ProbeNullPerturbation(coefficient).apply(command), command)

    def test_alternative_support_separates_and_other_axes_unchanged(self):
        for amplitude in (-.8, .8):
            command = np.array([amplitude, .17, -.4, 1], dtype=np.float32)
            outputs = [ProbeNullPerturbation(k).apply(command) for k in CONTEXTS.values()]
            self.assertLess(outputs[0][0], outputs[1][0])
            self.assertLess(outputs[1][0], outputs[2][0])
            for output in outputs:
                np.testing.assert_array_equal(output[1:], command[1:])

    def test_nonlinear_term_bounded_outside_actuator_range(self):
        fault = ProbeNullPerturbation(.5)
        for value in (-4., -1., 1., 4.):
            command = np.array([value, 0, 0, 0], dtype=np.float32)
            self.assertAlmostEqual(float(fault.apply(command)[0])-value, .48, places=6)

    def test_rejects_unregistered_fault_and_nonfinite_actions(self):
        for coefficient in (.3, float("nan"), True):
            with self.assertRaises(ValueError):
                ProbeNullPerturbation(coefficient)
        with self.assertRaises(ValueError):
            ProbeNullPerturbation(.5).apply(np.array([float("inf"), 0, 0, 0]))

    def test_candidates_are_fixed_bounded_and_executable(self):
        for name, x in CORRECTIONS.items():
            p = candidate_plan(name)
            self.assertEqual(p.correction, (x, 0., 0., 0.))
            self.assertTrue(p.requires_fresh_verification)
            self.assertEqual(p.schedule, "whole")

    def test_synthetic_collection_audit_and_tampering(self):
        c = json.loads(runner.CONFIG.read_text())
        m = {"config": c, "source_git_commit": "test", "experiment_run_id": "synthetic", "input_sha256": {}}
        m["manifest_id"] = runner.manifest_digest(m)
        env = SimpleNamespace(reset=lambda **kw: (np.zeros(39), {}), close=lambda: None)

        def probes(*args, seed, perturbation_factory, magnitude, **kwargs):
            fault = perturbation_factory()
            rows = []
            for direction, vector in PROBE_DIRECTIONS:
                command = vector * np.float32(magnitude)
                end = tuple(float(x) for x in fault.apply(command)[:3] * .04)
                rows.append(ProbeResult(seed, direction, tuple(float(x) for x in command), 4,
                                        (0., 0., 0.), end, end, .2, 0.))
            return rows

        def execute(**kwargs):
            coefficient = kwargs["fault"].coefficient
            correction = kwargs["plan"].correction[0]
            success = bool(np.sign(correction) == -np.sign(coefficient))
            return {"success": success, "steps": 10,
                    "verification_status": "ACCEPTED" if success else "REJECTED",
                    "initial_state_hash": kwargs["expected_initial_hash"]}

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(m))
            with patch.object(runner, "check_clean"), patch.object(runner, "git", return_value="test"), \
                 patch.object(runner, "create_push_environment", return_value=env), \
                 patch.object(runner, "run_symmetric_probes", side_effect=probes), \
                 patch.object(runner, "_execute", side_effect=execute) as calls, patch("builtins.print"):
                runner.run(path)
                self.assertEqual(calls.call_count, 144)
                with self.assertRaises(FileExistsError):
                    runner.run(path)
            result = runner.audit(path)
            self.assertEqual(result["statistics"]["witness_count"], 16)
            self.assertEqual(result["statistics"]["best_context_blind_successes_oracle"], 16)
            self.assertEqual(result["statistics"]["context_aware_successes_oracle"], 48)
            self.assertEqual(result["physical_steps"], 2976)
            data_path = path.parent / "outcomes.jsonl"
            original = data_path.read_text()
            data = [json.loads(x) for x in original.splitlines()]
            data[0]["initial_state_hash"] = "forged"
            data_path.write_text("\n".join(json.dumps(x) for x in data))
            with self.assertRaisesRegex(ValueError, "initial state"):
                runner.audit(path)
            data_path.write_text(original)
            plan_path = path.parent / "plans.json"
            plans = json.loads(plan_path.read_text())
            plans["plans"]["zero"]["correction"][0] = .1
            plan_path.write_text(json.dumps(plans))
            with self.assertRaisesRegex(ValueError, "plans changed"):
                runner.audit(path)

    def test_population_missing_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "incomplete"):
            summarize_support([], [], range(8500, 8516))


if __name__ == "__main__":
    unittest.main()

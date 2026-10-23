import json
from pathlib import Path
import unittest
from unittest.mock import patch

from src.analysis import movement_model_source_v1 as source
from src.probe.movement_model_binding_v1 import BoundMovementModelV1, canonical, estimate_bound_movement
from tests.test_movement_history_reference_v1 import synthetic_history

ROOT = Path(__file__).resolve().parents[1]


class MovementModelBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.models, cls.receipt = source.load_bank(ROOT)

    def test_actual_bank_binds_all_three_tasks_and_preserves_negative_qualification(self):
        self.assertEqual(set(self.models), {"push-v3", "reach-v3", "door-open-v3"})
        self.assertFalse(self.receipt["historical_precision_gate_passed"])
        self.assertFalse(self.receipt["physical_transfer_qualified"])
        self.assertEqual(self.receipt["new_model_fits"], 0)

    def test_task_swapping_cannot_be_hidden_by_reencoding_or_rehashing(self):
        for task in self.models:
            foreign = next(v for t, v in self.models.items() if t != task)
            with self.subTest(task=task), self.assertRaises(ValueError):
                BoundMovementModelV1(task, canonical(foreign.decoded()))

    def test_poisoned_changed_and_duplicate_fields_are_rejected(self):
        original = self.models["push-v3"]
        for key, value in (("future_success", True), ("training_samples", 99), ("physical_response_qualified", True)):
            model = original.decoded(); model[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                BoundMovementModelV1("push-v3", canonical(model))
        duplicate = original.model_json[:-1] + ',"training_samples":2150}'
        with self.assertRaises(ValueError):
            BoundMovementModelV1("push-v3", duplicate)

    def test_mutable_decode_does_not_modify_frozen_reference(self):
        reference = self.models["push-v3"]
        value = reference.decoded()
        value["coefficients"][0][0] += 1
        self.assertNotEqual(value, reference.decoded())
        self.assertEqual(json.loads(reference.model_json), reference.decoded())

    def test_wrong_task_history_fails_before_any_parameter_fit(self):
        history, _ = synthetic_history()
        with patch("src.probe.movement_model_binding_v1.estimate_movement", side_effect=AssertionError("must not fit")):
            with self.assertRaises(ValueError):
                estimate_bound_movement(self.models["reach-v3"], history)
            with self.assertRaises(ValueError):
                estimate_bound_movement(self.models["push-v3"].decoded(), history)

    def test_only_exact_matching_coefficients_and_visible_history_are_forwarded(self):
        history, _ = synthetic_history()
        with patch("src.probe.movement_model_binding_v1.estimate_movement", return_value={"sentinel": 1}) as fit:
            result = estimate_bound_movement(self.models["push-v3"], history)
        self.assertEqual(result, {"sentinel": 1})
        self.assertEqual(fit.call_args.args, (self.models["push-v3"].decoded(), history))

    def test_changed_archive_fails_before_loading_models(self):
        original = source.sha
        for changed in (source.SOURCE + "/models.json", source.AUDIT, source.SOURCE + "/TRAIN.jsonl.gz"):
            def digest(path):
                return "0"*64 if Path(path).resolve() == (ROOT / changed).resolve() else original(path)
            with self.subTest(changed=changed), patch.object(source, "sha", side_effect=digest), self.assertRaises(ValueError):
                source.load_bank(ROOT)

    def test_source_fees_keep_all_stages_and_unknown_factory_costs(self):
        costs = self.receipt["costs"]
        self.assertEqual(costs["direct_source_collection"]["environment_steps"], 21010)
        self.assertEqual(costs["legacy_comparison_source"]["environment_steps"], 2304)
        self.assertEqual(costs["known_full_source_environment_steps"], 23314)
        self.assertEqual(costs["known_full_source_controlled_resets"], 432)
        self.assertIsNone(costs["direct_source_collection"]["all_reset_calls"])
        self.assertIsNone(costs["direct_source_collection"]["simulation_frames"])


if __name__ == "__main__":
    unittest.main()

from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from src.analysis import movement_task_design_v1 as design
from src.analysis import movement_task_io_v1 as io
from scripts import collect_movement_task_v1 as collector


class MovementTaskDesignTests(unittest.TestCase):
    def test_historical_group_differences_reproduce_power_proxy_without_new_data(self):
        value = design.planning(Path(__file__).resolve().parents[1])
        self.assertAlmostEqual(value["paired_stream_sd"], 51.20785077975331)
        self.assertEqual((value["source_streams"], value["normal_approximation_required_groups"], value["frozen_groups"]), (16,52,54))
        self.assertEqual(io.read(io.PLANNING), value)
        self.assertEqual(value["new_task_outcomes_used"], 0)

    def test_exact_fresh_allocation_is_grouped_and_boundary_balanced(self):
        rows = design.population();self.assertEqual(len(rows), 1296)
        self.assertEqual(len({(r["unit"],r["variant"]) for r in rows}), 1296)
        self.assertEqual({r["seed"] for r in rows}, set(range(25000,25162)))
        for boundary in (16,32,64):
            self.assertEqual(len({r["unit"]//3 for r in rows if r["planned_boundary"] == boundary}), 18)
        for unit in range(162):
            self.assertEqual([r["variant"] for r in rows if r["unit"] == unit], list(design.VARIANTS))

    def test_operator_is_shared_within_group_and_changes_only_in_changed_condition(self):
        rows = design.population()
        for group in range(design.GROUPS):
            subset = [r for r in rows if r["unit"]//3 == group]
            changed = [design.destination(r) for r in subset if r["variant"].startswith("CHANGED_")]
            self.assertTrue(all(v == changed[0] for v in changed))
            self.assertTrue(all(design.destination(r) == design.INITIAL for r in subset if r["variant"].startswith("UNCHANGED_")))
        self.assertNotEqual(design.destination(rows[4]), design.destination(rows[28]))

    def test_config_rejects_missing_cases_changed_budgets_and_posthoc_contrast(self):
        original = io.read(io.CONFIG);io.validate(original)
        for field, value in (("executions",1295),("maximum_environment_steps",648001),("bootstrap_seed",12),
                             ("primary",["MOVE_ARX_KEEP","DIRECT_C8"]),("reserved_seeds",[25161,25399])):
            altered = deepcopy(original);altered[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):io.validate(altered)

    def test_caps_cover_all_methods_factory_resets_and_full_task_continuations(self):
        config = io.expected_config()
        self.assertEqual(config["maximum_environment_steps"], config["executions"]*500)
        self.assertEqual(config["maximum_controlled_resets"], config["executions"])
        self.assertEqual(config["maximum_simulation_frames"], config["executions"]*(51*500+500*5))

    def test_missing_committed_audit_blocks_preparation_before_environment_creation(self):
        def git(*args):
            if args == ("ls-files",):return "\n".join(n for n in io.REQUIRED if n != "scripts/audit_movement_task_v1.py")
            return ""
        with patch.object(io,"git",git), patch.object(collector,"create_task_environment",side_effect=AssertionError("no physics")), self.assertRaisesRegex(ValueError,"independent audits"):
            collector.prepare()

    def test_history_source_and_task_models_load_with_negative_transfer_status_preserved(self):
        previous, models, references, receipt = io.sources(io.read(io.CONFIG))
        self.assertEqual(set(models), set(design.TASKS));self.assertEqual(set(references), set(design.TASKS))
        self.assertEqual(previous["manifest_id"], io.expected_config()["source_manifest_id"])
        self.assertFalse(receipt["physical_transfer_qualified"])


if __name__ == "__main__":unittest.main()

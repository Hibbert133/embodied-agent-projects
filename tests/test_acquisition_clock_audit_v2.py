import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import run_acquisition_value as run
from scripts.audit_acquisition_value_clock_v2 import compiled_clock_units


class ClockAuditRepairTest(unittest.TestCase):
    def test_compiles_three_bound_models_without_reset_or_step(self):
        import mujoco
        manifest={"library_source_sha256":run.library_sources()}
        with patch.object(mujoco,"mj_step",side_effect=AssertionError("no robot stepping in clock audit")), \
             patch.object(mujoco,"MjData",side_effect=AssertionError("no robot state construction")):
            result=compiled_clock_units(manifest)
        self.assertEqual(set(result),set(run.TASKS))
        for value in result.values():
            self.assertEqual(value["compiled_timestep_seconds"],.0025)
            self.assertEqual(value["env_step_seconds"],.0125)
    def test_changed_model_xml_hash_is_rejected(self):
        manifest={"library_source_sha256":run.library_sources()}
        key="metaworld/assets/sawyer_xyz/sawyer_push_v3.xml"
        manifest["library_source_sha256"][key]="0"*64
        with self.assertRaises(ValueError):compiled_clock_units(manifest)


if __name__=="__main__":unittest.main()

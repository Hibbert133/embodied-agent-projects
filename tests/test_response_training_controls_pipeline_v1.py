"""Pure-file separation, timeout, complete accounting and whole-group summaries."""
from copy import deepcopy
from pathlib import Path
import json
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
import numpy as np
import numpy.testing

from src.analysis import response_training_controls_io_v1 as allocation
from src.analysis import response_training_controls_evaluation_v1 as evaluation
from src.analysis import observable_history_io_v1 as io
from src.probe import response_training_controls_v1 as core
from scripts import run_response_training_controls_v1 as runner
from scripts.audit_response_training_controls_v1 import independent_arrays, independent_aggregate
from tests.test_response_training_controls_v1 import trajectory


def entries():
    result = []
    for source in io.PROGRAMS:
        for task in io.TASKS:
            ts = []
            for group in range(18):
                for context in ("NOMINAL", "RANDOM"):
                    t = core.public_dict(trajectory(8, f"TRAIN/{group:02d}/{task}/{context}/{source}"))
                    t["task"] = task; ts.append(t)
            result.append({"source_bank": source, "task": task, "trajectories": ts})
    return result


def row(group, variant="F20_ISO_W16", value=.001, source="FEEDBACK8", replicate=0):
    return {"role": "DEV", "group": group, "task": "push-v3", "context": "NOMINAL", "program": "FEEDBACK8", "variant": variant,
        "case_id": str(group), "source": source, "kind": "GRU", "replicate": replicate, "stage": "POST_TASK", "rmse_m": value, "mse_m2": value**2}


class PipelineControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = entries()

    def test_fit_dev_split_is_complete_disjoint_and_grouped(self):
        fit, dev = (allocation.bundle(self.source, role) for role in ("FIT", "DEV"))
        a = {t["trajectory_id"] for e in fit["entries"] for t in e["trajectories"]}
        b = {t["trajectory_id"] for e in dev["entries"] for t in e["trajectories"]}
        self.assertEqual((len(a), len(b)), (144, 72)); self.assertFalse(a & b)
        self.assertEqual({int(x.split("/")[1]) for x in a}, set(range(12)))
        self.assertEqual({int(x.split("/")[1]) for x in b}, set(range(12, 18)))

    def test_wrong_role_schema_private_fields_and_dev_fit_poison_rejected(self):
        data = allocation.bundle(self.source, "FIT")
        mutations = []
        bad = deepcopy(data); bad["schema"] = "RESPONSE_TRAINING_CONTROLS_DEV_V1"; mutations.append(bad)
        bad = deepcopy(data); bad["entries"][0]["seed"] = 17; mutations.append(bad)
        bad = deepcopy(data); bad["entries"][0]["trajectories"][0]["trajectory_id"] = "TRAIN/12/push-v3/NOMINAL/FEEDBACK8"; mutations.append(bad)
        bad = deepcopy(data); bad["entries"][0]["trajectories"][0]["actual_noise"] = [0, 0]; mutations.append(bad)
        for bad in mutations:
            with tempfile.TemporaryDirectory() as d:
                p = Path(d)/"fit_public.json"; p.write_text(json.dumps(bad), encoding="utf-8")
                with self.assertRaises(ValueError): allocation.read_bundle(p, "FIT")

    def test_duplicate_source_and_trajectory_ids_rejected(self):
        bad = deepcopy(self.source); bad[0]["trajectories"][1] = bad[0]["trajectories"][0]
        with self.assertRaises(ValueError): allocation.bundle(bad, "FIT")
        bad = deepcopy(self.source); bad[0]["trajectories"][0]["split"] = "TEST"
        with self.assertRaises(ValueError): allocation.bundle(bad, "DEV")

    def test_guard_blocks_network_simulator_child_and_protected_data(self):
        with allocation.numeric_guard() as counts:
            with self.assertRaises(RuntimeError): __import__("metaworld")
            with self.assertRaises(RuntimeError): socket.socket()
            with self.assertRaises(RuntimeError): subprocess.Popen(["not-a-real-executable"])
            with self.assertRaises(RuntimeError): (allocation.SOURCE/"test/never.json").open()
            socket.gethostname()  # Local metadata query; not a transport attempt.
        self.assertEqual(counts["attempted_network_calls"], 1)
        self.assertEqual(counts["simulator_import_attempts"], 1)
        self.assertEqual(counts["child_process_attempts"], 1)
        self.assertEqual(counts["forbidden_data_reads"], 1)

    def test_training_guard_rejects_dev_and_original_raw_sources(self):
        with allocation.numeric_guard(allow_training=True) as counts:
            for p in (allocation.PUBLIC_SOURCE, allocation.SOURCE/"train/cases.jsonl.gz", Path("dev_public.json"), Path("evaluation_metadata.json")):
                with self.assertRaises(RuntimeError): p.open()
        self.assertEqual(counts["forbidden_data_reads"], 4)

    def test_timeout_is_terminal_and_not_retried(self):
        process = Mock(pid=123); process.wait.side_effect = [subprocess.TimeoutExpired("frozen", 1), -9]
        with tempfile.TemporaryDirectory() as d, patch.object(runner.subprocess, "Popen", return_value=process) as popen:
            with self.assertRaises(ValueError): runner.child(Path(d), "train", 1)
            receipt = io.read(Path(d)/"train_process.json")
            self.assertTrue(receipt["timed_out"]); self.assertFalse(receipt["retry"])
            self.assertIsNotNone(receipt["scientific_optimizer_steps_on_hard_timeout"])
            process.kill.assert_called_once(); self.assertEqual(popen.call_count, 1)

    def test_failed_child_is_retained_without_substitution(self):
        process = Mock(pid=456); process.wait.return_value = 7
        with tempfile.TemporaryDirectory() as d, patch.object(runner.subprocess, "Popen", return_value=process) as popen:
            with self.assertRaises(ValueError): runner.child(Path(d), "train", 10)
            self.assertEqual(io.read(Path(d)/"train_process.json")["returncode"], 7)
            self.assertEqual(popen.call_count, 1)

    def test_sources_and_initializations_do_not_become_replicates(self):
        rows = [row(12, value=v, source=source, replicate=rep) for v, (source, rep) in enumerate((s, r) for s in io.PROGRAMS for r in range(3))]
        rows.append(row(13, value=9))
        a = evaluation.aggregate(rows, ("variant",))
        b = independent_aggregate(rows, ("variant",))
        self.assertEqual(a, b)
        self.assertEqual(a[0]["allocated_trajectories"], 2)
        self.assertEqual(a[0]["rmse_m"], (2.5+9)/2)

    def test_missing_short_stage_is_null_and_registered(self):
        meta = {"case_id": "SHORT", "group": 12, "task": "push-v3", "context": "NOMINAL", "program": "FEEDBACK8", "role": "DEV", "labels": ["FIXED_PROBE"]}
        model = {"source": "FEEDBACK8", "kind": "LINEAR", "feature": "F20"}
        rows = evaluation.trajectory_rows(meta, model, "x", np.zeros((1, 2)), np.ones((1, 2)))
        post = next(r for r in rows if r["stage"] == "POST_TASK")
        self.assertIsNone(post["rmse_m"]); self.assertEqual(post["responses"], 0); self.assertIsNotNone(post["missing_reason"])
        meta["labels"] = []
        self.assertTrue(all(r["rmse_m"] is None for r in evaluation.trajectory_rows(meta, model, "x", np.empty((0, 2)), np.empty((0, 2)))))

    def test_primary_whole_group_interval_uses_all_six_groups(self):
        rows = [row(g, variant=v, value=value, source=s, replicate=r) for g in range(12, 18)
            for v, value in (("F20_ISO_W16", .001), ("F43_AXIS_W16", .002)) for s in io.PROGRAMS for r in range(3)]
        result = evaluation.summarize(rows)
        self.assertTrue(result["primary"]["all_six_groups_available"])
        np.testing.assert_allclose(result["primary"]["group_bootstrap_95_m"], [-.001, -.001])
        self.assertEqual(result["independent_qualification"], "NOT_ATTEMPTED")
        for r in rows:
            if r["group"] == 12: r["rmse_m"] = r["mse_m2"] = None
        self.assertFalse(evaluation.summarize(rows)["primary"]["all_six_groups_available"])

    def test_independent_feature_reconstruction_all_families(self):
        t = trajectory()
        for feature in core.FEATURES:
            x, y = independent_arrays(t, feature)
            np.testing.assert_array_equal(x, core.feature_array(t, feature))
            self.assertEqual(y.shape, (28, 2))

    def test_full_cost_grid_and_no_selection_rule(self):
        cfg = allocation.expected_config()
        self.assertEqual(cfg["neural_models"], 6*2*2*2*3)
        self.assertEqual(cfg["optimizer_updates"], cfg["neural_models"]*cfg["updates"])
        self.assertEqual(cfg["linear_models"], 6*3)
        self.assertTrue(cfg["candidate_selection"].startswith("NONE"))
        self.assertEqual(sum(cfg[k] for k in ("new_environment_steps", "new_all_resets", "new_physical_frames", "new_api_calls")), 0)


if __name__ == "__main__":
    unittest.main()

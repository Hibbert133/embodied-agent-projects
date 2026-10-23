from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.generate_heldout_manifest import (
    ROOT,
    build_manifest,
    canonical_manifest_id,
    write_manifest,
)


class HeldoutManifestTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config_path = ROOT / "configs/autoresearch/heldout_allocation_v1.json"
        self.config = json.loads(self.config_path.read_text(encoding="utf-8"))

    def build(self):
        return build_manifest(
            self.config,
            config_path=self.config_path,
            source_commit="a" * 40,
            timestamp_utc="2026-07-31T00:00:00+00:00",
            implementation_hashes={"matching": "b" * 40},
            frozen_source_artifacts={
                "passive_tuning_cases": {
                    "path": "outputs/example.csv",
                    "sha256": "c" * 64,
                }
            },
            dependency_versions={"python": "3.10.0", "metaworld": "3.1.1"},
        )

    def test_manifest_id_is_canonical_and_records_frozen_protocol(self) -> None:
        manifest = self.build()
        content = {
            key: value
            for key, value in manifest.items()
            if key not in {"manifest_id", "experiment_run_id"}
        }
        self.assertEqual(manifest["manifest_id"], canonical_manifest_id(content))
        self.assertEqual(manifest["seed_range"], {
            "start": 330, "stop_inclusive": 339, "count": 10
        })
        self.assertEqual(manifest["allocation"]["threshold"], 0.91612970415368)
        self.assertEqual(manifest["probe_max_environment_steps"], 64)
        self.assertIn("heldout_runner", manifest["implementation_paths"])
        self.assertIn("passive_tuning_cases", manifest["frozen_source_artifacts"])
        self.assertIn(manifest["manifest_id"][:12], manifest["experiment_run_id"])
        self.assertTrue(manifest["experiment_run_id"].startswith("heldout_20260731T000000Z_"))

    def test_write_refuses_to_overwrite_run_directory(self) -> None:
        manifest = self.build()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = write_manifest(manifest, root)
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8"))["manifest_id"],
                manifest["manifest_id"],
            )
            with self.assertRaises(FileExistsError):
                write_manifest(manifest, root)


if __name__ == "__main__":
    unittest.main()

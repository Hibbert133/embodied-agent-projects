"""Delivery guards: real process lifetime and immutable full-population records."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

PATH = Path(__file__).resolve().parents[1] / "outputs/chronological_cache_reference/validation_v1/finish_after_collector_v2.py"
SPEC = importlib.util.spec_from_file_location("chronological_delivery_job", PATH)
job = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(job)


class DeliveryGuardTest(unittest.TestCase):
    def test_dotnet_seven_digit_timestamp_and_timezone_are_exact(self):
        expected = 1792151617208514000
        self.assertEqual(job.creation_unix_ns("2026-10-16T11:53:37.2085140+00:00"), expected)
        self.assertEqual(job.creation_unix_ns("2026-10-16T19:53:37.208514+08:00"), expected)
        self.assertEqual(job.creation_unix_ns("2026-10-16T11:53:37.2085147Z"), expected + 700)
        with self.assertRaises(ValueError):
            job.creation_unix_ns("2026-10-16T11:53:37.208514")

    @unittest.skipUnless(sys.platform == "win32", "Windows process-handle contract")
    def test_live_process_handle_preserves_nonzero_terminal_exit(self):
        child = subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.buffer.read(1); sys.exit(7)"], stdin=subprocess.PIPE)
        witness = None
        try:
            witness = job.ProcessWitness(child.pid)
            self.assertIsNone(witness.poll())
            child.stdin.write(b"x")
            child.stdin.flush()
            self.assertEqual(child.wait(timeout=10), 7)
            self.assertEqual(witness.poll(1000), 7)
        finally:
            if witness is not None:
                witness.close()
            if child.poll() is None:
                child.kill()
                child.wait(timeout=10)
            child.stdin.close()

    def test_zero_exit_does_not_replace_complete_population_or_hashes(self):
        identity = {"experiment_run_id": "fixture", "manifest_id": "a" * 64, "source_git_commit": "b" * 40}
        manifest = {**identity, "config": {"main": {"executions": 2}}}
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            summary = {**identity, "phase": "MAIN", "status": "COMPLETED_REFERENCE", "executions": 2, "cases": [{}, {}]}
            status = {**summary}
            for name, value in (("summary.json", summary), ("status.json", status)):
                (folder / name).write_text(json.dumps(value), encoding="utf-8")
            completion = {**identity, "phase": "MAIN", "status": "COMPLETED_REFERENCE",
                          "artifact_sha256": {name: job.sha(folder / name) for name in ("summary.json", "status.json")}}
            (folder / "completion.json").write_text(json.dumps(completion), encoding="utf-8")
            self.assertEqual(job.validate_completed(manifest, folder, 0), summary)
            with self.assertRaisesRegex(ValueError, "did not exit"):
                job.validate_completed(manifest, folder, 7)
            status["status"] = "RUNNING"
            (folder / "status.json").write_text(json.dumps(status), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "complete main"):
                job.validate_completed(manifest, folder, 0)
            status["status"] = "COMPLETED_REFERENCE"
            (folder / "status.json").write_text(json.dumps(status), encoding="utf-8")
            summary["cases"].pop()
            (folder / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "full registered"):
                job.validate_completed(manifest, folder, 0)
            summary["cases"].append({"tampered": True})
            (folder / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "raw artifact differs"):
                job.validate_completed(manifest, folder, 0)


if __name__ == "__main__":
    unittest.main()

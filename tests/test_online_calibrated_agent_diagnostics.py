import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.analyze_online_calibrated_agent_diagnostics import diagnostics


class OnlineResourceDiagnosticsTest(unittest.TestCase):
    def prepare(self, directory, usage):
        root = Path(directory)
        identity = {"experiment_run_id": "synthetic", "manifest_id": "synthetic", "source_git_commit": "synthetic"}
        manifest = root/"manifest.json"
        manifest.write_text(json.dumps({**identity, "config": {"api": {"max_tokens": 512}}}))
        api = root/"api_audit.json"
        api.write_text(json.dumps({"attempts": [{"attempt": 1, "stage": "HEALTH", "status": "VALID_RESPONSE",
                                                "usage": usage, "raw_response": "{}"}]}))
        audit = root/"primary_audit.json"
        audit.write_text(json.dumps({**identity, "integrity": "PASSED", "artifact_sha256": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (manifest, api)}}))
        return manifest, audit, api

    def test_short_visible_return_does_not_hide_excess_reported_tokens(self):
        with tempfile.TemporaryDirectory() as directory:
            m, a, _ = self.prepare(directory, {"input_tokens": 10, "output_tokens": 3700})
            result = diagnostics(m, a)
            self.assertEqual(result["attempts_above_requested_reported_output"], [1])
            self.assertIs(result["all_reported_output_within_limit"], False)
            self.assertEqual(result["per_attempt"][0]["visible_response_utf8_bytes"], 2)

    def test_unknown_timeout_usage_does_not_pass_limit_check(self):
        with tempfile.TemporaryDirectory() as directory:
            m, a, _ = self.prepare(directory, {})
            result = diagnostics(m, a)
            self.assertIsNone(result["all_reported_output_within_limit"])
            self.assertEqual(result["attempts_without_output_usage"], [1])

    def test_changed_raw_usage_after_audit_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            m, a, raw = self.prepare(directory, {"output_tokens": 3700})
            raw.write_text(raw.read_text().replace("3700", "100"))
            with self.assertRaisesRegex(ValueError, "changed"):
                diagnostics(m, a)


if __name__ == "__main__":
    unittest.main()

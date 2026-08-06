import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SciAgentSyntheticAuditTest(unittest.TestCase):
    def test_script_is_explicitly_metric_ineligible(self):
        text = (ROOT / "scripts/run_probemem_sciagent_synthetic_audit.py").read_text(encoding="utf-8")
        self.assertIn('"research_metric_eligible": False', text)
        self.assertIn('"principle_after_counterexample"', text)


if __name__ == "__main__": unittest.main()

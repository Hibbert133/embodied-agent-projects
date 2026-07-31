"""Tests for coverage-aware memory analysis helpers."""

from __future__ import annotations

import unittest

from scripts.analyze_probemem_coverage_aware_memory import _percentile_90


class ProbeMemCoverageAwareMemoryAnalysisTest(unittest.TestCase):
    def test_p90_uses_deterministic_nearest_rank(self) -> None:
        self.assertEqual(_percentile_90([float(i) for i in range(1, 11)]), 9.0)
        self.assertEqual(_percentile_90([3.0]), 3.0)


if __name__ == "__main__":
    unittest.main()

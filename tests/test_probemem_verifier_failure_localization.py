import csv
import json
from pathlib import Path
import tempfile
import unittest

from scripts.audit_probemem_verifier_failure_localization import audit


COMP = "BOUNDED_PLANAR_COMPENSATION"
RETRY = "INDEPENDENT_STOCHASTIC_RETRY"


class VerifierFailureLocalizationTest(unittest.TestCase):
    def test_trigger_overlap_and_effects_are_descriptive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            decisions = [
                self._decision(21, "WITHIN_AMBIGUITY_BAND", True, False),
                self._decision(22, "WITHIN_AMBIGUITY_BAND|RECENT_SIMILAR_CONTRADICTION", True, True),
                self._decision(23, "CLEAR_DEFAULT", False, False),
            ]
            candidates = [
                self._candidate(21, COMP, "ACCEPTED"), self._candidate(21, RETRY, "REJECTED"),
                self._candidate(22, COMP, "REJECTED"), self._candidate(22, RETRY, "ACCEPTED"),
                self._candidate(23, COMP, "ACCEPTED"), self._candidate(23, RETRY, "REJECTED"),
            ]
            self._csv(root / "decisions.csv", decisions)
            self._csv(root / "candidate_outcomes.csv", candidates)
            result = audit(root)
            self.assertEqual(result["verifier_calls"], 2)
            self.assertEqual(result["trigger_counts_nonexclusive"]["WITHIN_AMBIGUITY_BAND"], 2)
            self.assertEqual(result["trigger_counts_nonexclusive"]["RECENT_SIMILAR_CONTRADICTION"], 1)
            self.assertEqual(result["authorized_override_effects"], {"HELPFUL": 1})
            self.assertEqual(result["blocked_alternative_effects"], {"HARMFUL": 1})

    @staticmethod
    def _decision(episode, reasons, called, override):
        return {
            "method": "BUDGETED_VERIFIER", "episode_id": episode, "seed": 4700 + episode,
            "admission_reasons": reasons, "verifier_called": called,
            "default_skill": COMP, "override_applied": override,
            "override_reason": "OVERRIDE_AUTHORIZED" if override else "ALTERNATIVE_NOT_BETTER",
        }

    @staticmethod
    def _candidate(episode, skill, status):
        return {"episode_id": episode, "candidate_skill": skill, "verification_status": status}

    @staticmethod
    def _csv(path: Path, rows: list[dict]) -> None:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()

from unittest import TestCase
from src.analysis.occam_training_namespace_diagnostic_v1 import attempt,COLLECTOR,PHASES


class NamespaceDiagnosticTests(TestCase):
    def test_original_phase_header_rejects_all_lifecycle_and_command_phases(self):
        source=COLLECTOR.read_bytes()
        for phase in PHASES:
            r=attempt(source,dict(phase='NATIVE',seed=1),dict(phase=phase));self.assertTrue(r['rejected']);self.assertEqual(r['journal_emissions'],0)

    def test_illustrative_cohort_header_preserves_payload_phase(self):
        for phase in PHASES:
            r=attempt(COLLECTOR.read_bytes(),dict(cohort='NATIVE',seed=1),dict(phase=phase))
            self.assertFalse(r['rejected']);self.assertEqual(r['record']['cohort'],'NATIVE');self.assertEqual(r['record']['phase'],phase)

    def test_foreign_seed_or_cohort_still_rejected(self):
        for payload in (dict(seed=2,phase='CONTROL'),dict(cohort='TRAIN',phase='CONTROL')):
            r=attempt(COLLECTOR.read_bytes(),dict(cohort='NATIVE',seed=1),payload);self.assertTrue(r['rejected'])

    def test_matching_owner_does_not_override_lifecycle_value(self):
        r=attempt(COLLECTOR.read_bytes(),dict(cohort='TRAIN',seed=1),dict(cohort='TRAIN',phase='GOAL_GENERATION'))
        self.assertFalse(r['rejected']);self.assertEqual(r['record']['phase'],'GOAL_GENERATION')

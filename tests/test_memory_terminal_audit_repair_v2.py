"""Actual saved-output audit regression, with no new main estimator evaluation."""
from pathlib import Path
from tempfile import TemporaryDirectory
from contextlib import ExitStack
from unittest.mock import patch
import shutil
import unittest
from src.analysis import memory_terminal_audit_v1 as old
from src.analysis import memory_terminal_audit_v2 as repaired
from src.analysis.response_qualification_io_v1 import ROOT

RUN=ROOT/'outputs/memory_terminal_reference/qualification_v1/memory_terminal_20261022T104925Z_a3d10e731af4'
DISABLED=('src.analysis.two_stage_terminal_dr_v1.estimate',
    'src.analysis.memory_terminal_qualification_v1.estimate',
    'src.analysis.memory_terminal_world_v1.atoms',
    'src.analysis.memory_terminal_world_v1.inputs',
    'src.analysis.memory_terminal_world_v1.true_q1',
    'src.analysis.memory_terminal_world_v1.true_q2',
    'src.analysis.memory_terminal_world_v1.target_truth')


class AuditRepairTests(unittest.TestCase):
    def test_frozen_reader_shadowing_failure_remains_reproducible(self):
        with self.assertRaisesRegex(UnboundLocalError,'rows'):
            old.audit(RUN/'manifest.json')

    def test_repair_only_renames_reader_and_two_references(self):
        source=Path(old.__file__).read_text(encoding='utf-8')
        wanted=source.replace('def rows(path):','def read_rows(path):').replace(
            "list(rows(out/'finite_atoms.jsonl'))", "list(read_rows(out/'finite_atoms.jsonl'))").replace(
            "iter(rows(out/'estimates.jsonl'))", "iter(read_rows(out/'estimates.jsonl'))")
        self.assertEqual(Path(repaired.__file__).read_text(encoding='utf-8'),wanted)
        self.assertEqual(wanted.count('read_rows('),3)

    def test_repaired_audit_checks_all_saved_output_with_main_functions_disabled(self):
        with TemporaryDirectory() as tmp,ExitStack() as stack:
            target=Path(tmp)
            for name in ('manifest.json','completion.json','finite_atoms.jsonl','estimates.jsonl','results.json','setting_summaries.csv'):
                shutil.copyfile(RUN/name,target/name)
            for name in DISABLED:
                stack.enter_context(patch(name,side_effect=AssertionError('Main numerical implementation used')))
            value=repaired.audit(target/'manifest.json')
            self.assertEqual(value['integrity'],'PASSED')
            self.assertEqual((value['finite_atoms'],value['estimate_rows'],value['exact_rational_identities'],value['both_wrong_cases_retained']),(44,2112,40,8))
            self.assertGreater(value['fields_checked'],100000)
            self.assertTrue((target/'audit.json').is_file())


if __name__=='__main__':unittest.main()

"""Presentation regression only, reading saved arrays; no simulator, fit or network."""
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from scripts import report_response_qualification_failure_v1 as old
from scripts import report_response_qualification_failure_v2 as current
from src.analysis.movement_diagnostic_guard_v1 import read_only_analysis_guard


class ReportTests(unittest.TestCase):
    def exercise(self,module):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/"reports").mkdir();data=root/"arrays";data.mkdir()
            for name in ("completion.json","independent_audit.json","group_summaries.json","training_geometry.json"):
                shutil.copyfile(module.OUTPUT/name,data/name)
            with patch.object(module,"ROOT",root),patch.object(module,"OUTPUT",data),read_only_analysis_guard():module.report()
            return (root/"reports/response_qualification_failure_analysis_v1_zh.md").read_text(encoding="utf-8")

    def test_preserved_export_failure_is_not_silently_rewritten(self):
        with self.assertRaises(TypeError):self.exercise(old)

    def test_v2_report_covers_full_populations_and_negative_result(self):
        result=self.exercise(current)
        for value in ("事后描述性分析","NOT_QUALIFIED","23,716","208,584","2,970","移动1–8","33–64","H1","H4"):self.assertIn(value,result)
        for task in ("push-v3","reach-v3","door-open-v3"):self.assertIn(task+"／UNCHANGED",result);self.assertIn(task+"／CHANGED",result)


if __name__=="__main__":unittest.main()

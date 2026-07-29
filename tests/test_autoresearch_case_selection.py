import csv,tempfile,unittest
from pathlib import Path
from scripts.run_budgeted_autoresearch import choose_cases,ensure_fresh_output
class CaseSelectionTest(unittest.TestCase):
 def test_completed_run_cannot_be_silently_overwritten(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d);(path/"candidate_summary.csv").write_text("done",encoding="utf-8")
   with self.assertRaisesRegex(RuntimeError,"completed run"):
    ensure_fresh_output(path)
 def test_selection_covers_labels_then_conditions_deterministically(self):
  rows=[
   {"case_id":"c1","initial_success":"False","counterfactual_label":"a","condition_id":"f1"},
   {"case_id":"c2","initial_success":"False","counterfactual_label":"b","condition_id":"f1"},
   {"case_id":"c3","initial_success":"False","counterfactual_label":"b","condition_id":"f2"},
   {"case_id":"c4","initial_success":"False","counterfactual_label":"c","condition_id":"f3"},
  ]
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"cases.csv"
   with p.open("w",newline="",encoding="utf-8") as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
   self.assertEqual(choose_cases(p),["c1","c3","c4","c2"])
if __name__=="__main__":unittest.main()

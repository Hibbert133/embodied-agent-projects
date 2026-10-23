import copy
import gzip
import json
from pathlib import Path
import unittest
from scripts.analyze_calibrated_tasks import verify
from scripts.run_calibrated_tasks import load_model

RUN=Path(__file__).resolve().parents[1]/"outputs/calibrated_tasks/development_v1/calibrated_tasks_20261013T111017Z_972172259b89"


class CalibratedTaskAuditTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest=json.loads((RUN/"manifest.json").read_text())
        cls.model,_=load_model(cls.manifest["config"])
        with gzip.open(RUN/"episodes.jsonl.gz","rt",encoding="utf-8") as handle: cls.records=[json.loads(x) for x in handle]
        cls.declarations=[json.loads(x) for x in (RUN/"decisions.jsonl").read_text().splitlines()]
        cls.status=json.loads((RUN/"status.json").read_text()); cls.summary=json.loads((RUN/"summary.json").read_text())

    def audit(self,records=None,declarations=None):
        return verify(self.manifest,records or self.records,declarations or self.declarations,self.status,self.summary,self.model)

    def tamper(self,method,edit):
        rows=list(self.records); i=next(i for i,r in enumerate(rows) if r["method"]==method)
        rows[i]=copy.deepcopy(rows[i]); edit(rows[i]); return rows

    def test_all_decisions_and_model_handoffs_replay(self):
        result=self.audit()
        self.assertEqual(result["replayed_decisions"],320)
        self.assertEqual(result["continuous_handoffs"],256)
        self.assertEqual(result["environment_resets"],320)
        self.assertEqual(result["integrity"],"PASSED")

    def test_different_prior_model_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"model association"):
            self.audit(self.tamper("PRIOR_AFFINE",lambda r:r.update(model_sha256="different")))

    def test_probe_task_rng_reseed_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"RNG reseed"):
            self.audit(self.tamper("CONT_NO_CORRECTION",lambda r:r["task_trace"][0].update(rng_before="reseeded")))

    def test_reset_at_task_handoff_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"discontinuity"):
            self.audit(self.tamper("CONT_NO_CORRECTION",lambda r:r["task_trace"][0].update(before_hash="reset")))

    def test_forged_prior_correction_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"decision replay"):
            self.audit(self.tamper("PRIOR_AFFINE",lambda r:r["decision"].update(correction=[0.,0.,0.,0.])))


if __name__=="__main__": unittest.main()

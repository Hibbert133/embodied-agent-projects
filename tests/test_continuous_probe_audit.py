"""Immutable real-log regression and deliberate handoff tampering."""
import copy
import json
from pathlib import Path
import unittest
from scripts.analyze_continuous_probe import verify

RUN=Path(__file__).resolve().parents[1]/"outputs/continuous_probe/development_v1/continuous_probe_20261013T103104Z_1092996bcf4f"


class ContinuousAuditTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest=json.loads((RUN/"manifest.json").read_text())
        cls.status=json.loads((RUN/"status.json").read_text())
        cls.summary=json.loads((RUN/"summary.json").read_text())
        cls.events=[json.loads(x) for x in (RUN/"events.jsonl").read_text().splitlines()]

    def audit(self,events=None):
        return verify(self.manifest,events or self.events,self.status,self.summary)

    def changed(self,kind,method,key,value):
        events=list(self.events)
        index=next(i for i,r in enumerate(events) if r["kind"]==kind and r["method"]==method)
        events[index]=copy.deepcopy(events[index]); events[index][key]=value
        return events

    def test_complete_log_replays_all_decisions_and_continuous_handoffs(self):
        r=self.audit()
        self.assertEqual(r["replayed_decisions"],160)
        self.assertEqual(r["continuous_handoffs"],96)
        self.assertEqual(r["environment_resets"],288)
        self.assertEqual(r["integrity"],"PASSED")

    def test_rng_reseed_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"RNG reseed"):
            self.audit(self.changed("step","CONT_NO_CORRECTION","rng_before","reseeded"))

    def test_state_reset_at_handoff_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"observation chain"):
            self.audit(self.changed("step","CONT_NO_CORRECTION","before_hash","initial-reset"))

    def test_step_counter_restart_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"counter"):
            self.audit(self.changed("step","CONT_NO_CORRECTION","host_calls",1))

    def test_forged_correction_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"decision replay"):
            self.audit(self.changed("decision","CONT_STATIC","decision",{"correction":[.2,0,0,0],"fit":None}))


if __name__=="__main__": unittest.main()

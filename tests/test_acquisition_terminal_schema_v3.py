import copy
import unittest
from scripts.audit_acquisition_value_v3 import verify_terminal


class TerminalSchemaAuditTest(unittest.TestCase):
    def fixtures(self):
        identity={"experiment_run_id":"run","manifest_id":"manifest","source_git_commit":"source"}
        counts={"episodes":2304,"cold_sources":24,"controlled_steps":378637,"controlled_resets":2328,"api_calls":0,"memory_writes":0}
        status={**identity,**counts,"status":"COMPLETED_TARGET_REPEAT_PASS"}
        summary={**status,"cold_sources":[{"source":i} for i in range(24)]}
        return status,summary,identity,counts
    def test_saved_list_and_counter_are_checked_in_their_actual_schemas(self):
        status,summary,identity,counts=self.fixtures()
        verify_terminal(status,summary,identity,counts,status["status"])
    def test_short_list_wrong_numeric_count_and_foreign_identity_fail(self):
        for field,value in (("cold_sources",[]),("cold_sources",24),("controlled_steps",0),("manifest_id","other")):
            status,summary,identity,counts=self.fixtures();summary[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):verify_terminal(status,summary,identity,counts,status["status"])
        status,summary,identity,counts=self.fixtures();status["cold_sources"]=23
        with self.assertRaises(ValueError):verify_terminal(status,summary,identity,counts,status["status"])


if __name__=="__main__":unittest.main()

import copy
import unittest
from scripts.report_acquisition_value import case
from tests import test_acquisition_value as fixture


class AcquisitionValueReportTest(unittest.TestCase):
    def test_trace_success_and_deadline_loss_are_recomputed(self):
        setup=fixture.AcquisitionValueTest();setup.setUp()
        with setup.fixtures():record=setup.branch("MID16_WIDE_KEEP")
        row=case(record)
        self.assertEqual(row["total_steps"],len(record["trace"]))
        self.assertEqual(row["deadline_loss"],row["total_steps"])
        record["outcome"]["deadline_loss"]=0
        with self.assertRaises(ValueError):case(record)
    def test_source_stop_remains_a_failed_zero_step_case(self):
        setup=fixture.AcquisitionValueTest();setup.setUp()
        record=fixture.run.execute({**setup.key,"method":"MID16_WIDE"},setup.operator,None,fixture.model(),.0001,setup.emit,setup.ledger)
        row=case(record)
        self.assertEqual((row["success"],row["stopped"],row["total_steps"],row["deadline_loss"]),(False,True,0,500))


if __name__=="__main__":unittest.main()

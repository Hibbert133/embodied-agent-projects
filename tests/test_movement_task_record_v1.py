from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from src.analysis.movement_model_source_v1 import load_bank
from src.analysis.movement_task_record_v1 import audit_record
from src.probe.movement_task_reference_v1 import METHODS
from tests.test_movement_task_reference_v1 import SyntheticHost, synthetic_valid_estimate


class MovementTaskRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.models, _ = load_bank(Path(__file__).resolve().parents[1]);cls.records = {}
        with patch("src.probe.movement_task_reference_v1.estimate_bound_movement", synthetic_valid_estimate):
            for method in METHODS:
                cls.records[method] = SyntheticHost().run(method, cls.models["push-v3"] if method == "MOVE_ARX_KEEP" else None)

    def test_replay_reconstructs_all_four_outcomes_and_costs_without_actor_or_optimizer(self):
        with patch("src.probe.movement_task_reference_v1.run_movement_task", side_effect=AssertionError("no actor")), patch(
                "src.probe.operator_identification.infer_operator", side_effect=AssertionError("no fit")):
            for method, record in self.records.items():
                self.assertEqual(audit_record(record, self.models["push-v3"] if method == "MOVE_ARX_KEEP" else None), record["outcome"])

    def test_changed_saved_decision_or_command_is_rejected(self):
        for kind, field in (("MOVEMENT_TASK_DECISION", "controller"), ("COMMAND", "command")):
            record = deepcopy(self.records["MOVE_ARX_KEEP"])
            event = next(e for e in record["events"] if e["kind"] == kind and
                         (kind != "COMMAND" or e["payload"]["phase"] == "TASK_AFTER_MOVEMENT"))
            if field == "controller":event["payload"][field]["offset"][0] += .03
            else:event["payload"][field][0] += .03
            with self.subTest(kind=kind), self.assertRaises(ValueError):audit_record(record, self.models["push-v3"])

    def test_repeated_movement_fits_and_decisions_or_unknown_events_fail(self):
        for kind in ("MOVEMENT_FIT_INTENT", "MOVEMENT_FIT_RESULT", "MOVEMENT_HISTORY", "MOVEMENT_TASK_DECISION"):
            record = deepcopy(self.records["MOVE_ARX_KEEP"])
            index = next(i for i, e in enumerate(record["events"]) if e["kind"] == kind)
            record["events"].insert(index, deepcopy(record["events"][index]))
            # Even coherent re-numbering cannot make this extra phase legal.
            for i, event in enumerate(record["events"]):event["payload"]["sequence"] = i
            with self.subTest(kind=kind), self.assertRaises(ValueError):audit_record(record, self.models["push-v3"])
        record = deepcopy(self.records["DIRECT_C8"]);record["events"][1]["kind"] = "REPROBE"
        with self.assertRaises(ValueError):audit_record(record, None)

    def test_fabricated_context_omitted_history_or_cost_changes_fail(self):
        for mode in ("context", "history", "cost", "future", "time", "unfinished", "trace"):
            record = deepcopy(self.records["MOVE_ARX_KEEP"])
            if mode == "context":
                record["context"][0]["observation"] = list(record["context"][0]["observation"])
                record["context"][0]["observation"][0] += .1
            elif mode == "history":
                event = next(e for e in record["events"] if e["kind"] == "MOVEMENT_HISTORY")
                event["payload"]["history"]["transitions"] = event["payload"]["history"]["transitions"][1:]
            elif mode == "cost":record["outcome"]["new_steps"] -= 1
            elif mode == "future":record["events"][0]["payload"]["oracle"] = True
            elif mode == "time":record["events"][1]["payload"]["saved_ns"] = -1
            elif mode == "unfinished":record["events"].pop()
            else:record["trace"][0]["command"][0] += .1
            with self.subTest(mode=mode), self.assertRaises(ValueError):audit_record(record, self.models["push-v3"])

    def test_early_success_and_actual_invalid_fit_are_replayed(self):
        for early in (False, True):
            record = SyntheticHost(early=early).run("MOVE_ARX_KEEP", self.models["push-v3"])
            self.assertEqual(audit_record(record, self.models["push-v3"]), record["outcome"])


if __name__ == "__main__":unittest.main()

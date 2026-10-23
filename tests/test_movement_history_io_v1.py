import copy
from dataclasses import asdict
import unittest

from src.analysis.movement_history_io_v1 import extract_movement
from src.probe.local_reprobe_v1 import PROGRAM, SCOPE
from tests.test_movement_history_reference_v1 import synthetic_history


def archived_fixture():
    history, _ = synthetic_history()
    physical = [{"logical_step": i, "after": asdict(history.context[0])} for i in range(16)]
    for step, obs in zip(range(14, 17), history.context):
        physical[step-1]["after"] = asdict(obs)
    events = []

    def save(kind, payload):
        saved = {"sequence": len(events), "saved_ns": 5*(len(events)+1), **payload}
        events.append({"kind": kind, "payload": saved})
        return saved

    save("REACQUIRE_CHOICE", {"at_calls": 16, "start": {"task": "push-v3", "completed_steps": 16,
        "current": asdict(history.context[-1]), "correction_xy": [[1., 0.], [0., 1.]], "offset_xy": [0., 0.]},
        "scope": SCOPE, "anchor": [.1, .6, .3], "maximum_reposition_steps": 64, "task_reserve": 100,
        "probe_program": [list(v) for v in PROGRAM], "relocation_method": "LOCAL_PID", "integral_gain": .32,
        "integral_limit": .5})
    for row in history.transitions:
        command = save("COMMAND", {"at_calls": row.completed_step-1, "decision_sequence": 0, "phase": "REPOSITION",
            "before": asdict(row.before), "command": row.command, "raw_policy": None})
        physical.append({"logical_step": row.completed_step-1, "phase": "REPOSITION", "command": row.command,
                         "after": asdict(row.after), "execution_started_ns": command["saved_ns"]+1,
                         "completed_ns": command["saved_ns"]+2, "executed_action_oracle": [999.]})
        save("STEP_RESULT", {"at_calls": row.completed_step, "command_sequence": command["sequence"], "after": asdict(row.after)})
    save("RELOCATION_EVIDENCE", {"at_calls": history.decision_step, "integral_xy": [0., 0.], "at_anchor": True,
        "controller": {"source": "RELOCATION_INTEGRAL_REFERENCE", "matrix_xy": [[1., 0.], [0., 1.]], "offset": [0., 0., 0., 0.]},
        "parameter_estimate_qualified": False, "task_utility_demonstrated": False})
    return {"task": "push-v3", "boundary_ready": True, "physical_rows": physical,
            "reacquisition": {"public": {"events": events}}, "fault_oracle": {"unread": 999}}, history


class MovementHistoryIOTest(unittest.TestCase):
    def test_actual_clock_convention_and_every_visible_transition_preserved(self):
        case, expected = archived_fixture()
        history, provenance = extract_movement(case)
        self.assertEqual(history, expected)
        self.assertEqual(provenance["responses"], 12)
        self.assertEqual(provenance["decision_step"], 28)
        self.assertEqual(provenance["status"], "SEALED_BEFORE_PROBE")

    def test_no_post_cutoff_probe_future_outcome_or_private_action_is_read(self):
        case, _ = archived_fixture()
        original, witness = extract_movement(case)
        case["reacquisition"]["public"]["events"].append({"kind": "PROBE_ENTRY", "payload": {"future_success": 999}})
        case["physical_rows"].append({"future_observation_oracle": 999})
        case["fault_oracle"] = object()
        for row in case["physical_rows"][:28]:
            row["executed_action_oracle"] = object()
        result, again = extract_movement(case)
        self.assertEqual(result.sha256, original.sha256)
        self.assertEqual(again, witness)

    def test_unknown_public_fields_and_wrong_phase_before_cutoff_reject(self):
        source, _ = archived_fixture()
        for index, key, value in ((1, "fault_oracle", []), (1, "phase", "WARM_PROBE"),
                                  (2, "future_success", True), (1, "decision_sequence", 999)):
            bad = copy.deepcopy(source)
            bad["reacquisition"]["public"]["events"][index]["payload"][key] = value
            with self.subTest(index=index, key=key), self.assertRaises(ValueError):
                extract_movement(bad)

    def test_missing_seal_pending_command_and_reversed_time_reject(self):
        source, _ = archived_fixture()
        for mode in ("missing_seal", "pending", "time", "sequence", "result_reference"):
            bad = copy.deepcopy(source)
            events = bad["reacquisition"]["public"]["events"]
            if mode == "missing_seal": events.pop()
            elif mode == "pending": events.pop(-2)
            elif mode == "time": events[2]["payload"]["saved_ns"] = 0
            elif mode == "sequence": events[2]["payload"]["sequence"] += 1
            else: events[2]["payload"]["command_sequence"] = 999
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                extract_movement(bad)

    def test_host_mismatch_and_result_saved_before_execution_reject(self):
        source, _ = archived_fixture()
        for index, key, value in ((13, "logical_step", 14), (16, "command", (0.,)*4),
                                  (16, "completed_ns", 999), (16, "phase", "POLICY")):
            bad = copy.deepcopy(source)
            bad["physical_rows"][index][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                extract_movement(bad)

    def test_missing_actual_operation_is_preserved_without_fabricated_history(self):
        case = {"boundary_ready": False, "reacquisition": None}
        history, provenance = extract_movement(case)
        self.assertIsNone(history)
        self.assertEqual(provenance, {"status": "NO_MOVEMENT_OPERATION", "responses": 0})
        case["boundary_ready"] = True
        with self.assertRaises(ValueError):
            extract_movement(case)


if __name__ == "__main__":
    unittest.main()

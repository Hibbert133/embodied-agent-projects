"""Read-only execution replay and synthetic complete-population statistics."""
from copy import deepcopy
from contextlib import contextmanager, redirect_stdout
import io as textio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.analysis import delayed_switch_effects_v1 as io
from scripts import audit_delayed_switch_effects_v1 as audit
from scripts import run_delayed_switch_effects_v1 as collector

SOFTWARE_RECEIPTS = []


def synthetic_rows():
    rows = []
    for spec in io.population():
        for index, method in enumerate(io.METHODS):
            steps = 100 + spec["unit"] % 7 + index * (spec["group"] % 5 - 2)
            rows.append({"unit": spec["unit"], "task": spec["task"], "seed": spec["seed"], "variant": method,
                "completed": True, "success": True, "stopped": False, "boundary_ready": True,
                "total_steps": steps, "deadline_loss": steps})
    return rows


class DelayedSwitchEffectsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = io.ROOT / io.SOURCE
        cls.manifest = io.read(root / "manifest.json")
        all_rows = list(audit.lines(root / "collection/cases.jsonl.gz"))
        cls.rows = all_rows[:3]
        cls.events = [r for r in audit.lines(root / "collection/events.jsonl.gz")
            if r["unit"] == 0 and r["variant"] in io.METHODS]
        cls.private = list(audit.lines(root / "collection/state_witnesses.jsonl.gz"))[:9]
        model_path = io.ROOT / cls.manifest["config"]["nominal_models"]
        cls.models = io.read(model_path)["joint"]
        cls.spec = {"unit": 0, "task": "push-v3", "seed": 21600, "fault_oracle": cls.rows[0]["fault_oracle"]}
        cls.fixture_manifest = {**cls.manifest, "allocation_oracle": [cls.spec],
            "config": {**io.expected_config(), "executions": 3}}
        cls.summary = io.read(root / "collection/summary.json")
        cls.summary.update(rows=[io.compact(r) for r in cls.rows], completed_executions=3,
            controlled_steps=sum(r["total_steps"] for r in cls.rows), lifecycle=cls.rows[-1]["ledger_after_close"],
            private_witness_records=9, event_count=len(cls.events))

    def setUp(self):
        self.counters = {"policy_queries": 0, "fit_calls": 0, "optimizer_nfev": 0}
        create = audit.old.create_task_policy
        def counted_policy(task):
            policy = create(task);get_action = policy.get_action
            def query(obs):
                self.counters["policy_queries"] += 1
                return get_action(obs)
            policy.get_action = query
            return policy
        self.patchers = [patch.object(audit.old, "create_task_policy", side_effect=counted_policy)]
        for name in ("infer_four", "infer_operator"):
            original = getattr(audit.old, name)
            def fit(*args, _original=original, **kwargs):
                self.counters["fit_calls"] += 1
                value = _original(*args, **kwargs)
                self.counters["optimizer_nfev"] += value.get("nfev", 0)
                return value
            self.patchers.append(patch.object(audit.old, name, side_effect=fit))
        for p in self.patchers: p.start()

    def tearDown(self):
        for p in reversed(self.patchers): p.stop()
        SOFTWARE_RECEIPTS.append({"test": self.id(), **self.counters, "new_environment_steps": 0,
            "new_resets": 0, "new_api_calls": 0, "new_scientific_seeds": 0,
            "scope": "Read-only committed v2 cases and synthetic statistics; no factory."})

    def replay(self, *, rows=None, events=None, private=None, summary=None, manifest=None):
        counts = {k: 0 for k in ("recomputed_policy_queries", "recomputed_parameter_fits", "recomputed_optimizer_nfev")}
        return audit.audit_data(manifest or self.fixture_manifest, self.models,
            self.rows if rows is None else rows, self.events if events is None else events,
            self.private if private is None else private, self.summary if summary is None else summary, counts)

    def test_complete_generator_allocation_and_exact_config(self):
        specs = io.population()
        self.assertEqual(len(specs), 216)
        self.assertEqual([s["seed"] for s in specs], list(range(21800, 22016)))
        self.assertEqual(len({s["generator_seed_oracle"] for s in specs}), 36)
        for group in range(36):
            members = [s for s in specs if s["group"] == group]
            self.assertEqual({(s["endpoint_oracle"], s["task"]) for s in members}, {(e, t) for e in (0, 1) for t in io.TASKS})
        config = io.read(io.CONFIG);io.validate(config)
        for key, value in (("new_api_calls", False), ("units", 215), ("task_seed_start", 21600), ("bootstrap_seed", 7)):
            changed = {**config, key: value}
            with self.assertRaises(ValueError): io.validate(changed)

    def test_real_saved_first_three_cases_stream_replay(self):
        result = self.replay()
        self.assertEqual(result["event_count"], len(self.events))
        self.assertEqual(result["private_witness_records"], 9)
        self.assertEqual(result["costs"]["new_control_steps"], 254)
        self.assertEqual(len(result["matched_boundary_comparisons"]), 2)
        self.assertEqual(result["rows"], self.summary["rows"])

    def test_allocation_fault_missing_and_extra_records_rejected(self):
        changed = deepcopy(self.fixture_manifest)
        changed["allocation_oracle"][0]["fault_oracle"]["bias_xy"][0] += .01
        with self.assertRaises(ValueError): self.replay(manifest=changed)
        with self.assertRaises(ValueError): self.replay(rows=self.rows[:-1])
        with self.assertRaises(ValueError): self.replay(rows=self.rows + [self.rows[-1]])
        with self.assertRaises(ValueError): self.replay(private=self.private[:-1])
        with self.assertRaises(ValueError): self.replay(events=self.events + [self.events[-1]])

    def test_private_timing_state_and_public_leak_rejected(self):
        for edit in ("late", "anchor", "graph", "public"):
            rows = deepcopy(self.rows);private = deepcopy(self.private);events = deepcopy(self.events)
            if edit == "late":
                private[0]["saved_ns"] = self.summary["collection_closed_ns"] + 1
                rows[0]["state_witnesses"][0] = private[0]
            elif edit == "anchor":
                private[0]["source_anchor_sequence"] += 1
                rows[0]["state_witnesses"][0] = private[0]
            elif edit == "graph":
                private[0]["witness"]["comparison_python_sha256"] = "0" * 64
                rows[0]["state_witnesses"][0] = private[0]
            else:
                next(e for e in events if e["event"] == "AGENT_EVENT")["public_payload"]["fault_oracle"] = self.spec["fault_oracle"]
            with self.subTest(edit=edit), self.assertRaises(ValueError): self.replay(rows=rows, private=private, events=events)

    def test_physical_cost_and_summary_mutations_rejected(self):
        for key in ("controlled_steps", "private_witness_records", "event_count", "new_api_calls"):
            summary = deepcopy(self.summary);summary[key] += 1
            with self.subTest(key=key), self.assertRaises(ValueError): self.replay(summary=summary)

    def test_statistics_preserve_denominator_and_whole_group_ci(self):
        rows = synthetic_rows();result = io.statistics(rows)
        self.assertEqual(result["units"], 216)
        self.assertFalse(result["individual_expected_effect_identified"])
        self.assertEqual(audit.check_statistics(rows, result)["integrity"], "PASSED")
        rows[1].update(success=False, stopped=True, total_steps=4, deadline_loss=500, boundary_ready=False)
        result = io.statistics(rows)
        self.assertEqual(result["methods"][1]["executions"], 216)
        self.assertEqual(result["methods"][1]["failures"], 1)
        self.assertEqual(result["methods"][1]["stops"], 1)
        with self.assertRaises(ValueError): io.statistics(rows[:-1])
        rows[1]["deadline_loss"] = 4
        with self.assertRaises(ValueError): io.statistics(rows)

    def test_independent_statistic_check_rejects_changed_result(self):
        rows = synthetic_rows();result = io.statistics(rows)
        result["contrasts"][0]["ci95"][1] += 1
        with self.assertRaises(ValueError): audit.check_statistics(rows, result)

    def test_collector_dispatches_each_saved_fault_and_refuses_overwrite(self):
        specs = io.population()[:1] + io.population()[6:7]
        config = {**io.expected_config(), "executions": 6}
        identity = {"experiment_run_id": "SOFTWARE_ONLY", "manifest_id": "SOFTWARE_ONLY", "source_git_commit": "SOFTWARE_ONLY"}
        manifest = {**identity, "config": config, "allocation_oracle": specs}
        seen = []
        @contextmanager
        def instrument(*args): yield
        def execute(key, supplied, model, emit, ledger, budget, saved, position, emit_private):
            spec = next(s for s in specs if s["unit"] == key["unit"])
            self.assertEqual(supplied["fault_oracle"], spec["fault_oracle"])
            self.assertEqual(set(key), set(identity) | set(audit.ALLOCATION))
            seen.append((key["unit"], key["variant"]))
            for label in ("INITIAL", "BOUNDARY", "FINAL"): emit_private("SOFTWARE_PLACEHOLDER", {"label": label})
            budget["completed"] += 1
            return {**key, "completed": True, "success": False, "stopped": True, "boundary_ready": False,
                "total_steps": 1, "deadline_loss": 500, "host_attempts": 1, "host_returned": 1, "policy_queries": 0,
                "parameter_fit_attempts": 0, "parameter_fit_results": 0, "optimizer_nfev": 0}
        with tempfile.TemporaryDirectory() as temp, patch.object(io, "clean"), patch.object(io, "load", return_value=(manifest, {t: {} for t in io.TASKS})), patch.object(io, "git", return_value="SOFTWARE_ONLY"), patch.object(collector.LifecycleLedger, "instrument", instrument), patch.object(collector, "execute_one", side_effect=execute), redirect_stdout(textio.StringIO()):
            path = Path(temp) / "manifest.json"
            collector.collect(path)
            self.assertEqual(seen, [(s["unit"], m) for s in specs for m in io.METHODS])
            summary = io.read(path.parent / "collection/summary.json")
            self.assertEqual(summary["private_witness_records"], 18)
            self.assertEqual(summary["controlled_steps"], 6)
            with self.assertRaises(FileExistsError): collector.collect(path)

    def test_collector_preserves_partial_failure_and_stops_allocation(self):
        identity = {"experiment_run_id": "SOFTWARE_ONLY", "manifest_id": "SOFTWARE_ONLY", "source_git_commit": "SOFTWARE_ONLY"}
        manifest = {**identity, "config": io.expected_config(), "allocation_oracle": io.population()[:1]}
        failed = {"completed": False, "error": {"type": "InjectedFailure", "message": "software fixture"}}
        @contextmanager
        def instrument(*args): yield
        with tempfile.TemporaryDirectory() as temp, patch.object(io, "clean"), patch.object(io, "load", return_value=(manifest, {t: {} for t in io.TASKS})), patch.object(io, "git", return_value="SOFTWARE_ONLY"), patch.object(collector.LifecycleLedger, "instrument", instrument), patch.object(collector, "execute_one", side_effect=collector.CollectionFailure(failed)) as execute:
            path = Path(temp) / "manifest.json"
            with self.assertRaises(collector.CollectionFailure): collector.collect(path)
            self.assertEqual(execute.call_count, 1)
            self.assertEqual(io.read(path.parent / "collection/failed_execution.json"), failed)
            self.assertEqual(io.read(path.parent / "collection/completion.json")["status"], "FAILED_PARTIAL")


if __name__ == "__main__": unittest.main()

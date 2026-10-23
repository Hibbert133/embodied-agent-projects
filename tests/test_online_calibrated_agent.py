import copy
import gzip
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np

from src.probe.online_calibrated_agent import OnlineClient, payload, validate_response, validate_payload
from src.probe.continuous import StepObservation
from scripts import run_online_calibrated_agent as runner
from scripts import analyze_online_calibrated_agent as analyzer


def answer(p, action=None):
    stage = p["stage"]
    chosen = action or ("ABSTAIN" if stage == "HEALTH" else "PROBE_16" if stage == "PRE_PROBE" else "RUN_AFFINE")
    candidate = next(c for c in p["candidates"] if c["operation"] == chosen)
    reference = "check" if stage == "HEALTH" else "initial" if stage == "PRE_PROBE" else "probe"
    return {"raw": json.dumps({"action_id": candidate["action_id"], "evidence_ids": [reference], "reason": "Use current evidence."}),
            "usage": {"input_tokens": 10, "output_tokens": 5}}


class OnlineApiContractTest(unittest.TestCase):
    def setUp(self):
        self.initial = StepObservation(tuple(np.zeros(39)), False, False, False)

    def test_request_scope_and_unknown_evidence_are_rejected(self):
        p = payload("PRE_PROBE", "q000", initial=self.initial)
        valid = json.loads(answer(p)["raw"])
        for field, value in (("action_id", "q999.0"), ("evidence_ids", ["future"]), ("reason", "")):
            invalid = {**valid, field: value}
            with self.assertRaises(ValueError):
                validate_response(invalid, p)
        with self.assertRaises(ValueError):
            validate_response({**valid, "injected_bias": [0.1, 0.]}, p)

    def test_nested_oracle_and_seed_fail_before_api(self):
        p = payload("PRE_PROBE", "q000", initial=self.initial)
        for field in ("seed", "injected_bias", "future_outcome"):
            invalid = copy.deepcopy(p)
            invalid["evidence"]["initial"][field] = 9400
            client = OnlineClient(runner.API_CONFIG, transport=lambda *_: self.fail("API must not be called"))
            with self.assertRaises(ValueError):
                client.decide(invalid)
            self.assertEqual(client.attempts, [])

    def test_probe_preserves_registered_task_reserve(self):
        with self.assertRaises(ValueError):
            payload("PRE_PROBE", "q000", initial=self.initial, remaining_steps=499)
        p = payload("PRE_PROBE", "q000", initial=self.initial)
        self.assertEqual(p["budget"]["reserved_task_steps"], 484)

    def test_post_probe_cannot_request_another_probe(self):
        p = payload("PRE_PROBE", "q000", initial=self.initial)
        p["stage"] = "POST_PROBE"
        with self.assertRaises(ValueError):
            validate_payload(p)

    def test_invalid_response_repaired_once_and_bound_to_same_request(self):
        calls = []
        def transport(p, config):
            calls.append(p)
            if len(calls) == 1:
                return {"raw": json.dumps({"action_id": "stale", "evidence_ids": ["initial"], "reason": "Invalid."}), "usage": {}}
            return answer(p, "RUN_UNCORRECTED")
        client = OnlineClient(runner.API_CONFIG, transport=transport)
        result = client.decide(payload("PRE_PROBE", "q000", initial=self.initial))
        self.assertTrue(result["valid"])
        self.assertEqual(result["selected_action"], "RUN_UNCORRECTED")
        self.assertEqual(len(calls), 2)
        self.assertIn("repair_feedback", calls[1])
        self.assertEqual(client.repairs, 1)

    def test_timeouts_not_retried_and_open_circuit_after_two_failures(self):
        def transport(p, config):
            if p["stage"] == "HEALTH":
                return answer(p)
            raise TimeoutError("API hard deadline exceeded: 210.000s")
        client = OnlineClient(runner.API_CONFIG, transport=transport)
        client.decide(payload("HEALTH", client.next_request_id))
        for _ in range(2):
            result = client.decide(payload("PRE_PROBE", client.next_request_id, initial=self.initial))
            self.assertFalse(result["valid"])
            self.assertEqual(result["failure"], "TIMEOUT")
        blocked = client.decide(payload("PRE_PROBE", client.next_request_id, initial=self.initial))
        self.assertEqual(blocked["failure"], "CIRCUIT_OPEN")
        self.assertEqual(len(client.attempts), 3)
        self.assertEqual(client.repairs, 0)
        self.assertEqual(runner.api_metrics(client)["timeouts"], 2)

    def test_total_and_repair_limits_include_health_and_all_attempts(self):
        def transport(p, config):
            if p["stage"] != "HEALTH" and "repair_feedback" not in p and len(client.attempts) < 15:
                return {"raw": "not JSON", "usage": {}}
            return answer(p)
        client = OnlineClient(runner.API_CONFIG, transport=transport)
        client.decide(payload("HEALTH", client.next_request_id))
        for _ in range(32):
            client.decide(payload("PRE_PROBE", client.next_request_id, initial=self.initial))
        self.assertEqual(len(client.attempts), 40)
        self.assertEqual(client.primary_calls, 32)
        self.assertEqual(client.repairs, 7)
        final = client.decide(payload("PRE_PROBE", client.next_request_id, initial=self.initial))
        self.assertEqual(final["failure"], "CALL_BUDGET_EXHAUSTED")
        self.assertEqual(len(client.attempts), 40)


class OnlineRunnerAuditTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "manifest.json"
        self.config = json.loads(runner.CONFIG.read_text(encoding="utf-8"))
        self.model, self.model_sha = runner.load_model(self.config)
        self.manifest = {"config": self.config, "source_git_commit": "synthetic",
                         "experiment_run_id": "synthetic_no_live_api_or_simulator", "input_sha256": {},
                         "model_sha256": self.model_sha}
        self.manifest["manifest_id"] = runner.manifest_digest(self.manifest)
        self.path.write_text(json.dumps(self.manifest), encoding="utf-8")

    def collect(self, action="RUN_AFFINE", preflight_fail=False):
        created = []
        case = self
        class Env:
            action_space = SimpleNamespace(low=-np.ones(4), high=np.ones(4))
            def __init__(self):
                self.index = len(created)+1
                created.append(self)
            def reset(self, **kwargs):
                self.observation = np.zeros(39)
                self.calls = 0
                return self.observation.copy(), {}
            def step(self, command):
                self.calls += 1
                if self.calls in (1, 17):
                    event = json.loads((case.path.parent / "events.jsonl").read_text().splitlines()[-1])
                    case.assertIn(event["event"], ("PROBE_STARTED", "TASK_STARTED"))
                    case.assertEqual(event["episode_index"], self.index)
                self.observation[:3] += .01 * command[:3]
                return self.observation.copy(), 0., False, False, {"success": self.calls == 18}
            def close(self):
                pass
        def transport(p, config):
            if preflight_fail:
                raise TimeoutError("API hard deadline exceeded: 210.000s")
            return answer(p, action if p["stage"] == "POST_PROBE" else None)
        factory = lambda config, **kwargs: OnlineClient(config, transport=transport, **kwargs)
        policy = SimpleNamespace(get_action=lambda _: np.zeros(4))
        with patch.object(runner, "check_clean"), patch.object(runner, "git", return_value="synthetic"), \
             patch.object(runner, "create_push_environment", side_effect=lambda _: Env()), \
             patch.object(runner, "create_push_policy", return_value=policy), patch("builtins.print"):
            runner.run(self.path, client_factory=factory)
            with self.assertRaises(FileExistsError):
                runner.run(self.path, client_factory=factory)
        self.created = created
        def read(name):
            return json.loads((self.path.parent / name).read_text(encoding="utf-8"))
        def rows(name):
            p = self.path.parent / name
            return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []
        records = []
        if (self.path.parent / "episodes.jsonl.gz").exists():
            with gzip.open(self.path.parent / "episodes.jsonl.gz", "rt", encoding="utf-8") as handle:
                records = [json.loads(x) for x in handle]
        return [self.manifest, records, rows("events.jsonl"), rows("decisions.jsonl"),
                read("status.json"), read("summary.json"), read("api_audit.json"), self.model]

    def verify(self, args):
        policy = SimpleNamespace(get_action=lambda _: np.zeros(4))
        with patch.object(analyzer, "create_push_policy", return_value=policy):
            return analyzer.verify(*args)

    def test_complete_live_control_contract_and_independent_replay(self):
        args = self.collect()
        result = self.verify(args)
        self.assertEqual(len(self.created), 96)
        self.assertEqual(result["physical_steps"], 96*18)
        self.assertEqual(result["api"]["attempts"], 33)
        self.assertEqual(result["statistics"]["complete_correction_chains"], 16)
        self.assertEqual(result["statistics"]["methods"]["LLM_AGENT"]["mean_amortized_steps"], 162)
        self.assertEqual(result["statistics"]["methods"]["LLM_AGENT"]["mean_amortized_resets"], 10)
        self.assertEqual(result["integrity"], "PASSED")

    def test_failed_preflight_never_creates_an_environment(self):
        args = self.collect(preflight_fail=True)
        result = self.verify(args)
        self.assertEqual(len(self.created), 0)
        self.assertEqual(result["status"], "FAILED_API_PREFLIGHT")
        self.assertEqual(result["api"]["attempts"], 1)
        self.assertEqual(result["api"]["timeouts"], 1)
        self.assertEqual(result["physical_steps"], 0)

    def test_api_selection_controls_actual_task_command(self):
        args = self.collect(action="RUN_UNCORRECTED")
        result = self.verify(args)
        llm = next(r for r in args[1] if r["method"] == "LLM_AGENT")
        self.assertEqual(llm["task_trace"][0]["command"], [0., 0., 0., 0.])
        self.assertEqual(result["statistics"]["complete_correction_chains"], 0)
        self.assertEqual(result["status"], "COMPLETED_INTERFACE_FAILED")

    def test_forged_actual_command_is_rejected(self):
        args = self.collect()
        llm = next(r for r in args[1] if r["method"] == "LLM_AGENT")
        llm["task_trace"][0]["command"][0] += .01
        with self.assertRaisesRegex(ValueError, "command"):
            self.verify(args)

    def test_rng_reset_at_handoff_is_rejected(self):
        args = self.collect()
        llm = next(r for r in args[1] if r["method"] == "LLM_AGENT")
        llm["task_trace"][0]["rng_before"] = llm["rng_initial"]
        with self.assertRaisesRegex(ValueError, "continuity"):
            self.verify(args)

    def test_response_tampering_and_false_timeout_count_are_rejected(self):
        args = self.collect()
        modified = copy.deepcopy(args)
        modified[6]["attempts"][1]["raw_response"] = modified[6]["attempts"][0]["raw_response"]
        with self.assertRaises(ValueError):
            self.verify(modified)
        args[6]["metrics"]["timeouts"] = 1
        with self.assertRaisesRegex(ValueError, "accounting"):
            self.verify(args)

    def test_decision_after_execution_is_rejected(self):
        args = self.collect()
        llm = next(r for r in args[1] if r["method"] == "LLM_AGENT")
        llm["sequences"]["execution"] = llm["sequences"]["task_end"]
        with self.assertRaises(ValueError):
            self.verify(args)


if __name__ == "__main__":
    unittest.main()

"""Protocol, leakage, and contract tests for ProbeMem-Online Gate A."""

from __future__ import annotations

import json
import csv
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts.check_probemem_online_seed_registry import partition_sets, seed_values
from scripts.generate_online_gate_a_collection_manifest import build_units
from scripts.run_glm_interface_ablation import build_tasks
from scripts.analyze_glm_interface_ablation import analyze
from src.probemem.compact_evidence import REGISTERED_SKILLS, SKILL_SEMANTICS, build_compact_causal_evidence
from src.probemem.online_glm_contract import OnlineGroundingDecision, OnlineGroundingGlmPolicy


def full_evidence() -> dict[str, object]:
    repetitions = [
        {"inference": {"estimated_drift_per_step": [0.03, -0.01]}},
        {"inference": {"estimated_drift_per_step": [0.02, -0.02]}},
    ]
    return {
        "evidence_id": "gate_a_episode001_attempt1",
        "episode_id": 1,
        "initial_evidence": {
            "task_state": {"progress_to_goal": 0.2, "final_object_goal_distance": 0.12},
        },
        "registered_probe_evidence": {
            "repetitions": repetitions,
            "consistency": {
                "repeat_count": 2,
                "estimated_bias_std_norm": 0.04,
                "relative_bias_std": 0.3,
                "dominant_axis_sign_agreement": 1.0,
                "mean_estimation_residual": 0.01,
            },
            "probe_environment_steps": 32,
        },
        "remaining_verification_budget": 500,
    }


def valid_decision(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "evidence_interpretation": {
            "persistent_directional_drift": True,
            "high_response_variance": False,
            "evidence_sufficient": True,
        },
        "action_predictions": {
            skill: {"predicted_status": "ACCEPTED", "accept_probability": 0.7, "confidence": 0.8}
            for skill in REGISTERED_SKILLS
        },
        "selected_skill": REGISTERED_SKILLS[0],
        "abstain": False,
        "reason": "Repeated responses support a persistent directional drift.",
    }
    value.update(changes)
    return value


class FakeMessages:
    def __init__(self, response: str) -> None:
        self.response = response
        self.requests: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.requests.append(kwargs)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=self.response)],
            usage=SimpleNamespace(input_tokens=100, output_tokens=30),
        )


class FakeClient:
    def __init__(self, response: str) -> None:
        self.messages = FakeMessages(response)


class ProbeMemOnlineGateATest(unittest.TestCase):
    def test_compact_evidence_is_exact_and_agent_visible(self) -> None:
        compact = build_compact_causal_evidence(full_evidence()).to_dict()
        self.assertEqual(compact["estimated_drift_xy"], [0.025, -0.015])
        self.assertEqual(compact["available_registered_skills"], list(REGISTERED_SKILLS))
        serialized = json.dumps(compact)
        for forbidden in ("condition", "fault", "perturbation", "threshold", "candidate_outcome"):
            self.assertNotIn(forbidden, serialized.lower())

    def test_nested_oracle_field_fails_before_api_call(self) -> None:
        client = FakeClient(json.dumps(valid_decision()))
        policy = OnlineGroundingGlmPolicy(client=client)
        with self.assertRaises(ValueError):
            policy.request_once({"evidence_id": "e", "nested": {"condition_id": "fault_01"}}, interface="FULL_PAYLOAD")
        self.assertEqual(client.messages.requests, [])

    def test_contract_requires_predictions_for_both_skills(self) -> None:
        payload = valid_decision()
        payload["action_predictions"] = {REGISTERED_SKILLS[0]: payload["action_predictions"][REGISTERED_SKILLS[0]]}  # type: ignore[index]
        with self.assertRaisesRegex(ValueError, "both and only"):
            OnlineGroundingDecision.from_mapping(payload)

    def test_abstain_and_execution_semantics_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "abstention"):
            OnlineGroundingDecision.from_mapping(valid_decision(abstain=True))
        invalid = valid_decision(selected_skill=None)
        with self.assertRaisesRegex(ValueError, "execution"):
            OnlineGroundingDecision.from_mapping(invalid)
        closed = OnlineGroundingDecision.fail_closed("invalid model output")
        self.assertTrue(closed.abstain)
        self.assertIsNone(closed.selected_skill)

    def test_skill_semantics_only_appear_in_interface_c(self) -> None:
        for interface, expected in (
            ("FULL_PAYLOAD", False),
            ("COMPACT_EVIDENCE", False),
            ("COMPACT_WITH_SKILL_SEMANTICS", True),
        ):
            client = FakeClient(json.dumps(valid_decision()))
            policy = OnlineGroundingGlmPolicy(client=client)
            decision, audit = policy.request_once(full_evidence(), interface=interface)
            self.assertIsNotNone(decision)
            payload = audit["request_payload"]
            self.assertEqual("registered_skill_semantics" in payload, expected)
            self.assertNotIn("condition_id", json.dumps(payload))
        self.assertIn("ABSTAIN", SKILL_SEMANTICS)

    def test_output_cannot_contain_continuous_skill_parameters(self) -> None:
        payload = valid_decision(correction=[0.1, 0.0])
        with self.assertRaisesRegex(ValueError, "unexpected fields"):
            OnlineGroundingDecision.from_mapping(payload)

    def test_seed_registry_is_disjoint_and_fresh(self) -> None:
        registry = {
            "partitions": {
                "gate_a_collection": [4000, 4099],
                "gate_b_bootstrap": [4100, 4199],
                "gate_c_stream": [4300, 4499],
            }
        }
        partitions = partition_sets(registry)
        self.assertEqual(len(partitions["gate_a_collection"]), 100)
        self.assertEqual(list(seed_values({"seed_range": [4000, 4002], "random_namespaces": {"seed": 99}})), [4000, 4001, 4002])

    def test_collection_manifest_has_crossed_queue_and_independent_namespaces(self) -> None:
        config = {
            "seed_range": [4000, 4099],
            "conditions": ["fault_01", "fault_05"],
            "random_namespaces": {"initial_perturbation": 19101, "registered_probe": 19102, "paired_verification": 19103},
        }
        units = build_units(config)
        self.assertEqual(len(units), 200)
        self.assertEqual({row["condition_id_oracle"] for row in units}, {"fault_01", "fault_05"})
        self.assertTrue(all(len({row["initial_perturbation_seed"], row["diagnostic_probe_seed"], row["paired_verification_seed"]}) == 3 for row in units))

    def test_interface_tasks_are_latin_square_and_do_not_leak_condition(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            rows = []
            compact = build_compact_causal_evidence(full_evidence()).to_dict()
            for episode_id in range(1, 31):
                full = full_evidence()
                full["episode_id"] = episode_id
                compact_row = dict(compact)
                compact_row["episode_id"] = episode_id
                rows.append({
                    "episode_id": episode_id,
                    "condition_id_evaluator_only": "fault_01" if episode_id <= 15 else "fault_05",
                    "agent_visible_full_evidence": full,
                    "agent_visible_compact_evidence": compact_row,
                })
            (source / "agent_evidence.json").write_text(json.dumps(rows), encoding="utf-8")
            with patch("scripts.run_glm_interface_ablation.ROOT", root):
                tasks = build_tasks({"source_collection_run": "source"})
            self.assertEqual(len(tasks), 90)
            self.assertEqual([task["interface"] for task in tasks[:3]], [
                "FULL_PAYLOAD", "COMPACT_EVIDENCE", "COMPACT_WITH_SKILL_SEMANTICS",
            ])
            self.assertEqual([task["interface"] for task in tasks[3:6]], [
                "COMPACT_EVIDENCE", "COMPACT_WITH_SKILL_SEMANTICS", "FULL_PAYLOAD",
            ])
            self.assertTrue(all("condition_id" not in json.dumps(task["agent_visible_evidence"]) for task in tasks))

    def test_analyzer_applies_absolute_and_comparative_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = root / "run"
            source = root / "source"
            config_dir = root / "configs"
            run.mkdir()
            source.mkdir()
            config_dir.mkdir()
            config = {
                "protocol": "synthetic_gate_a",
                "registered_target_mapping_evaluator_only": {
                    "fault_01": REGISTERED_SKILLS[0], "fault_05": REGISTERED_SKILLS[1],
                },
                "promotion_gate": {
                    "post_repair_validity_minimum": 0.9,
                    "stable_bias_compensation_rate_minimum": 0.8,
                    "stochastic_retry_rate_minimum": 0.7,
                    "stochastic_abstention_rate_maximum": 0.2,
                    "compact_semantics_correct_selection_net_gain_minimum": 3,
                    "compact_semantics_stochastic_abstention_reduction_minimum": 0.5,
                },
            }
            (config_dir / "gate.json").write_text(json.dumps(config), encoding="utf-8")
            (run / "immutable_manifest.json").write_text(json.dumps({
                "experiment_run_id": "synthetic", "manifest_id": "m", "source_git_commit": "c",
                "config_path": "configs/gate.json", "source_collection_run": "source",
            }), encoding="utf-8")
            (run / "run_status.json").write_text(json.dumps({"status": "COMPLETED"}), encoding="utf-8")
            candidate_rows = []
            audit_rows = []
            for episode_id in range(1, 31):
                condition = "fault_01" if episode_id <= 15 else "fault_05"
                for skill in REGISTERED_SKILLS:
                    target = config["registered_target_mapping_evaluator_only"][condition]
                    candidate_rows.append({
                        "episode_id": episode_id, "candidate_skill": skill,
                        "verification_status": "ACCEPTED" if skill == target else "REJECTED",
                    })
                for interface in ("FULL_PAYLOAD", "COMPACT_EVIDENCE", "COMPACT_WITH_SKILL_SEMANTICS"):
                    if interface == "FULL_PAYLOAD" and condition == "fault_05":
                        decision = OnlineGroundingDecision.fail_closed("insufficient")
                    else:
                        selected = config["registered_target_mapping_evaluator_only"][condition]
                        body = valid_decision(selected_skill=selected)
                        decision = OnlineGroundingDecision.from_mapping(body)
                    audit_rows.append({
                        "episode_id": episode_id, "interface": interface,
                        "condition_id_evaluator_only": condition,
                        "base_attempt": {"valid": True, "latency_ms": 10, "usage": {"input_tokens": 5, "output_tokens": 2}, "request_payload": {}},
                        "repair_attempt": None, "final_valid": True,
                        "final_decision": decision.to_dict(), "action_executed": False,
                    })
            with (source / "candidate_results.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=("episode_id", "candidate_skill", "verification_status"))
                writer.writeheader()
                writer.writerows(candidate_rows)
            (run / "ablation_audit.json").write_text(json.dumps(audit_rows), encoding="utf-8")
            with patch("scripts.analyze_glm_interface_ablation.ROOT", root):
                result = analyze(run)
            self.assertTrue(result["promotion"]["passed"])
            self.assertEqual(result["promotion"]["comparative"]["net_correct_skill_gain"], 15)
            self.assertTrue(result["gate_b_authorized"])
            self.assertFalse(result["validation_authorized"])


if __name__ == "__main__":
    unittest.main()

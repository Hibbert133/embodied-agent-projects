from pathlib import Path
import unittest

from src.diagnosis import Hypothesis, HypothesisRevision, apply_revision
from src.evaluation import ResearchMetrics
from src.memory import VerifiedExperience
from src.planner import (
    CorrectiveIntervention,
    CriterionOperator,
    VerificationCriterion,
)
from src.probe import ProbeKind, ProbePlan
from src.reasoning import (
    EvidencePacket,
    EvidenceSource,
    ResearchCycle,
    ResearchCycleEvent,
    ResearchCycleState,
)
from src.uncertainty import (
    EvidenceAcquisitionDecision,
    EvidenceAction,
    ThresholdEvidencePolicy,
    UncertaintyEstimate,
)
from src.verification import (
    VerificationPlan,
    VerificationResult,
    VerificationStatus,
)
from src.visualization import ArtifactKind, ArtifactManifestEntry


def hypothesis() -> Hypothesis:
    return Hypothesis(
        hypothesis_id="h1",
        mechanism="systematic execution bias",
        statement="commanded x motion produces repeatable positive drift",
        predictions=("opposing directional probes produce a non-zero midpoint",),
        confidence=0.6,
        supporting_evidence_ids=("failure-1",),
    )


def intervention() -> CorrectiveIntervention:
    return CorrectiveIntervention(
        intervention_id="i1",
        hypothesis_id="h1",
        strategy="bounded planar compensation",
        parameters={"x": -0.1},
        predicted_effect="reduce lateral drift",
        verification_criteria=(
            VerificationCriterion(
                "final_object_goal_distance", CriterionOperator.LESS_EQUAL, 0.05
            ),
        ),
        max_verification_steps=500,
    )


class ActiveEvidenceContractTest(unittest.TestCase):
    def test_evidence_rejects_nested_oracle_truth(self):
        with self.assertRaisesRegex(ValueError, "Oracle-only"):
            EvidencePacket(
                "e1",
                EvidenceSource.FAILED_ROLLOUT,
                1,
                20,
                {"summary": {"perturbation_type": "action_bias"}},
            )

    def test_uncertainty_gate_makes_explicit_probe_or_update_decision(self):
        high = UncertaintyEstimate(
            "u-high", ("e1",), 0.8, 0.2, 0.7, ("axis response",), "ambiguous drift"
        )
        low = UncertaintyEstimate(
            "u-low", ("e1",), 0.2, 0.1, 0.2, (), "repeatable evidence"
        )
        policy = ThresholdEvidencePolicy(0.6)
        self.assertEqual(
            policy.decide(high, decision_id="d1", available_probe_steps=32).action,
            EvidenceAction.REQUEST_PROBE,
        )
        self.assertEqual(
            policy.decide(low, decision_id="d2", available_probe_steps=32).action,
            EvidenceAction.UPDATE_HYPOTHESIS,
        )

    def test_probe_requires_explicit_authorization_and_respects_budget(self):
        direct = EvidenceAcquisitionDecision(
            "d1", "u1", EvidenceAction.UPDATE_HYPOTHESIS, "evidence sufficient"
        )
        with self.assertRaisesRegex(ValueError, "REQUEST_PROBE"):
            ProbePlan.from_decision(
                direct,
                plan_id="p1",
                kind=ProbeKind.DIRECTIONAL_ACTION,
                objective="estimate planar response",
                target_uncertainty="unknown drift axis",
                expected_observation="opposing displacement midpoint",
                max_steps=8,
                stop_conditions=("budget exhausted",),
                safety_constraints=("zero gripper command",),
                parameters={},
            )
        request = EvidenceAcquisitionDecision(
            "d2", "u1", EvidenceAction.REQUEST_PROBE, "missing axis evidence", 8
        )
        plan = ProbePlan.from_decision(
            request,
            plan_id="p2",
            kind=ProbeKind.DIRECTIONAL_ACTION,
            objective="estimate planar response",
            target_uncertainty="unknown drift axis",
            expected_observation="opposing displacement midpoint",
            max_steps=8,
            stop_conditions=("budget exhausted",),
            safety_constraints=("zero gripper command",),
            parameters={"axis": "x"},
        )
        self.assertEqual(plan.authorized_by_decision_id, "d2")

    def test_hypothesis_revision_is_append_only(self):
        revised = apply_revision(
            hypothesis(),
            HypothesisRevision(
                "h1",
                1,
                0.8,
                "directional probe supports a repeatable midpoint",
                added_supporting_evidence_ids=("probe-1",),
            ),
        )
        self.assertEqual(revised.revision, 2)
        self.assertEqual(revised.supporting_evidence_ids, ("failure-1", "probe-1"))

    def test_memory_rejects_unverified_or_rejected_conclusions(self):
        plan = VerificationPlan.from_intervention(intervention(), plan_id="v1")
        rejected = VerificationResult(
            plan.plan_id,
            intervention().intervention_id,
            "verification-evidence-1",
            VerificationStatus.REJECTED,
            {"success": False},
            "declared criterion was not satisfied",
        )
        with self.assertRaisesRegex(ValueError, "ACCEPTED"):
            VerifiedExperience("x1", hypothesis(), intervention(), rejected)
        accepted = VerificationResult(
            plan.plan_id,
            intervention().intervention_id,
            "verification-evidence-2",
            VerificationStatus.ACCEPTED,
            {"success": True},
            "all declared criteria were satisfied",
        )
        experience = VerifiedExperience("x2", hypothesis(), intervention(), accepted)
        self.assertEqual(experience.verification.status, VerificationStatus.ACCEPTED)

    def test_lifecycle_rejects_skips_and_commits_only_after_acceptance(self):
        cycle = ResearchCycle("cycle-1")
        with self.assertRaisesRegex(ValueError, "invalid"):
            cycle.transition(ResearchCycleEvent.REQUEST_PROBE, "d1")
        for event, reference in (
            (ResearchCycleEvent.ASSESS_UNCERTAINTY, "u1"),
            (ResearchCycleEvent.UPDATE_HYPOTHESIS, "h1-r1"),
            (ResearchCycleEvent.PROPOSE_INTERVENTION, "i1"),
            (ResearchCycleEvent.EXECUTE_VERIFICATION, "v1"),
            (ResearchCycleEvent.ACCEPT_VERIFICATION, "vr1"),
            (ResearchCycleEvent.COMMIT_MEMORY, "x1"),
        ):
            cycle = cycle.transition(event, reference)
        self.assertEqual(cycle.state, ResearchCycleState.MEMORY_COMMITTED)

    def test_research_metrics_and_visual_artifact_require_provenance(self):
        metrics = ResearchMetrics(0.8, 32, 0.7, True, 0.2, 1)
        self.assertEqual(metrics.evidence_environment_steps, 32)
        artifact = ArtifactManifestEntry(
            "fig-1",
            ArtifactKind.FIGURE,
            Path("outputs/figure.png"),
            Path("outputs/results.csv"),
            "lowest final distance among failed verification rollouts",
        )
        self.assertEqual(artifact.kind, ArtifactKind.FIGURE)


class CompatibilityImportTest(unittest.TestCase):
    def test_legacy_and_package_probe_exports_are_identical(self):
        from src.diagnostic_probes import estimate_planar_bias as legacy
        from src.probe import estimate_planar_bias as packaged

        self.assertIs(legacy, packaged)

    def test_rollout_and_trajectory_public_imports_remain_available(self):
        from src.rollout import EpisodeResult, run_episode
        from src.trajectory import TrajectoryRecorder, build_agent_view

        self.assertTrue(callable(run_episode))
        self.assertTrue(callable(build_agent_view))
        self.assertIsNotNone(EpisodeResult)
        self.assertIsNotNone(TrajectoryRecorder)


if __name__ == "__main__":
    unittest.main()

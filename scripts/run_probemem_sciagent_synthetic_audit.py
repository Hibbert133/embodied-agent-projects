"""Exercise four SciAgent pathways with synthetic, metric-ineligible records."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from src.probemem.regime_memory import SIGNATURE_FIELDS  # noqa: E402
from src.probemem_sciagent.principle_memory import PrincipleMemory  # noqa: E402
from src.probemem_sciagent.schemas import ExperienceRecord, HypothesisRecord, MicroProbeRecord, SciAgentDecision  # noqa: E402


COMP = "BOUNDED_PLANAR_COMPENSATION"
RETRY = "INDEPENDENT_STOCHASTIC_RETRY"


def main() -> int:
    output = ROOT / "outputs/probemem_sciagent/demo/synthetic_pathway_audit/static_v1"
    output.mkdir(parents=True, exist_ok=False)
    direct = SciAgentDecision(
        "Stable direct evidence.", (f"Stable response favors {COMP}", f"Alternative is {RETRY}"),
        (), (), "ACT_DIRECTLY", None, COMP, "Counteract stable drift.", "", 0.8, None,
    )
    pre = SciAgentDecision(
        "Action utility remains ambiguous.", (f"Hypothesis A favors {COMP}", f"Hypothesis B favors {RETRY}"),
        (), (), "RUN_MICRO_PROBE", "RETRY_REPEATABILITY_PROBE", COMP,
        "Measure retry repeatability.", "Missing action-conditioned evidence.", 0.5, None,
        probe_justification_codes=("MISSING_ACTION_CONDITIONED_EVIDENCE",),
    )
    post = SciAgentDecision(
        "Retry trials produced repeatable progress.", (f"Probe weakens {COMP}", f"Probe supports {RETRY}"),
        (), (), "ACT_DIRECTLY", None, RETRY, "Use an independent realization.", "", 0.75, None,
    )
    probe = MicroProbeRecord(
        "synthetic_probe", "synthetic_episode", 0, "RETRY_REPEATABILITY_PROBE",
        "synthetic_pre", {"num_trials": 3, "positive_progress_rate": 1.0, "mean_progress": 0.02,
        "progress_variance": 0.0, "severe_failure_rate": 0.0}, 192, (1, 2, 3), 2, True,
    )
    hypothesis = HypothesisRecord(
        "synthetic_hypothesis", "Stable response supports bounded compensation.",
        ("STABLE_DIRECTIONAL_RESPONSE",), COMP,
        supporting_experience_ids=("s1", "s2", "s3", "s4"),
        tested_experience_ids=("s1", "s2", "s3", "s4"),
        targeted_probe_record_ids=("targeted1",), verification_count=4, support_count=4,
        independent_seed_count=3, targeted_verification_count=1,
        most_recent_verification_status="ACCEPTED", status="SUPPORTED", created_at_step=1, updated_at_step=10,
    )
    principles = PrincipleMemory(); principle = principles.promote(hypothesis, step=11)
    counterexample = ExperienceRecord(
        "synthetic_counterexample", "synthetic_later_episode", 1,
        {name: 0.0 for name in SIGNATURE_FIELDS}, COMP, "ACCEPTED", 0.8,
        "Principle predicted success.", "REJECTED", 0.2, 100,
        (principle.principle_id,), (), 20,
    )
    restricted = principles.observe_cited(principle.principle_id, experience=counterexample, step=21)
    artifact = {
        "label": "SYNTHETIC_INTEGRATION_AUDIT", "research_metric_eligible": False,
        "direct_action": direct.to_dict(), "probe_admission": pre.to_dict(),
        "probe_record": asdict(probe), "probe_induced_action_change": post.to_dict(),
        "principle_before_counterexample": principle.to_dict(),
        "principle_after_counterexample": restricted.to_dict(),
    }
    (output / "pathways.json").write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    print(f"synthetic audit: {output / 'pathways.json'}")
    return 0


if __name__ == "__main__": raise SystemExit(main())

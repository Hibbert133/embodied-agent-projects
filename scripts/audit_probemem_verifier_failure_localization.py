"""No-rollout mechanism audit of the immutable ProbeMem verifier Demo trace."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any


BUDGETED = "BUDGETED_VERIFIER"
SKILLS = ("BOUNDED_PLANAR_COMPENSATION", "INDEPENDENT_STOCHASTIC_RETRY")
ORDER = {"ACCEPTED": 2, "INCONCLUSIVE": 1, "REJECTED": 0}
TRIGGERS = (
    "WITHIN_AMBIGUITY_BAND",
    "GLOBAL_RECENT_MEMORY_CONFLICT",
    "RECENT_SIMILAR_CONTRADICTION",
)


def audit(run_dir: Path) -> dict[str, Any]:
    decisions = [row for row in _csv(run_dir / "decisions.csv") if row["method"] == BUDGETED]
    candidates = {
        (int(row["episode_id"]), row["candidate_skill"]): row
        for row in _csv(run_dir / "candidate_outcomes.csv")
    }
    trigger_counts: Counter[str] = Counter()
    exclusive_counts: Counter[str] = Counter()
    blocker_counts: Counter[str] = Counter()
    admitted = []
    for row in decisions:
        reasons = _tokens(row["admission_reasons"])
        active = tuple(reason for reason in reasons if reason in TRIGGERS)
        trigger_counts.update(active)
        if len(active) == 1:
            exclusive_counts.update(active)
        if not _bool(row["verifier_called"]):
            continue
        blockers = tuple(
            reason for reason in _tokens(row["override_reason"])
            if reason != "OVERRIDE_AUTHORIZED"
        )
        blocker_counts.update(blockers)
        default = row["default_skill"]
        alternative = next(skill for skill in SKILLS if skill != default)
        default_status = candidates[(int(row["episode_id"]), default)]["verification_status"]
        alternative_status = candidates[(int(row["episode_id"]), alternative)]["verification_status"]
        delta = ORDER[alternative_status] - ORDER[default_status]
        admitted.append({
            "episode_id": int(row["episode_id"]), "seed": int(row["seed"]),
            "admission_reasons": list(active), "default_skill": default,
            "alternative_skill": alternative, "override_applied": _bool(row["override_applied"]),
            "guard_reason": row["override_reason"], "default_status": default_status,
            "alternative_status": alternative_status,
            "alternative_effect": "HELPFUL" if delta > 0 else "HARMFUL" if delta < 0 else "TIE",
        })
    leave_one_out = {}
    for removed in TRIGGERS:
        retained = 0
        for row in decisions:
            active = {reason for reason in _tokens(row["admission_reasons"]) if reason in TRIGGERS}
            if active - {removed}:
                retained += 1
        leave_one_out[removed] = {
            "descriptive_calls_retained": retained,
            "descriptive_call_rate": None if not decisions else retained / len(decisions),
        }
    authorized = [row for row in admitted if row["override_applied"]]
    blocked = [row for row in admitted if not row["override_applied"]]
    result = {
        "schema_version": 1,
        "experiment_run_id": run_dir.name,
        "operational_cases": len(decisions),
        "verifier_calls": len(admitted),
        "trigger_counts_nonexclusive": dict(sorted(trigger_counts.items())),
        "single_trigger_only_counts": dict(sorted(exclusive_counts.items())),
        "descriptive_leave_one_trigger_out": leave_one_out,
        "guard_blocker_counts_nonexclusive": dict(sorted(blocker_counts.items())),
        "authorized_override_effects": dict(Counter(row["alternative_effect"] for row in authorized)),
        "blocked_alternative_effects": dict(Counter(row["alternative_effect"] for row in blocked)),
        "admitted_cases": admitted,
        "interpretation": [
            "This is a no-new-rollout attribution audit of frozen decisions and paired evaluator outcomes.",
            "Leave-one-trigger-out counts are descriptive arithmetic, not a proposed gate or threshold.",
            "The audit cannot authorize retuning, rerunning, GLM, validation, held-out execution, or reserved seeds.",
        ],
    }
    return result


def build_report(result: dict[str, Any]) -> str:
    triggers = result["trigger_counts_nonexclusive"]
    single = result["single_trigger_only_counts"]
    blockers = result["guard_blocker_counts_nonexclusive"]
    return f"""# ProbeMem Verifier Failure-Localization Audit

## Scope

This audit uses no new rollout, API call, memory write, threshold fit, or seed.
It attributes the immutable Demo's {result['verifier_calls']}/{result['operational_cases']}
Budgeted verifier calls and guard outcomes. It does not propose a replacement
admission or override rule.

## Admission localization

Atomic trigger presence was: ambiguity band {triggers.get('WITHIN_AMBIGUITY_BAND', 0)},
recent similar contradiction {triggers.get('RECENT_SIMILAR_CONTRADICTION', 0)},
and global/recent conflict {triggers.get('GLOBAL_RECENT_MEMORY_CONFLICT', 0)}.
Single-trigger-only calls were {json.dumps(single, sort_keys=True)}.

Descriptively removing only the contradiction trigger from the already-frozen
trace would retain {result['descriptive_leave_one_trigger_out']['RECENT_SIMILAR_CONTRADICTION']['descriptive_calls_retained']}
calls; removing only the ambiguity-band trigger would retain
{result['descriptive_leave_one_trigger_out']['WITHIN_AMBIGUITY_BAND']['descriptive_calls_retained']}.
These are overlap counts, not registered candidate policies and must not be used
to select a new rule on seeds 4700--4749.

## Guard localization

Nonexclusive blocker counts were {json.dumps(blockers, sort_keys=True)}.
The two authorized alternatives comprised
{json.dumps(result['authorized_override_effects'], sort_keys=True)}. The nine
blocked alternatives comprised
{json.dumps(result['blocked_alternative_effects'], sort_keys=True)}.

The failure is therefore not merely excess admission: the posterior/applicability
stack both authorized a harmful alternative and rejected a helpful one. A valid
successor must pose a new calibration or causal-evidence question on fresh seeds;
this audit does not choose its parameters.

## Claim boundary

No parameter is changed. Seeds 4750--4799, validation, held-out execution, GLM,
and principle generation remain blocked.
"""


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(item for item in value.split("|") if item and item != "CLEAR_DEFAULT")


def _bool(value: Any) -> bool:
    return value is True or str(value).lower() == "true"


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    result = audit(run_dir)
    output = run_dir / "failure_localization_audit.json"
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    report = Path(__file__).resolve().parents[1] / "reports/probemem_verifier_failure_localization_audit.md"
    report.write_text(build_report(result), encoding="utf-8")
    print(f"audit: {output}")
    print(f"report: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

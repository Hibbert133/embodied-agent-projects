"""Read-only, post-hoc robustness audit of frozen additional-experiment decisions.

No simulation, API, memory replay, threshold fitting, or promotion is performed.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
METHODS = ("BASELINE", "MEMORY_ONLY", "EVIDENCE_ACQUISITION_ENABLED",
           "PROBE_MEMORY", "FULL_PROBEMEM")
CONTRASTS = ((METHODS[2], METHODS[0]), (METHODS[1], METHODS[0]),
             (METHODS[3], METHODS[2]), (METHODS[4], METHODS[3]))
IDENTITY = ("experiment_run_id", "manifest_id", "source_git_commit")
STATUSES = {"ACCEPTED", "INCONCLUSIVE", "REJECTED"}


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def paired_counts(left, right):
    if not left or len(left) != len(right):
        raise ValueError("nonempty aligned pairs required")
    wins = sum(a and not b for a, b in zip(left, right))
    losses = sum(b and not a for a, b in zip(left, right))
    discordant = wins + losses
    # Exact two-sided binomial reference calculation, conditional on discordance.
    p = min(1.0, 2 * sum(math.comb(discordant, k)
                         for k in range(min(wins, losses) + 1)) / 2 ** discordant)
    return {"n": len(left), "wins": wins, "ties": len(left) - discordant,
            "losses": losses, "difference": (wins - losses) / len(left),
            "exact_discordance_p_reference": p}


def validate_tables(status, population, decisions, outcomes):
    """Reject duplicate/missing pairs and incorrectly associated realizations."""
    operational = [r for r in population if r["operational"] == "True"]
    seeds = [int(r["seed"]) for r in operational]
    if len(set(seeds)) != len(seeds) or len(seeds) != status["operational_cases"]:
        raise ValueError("operational population mismatch")
    by_seed = {int(r["seed"]): r for r in operational}
    by_method = {m: {} for m in METHODS}
    episode_seeds = {}
    for row in decisions:
        if any(row[k] != status[k] for k in IDENTITY):
            raise ValueError("decision provenance mismatch")
        method, episode, seed = row["method"], int(row["episode_id"]), int(row["seed"])
        if method not in by_method or episode in by_method[method]:
            raise ValueError("unknown method or duplicate decision")
        if seed not in by_seed or row["verification_status"] not in STATUSES:
            raise ValueError("invalid population or status")
        if episode in episode_seeds and episode_seeds[episode] != seed:
            raise ValueError("episode seed mismatch")
        for key in ("condition_id_oracle", "mechanism_oracle"):
            if row[key] != by_seed[seed][key]:
                raise ValueError("population stratum mismatch")
        episode_seeds[episode] = seed
        by_method[method][episode] = row
    episodes = set(episode_seeds)
    if len(episodes) != len(seeds) or set(episode_seeds.values()) != set(seeds):
        raise ValueError("episode population mismatch")
    if any(set(rows) != episodes for rows in by_method.values()):
        raise ValueError("missing method pairs")
    indexed = {}
    for row in outcomes:
        if any(row[k] != status[k] for k in IDENTITY):
            raise ValueError("outcome provenance mismatch")
        episode, realization = int(row["episode_id"]), int(row["realization"])
        seed = int(row["seed"])
        key = (episode, row["action_signature_id"], realization)
        if key in indexed:
            raise ValueError("duplicate outcome")
        if episode_seeds.get(episode) != seed or realization not in range(4):
            raise ValueError("outcome episode or realization mismatch")
        if row["verification_status"] not in STATUSES or row["evaluator_only"] != "True":
            raise ValueError("invalid evaluator outcome")
        if row["initial_state_hash"] != by_seed[seed]["initial_state_hash"]:
            raise ValueError("reset state mismatch")
        indexed[key] = row
    for rows in by_method.values():
        for episode, row in rows.items():
            for realization in range(4):
                outcome = indexed.get((episode, row["selected_action_signature_id"], realization))
                placeholder = outcome is not None and (
                    outcome["skill"] == "" and outcome["verification_status"] == "REJECTED"
                    and outcome["steps"] == "0" and outcome["success"] == "False")
                if outcome is None or (outcome["skill"] != row["selected_skill"] and not placeholder):
                    raise ValueError("missing or mismatched selected-action realization")
                if realization == 0 and outcome["verification_status"] != row["verification_status"]:
                    raise ValueError("primary outcome mismatch")
    return by_method, indexed


def audit(run_dir):
    names = ("run_status.json", "immutable_manifest.json", "population.csv",
             "decisions.csv", "candidate_outcomes.csv", "analysis_summary.json")
    hashes = {name: hashlib.sha256((run_dir / name).read_bytes()).hexdigest() for name in names}
    status = json.loads((run_dir / names[0]).read_text())
    manifest = json.loads((run_dir / names[1]).read_text())
    content = {k: v for k, v in manifest.items() if k != "manifest_id"}
    digest = hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if digest != manifest["manifest_id"] or any(manifest[k] != status[k] for k in IDENTITY):
        raise ValueError("manifest provenance mismatch")
    if status["status"] != "COMPLETED_WITH_POPULATION_IMBALANCE":
        raise ValueError("unexpected source status")
    by_method, outcomes = validate_tables(status, *(read_csv(run_dir / n) for n in names[2:5]))
    historical = json.loads((run_dir / names[5]).read_text())
    if any(historical[k] != status[k] for k in IDENTITY):
        raise ValueError("historical summary provenance mismatch")
    episodes = sorted(by_method[METHODS[0]])
    strata = {"all": episodes}
    for field in ("mechanism_oracle", "condition_id_oracle"):
        for value in sorted({r[field] for r in by_method[METHODS[0]].values()}):
            strata[value] = [e for e in episodes if by_method[METHODS[0]][e][field] == value]
    comparisons = []
    for left, right in CONTRASTS:
        for stratum, ids in strata.items():
            result = paired_counts(
                [by_method[left][e]["verification_status"] == "ACCEPTED" for e in ids],
                [by_method[right][e]["verification_status"] == "ACCEPTED" for e in ids])
            comparisons.append({"left": left, "right": right, "stratum": stratum, **result})
    sensitivity = []
    for method, rows in by_method.items():
        counts = [sum(outcomes[e, rows[e]["selected_action_signature_id"], r]["verification_status"]
                      == "ACCEPTED" for e in episodes) for r in range(4)]
        if counts[0] != historical["methods"][method]["successful_recoveries"]:
            raise ValueError("historical recovery summary mismatch")
        sensitivity.append({"method": method, "n_states": len(episodes),
                            "accepted_by_realization": counts,
                            "nonexecuted_failure_states": sum(
                                outcomes[e, rows[e]["selected_action_signature_id"], 0]["skill"] == ""
                                for e in episodes),
                            "frozen_action_mean_acceptance": sum(counts) / (4 * len(episodes))})
    return {**{k: status[k] for k in IDENTITY}, "source_status": status["status"],
            "audit_kind": "POST_HOC_NO_NEW_ROLLOUT_NO_PROMOTION",
            "input_sha256": hashes, "comparisons": comparisons,
            "frozen_decision_sensitivity": sensitivity,
            "historical_paired_bootstrap": historical["paired_recovery_differences"],
            "limitations": [
                "Exact discordance p-values are exploratory reference calculations, not new promotion gates.",
                "Chronological memory induces dependence; episode-wise bootstrap and binomial references do not establish policy-level uncertainty.",
                "Four realizations reuse fixed decisions from the original memory history; this is not a replay of four online policies or 240 independent states.",
                "Blank-skill, zero-step REJECTED records are nonexecuted plan failures, retained in the denominator, not physical verification trials.",
                "Zero observed paired differences do not establish equivalence or a zero population effect.",
                "Strata are evaluator-only, post-hoc, small, and unadjusted for multiple comparisons."]}


def render(result):
    lines = ["# Additional-experiment robustness audit", "",
             "Post-hoc analysis only; no new rollout, API call, memory replay, or promotion.", ""]
    lines += [f"- {key}: `{result[key]}`" for key in IDENTITY]
    lines += ["", "## Paired binary recovery", "",
              "Wins/losses mean gaining/losing ACCEPTED recovery; they differ from ordinal transfer labels.", "",
              "| Left minus right | Population | N | Win / tie / loss | Difference (pp) | Exact p reference |",
              "|---|---|---:|---:|---:|---:|"]
    for r in result["comparisons"]:
        lines.append(f'| {r["left"]} − {r["right"]} | {r["stratum"]} | {r["n"]} | '
                     f'{r["wins"]} / {r["ties"]} / {r["losses"]} | {100*r["difference"]:+.2f} | '
                     f'{r["exact_discordance_p_reference"]:.4f} |')
    lines += ["", "## Frozen-action realization sensitivity", "",
              "Realization 0 is the registered primary result. Later realizations are evaluator-only.", "",
              "| Method | Accepted r0 / r1 / r2 / r3 | Mean acceptance | Nonexecuted states |", "|---|---|---:|---:|"]
    for r in result["frozen_decision_sensitivity"]:
        lines.append(f'| {r["method"]} | {" / ".join(map(str, r["accepted_by_realization"]))} | '
                     f'{r["frozen_action_mean_acceptance"]:.1%} | {r["nonexecuted_failure_states"]} |')
    lines += ["", "## Interpretation limits", ""] + [f"- {s}" for s in result["limitations"]]
    lines += ["", "Input SHA-256 hashes and unchanged historical bootstrap intervals are in `audit.json`.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source, target = args.run_dir.resolve(), args.output.resolve()
    if target == source or source in target.parents:
        raise ValueError("audit output must be outside the immutable source run")
    result = audit(source)
    result["audit_code_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    result["audit_base_git_commit"] = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    target.mkdir(parents=True, exist_ok=False)
    (target / "audit.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    (target / "report.md").write_text(render(result), encoding="utf-8")
    print(target)


if __name__ == "__main__":
    main()

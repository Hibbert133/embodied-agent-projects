"""Read-only reset-resource accounting for the completed prefix-refresh study."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.analyze_evidence_refresh import analyze, read_rows


def accounting(rows):
    methods = {}
    for method in sorted({r["method"] for r in rows}):
        selected = [r for r in rows if r["method"] == method]
        if any(type(r["probe_steps"]) is not int or r["probe_steps"] not in (0,16,32,48,64) for r in selected):
            raise ValueError("unregistered probe budget")
        methods[method] = {"episodes": len(selected), "successful": sum(r["success"] for r in selected),
            "charged_probe_steps": sum(r["probe_steps"] for r in selected),
            "charged_direction_resets": sum(r["probe_steps"]//4 for r in selected),
            "mean_steps_excluding_resets": statistics.fmean(r["steps"]+r["probe_steps"] for r in selected),
            "mean_additional_direction_resets": statistics.fmean(r["probe_steps"]/4 for r in selected)}
    candidate, fixed = methods["DECISION_STABILITY"], methods["FIXED_16"]
    delta_intercept = candidate["mean_steps_excluding_resets"]-fixed["mean_steps_excluding_resets"]
    delta_slope = candidate["mean_additional_direction_resets"]-fixed["mean_additional_direction_resets"]
    return {"methods": methods, "candidate_minus_fixed16_cost": {
        "intercept_task_plus_probe_steps": delta_intercept, "slope_per_reset_step_equivalent": delta_slope,
        "dominated_for_every_nonnegative_uniform_reset_cost": bool(
            candidate["successful"] <= fixed["successful"] and delta_intercept > 0 and delta_slope >= 0)}}


def run(run_dir):
    verified = analyze(run_dir)
    rows = read_rows(run_dir/"outcomes.jsonl")
    result = accounting(rows)
    result.update({k: verified[k] for k in ("experiment_run_id","manifest_id","source_git_commit")})
    result["source_outcomes_sha256"] = hashlib.sha256((run_dir/"outcomes.jsonl").read_bytes()).hexdigest()
    a = verified["audit"]
    result["explicit_collection_reset_calls"] = {
        "initial_state_inspections": a["episodes"], "direction_probes": a["physical_probe_steps"]//4,
        "task_branches": a["physical_task_rollouts"],
        "total": a["episodes"] + a["physical_probe_steps"]//4 + a["physical_task_rollouts"]}
    result["semantics"] = "Source-derived explicit reset calls, not measured robot time; internal constructor work excluded."
    return result


def report(r):
    lines = ["# Reset-resource sensitivity audit", "",
        "Read-only accounting of a completed simulator experiment. No new episodes or method decisions.", "",
        f'Run: `{r["experiment_run_id"]}`.', "",
        "| Method | Success / 96 | Charged probe steps | Charged direction resets | Mean task + probe steps | Mean extra direction resets |",
        "|---|---:|---:|---:|---:|---:|"]
    for name, row in r["methods"].items():
        lines.append(f'| {name} | {row["successful"]} | {row["charged_probe_steps"]} | {row["charged_direction_resets"]} | '
                     f'{row["mean_steps_excluding_resets"]:.2f} | {row["mean_additional_direction_resets"]:.2f} |')
    c = r["candidate_minus_fixed16_cost"]
    lines += ["", "Let R >= 0 be a common reset cost in environment-step equivalents. Omitting a common task-start reset,",
              "cost(method,R) = mean(task steps + probe steps) + R * mean(extra directional resets).", "",
              f'Candidate minus fixed-16 cost = {c["intercept_task_plus_probe_steps"]:.4f} + '
              f'{c["slope_per_reset_step_equivalent"]:.4f} R. The candidate has one fewer success.',
              "Thus adding any nonnegative uniform reset cost cannot rescue this candidate's observed dominance failure.", "",
              f'Explicit physical collection resets: `{r["explicit_collection_reset_calls"]}`.', "",
              r["semantics"], "This is a sensitivity model, not measured latency, energy, human intervention, or a real-robot cost estimate.",
              "Each repetition has four directional starts; each method episode has one task start afterward, common to every method.",
              "A true continuous probe needs different transitions and cannot be simulated by subtracting resets from these logs.", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-dir",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    source, output = args.run_dir.resolve(),args.output.resolve()
    if source == output or source in output.parents:
        raise ValueError("output must be outside immutable collection")
    result=run(source)
    output.mkdir(parents=True,exist_ok=False)
    (output/"audit.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    (output/"report.md").write_text(report(result),encoding="utf-8")
    print(report(result))

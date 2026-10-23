"""Replay calibrated task decisions, model binding, and continuous RNG logs."""
import argparse
from dataclasses import asdict
import gzip
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
from scripts.run_calibrated_tasks import load,load_model,plan,summarize,METHODS
from scripts.run_response_calibration import restore
from scripts.run_continuous_probe import state_hash,normalized
from scripts.build_autoresearch_benchmark import get_conditions
from src.probe.continuous import StepObservation,symmetric_program


def rng_hash(rng):
    return hashlib.sha256(json.dumps(rng.bit_generator.state,sort_keys=True).encode()).hexdigest()


def verify(m,records,declarations,status,summary,model):
    c=m["config"]; identity={k:m[k] for k in ("experiment_run_id","manifest_id","source_git_commit")}
    expected=[(seed,condition,method) for seed in range(9100,9116) for condition in c["conditions"] for method in METHODS]
    if [(r["seed"],r["condition_oracle"],r["method"]) for r in records]!=expected or len(declarations)!=320:
        raise ValueError("complete paired population mismatch")
    if any(any(r.get(k)!=v for k,v in identity.items()) for r in records+declarations+[status,summary]):
        raise ValueError("provenance mismatch")
    conditions={x.condition_id:x for x in get_conditions(0)}
    outcomes=[]; prefix_groups={}; initial_groups={}; task_steps=0
    for index,(record,declaration) in enumerate(zip(records,declarations),1):
        key={**identity,"episode_index":index,"seed":record["seed"],"condition_oracle":record["condition_oracle"],
             "method":record["method"],"model_sha256":m["model_sha256"]}
        if any(record.get(k)!=v or declaration.get(k)!=v for k,v in key.items()): raise ValueError("episode/model association mismatch")
        probe=record["probe"]; initial=StepObservation(**probe["initial"]); handoff=StepObservation(**probe["handoff"])
        method=record["method"]; seed=record["seed"]; condition=record["condition_oracle"]
        initial_groups.setdefault(seed,set()).add(state_hash(initial.observation))
        evidence=None; n_probe=0
        if method=="NO_PROBE":
            if probe["evidence"] is not None or handoff!=initial: raise ValueError("no-probe state mismatch")
        else:
            evidence=restore(probe["evidence"]); n_probe=evidence.steps
            if normalized(asdict(evidence))!=probe["evidence"] or not 1<=n_probe<=16 or evidence.requested_steps!=16:
                raise ValueError("continuous evidence schema mismatch")
            previous=initial.observation
            for row,command in zip(evidence.transitions,symmetric_program()):
                if row.before!=previous or row.command!=command or len(row.after)!=39 or not np.isfinite(row.after).all():
                    raise ValueError("continuous trajectory/command mismatch")
                previous=row.after
            if previous!=handoff.observation or evidence.final!=handoff: raise ValueError("probe handoff mismatch")
            stop="SUCCESS" if handoff.success else "TERMINATED" if handoff.terminated else "TRUNCATED" if handoff.truncated else "PROGRAM_COMPLETE"
            if evidence.stop_reason!=stop or (stop=="PROGRAM_COMPLETE" and n_probe!=16): raise ValueError("probe stop mismatch")
            prefix_groups.setdefault((seed,condition),set()).add(json.dumps(probe["evidence"],sort_keys=True))
        rebuilt=plan(method,evidence,model)
        if normalized(rebuilt)!=record["decision"] or declaration["decision"]!=record["decision"] or declaration["probe"]!=probe:
            raise ValueError("visible-only decision replay mismatch")
        noise_seed=int(np.random.SeedSequence([seed,c["conditions"].index(condition),0xC81]).generate_state(1)[0])
        rng=np.random.default_rng(noise_seed)
        for _ in range(n_probe): rng.normal(0,.05,3)
        if probe["host_calls"]!=n_probe or probe["rng_handoff"]!=rng_hash(rng): raise ValueError("probe RNG/counter mismatch")
        trace=record["task_trace"]; previous=state_hash(handoff.observation)
        ended=handoff.success or handoff.terminated or handoff.truncated; success=handoff.success; first=0 if success else None
        for i,row in enumerate(trace,1):
            if ended: raise ValueError("task step after termination")
            if row["host_calls"]!=n_probe+i or row["before_hash"]!=previous: raise ValueError("handoff/state/counter discontinuity")
            if row["rng_before"]!=rng_hash(rng): raise ValueError("task RNG reseed detected")
            rng.normal(0,.05,3)
            if row["rng_after"]!=rng_hash(rng): raise ValueError("task RNG advance mismatch")
            if len(row["command"])!=4 or not np.isfinite(row["command"]).all(): raise ValueError("invalid task command")
            if any(type(row[k]) is not bool for k in ("success","terminated","truncated")): raise ValueError("invalid terminal flag")
            success=row["success"]; ended=success or row["terminated"] or row["truncated"]; previous=row["after_hash"]
            if success: first=i
        if n_probe+len(trace)>500 or (not ended and n_probe+len(trace)!=500): raise ValueError("task budget/stop mismatch")
        fit=rebuilt["fit"]
        error=float(np.linalg.norm(np.array(fit["bias_in_command_units"])-conditions[condition].parameters["bias"][:2])) if fit and fit["valid"] else None
        expected_outcome={**key,"success":success,"success_equal_484_policy_steps":first is not None and first<=484,
            "probe_steps":n_probe,"task_steps":len(trace),"total_steps":n_probe+len(trace),"environment_resets":1,"actuator_resets":1,
            "host_calls":n_probe+len(trace),"initial_hash":state_hash(initial.observation),"handoff_hash":state_hash(handoff.observation),
            "final_hash":previous,"offset_error_oracle":error}
        if record["outcome"]!=expected_outcome: raise ValueError("outcome reconstruction mismatch")
        outcomes.append(record["outcome"]); task_steps+=len(trace)
    if any(len(v)!=1 for v in prefix_groups.values()) or any(len(v)!=1 for v in initial_groups.values()):
        raise ValueError("paired initial/probe population mismatch")
    stats=summarize(outcomes,c)
    if stats!=summary["statistics"]: raise ValueError("registered statistics mismatch")
    expected_status="COMPLETED_FEASIBILITY_PASS" if stats["gate_passed"] else "COMPLETED_FEASIBILITY_FAILED"
    counts={"status":expected_status,"complete_units":64,"episodes":320,"physical_steps":sum(r["total_steps"] for r in outcomes),
            "environment_resets":320,"api_calls":0,"memory_writes":0}
    if counts["physical_steps"]>160000 or any(status.get(k)!=v or summary.get(k)!=v for k,v in counts.items()): raise ValueError("physical accounting/completion mismatch")
    costs={}
    affine=stats["methods"]["PRIOR_AFFINE"]
    for baseline,v in stats["methods"].items():
        if baseline=="PRIOR_AFFINE": continue
        intercept=affine["mean_amortized_steps"]-v["mean_amortized_steps"]
        slope=affine["mean_amortized_resets"]-v["mean_amortized_resets"]
        costs[baseline]={"affine_minus_baseline_step_intercept":intercept,"reset_cost_slope":slope,
            "equal_mean_cost_at_reset_step_equivalent":-intercept/slope if slope>0 and intercept<0 else None}
    return {**identity,**counts,"model_sha256":m["model_sha256"],"integrity":"PASSED","statistics":stats,
            "replayed_decisions":320,"continuous_handoffs":256,"verified_task_steps":task_steps,
            "offline_steps":2304,"offline_resets":144,"reset_cost_sensitivity":costs,
            "audit_scope":"Decision/model replay, exact observation hash chains and RNG consumption. Task dynamics are not resimulated."}


def analyze(path):
    m=load(path); output=path.parent; model,sha=load_model(m["config"])
    if sha!=m["model_sha256"]: raise ValueError("qualified model changed")
    with gzip.open(output/"episodes.jsonl.gz","rt",encoding="utf-8") as handle: records=[json.loads(x) for x in handle]
    declarations=[json.loads(x) for x in (output/"decisions.jsonl").read_text().splitlines()]
    result=verify(m,records,declarations,json.loads((output/"status.json").read_text()),json.loads((output/"summary.json").read_text()),model)
    result["artifact_sha256"]={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()}
    return result


def report(r):
    lines=["# Qualified response prior: prospective task utility","",f'Status: `{r["status"]}`. Integrity: `{r["integrity"]}`.',"",
        "16 independent task-seed clusters x four contexts; 500 online steps per method episode. All states included.","",
        "| Method | Success / 64 | Mean online steps | Offline steps | Mean amortized steps | Mean offset error | Success with 484 policy steps |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for method,v in r["statistics"]["methods"].items():
        error=f'{v["mean_offset_error_oracle"]:.4f}' if v["mean_offset_error_oracle"] is not None else "n/a"
        lines.append(f'| {method} | {v["successful"]} | {v["mean_online_steps"]:.2f} | {v["offline_steps"]} | {v["mean_amortized_steps"]:.2f} | {error} | {v["success_equal_484_policy_steps"]} |')
    lines += ["","Both priors pay 2,304 offline steps and 144 resets, amortized over 64 units. Offline artifacts were physically shared, not recollected.",
              "The final column is a secondary equal-policy-step cap that permits additional probe cost; it is not used for promotion.",""]
    for baseline,v in r["statistics"]["affine_minus_baseline"].items():
        low,high=v["cluster_bootstrap_95"]
        lines.append(f'- Affine minus {baseline}: {100*v["difference"]:+.2f} pp; seed-cluster 95% interval [{100*low:.2f}, {100*high:.2f}] pp.')
    lines += ["",f'Registered utility gates: `{r["statistics"]["gates"]}`.',"",
        f'{r["replayed_decisions"]} decisions, {r["continuous_handoffs"]} continuous handoffs, and {r["verified_task_steps"]} task-step state/RNG links verified.',
        f'New physical task collection: {r["physical_steps"]} steps and {r["environment_resets"]} initial resets.',"",r["audit_scope"],"",
        "This is a standard calibrated-identification baseline. Task benefit does not establish algorithm novelty, multi-task transfer, or publication readiness.",""]
    return "\n".join(lines)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--manifest",type=Path,required=True); p.add_argument("--output",type=Path,required=True)
    a=p.parse_args(); source=a.manifest.resolve(); output=a.output.resolve()
    if output==source.parent or source.parent in output.parents: raise ValueError("audit must be outside immutable collection")
    result=analyze(source); output.mkdir(parents=True,exist_ok=False)
    (output/"audit.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    (output/"report.md").write_text(report(result),encoding="utf-8"); print(report(result))

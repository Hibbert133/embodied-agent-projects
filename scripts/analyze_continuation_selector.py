"""Rebuild training, causal choices, fixed-branch actions, continuous noise and costs."""
import argparse
from collections import Counter, deque
from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import run_continuation_selector as run
from scripts import analyze_conditional_continuation as fixed
from src.probe.continuation_selector import choose, train, digest
from src.probe.operator_identification import visible_samples
from src.probe.task_value_learner import KernelModel


def statistics(manifest, rows, pairs, repetitions):
    c = manifest["config"]
    indexed = {(r["stream"],r["task"],r["replicate"],r["method"]):r for r in rows}
    expected = {(s,t,r,m) for s in range(16) for t in run.TASKS for r in range(2) for m in run.METHODS}
    pkeys = {(r["stream"],r["task"],r["replicate"],r["method"]) for r in pairs}
    rkeys = {(r["stream"],r["task"],r["replicate"],r["method"]) for r in repetitions}
    if len(rows)!=1152 or set(indexed)!=expected or len(pairs)!=864 or pkeys!={(s,t,r,m) for s in range(16) for t in run.TASKS for r in range(2) for m in run.PORTFOLIO}:
        raise ValueError("complete registered selector population and common prefixes required")
    if len(repetitions)!=576 or rkeys!={(s,t,1,m) for s in range(16) for t in run.TASKS for m in run.METHODS}:
        raise ValueError("complete cross-future prefix population required")
    if any(r["reason"] not in ("MATCHED_ACTIVE_PREFIX","ENDED_BEFORE_EIGHT","ENDED_AT_EIGHT") for r in pairs+repetitions):
        raise ValueError("unmatched declared prefix")
    methods = {}
    for method in run.METHODS:
        part = [r for r in rows if r["method"]==method]
        nominal = 0 if method=="NO_PROBE" else 21010
        training = 101069 if method in run.LEARNED_METHODS else 0
        methods[method] = {"cases":96,"successes":sum(r["success"] for r in part),"stops":sum(r["stopped"] for r in part),
                           "mean_deadline_loss":sum(r["deadline_loss"] for r in part)/96,
                           "total_steps":sum(r["total_steps"] for r in part),
                           "mean_steps":sum(r["total_steps"] for r in part)/96,
                           "mean_probe_steps":sum(r["fixed_probe_steps"] for r in part)/96,
                           "mean_policy_measure_steps":sum(r["policy_measure_steps"] for r in part)/96,
                           "nominal_offline_steps":nominal,"nominal_offline_resets":288 if nominal else 0,
                           "training_offline_steps":training,"training_offline_resets":672 if training else 0,
                           "mean_amortized_steps":(sum(r["total_steps"] for r in part)+nominal+training)/96}
    rng = np.random.default_rng(c["bootstrap_seed"])
    indices = np.concatenate((rng.choice(np.arange(0,16,2),size=(c["bootstrap_samples"],8),replace=True),
                              rng.choice(np.arange(1,16,2),size=(c["bootstrap_samples"],8),replace=True)),axis=1)
    contrasts = {}
    for baseline in run.METHODS:
        if baseline=="MEAN_COST_RBF": continue
        values = np.array([[np.mean([indexed[(s,t,r,"MEAN_COST_RBF")][field]-indexed[(s,t,r,baseline)][field]
                                     for t in run.TASKS for r in range(2)])
                            for field in ("success","deadline_loss","total_steps","fixed_probe_steps")] for s in range(16)],float)
        ci = np.quantile(values[indices].mean(axis=1),(.025,.975),axis=0)
        contrasts[baseline] = {name:{"difference":float(values[:,i].mean()),"paired_cluster_percentile_95":ci[:,i].tolist()}
                               for i,name in enumerate(("success_rate","deadline_loss","actual_steps","probe_steps"))}
    primary = contrasts["POINT16_CYCLE"]; main = methods["MEAN_COST_RBF"]
    dominated = [m for m,v in methods.items() if m!="MEAN_COST_RBF" and v["successes"]>=main["successes"] and v["mean_deadline_loss"]<=main["mean_deadline_loss"]
                 and (v["successes"]>main["successes"] or v["mean_deadline_loss"]<main["mean_deadline_loss"])]
    signal = main["successes"]>=max(v["successes"] for m,v in methods.items() if m!="MEAN_COST_RBF") and primary["deadline_loss"]["paired_cluster_percentile_95"][1]<0 and not dominated
    return {"methods":methods,"main_minus_each_baseline":contrasts,"primary_baseline":"POINT16_CYCLE",
            "development_signal":bool(signal),"main_dominated_by":dominated,"independent_operator_streams":16,
            "strata_streams":[8,8],"prefix_checks":{"cross_method_pairs":864,"across_future_pairs":576},
            "scope":"Prospective standard empirical selector feasibility, not algorithm novelty or independent confirmation of a novel method."}


def verify_record(record, model, sigma, operator, events, env_dt, artifact):
    method = record["method"]
    decisions = [d for d in record["decisions"] if d["action"] in ("SELECT_CONTINUATION","SELECT_INITIAL_PORTFOLIO")]
    selected = method
    if method not in run.LEARNED_METHODS:
        if decisions: raise ValueError("fixed baseline used a learned choice")
    elif method == run.INITIAL_SELECTOR:
        if len(decisions)!=1 or decisions[0]["action"]!="SELECT_INITIAL_PORTFOLIO":
            raise ValueError("exactly one initial task-only choice required")
        decision=decisions[0]; expected=run.choose_initial(record["task"],artifact)
        fixed.equal(expected,decision["selection"]); selected=expected["selected_branch"]
        if decision["at_host_calls"]!=0 or decision["noise_hash"]!=record["initial_noise_hash"] or decision["controller"] is not None or decision["observation_sha256"]!=run.state_hash(record["initial"]["observation"]):
            raise ValueError("initial task-only evidence/budget differs")
        if not record["trace"] or decision["sequence"]>=record["trace"][0]["intent_sequence"] or decision["saved_ns"]>=record["trace"][0]["execution_started_ns"] or type(decision["decision_latency_ns"]) is not int or decision["decision_latency_ns"]<0:
            raise ValueError("initial selection did not precede physical execution")
    elif len(record["trace"])<8 or any(record["trace"][7]["after"][k] for k in ("success","terminated","truncated")):
        if decisions: raise ValueError("selection after prefix already ended")
        selected = "DIRECT_G8"
    else:
        trace = record["trace"][:8]
        samples = visible_samples([run.ContinuousTransition(tuple(r["command"]),tuple(r["before"]["observation"]),tuple(r["after"]["observation"])) for r in trace])
        try:
            reference, _ = run.GaussianReference.from_visible(model,samples,sigma)
        except ValueError:
            if decisions: raise ValueError("choice without finite visible reference")
            selected = "DIRECT_G8"
        else:
            if len(decisions)!=1 or decisions[0]["action"]!="SELECT_CONTINUATION": raise ValueError("exactly one saved eight-step choice required")
            decision = decisions[0]; policy = run.create_task_policy(record["task"])
            observations = [record["initial"]["observation"]]+[r["after"]["observation"] for r in trace]
            raw = np.asarray(policy.get_action(np.asarray(observations[-1])),np.float32).tolist()
            view = run.supervised.evidence(record["task"],observations,[r["command"] for r in trace],reference.controller(),raw)
            run.normal(decision["visible_evidence"])
            fixed.equal(asdict(view),decision["visible_evidence"])
            expected = choose(view,artifact,method); fixed.equal(expected,decision["selection"])
            selected = expected["selected_branch"]
            if decision["at_host_calls"]!=8 or decision["noise_hash"]!=trace[-1]["noise_after_hash"] or decision["observation_sha256"]!=run.state_hash(observations[-1]) or decision["controller"] is not None:
                raise ValueError("choice evidence/budget boundary differs")
            if not trace[-1]["completed_ns"]<decision["saved_ns"] or type(decision["decision_latency_ns"]) is not int or decision["decision_latency_ns"]<0:
                raise ValueError("choice timing differs")
            prefix_complete = [e for e in events if e["event"]=="STEP_COMPLETE" and e["host_calls"]==8]
            if len(prefix_complete)!=1 or decision["sequence"]<=prefix_complete[0]["sequence"] or len(record["trace"])<=8 or decision["sequence"]>=record["trace"][8]["intent_sequence"]:
                raise ValueError("choice did not precede continuation execution")
            if any(row["decision_sequence"]==decision["sequence"] for row in record["trace"]):
                raise ValueError("branch choice used as a continuous controller")
    removed = {d["sequence"] for d in decisions}
    if len([e for e in events if e["event"]=="DECISION" and e["sequence"] in removed])!=len(removed):
        raise ValueError("missing or duplicate saved selection event")
    for decision in decisions:
        matching = [e for e in events if e["event"]=="DECISION" and e["sequence"]==decision["sequence"]]
        if len(matching)!=1: raise ValueError("selection journal event missing")
        fixed.equal(decision,matching[0])
    mapped = {**record,"method":selected,"decisions":[{**d,"method":selected} for d in record["decisions"] if d["sequence"] not in removed]}
    business = deque({**e,"method":selected} for e in events if not(e["event"]=="DECISION" and e["sequence"] in removed))
    fixed.verify_record(mapped,model,sigma,operator,business,env_dt)
    if business: raise ValueError("fixed physical branch replay incomplete")
    return {"selected_branch":selected if decisions or method not in run.LEARNED_METHODS else None,
            "physical_replay_method":selected,"selection":decisions[0]["selection"] if decisions else None,
            "latency_ns":decisions[0]["decision_latency_ns"] if decisions else None}


def analyze(path):
    m = run.load(path); c=m["config"]; output=path.parent; identity={k:m[k] for k in run.IDENTITY}
    for name,expected in m["input_sha256"].items():
        data=subprocess.check_output(["git","show",m["source_git_commit"]+":"+name],cwd=ROOT)
        if __import__("hashlib").sha256(data).hexdigest()!=expected: raise ValueError("frozen Git binding differs")
    artifact = run.supervised.load(c,m["training_artifact_sha256"])
    cases, provenance = run.supervised.extract_source(c)
    if digest(train(cases))!=digest(artifact): raise ValueError("training reconstruction differs")
    trained = ROOT/c["training_output"]
    if json.loads((trained/"dataset.json").read_text(encoding="utf-8"))!={"role":provenance["role"],"cases":run.normal([asdict(case) for case in cases])} or json.loads((trained/"provenance.json").read_text(encoding="utf-8"))!=provenance:
        raise ValueError("training source projection differs")
    equations = 0
    for task, value in artifact["tasks"].items():
        all_losses = np.array([case.branch_future_losses for case in sorted((x for x in cases if x.evidence.task==task),key=lambda x:x.source_group)])
        losses=all_losses[:,[run.supervised.FULL_BRANCHES.index(m) for m in run.BRANCHES],:]
        for key,target in (("mean_rbf",(losses[:,1:]-losses[:,:1]).mean(axis=2)/500.),("single_rbf",(losses[:,1:,0]-losses[:,:1,0])/500.)):
            model = KernelModel.from_saved(value[key]); z=model.support
            gram=np.exp(-((z[:,None]-z[None,:])**2).sum(axis=2)/(2*model.bandwidth_squared))
            if not np.allclose((gram+np.eye(8))@model.weights,target-target.mean(axis=0),atol=1e-12,rtol=0):
                raise ValueError("ridge normal equation differs")
            equations += 4
    models,_,_=run.load_bank(c); profile=json.loads((ROOT/c["nominal_profile_path"]).read_text(encoding="utf-8"))
    clocks=fixed.compiled_clock_units(m); journal=fixed.JournalAudit(identity); rows=[]; pairs=[]; repetitions=[]; choices=[]
    for stream in range(16):
        events=iter(fixed.read_lines(output/f"events_{stream:02}.jsonl.gz")); records={}
        operator=next(v for v in m["operators_oracle"][stream]["states_oracle"] if v["id"]=="A")
        for record in fixed.read_lines(output/f"episodes_{stream:02}.jsonl.gz"):
            if any(record[k]!=v for k,v in identity.items()) or record["stream"]!=stream or record["seed"]!=run.task_seed(stream,record["task"]) or record["operator_id_oracle"]!="A":
                raise ValueError("foreign evaluation record")
            business=deque(); needed=3+len(record["decisions"])+2*len(record["trace"])
            while len(business)<needed:
                item=journal.accept(next(events))
                if item is not None: business.append(item)
            choice=verify_record(record,models[record["task"]],profile["rms_m"][record["task"]],operator,business,clocks[record["task"]]["env_step_seconds"],artifact)
            if journal.ledger!=record["ledger_after"]: raise ValueError("branch lifecycle boundary differs")
            rows.append({**{k:record[k] for k in (*run.IDENTITY,"stream","task","replicate","seed","method","operator_id_oracle")},**record["outcome"]})
            records[(record["task"],record["replicate"],record["method"])]=record
            if record["method"] in run.LEARNED_METHODS:
                choices.append({"stream":stream,"task":record["task"],"replicate":record["replicate"],"method":record["method"],**choice})
        if next(events,None) is not None: raise ValueError("extra journal events")
        journal.boundary()
        for task in run.TASKS:
            for future in range(2):
                for method in run.PORTFOLIO:
                    pairs.append({"stream":stream,"task":task,"replicate":future,"method":method,"reason":run.prefix_match(records[(task,future,method)],records[(task,future,"DIRECT_G8")])})
            for method in run.METHODS:
                repetitions.append({"stream":stream,"task":task,"replicate":1,"method":method,"reason":run.prefix_match(records[(task,1,method)],records[(task,0,method)])})
        print(f"Audited stream {stream+1}/16: {len(rows)}/1152",flush=True)
    for stream in range(16):
        for task in run.TASKS:
            for method in run.LEARNED_METHODS:
                group=[r for r in choices if r["stream"]==stream and r["task"]==task and r["method"]==method]
                if len(group)!=2 or group[0]["selection"]!=group[1]["selection"] or group[0]["selected_branch"]!=group[1]["selected_branch"]:
                    raise ValueError("same-prefix choice changed across future noise")
    stats=statistics(m,rows,pairs,repetitions); steps=sum(r["total_steps"] for r in rows); counts=journal.ledger["counts"]
    if steps>576000 or counts["simulation_frames_completed"]>33000000 or journal.ledger["by_phase"]["CONTROLLED_RESET"]["reset_completed"]!=1152 or counts["simulation_frames_completed"]!=500*counts["reset_completed"]+5*steps:
        raise ValueError("whole experiment cost differs")
    status_name="COMPLETED_SELECTOR_PASSED" if stats["development_signal"] else "COMPLETED_SELECTOR_FAILED"
    expected={**identity,"status":status_name,"episodes":1152,"controlled_steps":steps,"controlled_resets":1152,"api_calls":0,"memory_writes":0,"lifecycle":journal.ledger}
    summary=json.loads((output/"summary.json").read_text(encoding="utf-8")); status=json.loads((output/"status.json").read_text(encoding="utf-8"))
    if status!=expected or any(summary[k]!=v for k,v in expected.items()) or summary["cases"]!=rows or summary["pairs"]!=pairs or summary["prefix_repetitions"]!=repetitions or summary["statistics"]!=stats:
        raise ValueError("terminal statistics or population differs")
    return {**expected,"integrity":"PASSED","statistics":stats,"choices":choices,"training_ridge_equations_checked":equations,
            "events_checked":journal.sequence,"frozen_git_inputs_checked":len(m["input_sha256"]),"clock_units":clocks,
            "artifact_sha256":{p.name:run.digest(p) for p in output.iterdir() if p.is_file()},
            "scope":"Training projection/choices rebuilt; independent ridge equations and noise; fixed-branch verifier and Gaussian/point mathematics explicitly reused. No dynamics resimulation, full hidden-state or physical/probability qualification; no algorithm novelty."}


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("--manifest",type=Path,required=True); parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args(); destination=args.output.resolve()
    if destination.exists() or args.manifest.resolve().parent in destination.parents: raise FileExistsError("new external audit directory required")
    result=analyze(args.manifest.resolve()); destination.mkdir(parents=True,exist_ok=False); run.write_json(destination/"audit.json",result)
    print(json.dumps({k:result[k] for k in ("integrity","status","episodes","controlled_steps")}))

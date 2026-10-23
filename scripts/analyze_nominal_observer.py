"""Independent inverse-formula / chronology / fixed-policy replay; no new physics."""
import argparse
from dataclasses import asdict
import gzip
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import numpy as np
from scripts.run_nominal_observer import load,model,identity,noise_seed,population,summarize
from scripts.run_continuous_probe import normalized,state_hash
from src.probe.continuous import StepObservation,symmetric_program
from src.probe.nominal_observer import InverseSample,passive_affine_fit,mean_blocks
from src.rollout.task_registry import create_task_policy


def rng_hash(rng):
    return hashlib.sha256(json.dumps(rng.bit_generator.state,sort_keys=True).encode()).hexdigest()


def verify_record(m,record,declarations,frozen):
    key={k:record[k] for k in (*identity(m),"episode_index","seed","task","program","model_sha256")}
    if any(key[k]!=v for k,v in identity(m).items()) or key["model_sha256"]!=m["config"]["model_sha256"]:
        raise ValueError("source/model association mismatch")
    if any(any(r.get(k)!=v for k,v in key.items()) for r in [record["outcome"],*declarations]):
        raise ValueError("snapshot/outcome provenance mismatch")
    initial=StepObservation(**record["initial"]);previous=initial;delta_previous=None;samples=[];snapshots=[]
    a,b,c=np.array(frozen.inertia),np.array(frozen.response),np.array(frozen.intercept)
    task=record["task"];program=record["program"];policy=create_task_policy(task)
    rng=np.random.default_rng(noise_seed(record["seed"],m["config"]["tasks"].index(task)))
    probe=symmetric_program() if program=="PROBE_THEN_POLICY" else ()
    n_probe=record["outcome"]["probe_steps"]
    if not 0<=n_probe<=len(probe):raise ValueError("probe budget mismatch")
    handoff=record["handoff"]
    if n_probe==0 and handoff!=normalized({"host_calls":0,"observation":asdict(initial),"rng_hash":rng_hash(rng)}):
        raise ValueError("initial/no-probe handoff mismatch")
    for index,row in enumerate(record["trace"],1):
        before,after=StepObservation(**row["before"]),StepObservation(**row["after"])
        if before!=previous or row["host_calls"]!=index or len(after.observation)!=39:
            raise ValueError("state/counter continuity mismatch")
        if before.success or before.terminated or before.truncated:raise ValueError("step after termination")
        expected_phase="PROBE" if index<=n_probe else "POLICY"
        if row["phase"]!=expected_phase:raise ValueError("probe/policy phase mismatch")
        if expected_phase=="PROBE":
            expected=list(probe[index-1])
            if row["raw_policy"] is not None:raise ValueError("policy attached to diagnostic probe")
        else:
            raw=np.asarray(policy.get_action(np.array(before.observation)),dtype=np.float32)
            if row["raw_policy"]!=raw.tolist():raise ValueError("fixed policy was changed")
            expected=np.clip(raw,-1,1).tolist()
        if row["command"]!=expected:raise ValueError("fixed bounded command mismatch")
        if row["rng_before"]!=rng_hash(rng):raise ValueError("actuator RNG reseeded")
        rng.normal(0,.05,3)
        if row["rng_after"]!=rng_hash(rng):raise ValueError("actuator RNG advance mismatch")
        delta=np.asarray(after.observation[:2])-before.observation[:2]
        estimate=None if delta_previous is None else np.linalg.solve(b,delta-a@delta_previous-c)
        sample=None if estimate is None else InverseSample(index,tuple(expected),tuple(float(v) for v in estimate),expected_phase)
        if normalized(sample.to_dict() if sample else None)!=row["inverse_sample"]:raise ValueError("visible inverse-formula replay mismatch")
        if sample:samples.append(sample)
        delta_previous=delta;previous=after
        if index==n_probe and handoff!=normalized({"host_calls":index,"observation":asdict(after),"rng_hash":rng_hash(rng)}):
            raise ValueError("probe/policy handoff mismatch")
        if index in m["config"]["snapshot_steps"]:
            fit=normalized(passive_affine_fit(samples))
            if len(snapshots)>=len(declarations):raise ValueError("snapshot chronology missing")
            declaration=declarations[len(snapshots)]
            expected_declaration={**key,"step":index,"fit":fit,"samples_seen":len(samples),
                "rng_hash":rng_hash(rng),"observation_hash":state_hash(after.observation)}
            if declaration!=expected_declaration or "nominal_identity_error_inf" in declaration:
                raise ValueError("snapshot used future/evaluator information")
            error=float(np.max(np.abs(np.array(fit["matrix"])-np.array([[1.,0.,0.],[0.,1.,0.]])))) if fit["valid"] else None
            snapshots.append({"step":index,"fit":fit,"nominal_identity_error_inf":error})
    ended=previous.success or previous.terminated or previous.truncated
    total=len(record["trace"])
    if total>500 or not ended and total!=500:raise ValueError("total budget or stopping mismatch")
    if program=="PROBE_THEN_POLICY" and n_probe<16 and not any(handoff["observation"][name] for name in ("success","terminated","truncated")):
        raise ValueError("incomplete diagnostic program")
    if len(declarations)!=len(snapshots):raise ValueError("extra future snapshot")
    blocks=mean_blocks(samples);score=max((r["nominal_mean_error_inf"] for r in blocks),default=None)
    expected_outcome={**key,"success":previous.success,"total_steps":total,"probe_steps":n_probe,
        "environment_resets":1,"actuator_resets":1,"blocks":blocks,"maximum_block_error":score,
        "inverse_samples":len(samples),"incomplete_block_samples":len(samples)%4,"snapshots":snapshots,
        "missing_snapshot_steps":[t for t in m["config"]["snapshot_steps"] if t>total]}
    if expected_outcome!=record["outcome"]:raise ValueError("block/fit/cost scoring mismatch")
    return expected_outcome,state_hash(initial.observation)


def analyze(path):
    m=load(path);root=path.parent;frozen=model(m["config"])
    declarations=[json.loads(line) for line in (root/"snapshots.jsonl").read_text().splitlines()]
    expected=population(m["config"]);outcomes=[];initials={};cursor=0
    with gzip.open(root/"episodes.jsonl.gz","rt",encoding="utf-8") as handle:
        for index,line in enumerate(handle,1):
            r=json.loads(line)
            if index>96 or r["episode_index"]!=index or (r["seed"],r["task"],r["program"])!=expected[index-1]:
                raise ValueError("qualification population/order mismatch")
            end=cursor
            while end<len(declarations) and declarations[end]["episode_index"]==index:end+=1
            outcome,initial=verify_record(m,r,declarations[cursor:end],frozen)
            cursor=end;outcomes.append(outcome);initials.setdefault((r["seed"],r["task"]),set()).add(initial)
    if len(outcomes)!=96 or cursor!=len(declarations) or any(len(v)!=1 for v in initials.values()):
        raise ValueError("paired initial state/snapshot population mismatch")
    status=json.loads((root/"status.json").read_text());summary=json.loads((root/"summary.json").read_text())
    statistics=summarize(outcomes,m["config"])
    if summary["statistics"]!=statistics:raise ValueError("registered statistics mismatch")
    counts={"status":"COMPLETED_FEASIBILITY_PASS" if statistics["gate_passed"] else "COMPLETED_FEASIBILITY_FAILED",
        "episodes":96,"physical_steps":sum(r["total_steps"] for r in outcomes),"environment_resets":96,"snapshots":len(declarations),
        "api_calls":0,"memory_writes":0,"nominal_model_refits":0}
    if counts["physical_steps"]>48000 or any(any(v.get(k)!=x for k,x in {**identity(m),**counts}.items()) for v in (status,summary)):
        raise ValueError("physical accounting or completion mismatch")
    return {**identity(m),**counts,"integrity":"PASSED","statistics":statistics,"replayed_visible_transitions":counts["physical_steps"],
        "continuous_probe_handoffs":48,"old_offline_steps":2304,"old_offline_resets":144,
        "frozen_model_sha256":m["config"]["model_sha256"],"installed_policy_hashes_checked":m["policy_sha256"],
        "artifact_sha256":{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir() if p.is_file()},
        "scope":"Independent inverse formula, saved snapshots before evaluator labels, fixed-policy commands, full visible state/RNG chains and costs. No task dynamics resimulation; empirical feasibility is not a physical/probability contract."}


def report(r):
    lines=["# 名义响应观察：多任务独立审计", "",f'状态 `{r["status"]}`；完整性 `{r["integrity"]}`。',"",
        "| 任务/程序 | 有块轨迹/16 | 轨迹最大块误差 p90 | 最大值 | 名义任务成功/16 |", "|---|---:|---:|---:|---:|"]
    for name,v in r["statistics"]["strata"].items():
        p90=f'{v["p90_episode_max_error"]:.4f}' if v["p90_episode_max_error"] is not None else "n/a"
        maximum=f'{v["maximum_episode_error"]:.4f}' if v["maximum_episode_error"] is not None else "n/a"
        lines.append(f'| {name} | {v["scored_episodes"]} | {p90} | {maximum} | {v["known_nominal_successes"]} |')
    lines += ["",f'固定可行性门：`{r["statistics"]["gates"]}`。',"",
        f'新物理成本 {r["physical_steps"]} 步/96 初始重置；原离线资源 2,304 步/144 次重置另列。',"",
        "公开名义零偏置、噪声标准差 0.05；新任务与程序各 16 个种子。平均四步误差是经验结果，不是 Gaussian 噪声的确定性界。", "",
        "观察资格、概率/任务成功保证仍未建立。被动点辨识没有改变本轮动作，也没有与新控制方法比较任务收益。", "",r["scope"],""]
    return "\n".join(lines)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--manifest",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    a=p.parse_args();source,output=a.manifest.resolve(),a.output.resolve()
    if output==source.parent or source.parent in output.parents:raise ValueError("audit must be outside original collection")
    result=analyze(source);output.mkdir(parents=True,exist_ok=False)
    (output/"audit.json").write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    (output/"report.md").write_text(report(result),encoding="utf-8");print(report(result))

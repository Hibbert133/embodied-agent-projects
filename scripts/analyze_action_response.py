"""Streaming decision/command/RNG audit without robot dynamics resimulation.

Registered planners, predictors, LP and point optimizers are reused. An injected
replay environment supplies only already-recorded observations; separate RNG/
action arithmetic and durable-event comparison verify what was executed.
"""
import argparse
from contextlib import ExitStack
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
from scripts import run_action_response as runner


def equal(actual,expected,path="root"):
    if isinstance(actual,dict) and isinstance(expected,dict):
        if set(actual)!=set(expected):raise ValueError("schema differs: "+path)
        for key in actual:equal(actual[key],expected[key],path+"."+key)
    elif isinstance(actual,(list,tuple)) and isinstance(expected,(list,tuple)):
        if len(actual)!=len(expected):raise ValueError("sequence length differs: "+path)
        for i,(a,b) in enumerate(zip(actual,expected)):equal(a,b,path+f"[{i}]")
    elif type(actual) is int and type(expected) is int:
        if actual!=expected:raise ValueError("integer differs: "+path)
    elif type(actual) in (int,float) and type(expected) in (int,float):
        if not np.isclose(actual,expected,atol=1e-9,rtol=1e-9):raise ValueError("number differs: "+path)
    elif actual!=expected:raise ValueError("value differs: "+path)


class ReplayEnvironment:
    action_space=SimpleNamespace(low=-np.ones(4,dtype=np.float32),high=np.ones(4,dtype=np.float32))
    def __init__(self,record,operator):
        self.record,self.operator=record,operator;self.calls=0;self.resets=0;self.intent=None
        self.rng=np.random.default_rng(runner.actuator_seed(record["seed"],record["task"]))
    def reset(self,seed):
        if self.resets or seed!=self.record["seed"]:raise ValueError("extra/wrong replay reset")
        self.resets+=1
        return np.array(self.record["initial"]["observation"]),{}
    def step(self,actual):
        if self.calls>=len(self.record["trace"]) or self.intent is None:raise ValueError("execution without saved step intent")
        row=self.record["trace"][self.calls];intent=self.intent
        before=hashlib.sha256(json.dumps(self.rng.bit_generator.state,sort_keys=True).encode()).hexdigest()
        sent=np.array(intent["command"],dtype=np.float32);expected=sent.copy()
        expected[:2]=np.array(self.operator["matrix_xy"],dtype=np.float32)@sent[:2]+np.array(self.operator["bias_xy"],dtype=np.float32)
        expected[:3]+=self.rng.normal(0,.05,3).astype(np.float32);expected=np.clip(expected,-1,1)
        after=hashlib.sha256(json.dumps(self.rng.bit_generator.state,sort_keys=True).encode()).hexdigest()
        if not np.array_equal(np.asarray(actual),expected) or before!=row["rng_before"] or after!=row["rng_after"]:
            raise ValueError("independent injected action/RNG arithmetic differs")
        if intent["sequence"]!=row["intent_sequence"] or intent["command"]!=row["command"] or intent["decision_sequence"]!=row["decision_sequence"]:
            raise ValueError("intent was substituted before execution")
        if intent["saved_ns"]>=row["completed_ns"]:raise ValueError("intent did not precede recorded execution")
        self.calls+=1;self.intent=None;final=row["after"]
        return np.array(final["observation"]),0.,final["terminated"],final["truncated"],{"success":final["success"]}
    def close(self):pass


def verify_episode(m,record,operator,state,model,sigma,next_event):
    environment=ReplayEnvironment(record,operator);declarations=[]
    def emit(kind,row):
        saved=next_event()
        equal(runner.normalized(row),{k:v for k,v in saved.items() if k not in ("event","sequence","saved_ns")},"durable event payload")
        if saved["event"]!=kind:raise ValueError("event ordering/type differs")
        if kind=="STEP_INTENT":
            if environment.intent is not None:raise ValueError("unconsumed physical intent")
            environment.intent=saved
        else:declarations.append(saved)
        return saved
    key={k:record[k] for k in (*runner.IDENTITY,"episode_index","stream","task","scenario","method","episode_in_stream","seed","operator_id_oracle")}
    if runner.saved_cache(state["cache"])!=record["cache_before"] or state["version"]!=record["cache_version_before"]:
        raise ValueError("foreign/future/cross-method parameter cache")
    with patch.object(runner,"create_task_environment",return_value=environment):
        try:replay=runner.run_episode(m,key,operator,state,model,sigma,emit)
        except runner.EpisodeFailure as exc:raise ValueError("replay rejected: "+exc.record["error"]) from exc
    if environment.calls!=record["outcome"]["total_steps"] or environment.resets!=1:raise ValueError("recorded cost/reset differs")
    for row in replay["trace"]:row.pop("completed_ns")
    expected=json.loads(json.dumps(record))
    for row in expected["trace"]:row.pop("completed_ns")
    equal(runner.normalized(replay),expected,"case replay")
    if record["outcome"]["total_steps"]>500:raise ValueError("case budget exceeded")
    return record["outcome"],len(declarations)


def verify_git_inputs(m):
    names=m["input_sha256"]
    queries="".join(m["source_git_commit"]+":"+name+"\n" for name in names)
    result=subprocess.run(["git","cat-file","--batch"],cwd=ROOT,input=queries.encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True)
    stream=io.BytesIO(result.stdout)
    for name,expected in names.items():
        header=stream.readline().split()
        if len(header)!=3 or header[1]!=b"blob":raise ValueError("missing frozen Git input: "+name)
        data=stream.read(int(header[2]))
        if stream.read(1)!=b"\n" or hashlib.sha256(data).hexdigest()!=expected:raise ValueError("frozen Git input differs: "+name)


def analyze(manifest):
    m=runner.load(manifest);models,source,source_audit=runner.load_bank(m["config"])
    profile=json.loads((manifest.parent/"nominal_profile.json").read_text())
    expected_profile=runner.nominal_reference_profile(models,source,source_audit)
    equal(profile,expected_profile,"nominal reference profile")
    verify_git_inputs(m);outcomes=[];choices=0;last_sequence=0;initials={}
    with ExitStack() as stack:
        events=stack.enter_context(gzip.open(manifest.parent/"events.jsonl.gz","rt",encoding="utf-8"))
        cases={p:stack.enter_context(gzip.open(manifest.parent/("episodes_"+p+".jsonl.gz"),"rt",encoding="utf-8")) for p in runner.METHODS}
        def next_event():
            nonlocal last_sequence
            try:event=json.loads(next(events))
            except StopIteration:raise ValueError("missing durable event")
            if event["sequence"]!=last_sequence+1:raise ValueError("missing/reordered event sequence")
            last_sequence=event["sequence"];return event
        for stream in range(8):
            bank=m["operators_oracle"][stream]
            for task in runner.TASKS:
                for scenario in runner.SCENARIOS:
                    for method in runner.METHODS:
                        state={"cache":None,"version":0,"last_update_episode":None}
                        for episode in range(6):
                            try:record=json.loads(next(cases[method]))
                            except StopIteration:raise ValueError("missing chronological case")
                            label="A" if scenario=="STATIONARY" else bank["schedule_oracle"][episode]
                            operator=next(o for o in bank["states_oracle"] if o["id"]==label)
                            expected={**runner.identity(m),"episode_index":len(outcomes)+1,"stream":stream,"task":task,"scenario":scenario,
                                "method":method,"episode_in_stream":episode,"seed":runner.environment_seed(stream,task,episode),"operator_id_oracle":label}
                            if any(record[k]!=v for k,v in expected.items()):raise ValueError("source population/order changed")
                            result,n=verify_episode(m,record,operator,state,models[task],profile["rms_m"][task],next_event)
                            outcomes.append(result);choices+=n
                            initials.setdefault((stream,task,episode),set()).add(runner.state_hash(record["initial"]["observation"]))
                    print(f"Audit stream={stream} task={task} scenario={scenario}: {len(outcomes)}/4608",flush=True)
        if any(next(handle,None) is not None for handle in cases.values()) or next(events,None) is not None:raise ValueError("extra source cases/events")
    if any(len(v)!=1 for v in initials.values()):raise ValueError("matched initial state differs")
    stats=runner.summarize(m,outcomes);summary=json.loads((manifest.parent/"summary.json").read_text());status=json.loads((manifest.parent/"status.json").read_text())
    expected_status="COMPLETED_COMPETITIVE_PASS" if stats["strong_baseline_competitive_gate"] else "COMPLETED_COMPETITIVE_FAILED"
    counts={"episodes":4608,"physical_steps":sum(r["total_steps"] for r in outcomes),"environment_resets":4608,"api_calls":0,"memory_writes":0}
    if any(status[k]!=v or summary[k]!=v for k,v in counts.items()) or status["status"]!=expected_status or summary["status"]!=expected_status:raise ValueError("status/cost differs")
    equal(stats,summary["statistics"],"registered statistics")
    return {**runner.identity(m),**counts,"status":expected_status,"integrity":"PASSED","replayed_choices":choices,
        "replayed_step_intents":counts["physical_steps"],"matched_git_inputs":len(m["input_sha256"]),"statistics":stats,
        "artifact_sha256":{p.name:runner.digest(p) for p in manifest.parent.iterdir() if p.is_file()},
        "scope":"Streaming recorded-observation replay; registered selector/predictor/LP/point optimizer and summaries reused, independent injected-action arithmetic/RNG, saved-event order, commands, cache ownership and all costs checked. No dynamics resimulation or confidence qualification."}


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--manifest",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args()
    source=a.manifest.resolve();target=a.output.resolve()
    if target.exists() or target==source.parent or source.parent in target.parents:raise FileExistsError("audit requires a new external directory")
    result=analyze(source);target.mkdir(parents=True,exist_ok=False);runner.write_json(target/"audit.json",result)
    print(json.dumps({k:result[k] for k in ("status","integrity","episodes","physical_steps","replayed_choices")}))

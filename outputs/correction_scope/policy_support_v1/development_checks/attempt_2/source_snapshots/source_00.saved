"""Post-hoc fixed-program compatibility with factual public feedback.

No state after a differing command is ever consumed. A compatibility result is
not a new execution, a general off-policy estimator or a deployment qualification.
"""
from collections import Counter,defaultdict
from contextlib import contextmanager,ExitStack
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime,timezone
from itertools import groupby
from pathlib import Path
from time import perf_counter_ns
import gzip,json,random,subprocess
import numpy as np
from src.analysis import response_qualification_io_v1 as io
from src.analysis import learned_acquisition_native_io_v1 as native
from src.analysis.capsule_record_json_v2 import normalize
from src.analysis.release_learning_guard_v1 import read_only
from src.probe import correction_scope_program_v1 as actor
from src.probe.continuous import StepObservation
from src.probe.physical_reprobe_v1 import StepReceipt

ROOT=io.ROOT;BASE=ROOT/'outputs/correction_scope/policy_support_v1'
CONFIG=ROOT/'configs/movement_task/correction_policy_support_v1.json'
PROTOCOL=ROOT/'docs/protocols/correction_policy_support_v1_zh.md'
SOURCE=ROOT/'outputs/learned_acquisition/native_v1/run_20261027T042530Z_3c437c6d3f5d'
ACTIONS=('CONTINUE','VALIDATE8','MOVE_MEASURE');RATES=(.125,.5,2.,8.)
CANDIDATES=tuple((action,rate) for action in ACTIONS for rate in RATES)


@contextmanager
def no_model_activity(receipt):
    from unittest.mock import patch
    from src.analysis import transfer_risk_math_v1 as network,correction_scope_risk_reference_v1 as risk
    from src.probe import correction_scope_model_v1 as model
    receipt['attempts']=0
    def denied(*args,**kwargs):receipt['attempts']+=1;raise RuntimeError('No model load, inference or fit in fixed-program support analysis')
    with ExitStack() as stack:
        for obj,name in ((np,'load'),(network,'forward'),(network,'fit'),(risk,'predict'),(model,'predict'),(model,'fit')):stack.enter_context(patch.object(obj,name,denied))
        yield


def bounded_bits(command):
    u=np.asarray(command,dtype='<f4')
    io.require(u.shape==(4,) and np.isfinite(u).all() and np.max(np.abs(u))<=1,'bounded finite factual float32 command')
    return u.tobytes()


def ended(current):return any(current[k] for k in ('success','terminated','truncated'))


def random_fingerprint():
    s=np.random.get_state()
    return io.digest([random.getstate(),s[0],s[1].tolist(),int(s[2]),int(s[3]),float(s[4])])


class DifferentCommand(Exception):pass


class CausalReader:
    """Only releases response i after exact command i agreement."""
    def __init__(self,initial,steps):
        actor.model.public_state(initial)
        self.initial=deepcopy(initial);self.current=deepcopy(initial);self.steps=steps
        self.matched=self.examined=self.responses=0;self.difference=None;self.sealed=False;self.prefix=[]
    def consume(self,saved):
        io.require(not self.sealed and self.matched<len(self.steps),'no response after mismatch/source end')
        io.require(saved['at_calls']==self.matched and normalize(saved['before'])==normalize(self.current),'causal current observation')
        factual=self.steps[self.matched];self.examined+=1
        if bounded_bits(saved['command'])!=bounded_bits(factual['command']):
            self.difference=dict(at_control_index=self.matched,replayed_intended_command=saved['command'],factual_sent_command=factual['command'])
            self.sealed=True;raise DifferentCommand()
        # Deliberately do not access factual['after'] above the agreement test.
        response=deepcopy(factual['after']);actor.model.public_state(response);self.responses+=1;self.matched+=1;self.current=response
        self.prefix.append(dict(command=factual['command'],after=response))
        return StepReceipt(StepObservation(**response),self.matched)
    def summary(self):
        complete=self.difference is None
        if complete:io.require(self.matched==len(self.steps) and (ended(self.current) or self.matched==500),'complete factual endpoint')
        return dict(status='SUPPORTED_FACTUAL_OUTCOME' if complete else 'UNKNOWN_AFTER_COMMAND_DIFFERENCE',
            matched_prefix_steps=self.matched,source_commands_examined=self.examined,source_responses_consumed=self.responses,
            first_difference=self.difference,matched_prefix_sha256=io.digest([self.initial,self.prefix]),
            supported_loss=(self.matched if self.current['success'] else 500) if complete else None,
            supported_success=bool(self.current['success']) if complete else None)


def replay(initial,steps,task,boundary,action,rate,*,policy=None):
    from src.rollout.task_registry import create_task_policy
    io.require((action,rate) in CANDIDATES,'registered fixed program')
    reader=CausalReader(initial,steps);events=[];queries=0;before_rng=random_fingerprint()
    fixed=create_task_policy(task) if policy is None else policy
    before_policy=deepcopy(getattr(fixed,'__dict__',{}))
    def query(observation):
        nonlocal queries
        io.require(np.array_equal(observation,reader.current['observation']),'no future or different policy observation')
        queries+=1;return np.asarray(fixed.get_action(np.array(observation,copy=True)),np.float32)
    def save(kind,payload):
        # Software order only. These numbers are not physical timestamps.
        ack=dict(normalize(payload),sequence=len(events),saved_ns=len(events)+1)
        events.append(dict(kind=kind,payload=ack));return ack
    try:
        if not ended(initial):actor.run(task,StepObservation(**deepcopy(initial)),boundary,action,rate,query,reader.consume,save,bank=None)
    except DifferentCommand:pass
    io.require(before_rng==random_fingerprint() and before_policy==getattr(fixed,'__dict__',{}),'fixed policy and global RNG side effects')
    answer=reader.summary();answer.update(replay_fixed_policy_queries=queries,replayed_controller_events=len(events),
        event_classification='SOFTWARE_COMPATIBILITY_ONLY_NOT_EXECUTED_COMMANDS',physical_steps_generated=0)
    return answer


def project(case,events):
    initial=deepcopy(case['initial']);steps=[]
    for e in events:
        if e['event']=='STEP_COMPLETE':
            io.require(e['logical_step']==len(steps),'consecutive saved factual public feedback')
            steps.append(dict(command=deepcopy(e['command']),after=deepcopy(e['after'])))
    io.require(len(steps)==case['total_steps'] and 0<=len(steps)<=500,'source physical count')
    io.require((steps[-1]['after'] if steps else initial)==case['final'],'actual source endpoint')
    return initial,steps


def source_traces():
    cases=list(io.rows(SOURCE/'native/cases.jsonl.gz'));outer=iter(groupby(io.rows(SOURCE/'native/events.jsonl.gz'),native.case_key))
    io.require(len(cases)==54,'complete source54')
    for spec,case in zip(native.population(),cases):
        io.require(all(case[k]==spec[k] for k in native.KEYS),'source assignment')
        key,events=next(outer);io.require(key==native.case_key(spec),'source event ownership')
        initial,steps=project(case,events);yield spec,case,initial,steps
    io.require(next(outer,None) is None,'unallocated source events')


def one_bound(attempts,traces):
    io.require(len(attempts)==3 and sorted(x['source_program'] for x in attempts)==sorted(native.PROGRAMS),'all three source programs retained')
    # Compare only responses already consumed on matching prefixes. Never splice.
    for i,left in enumerate(attempts):
        for right in attempts[i+1:]:
            li,ls=traces[left['source_program']];ri,rs=traces[right['source_program']]
            io.require(li==ri,'same controlled initial public state')
            for n in range(min(left['matched_prefix_steps'],right['matched_prefix_steps'])):
                io.require(bounded_bits(ls[n]['command'])==bounded_bits(rs[n]['command']) and ls[n]['after']==rs[n]['after'],
                    'common-noise deterministic coupling contradicted by factual prefixes')
    known=[x for x in attempts if x['status']=='SUPPORTED_FACTUAL_OUTCOME']
    if known:
        values={(r['supported_loss'],r['supported_success']) for r in known}
        io.require(len(values)==1,'contradictory complete factual outcomes')
        loss,success=next(iter(values));return dict(status='SUPPORTED_FACTUAL_OUTCOME',lower=loss,upper=loss,success=success,
            source_programs=[r['source_program'] for r in known],longest_supported_prefix=max(r['matched_prefix_steps'] for r in attempts))
    lower=max(r['matched_prefix_steps']+1 for r in attempts)
    io.require(lower<=500,'unknown future after registered deadline')
    return dict(status='PARTIALLY_IDENTIFIED',lower=lower,upper=500,success=None,source_programs=[],longest_supported_prefix=lower-1)


def aggregate(rows,traces_by_unit,learned_losses):
    buckets=defaultdict(list)
    for row in rows:buckets[(tuple(row['unit']),row['action'],row['rate'])].append(row)
    bounds=[]
    for (unit,action,rate),attempts in buckets.items():
        b=one_bound(attempts,traces_by_unit[unit]);bounds.append(dict(unit=list(unit),action=action,rate=rate,**b))
    io.require(len(bounds)==216,'all18 units and12 fixed programs')
    summaries=[]
    for action,rate in CANDIDATES:
        values=[b for b in bounds if (b['action'],b['rate'])==(action,rate)]
        low=sum(b['lower'] for b in values);high=sum(b['upper'] for b in values);learned=sum(learned_losses[tuple(b['unit'])] for b in values)
        groups=[]
        for group in range(3):
            v=[b for b in values if b['unit'][1]==group]
            io.require(len(v)==6,'each independent source group complete')
            groups.append(dict(group=group,n=6,supported=sum(b['status']=='SUPPORTED_FACTUAL_OUTCOME' for b in v),
                lower_mean=sum(b['lower'] for b in v)/6,upper_mean=sum(b['upper'] for b in v)/6))
        summaries.append(dict(action=action,rate=rate,n=18,supported=sum(b['status']=='SUPPORTED_FACTUAL_OUTCOME' for b in values),
            unknown=sum(b['status']=='PARTIALLY_IDENTIFIED' for b in values),lower_total=low,upper_total=high,lower_mean=low/18,upper_mean=high/18,
            fixed_minus_learned_lower_mean=(low-learned)/18,fixed_minus_learned_upper_mean=(high-learned)/18,groups=groups))
    return bounds,summaries


def source_bindings():
    commit=io.read(CONFIG)['source_result_commit'];paths=[SOURCE/n for n in ('manifest.json','native/summary.json','native/completion.json',
        'native_audit_repair_v2/audit.json','native_audit_repair_v2/native_gate.json','audit_repair_control_v2/receipt.json',
        'record_archives/index.json','pipeline_control/audit-native_failure.json','result_delivery/results.json')]
    result={}
    for p in paths:
        name=p.relative_to(ROOT).as_posix();data=subprocess.check_output(['git','show',commit+':'+name],cwd=ROOT)
        io.require(io.sha(p)==__import__('hashlib').sha256(data).hexdigest(),'source committed bytes '+name);result[name]=io.sha(p)
    pack=io.read(SOURCE/'record_archives/index.json')
    for f in pack['files']:
        io.require(io.sha(ROOT/f['original'])==f['sha256'],'retained source raw checksum');result[f['original']]=f['sha256']
    io.require(io.read(SOURCE/'native_audit_repair_v2/audit.json')['integrity']=='PASSED','supplemental source audit')
    return result


def prepare(sources):
    v=io.read(BASE/'freeze_validation/complete.json')
    io.require(v['integrity']=='PASSED' and not io.git('status','--porcelain','--untracked-files=no'),'clean committed support freeze')
    io.require(not list(BASE.glob('run_*/manifest.json')),'one frozen read-only allocation, no rerun')
    for n,h in v['source_sha256'].items():io.require(io.sha(ROOT/n)==h,'support source immutable '+n)
    head=io.git('rev-parse','HEAD');out=BASE/('run_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+head[:12]);out.mkdir(exist_ok=False)
    m=dict(protocol='CORRECTION_POLICY_SUPPORT_V1',classification='POST_HOC_FACTUAL_COMPATIBILITY_AND_PARTIAL_BOUNDS_NOT_DEPLOYMENT',
        source_git_commit=head,config=io.read(CONFIG),source_sha256={n:io.sha(ROOT/n) for n in sources},input_sha256=source_bindings(),
        replay_attempts_per_implementation=648,physical_interactions=0,new_model_fits=0,online_LLM_API_calls=0)
    m['manifest_id']=io.digest(m);io.write(out/'manifest.json',m);return out/'manifest.json'


def checked(path):
    path=Path(path).resolve();m=io.read(path);copy=dict(m);mid=copy.pop('manifest_id')
    io.require(path.parent.parent==BASE and mid==io.digest(copy) and m['config']==io.read(CONFIG),'frozen support manifest')
    for n,h in {**m['source_sha256'],**m['input_sha256']}.items():io.require(io.sha(ROOT/n)==h,'immutable support bytes '+n)
    return m


def analyze(path):
    path=Path(path).resolve();m=checked(path);out=path.parent/'analysis';out.mkdir(exist_ok=False);start=perf_counter_ns();guard={}
    rows=[];traces=defaultdict(dict);learned={};initial_witnesses=defaultdict(set);model_guard={}
    try:
        with read_only(guard),no_model_activity(model_guard):
            for spec,case,initial,steps in source_traces():
                unit=native.unit_key(spec);program=spec['program'];traces[unit][program]=(initial,steps)
                w=case['state_witness_refs'][0];io.require(w['label']=='INITIAL','initial coupling witness')
                initial_witnesses[unit].add((w['native_sha256'],w['comparison_python_sha256']))
                if program=='LEARNED_JOINT_BANK0':learned[unit]=case['deadline_loss']
                for action,rate in CANDIDATES:
                    answer=replay(initial,steps,spec['task'],spec['planned_boundary'],action,rate)
                    if answer['status']=='SUPPORTED_FACTUAL_OUTCOME':
                        io.require(answer['supported_loss']==case['deadline_loss'] and answer['supported_success']==case['success'],'complete actual outcome')
                    rows.append(dict(source_spec=spec,source_case_sha256=io.digest(case),source_program=program,unit=list(unit),action=action,rate=rate,**answer))
            io.require(len(rows)==648 and all(len(v)==1 for v in initial_witnesses.values()) and len(initial_witnesses)==18,'complete source and native/RNG coupling')
            io.require(sum(r['replay_fixed_policy_queries'] for r in rows)<=324000,'main replay CPU policy-query budget')
            bounds,summaries=aggregate(rows,traces,learned)
        io.write(out/'attempts.json',rows);io.write(out/'unit_bounds.json',bounds);io.write(out/'fixed_program_bounds.json',summaries)
        result=dict(integrity='FOR_INDEPENDENT_AUDIT',manifest_id=m['manifest_id'],source_cases=54,attempts=648,unit_programs=216,
            replay_fixed_policy_queries=sum(r['replay_fixed_policy_queries'] for r in rows),responses_consumed=sum(r['source_responses_consumed'] for r in rows),
            guard=guard,model_guard=model_guard,source_models_not_loaded_or_refit=True,no_unexecuted_future_states_generated=True,
            current_native_v1_qualification_remains_failed=True,new_physics=0,new_fits=0,online_LLM_API_calls=0,
            wall_ns=perf_counter_ns()-start,artifact_sha256={p.name:io.sha(p) for p in out.iterdir() if p.is_file()})
        io.write(out/'receipt.json',result);return result
    except BaseException:
        import traceback
        io.write(out/'failure.json',dict(integrity='FAILED',exception=traceback.format_exc(),guard=guard,attempts_completed=len(rows),
            replay_policy_queries=sum(r['replay_fixed_policy_queries'] for r in rows),wall_ns=perf_counter_ns()-start,no_automatic_retry=True));raise

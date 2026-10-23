"""Independent saved-record replay; never imports/calls the restore implementation."""
import argparse
import copy
import gzip
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
from scripts import run_strong_chronological_reference_v1 as io
from src.rollout.task_registry import create_task_policy
from src.probe.cache_acquisition_evidence_v1 import digest


def strip_wall(row):
    out=copy.deepcopy(row)
    for key in ('intent_sequence','execution_started_ns','completed_ns','ledger_before','ledger_after'):out.pop(key,None)
    if 'episode' in out.get('info',{}):out['info']['episode'].pop('t',None)
    return out


def compare_pair(left,right):
    if [strip_wall(r) for r in left] != [strip_wall(r) for r in right]:
        raise ValueError('restored continuation mismatch')


def noise(seed):
    key=int(np.random.SeedSequence([seed,64001]).generate_state(1)[0])
    return np.random.default_rng(key).normal(0,.05,(500,3)).astype('<f4')


def expected_applied(command,private_noise):
    # Rebuild independent float32 actuator arithmetic from the registered formula.
    value=np.asarray(command,dtype=np.float32).copy()
    value[0]=np.float32(value[0]+np.float32(.1));value[1]=np.float32(value[1]+np.float32(-.06))
    value[:3]=value[:3]+private_noise
    return np.minimum(np.maximum(value,np.float32(-1)),np.float32(1))


def audit(path):
    m=io.read(path);folder=path.parent/'collection';s=io.read(folder/'summary.json')
    if digest({k:v for k,v in m.items() if k!='manifest_id'})!=m['manifest_id']:raise ValueError('manifest digest')
    identity={k:m[k] for k in io.IDENTITY}
    if any(s[k]!=v for k,v in identity.items()):raise ValueError('summary identity')
    expected=[{'case':i,'seed':18800+i,'replicate':r,'prefix_steps':p,'task':t}
        for i,(r,p,t) in enumerate((r,p,t) for r in range(2) for p in (8,488) for t in ('push-v3','reach-v3','door-open-v3'))]
    if m['population_oracle']!=expected:raise ValueError('independent population')
    if any(io.sha(ROOT/n)!=h for n,h in m['input_sha256'].items()):raise ValueError('frozen source changed')
    completion=io.read(folder/'completion.json')
    if any(completion[k]!=v for k,v in identity.items()):raise ValueError('completion identity')
    if any(io.sha(folder/n)!=h for n,h in completion['artifact_sha256'].items()):raise ValueError('collection bytes changed')
    if s['status']!='COLLECTED_FOR_INDEPENDENT_AUDIT' or s['failure'] is not None or len(s['cases'])!=12:raise ValueError('complete qualification population required')
    if [r['case'] for r in s['cases']]!=list(range(12)):raise ValueError('missing/duplicate case ownership')
    with gzip.open(folder/'events.jsonl.gz','rt',encoding='utf-8') as handle:events=[json.loads(line) for line in handle]
    prior=-1;byseq={};pending=None;phase=None;logical=None;obs=None;time=None;spec=None;policy=None;queries=0;step_count=0
    captures={};restores=0;cases=0;current_branch=None;branch_rows={};reset_intents={};reset_count=0;reset_frames=0
    block=np.asarray([[.4,0,0,0],[.4,0,0,0],[-.4,0,0,0],[-.4,0,0,0],
                      [0,.4,0,0],[0,.4,0,0],[0,-.4,0,0],[0,-.4,0,0]],np.float32)
    for index,event in enumerate(events):
        if event['sequence']!=index or event['saved_ns']<prior:raise ValueError('journal order')
        if any(event[k]!=v for k,v in identity.items()):raise ValueError('event identity')
        prior=event['saved_ns'];byseq[index]=event;kind=event['event']
        if kind=='LIFECYCLE_RESET_INTENT':reset_intents[index]=event
        elif kind=='LIFECYCLE_RESET_COMPLETE':
            start=reset_intents.pop(event['intent_sequence']);before=start['before']['counts'];after=event['after']['counts']
            if after.get('simulation_frames_completed',0)-before.get('simulation_frames_completed',0)!=500:raise ValueError('reset frame accounting')
            reset_count+=1;reset_frames+=500
        elif kind=='CONTROLLED_INITIAL':
            spec=m['population_oracle'][event['case']];policy=create_task_policy(spec['task']);logical=0;obs=event['observation'];time=event['simulation_time'];current_branch=None
        elif kind=='CAPTURE_COMPLETE':
            if event['case']!=spec['case'] or event['case'] in captures:raise ValueError('capture owner')
            if logical!=spec['prefix_steps'] or event['logical_step']!=logical or event['observation']!=obs or event['simulation_time']!=time:raise ValueError('capture boundary')
            start=byseq[event['intent_sequence']]
            if start['event']!='CAPTURE_INTENT' or start['ledger']!=event['ledger']:raise ValueError('capture performed physical work')
            captures[event['case']]=event
        elif kind=='RESTORE_COMPLETE':
            start=byseq[event['intent_sequence']];cap=captures[event['case']]
            if start['event']!='RESTORE_INTENT' or start['ledger']!=event['ledger']:raise ValueError('restore rewound physical costs')
            if event['native_sha256']!=cap['native_sha256'] or event['python_semantic_sha256']!=cap['python_semantic_sha256']:raise ValueError('restored boundary signature')
            if any(event[k]!=cap[k] for k in ('model_address','data_address')):raise ValueError('native addresses changed')
            logical=cap['logical_step'];obs=cap['observation'];time=cap['simulation_time'];restores+=1
        elif kind=='BRANCH_CHOICE':
            if event['case']!=spec['case'] or event['logical_step']!=spec['prefix_steps'] or logical!=spec['prefix_steps']:raise ValueError('branch boundary')
            current_branch=event['branch'];phase=current_branch;branch_rows[(spec['case'],current_branch)]=[]
        elif kind=='STEP_INTENT':
            if event['case']!=spec['case'] or pending is not None or event['logical_step']!=logical or logical>=500:raise ValueError('step order/budget')
            pending=event
            if event['phase']=='PREFIX':probe_index=logical if logical<8 else None
            elif current_branch and event['phase']==current_branch:
                offset=logical-spec['prefix_steps'];probe_index=offset if current_branch.startswith('PROBE8') and offset<8 else None
            else:raise ValueError('step without saved branch')
            if probe_index is None:
                command=np.clip(np.asarray(policy.get_action(np.asarray(obs))),-1,1).astype(np.float32);queries+=1
            else:command=block[probe_index]
            if not np.array_equal(command,np.asarray(event['command'],np.float32)):raise ValueError('saved command differs from fixed program')
        elif kind=='STEP_COMPLETE':
            if pending is None or event['case']!=spec['case'] or event['intent_sequence']!=pending['sequence'] or event['logical_step']!=logical:raise ValueError('completion without intent')
            if not(pending['saved_ns']<=event['execution_started_ns']<=event['completed_ns']<=event['saved_ns']):raise ValueError('execution timestamp')
            if event['command']!=pending['command']:raise ValueError('saved command not consumed')
            applied=expected_applied(event['command'],noise(spec['seed'])[logical])
            if not np.array_equal(applied,np.asarray(event['executed_action_oracle'],np.float32)):raise ValueError('private noise/actuator mismatch')
            if event['simulation_time_before']!=time or not np.isclose(event['simulation_time_after']-time,.0125,atol=1e-10,rtol=0):raise ValueError('physical branch clock')
            before=event['ledger_before']['counts'];after=event['ledger_after']['counts']
            if after.get('simulation_frames_completed',0)-before.get('simulation_frames_completed',0)!=5 or after.get('reset_attempts',0)!=before.get('reset_attempts',0):raise ValueError('step frame/reset cost')
            logical+=1;step_count+=1;obs=event['observation'];time=event['simulation_time_after']
            if event['noise_cursor_after']!=logical:raise ValueError('noise cursor')
            if event['phase']!='PREFIX':
                row={k:v for k,v in event.items() if k not in (*io.IDENTITY,'event','sequence','saved_ns','case','phase')}
                branch_rows[(spec['case'],current_branch)].append(row)
            pending=None
        elif kind=='CASE_COMPLETE':cases+=1
    if pending or reset_intents or cases!=12 or restores!=36 or step_count!=4032 or reset_count!=612:raise ValueError('incomplete actual costs/population')
    if s['actual_controlled_steps']!=step_count or s['actual_controlled_resets']!=12 or s['restore_calls']!=restores or s['policy_queries']!=queries:raise ValueError('summary counts differ')
    counts=s['lifecycle']['counts']
    if s['universal_complete_hidden_state_qualification'] is not False or any(s[k]!=0 for k in ('api_calls','nominal_fits','selector_fits','policy_updates')):raise ValueError('qualification scope changed')
    if counts['reset_completed']!=reset_count or counts['simulation_frames_completed']!=reset_frames+5*step_count or counts['simulation_frames_attempted']!=326160:raise ValueError('full lifecycle mismatch')
    pairs=0
    for record in s['cases']:
        if {k:record[k] for k in ('case','seed','replicate','prefix_steps','task')}!=m['population_oracle'][record['case']]:raise ValueError('case allocation')
        branches=record['branches']
        if [b['branch'] for b in branches]!=['DIRECT_0','PROBE8_0','DIRECT_1','PROBE8_1']:raise ValueError('branch programs changed')
        for branch in branches:
            rows=branch_rows[(record['case'],branch['branch'])]
            choice=byseq[branch['choice_sequence']]
            if choice['event']!='BRANCH_CHOICE' or choice['case']!=record['case'] or choice['branch']!=branch['branch'] or any(r['intent_sequence']<=choice['sequence'] for r in rows):raise ValueError('choice recorded after execution')
            if rows!=branch['trace'] or len(rows)!=min(32,500-record['prefix_steps']):raise ValueError('record/journal branch trace differs')
            if record['prefix_steps']==488 and (not rows[-1]['truncated'] or any(r['truncated'] or r['terminated'] for r in rows[:-1])):raise ValueError('late horizon termination')
        for a,b in ((0,2),(1,3)):compare_pair(branches[a]['trace'],branches[b]['trace']);pairs+=1
    return {**{k:m[k] for k in io.IDENTITY},'integrity':'PASSED','contexts':cases,'matched_continuation_pairs':pairs,'events_checked':len(events),
        'actual_controlled_steps':step_count,'actual_all_resets':reset_count,'actual_requested_frames':326160,'restore_calls':restores,
        'audit_policy_queries':queries,'recorded_policy_queries':s['policy_queries'],'new_environment_steps':0,'new_api_calls':0,
        'summary_sha256':io.sha(folder/'summary.json'),'events_sha256':io.sha(folder/'events.jsonl.gz'),
        'registered_restore_contract_passed':True,'universal_complete_hidden_state_qualification':False,
        'scope':'Independent saved command/noise/lifecycle/trace audit; no native state capture/restore or Env construction. Native boundary signatures are source-generated evidence, not an independent hidden-state proof.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',type=Path,required=True);args=parser.parse_args()
    result=audit(args.manifest.resolve());output=args.manifest.resolve().parent/'audit.json';io.write(output,result,exclusive=True)
    print(json.dumps({k:v for k,v in result.items() if k not in io.IDENTITY}),flush=True)

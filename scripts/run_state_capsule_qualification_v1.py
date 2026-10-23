"""One-shot evaluator restore-contract qualification; no task-performance claim."""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import random
import subprocess
import sys
from time import perf_counter_ns

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from scripts import run_strong_chronological_reference_v1 as io
from src.analysis.state_capsule_v1 import capture, restore, layers, native_hash, state_signature, python_state, NativeCopies
from src.probe.chronological_cache_reference import BLOCK8
from src.probe.cache_acquisition_evidence_v1 import digest
from src.probe.lifecycle_ledger import LifecycleLedger
from src.rollout.task_registry import create_task_environment, create_task_policy

CONFIG = ROOT/'configs/state_capsule/qualification_v1.json'
PROTOCOL = 'docs/protocols/state_capsule_qualification_v1.md'


def population(config):
    return [{'case': i, 'seed': 18800+i, 'replicate': replicate, 'prefix_steps': prefix, 'task': task}
            for i, (replicate, prefix, task) in enumerate((r, p, t) for r in range(2) for p in (8, 488) for t in config['tasks'])]


def validate(c):
    if (c['protocol_id'] != 'state_capsule_qualification_v1' or c['tasks'] != ['push-v3','reach-v3','door-open-v3'] or
        c['seed_start'] != 18800 or c['seed_end'] != 18811 or c['reserved'] != [18812,18999] or c['prefix_lengths'] != [8,488] or
        c['replicates'] != 2 or c['branch_horizon'] != 32 or c['logical_step_budget'] != 500 or c['noise_namespace'] != 64001 or
        c['noise_std'] != .05 or c['bias_xy_oracle'] != [.1,-.06] or c['branch_order'] != ['DIRECT_0','PROBE8_0','DIRECT_1','PROBE8_1'] or
        c['expected_contexts'] != 12 or c['maximum_environment_steps'] != 7392 or c['maximum_controlled_resets'] != 12 or
        c['maximum_simulation_frames'] != 1000000 or c['excluded_trajectory_equality_paths'] != ['info.episode.t'] or
        any(c[k] != 0 for k in ['api_calls','nominal_fits','selector_fits','policy_updates'])):
        raise ValueError('frozen restore qualification changed')


def prepare():
    io.clean(); c = io.read(CONFIG); validate(c)
    source, _, _ = io.load(ROOT/c['source_manifest'])
    output = ROOT/c['output_root']
    if list(output.glob('*/manifest.json')): raise FileExistsError('one-shot qualification already prepared')
    names = set(source['input_sha256']) | set(io.git('ls-files','src','scripts','tests').splitlines()) | {
        CONFIG.relative_to(ROOT).as_posix(), PROTOCOL, 'docs/research/state_capsule_boundary_v1.md','outputs/state_capsule/.gitattributes'}
    commit = io.git('rev-parse','HEAD'); run_id = 'state_capsule_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+commit[:12]
    api = NativeCopies()
    manifest = {'experiment_run_id':run_id,'source_git_commit':commit,'source_manifest_id':source['manifest_id'],
                'config':c,'population_oracle':population(c),'input_sha256':{n:io.sha(ROOT/n) for n in sorted(names)},
                'library_source_sha256':source['library_source_sha256'],'policy_sha256':source['policy_sha256'],
                'native_library_path':str(api.library_path),'native_library_sha256':api.library_sha256}
    manifest['manifest_id'] = digest(manifest)
    folder=output/run_id;folder.mkdir(parents=True);io.write(folder/'manifest.json',manifest,exclusive=True)
    print((folder/'manifest.json').relative_to(ROOT),flush=True)


def load(path):
    m=io.read(path);validate(m['config'])
    if digest({k:v for k,v in m.items() if k!='manifest_id'})!=m['manifest_id'] or any(io.sha(ROOT/n)!=h for n,h in m['input_sha256'].items()):
        raise ValueError('frozen input/manifest changed')
    source,_,_=io.load(ROOT/m['config']['source_manifest'])
    if source['manifest_id']!=m['source_manifest_id'] or population(m['config'])!=m['population_oracle'] or NativeCopies().library_sha256!=m['native_library_sha256']:
        raise ValueError('source/population/native runtime changed')
    return m


def inventory(env):
    return [{ 'class':type(layer).__module__+'.'+type(layer).__qualname__,
              'fields':{k:type(v).__module__+'.'+type(v).__qualname__ for k,v in vars(layer).items()}}
            for layer in layers(env)]


def comparable(row):
    out={k:v for k,v in row.items() if k not in ('intent_sequence','execution_started_ns','completed_ns','ledger_before','ledger_after')}
    out=json.loads(json.dumps(out))
    if 'episode' in out['info']: out['info']['episode'].pop('t',None)
    return out


def run(path):
    io.clean();m=load(path);c=m['config'];identity={k:m[k] for k in io.IDENTITY}
    if io.git('rev-parse','HEAD')!=m['source_git_commit']:raise ValueError('freeze commit differs')
    folder=path.parent/'collection';folder.mkdir();records=[];sequence=0;control_steps=0;restores=0;capture_ns=restore_ns=0;policy_queries=0
    with gzip.open(folder/'events.jsonl.gz','xt',encoding='utf-8') as journal:
        def emit(event,payload):
            nonlocal sequence
            value=io.normal({**identity,'event':event,'sequence':sequence,'saved_ns':perf_counter_ns(),**payload});sequence+=1
            journal.write(json.dumps(value,ensure_ascii=False,allow_nan=False)+'\n');journal.flush();return value
        ledger=LifecycleLedger(emit,c['maximum_simulation_frames'])
        import metaworld
        from metaworld.sawyer_xyz_env import SawyerXYZEnv
        from gymnasium.envs.mujoco import MujocoEnv
        failure=None
        try:
            with ledger.instrument(SawyerXYZEnv,MujocoEnv,metaworld):
                for spec in m['population_oracle']:
                    env=None;record={**identity,**spec,'branches':[],'capture':None};records.append(record)
                    try:
                        np.random.seed(spec['seed']+64001);random.seed(spec['seed']+64002)
                        emit('FACTORY_INTENT',{'case':spec['case'],'ledger':ledger.snapshot()})
                        with ledger.scope('FACTORY_SETUP'):env=create_task_environment(spec['task'],spec['seed'])
                        emit('FACTORY_COMPLETE',{'case':spec['case'],'ledger':ledger.snapshot()})
                        with ledger.scope('CONTROLLED_RESET'):obs,_=env.reset(seed=spec['seed'])
                        base=env.unwrapped;policy=create_task_policy(spec['task']);record['inventory']=inventory(env)
                        for offset,space in enumerate([base.action_space,base.observation_space,base.goal_space]):space.seed(spec['seed']+64010+offset)
                        rng_seed=int(np.random.SeedSequence([spec['seed'],64001]).generate_state(1)[0])
                        noise=np.random.default_rng(rng_seed).normal(0,.05,(500,3)).astype('<f4');noise.flags.writeable=False
                        context={'observation':np.asarray(obs).copy(),'cursor':0,'noise':noise}
                        emit('CONTROLLED_INITIAL',{'case':spec['case'],'observation':obs,'simulation_time':float(base.data.time),'ledger':ledger.snapshot()})
                        def raw_policy():
                            nonlocal policy_queries
                            policy_queries+=1
                            return np.clip(policy.get_action(context['observation']),-1,1)
                        def step(command,phase):
                            nonlocal control_steps
                            cursor=context['cursor']
                            if cursor>=500 or control_steps>=c['maximum_environment_steps']:raise ValueError('actual/logical step cap')
                            command=np.asarray(command,np.float32)
                            if command.shape!=(4,) or not np.isfinite(command).all() or np.any(abs(command)>1):raise ValueError('invalid saved command')
                            witnesses=[float(np.random.random()),random.random(),float(base.np_random.random()),
                                float(base.action_space.np_random.random()),float(base.observation_space.np_random.random()),float(base.goal_space.np_random.random())]
                            action=command.copy();action[:2]+=np.asarray(c['bias_xy_oracle'],np.float32);action[:3]+=context['noise'][cursor];action=np.clip(action,-1,1)
                            before=ledger.snapshot();intent=emit('STEP_INTENT',{'case':spec['case'],'phase':phase,'logical_step':cursor,'command':command.tolist(),'ledger_before':before})
                            started=perf_counter_ns();time_before=float(base.data.time)
                            with ledger.scope('CONTROL'):next_obs,reward,term,trunc,info=env.step(action)
                            control_steps+=1;context['cursor']+=1;context['observation']=np.asarray(next_obs).copy()
                            row=io.normal({'logical_step':cursor,'command':intent['command'],'executed_action_oracle':action.tolist(),'rng_witness':witnesses,
                                'observation':next_obs,'reward':reward,'terminated':bool(term),'truncated':bool(trunc),'info':info,
                                'simulation_time_before':time_before,'simulation_time_after':float(base.data.time),'noise_cursor_after':context['cursor'],
                                'intent_sequence':intent['sequence'],'execution_started_ns':started,'completed_ns':perf_counter_ns(),
                                'ledger_before':before,'ledger_after':ledger.snapshot()})
                            emit('STEP_COMPLETE',{'case':spec['case'],'phase':phase,**row});return row
                        for index in range(spec['prefix_steps']):
                            cmd=BLOCK8[index] if index<8 else raw_policy()
                            row=step(cmd,'PREFIX')
                            if row['terminated'] or row['truncated']:raise ValueError('prefix ended before registered capture')
                        before=ledger.snapshot();intent=emit('CAPTURE_INTENT',{'case':spec['case'],'ledger':before});t=perf_counter_ns()
                        capsule=capture(env,policy,context);elapsed=perf_counter_ns()-t;capture_ns+=elapsed
                        semantic=state_signature(python_state(layers(env),policy,context),base.model,base.data)
                        record['capture']={'intent_sequence':intent['sequence'],'native_sha256':capsule.native_sha256,'python_payload_sha256':capsule.python_sha256,
                            'python_semantic_sha256':semantic,'model_address':base.model._address,'data_address':base.data._address,
                            'observation':context['observation'].tolist(),'logical_step':context['cursor'],'simulation_time':float(base.data.time),
                            'graph_payload_bytes':len(capsule._graph.payload),'python_array_buffer_bytes':sum(len(v) for v in capsule._graph.buffers),'wall_ns':elapsed}
                        if ledger.snapshot()!=before:raise ValueError('capture changed physical ledger')
                        emit('CAPTURE_COMPLETE',{'case':spec['case'],**record['capture'],'ledger':ledger.snapshot()})
                        for number,branch in enumerate(c['branch_order']):
                            if number:
                                base.model.body_pos[-1,0]+=.013;base.model.site_pos[-1,1]+=.02;base.model.opt.gravity[2]+=.4
                                base.data.qvel[:]+=.2;base.data.qacc_warmstart[:]+=.1;base.data.mocap_pos[:,0]+=.03
                                base.curr_path_length+=3
                                if '_prev_obs' in vars(base):base._prev_obs=np.asarray(base._prev_obs)+.7
                                for layer in layers(env):
                                    if '_elapsed_steps' in vars(layer):layer._elapsed_steps+=5
                                context['cursor']+=3;np.random.random();random.random();base.np_random.random()
                                before=ledger.snapshot();event=emit('RESTORE_INTENT',{'case':spec['case'],'branch':branch,'ledger':before});t=perf_counter_ns()
                                context=restore(capsule,env,policy);elapsed=perf_counter_ns()-t;restore_ns+=elapsed;restores+=1
                                if ledger.snapshot()!=before:raise ValueError('restore changed physical ledger')
                                if native_hash(base.model,base.data)!=capsule.native_sha256 or state_signature(python_state(layers(env),policy,context),base.model,base.data)!=semantic:
                                    raise ValueError('restored native/Python semantic state differs')
                                emit('RESTORE_COMPLETE',{'case':spec['case'],'branch':branch,'intent_sequence':event['sequence'],'wall_ns':elapsed,
                                    'native_sha256':capsule.native_sha256,'python_semantic_sha256':semantic,
                                    'model_address':base.model._address,'data_address':base.data._address,'ledger':ledger.snapshot()})
                            declaration=emit('BRANCH_CHOICE',{'case':spec['case'],'branch':branch,'logical_step':context['cursor']})
                            saved={'branch':declaration['branch'],'choice_sequence':declaration['sequence'],'trace':[]};record['branches'].append(saved)
                            for index in range(32):
                                cmd=BLOCK8[index] if saved['branch'].startswith('PROBE8') and index<8 else raw_policy()
                                row=step(cmd,saved['branch']);saved['trace'].append(row)
                                if row['terminated'] or row['truncated']:break
                        if any([comparable(r) for r in record['branches'][a]['trace']]!=[comparable(r) for r in record['branches'][b]['trace']] for a,b in [(0,2),(1,3)]):
                            raise ValueError('repeated continuation differs')
                        emit('CASE_COMPLETE',{'case':spec['case'],'ledger':ledger.snapshot()});print('qualification',spec['case']+1,'/12',flush=True)
                    finally:
                        if env is not None:env.close()
        except BaseException as error:
            failure={'type':type(error).__name__,'reason':str(error)};emit('QUALIFICATION_FAILED',failure)
        status='COLLECTED_FOR_INDEPENDENT_AUDIT' if failure is None else 'FAILED_SAVED_NOT_RETRIED'
        summary={**identity,'status':status,'cases':records,'actual_controlled_steps':control_steps,'actual_controlled_resets':ledger.by_phase.get('CONTROLLED_RESET',{}).get('reset_attempts',0),
            'lifecycle':ledger.snapshot(),'restore_calls':restores,'capture_wall_ns':capture_ns,'restore_wall_ns':restore_ns,'failure':failure,
            'policy_queries':policy_queries,
            'api_calls':0,'nominal_fits':0,'selector_fits':0,'policy_updates':0,'universal_complete_hidden_state_qualification':False}
        io.write(folder/'summary.json',summary,exclusive=True)
    io.write(folder/'completion.json',{**identity,'status':status,'artifact_sha256':{p.name:io.sha(p) for p in folder.iterdir() if p.is_file()}},exclusive=True)
    print(json.dumps({'status':status,'cases':len(records),'steps':control_steps,'failure':failure}),flush=True)
    if failure:raise SystemExit(1)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('operation',choices=['prepare','run']);parser.add_argument('--manifest',type=Path)
    args=parser.parse_args()
    if args.operation=='prepare':prepare()
    elif args.manifest:run(args.manifest.resolve())
    else:parser.error('--manifest required')

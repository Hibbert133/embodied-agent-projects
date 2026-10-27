"""Frozen independent behavior data for a standard performance reference.

This phase allocates NATIVE/TRAIN only; scientific CAL/QUAL remains unopened.
"""
from pathlib import Path
from datetime import datetime,timezone
import shutil
import numpy as np
from src.analysis import response_qualification_io_v1 as io
from src.analysis.episode_seed_inventory_v2 import discover,scan,verify_unchanged
from src.analysis.episode_seed_inventory_audit_v2 import audit as seed_audit
ROOT=io.ROOT;BASE=ROOT/'outputs/occam_reference_train';VALIDATION=BASE/'freeze_validation_v1';OUTPUT=BASE/'development_v1'
CONFIG=ROOT/'configs/movement_task/occam_reference_train_v1.json';PROTOCOL=ROOT/'docs/protocols/occam_reference_train_v1_zh.md';SEEDS=ROOT/'docs/protocols/occam_reference_train_seeds_v1.json'
QUERY=ROOT/'outputs/episode_seed_inventory/query_v2/occam_training_20261028';RUNTIME=ROOT/'outputs/response_action/validation_v1/runtime_lock.json'
TRAIN_PYTHON=Path(r'C:/Users/Administrator/Documents/ChatGPT/robotic agent/.venv-history-training-cpu22/Scripts/python.exe')
KEYS=('phase','group','task','seed','context','planned_boundary','acquisition_action','behavior')
IDENTITY=('experiment_run_id','manifest_id','source_git_commit');PHASES=('NATIVE','TRAIN');BEHAVIORS=('RANDOM_WINDOW','BLOCK_FIXED');ACTIONS=('CONTINUE','VALIDATE8','MOVE_MEASURE')


def population(phase):
    io.require(phase in PHASES,'registered reference training phase');groups,start=(1,166000) if phase=='NATIVE' else (18,166100)
    return [dict(phase=phase,group=g,task=t,seed=start+3*g+i,context=c,planned_boundary=(16,32,64)[g%3],acquisition_action=a,behavior=b)
        for g in range(groups) for i,t in enumerate(('push-v3','reach-v3','door-open-v3')) for c in ('UNCHANGED','CHANGED') for a in ACTIONS for b in BEHAVIORS]


def validate_spec(spec):io.require(type(spec) is dict and set(spec)==set(KEYS) and spec in population(spec.get('phase')),'exact behavior allocation')
def key(spec):return tuple(spec[k] for k in KEYS)
def schedule(spec):
    validate_spec(spec)
    rng=np.random.default_rng(np.random.SeedSequence([spec['seed'],2026102833,ACTIONS.index(spec['acquisition_action'])]))
    values=rng.integers(0,4,31).tolist()
    return values if spec['behavior']=='RANDOM_WINDOW' else [values[0]]*31
def limits(phase):
    n=len(population(phase));return dict(executions=n,control_steps=500*n,controlled_resets=n,all_resets=51*n,physical_frames=28000*n,
        actual_policy_queries_max=500*n,audit_policy_queries_max=500*n,online_filter_updates=0,new_scientific_training_during_collection=0,online_LLM_API_calls=0)
def registry():return dict(protocol='OCCAM_REFERENCE_TRAIN_V1',native_episode_seed_range=[166000,166002],TRAIN_episode_seed_range=[166100,166153],
    reserved_episode_seed_ranges=[[166003,166099],[166154,166999],[167000,168999]],operator_nonce=2026102831,noise_namespace=2026102832,behavior_rng_seed_namespace=2026102833,
    model_init_rng_seed=2026102834,optimizer_rng_seed=2026102835)
def initial_fault():return dict(matrix_xy=[[1.,0.],[0.,1.]],bias_xy=[.12,-.08],deadzone_xy=[0.,0.])
def destination(spec):
    validate_spec(spec)
    if spec['context']=='UNCHANGED':return initial_fault()
    r=np.random.default_rng(np.random.SeedSequence([2026102831,PHASES.index(spec['phase']),spec['group']]))
    return dict(matrix_xy=[[float(r.uniform(.75,1.25)),float(r.uniform(-.2,.2))],[float(r.uniform(-.2,.2)),float(r.uniform(.75,1.25))]],bias_xy=r.uniform(-.2,.2,2).tolist(),deadzone_xy=[0.,0.])
def noise(spec):
    validate_spec(spec);v=np.random.default_rng(np.random.SeedSequence([spec['seed'],2026102832])).normal(0,.05,(500,3)).astype('<f4');v.flags.writeable=False;return v
def learning():return dict(history_steps=8,window_steps=16,bases=8,outputs=1,context_size=16,encoder_hidden=[64],head_hidden=[256,256,256],
    pretrain_attempts=1000,meta_attempts=4000,matched_ERM_attempts=4000,batch_episodes=8,max_support=30,learning_rate=.001,weight_decay=.0001,gradient_norm_limit=10.,
    Adam_updates_max=9000,meta_linear_solves_max=960000,all_training_linear_solves_max=1000000,training_wall_seconds_max=7200,
    target_normalization_floor=.05,model_init_rng_seed=2026102834,optimizer_rng_seed=2026102835,
    support='random-length chronological prefix of complete nonterminal observed windows; zero support uses prior',
    scoring='equal allocated episode mass; per-episode all actual window MSE, including terminal short; empty episode contributes zero with explicit availability',
    checkpoints='PRETRAIN_1000, META_FINAL, MATCHED_ERM_FINAL; no best-checkpoint or QUAL selection',
    CPU='torch2.2.2+cpu, numpy1.26.4, float64, one thread, deterministic; no packages installed')
def config():return dict(protocol='OCCAM_REFERENCE_TRAIN_V1',scope='STANDARD_REFERENCE_TRAINING_NOT_NOVELTY_OR_TASK_QUALIFICATION',
    populations={p:population(p) for p in PHASES},limits={p:limits(p) for p in PHASES},learning=learning(),
    complete_limits=dict(executions=684,control_steps=342000,all_resets=34884,physical_frames=19152000),
    fixed_low_level_policy=True,noise_sigma=.05,per_execution_steps=500,online_LLM_API_calls=0,
    scientific_CAL_QUAL_opened=False,old_QUAL_used=False,publication_goal_complete=False)


def checked(path):
    path=Path(path).resolve();m=io.read(path);v=dict(m);mid=v.pop('manifest_id')
    io.require(path.name=='manifest.json' and path.parent.parent==OUTPUT.resolve() and io.digest(v)==mid and m['config']==config(),'frozen behavior manifest')
    for n,h in m['source_sha256'].items():io.require(io.sha(ROOT/n)==h,'behavior source changed '+n)
    return m


def verify_training_runtime():
    lock=io.read(VALIDATION/'training_runtime_lock.json')
    for name,h in lock['critical_entry_sha256'].items():io.require(io.sha(Path(name))==h,'isolated training runtime entry changed')
    io.require(TRAIN_PYTHON.is_file(),'existing training executable')


def prepare():
    q=io.read(VALIDATION/'complete.json');io.require(q['integrity']=='PASSED' and not io.git('status','--porcelain','--untracked-files=no'),'committed complete freeze')
    io.require(io.read(CONFIG)==config() and io.read(SEEDS)==registry() and not list(OUTPUT.glob('*/manifest.json')),'one allocation only')
    for n,h in q['source_sha256'].items():io.require(io.sha(ROOT/n)==h and io.git('ls-files','--error-unmatch',n)==n,'frozen verified source')
    from src.analysis.response_action_io_v1 import verify_runtime
    verify_runtime(io.read(RUNTIME));verify_training_runtime();io.require(shutil.disk_usage(ROOT).free>=4*1024**3,'four GiB initial reserve')
    old=io.read(QUERY/'inventory.json');io.require(old['status']=='NO_REGISTERED_COLLISION' and io.read(QUERY/'audit.json')['integrity']=='PASSED','independent prior inventory');verify_unchanged(ROOT,old)
    own={CONFIG.resolve(),PROTOCOL.resolve(),SEEDS.resolve()};scope=scan(ROOT,166000,168999,[p for p in discover(ROOT) if p.resolve() not in own]);audit=seed_audit(ROOT,scope)
    io.require(scope['status']=='NO_REGISTERED_COLLISION' and audit['integrity']=='PASSED','current independent inventory')
    head=io.git('rev-parse','HEAD');names=set(io.git('ls-files','src','scripts','tests').splitlines())|set(q['source_sha256'])
    names|={p.relative_to(ROOT).as_posix() for p in (CONFIG,PROTOCOL,SEEDS,VALIDATION/'complete.json',RUNTIME)}
    m=dict(experiment_run_id='occam_reference_train_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+head[:12],source_git_commit=head,
        source_sha256={n:io.sha(ROOT/n) for n in sorted(names)},config=config(),online_LLM_API_calls=0)
    m['manifest_id']=io.digest(m);out=OUTPUT/m['experiment_run_id'];out.mkdir(parents=True,exist_ok=False)
    io.write(out/'manifest.json',m);io.write(out/'seed_scope.json',scope);io.write(out/'seed_scope_audit.json',audit);return out/'manifest.json'


def phase_gate(path,phase):
    m=checked(path);io.require(phase in PHASES,'phase')
    if phase=='TRAIN':io.require(io.read(Path(path).parent/'native/audit.json')['integrity']=='PASSED','complete native data path audit')
    io.require(shutil.disk_usage(ROOT).free>=2*1024**3,'two GiB phase reserve');return m

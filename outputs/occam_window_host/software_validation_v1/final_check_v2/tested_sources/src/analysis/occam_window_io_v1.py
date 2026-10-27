"""One-shot native host qualification, not learned-model qualification."""
from pathlib import Path
from datetime import datetime,timezone
import shutil
import numpy as np
from src.analysis import response_qualification_io_v1 as io
from src.analysis.episode_seed_inventory_v2 import scan,verify_unchanged,discover
from src.analysis.episode_seed_inventory_audit_v2 import audit as audit_inventory
ROOT=io.ROOT;BASE=ROOT/'outputs/occam_window_host';VALIDATION=BASE/'software_validation_v1';OUTPUT=BASE/'native_v1'
CONFIG=ROOT/'configs/movement_task/occam_window_host_v1.json';PROTOCOL=ROOT/'docs/protocols/occam_window_host_v1_zh.md'
SEEDS=ROOT/'docs/protocols/occam_window_host_seeds_v1.json'
QUERY=ROOT/'outputs/episode_seed_inventory/query_v2/occam_window_contract_20261028'
RUNTIME=ROOT/'outputs/response_action/validation_v1/runtime_lock.json'
KEYS=('group','task','seed','context','planned_boundary','acquisition_action','fixture_sign')
IDENTITY=('experiment_run_id','manifest_id','source_git_commit')


def population():
    return [dict(group=g,task=t,seed=164000+3*g+i,context=c,planned_boundary=(16,32,64)[g],
        acquisition_action=('CONTINUE','VALIDATE8','MOVE_MEASURE')[g],fixture_sign=s)
        for g in range(3) for i,t in enumerate(('push-v3','reach-v3','door-open-v3')) for c in ('UNCHANGED','CHANGED') for s in (-1,1)]


def validate_spec(spec):io.require(type(spec) is dict and set(spec)==set(KEYS) and spec in population(),'exact native software allocation')
def key(spec):return tuple(spec[k] for k in KEYS)
def limits():return dict(executions=36,control_steps=18000,controlled_resets=36,all_resets=1836,physical_frames=1008000,
    online_LLM_API_calls=0,scientific_model_training=0,initial_C8_fits=0,maximum_filter_updates=1116,maximum_audit_filter_updates=1116,
    maximum_fixed_policy_queries=18000,maximum_audit_fixed_policy_queries=18000)
def registry():return dict(protocol='OCCAM_WINDOW_HOST_V1',native_episode_seed_range=[164000,164008],
    reserved_episode_seed_range=[164009,164999],noise_namespace=2026102812,operator_nonce=2026102811)
def config():return dict(protocol='OCCAM_WINDOW_HOST_V1',scope='UNTRAINED_NATIVE_SOFTWARE_CONTRACT_NOT_SCIENTIFIC_TRAIN_CAL_QUAL',
    population=population(),limits=limits(),window_steps=16,history_steps=8,beta=0.,noise_sigma=.05,
    public_cost='actual deadline increments /500 + terminal-zero public potential difference; full sum reconstructs cutoff loss',
    potential='min(1,Euclidean distance in metres to public goal); hand for reach, object for push/door; terminal=0',
    failure='500 cutoff loss; actual interaction and unexecuted penalty separate; infrastructure error stops one-shot population',
    partial_window='factual terminal cost saved; no filter update; terminal labels may only score a future independently frozen training objective',
    scientific_collection_authorized=False,online_LLM_API_calls=0,paper_reproduction_complete=False,publication_goal_complete=False)
def initial_fault():return dict(matrix_xy=[[1.,0.],[0.,1.]],bias_xy=[.12,-.08],deadzone_xy=[0.,0.])
def destination(spec):
    validate_spec(spec)
    if spec['context']=='UNCHANGED':return initial_fault()
    r=np.random.default_rng(np.random.SeedSequence([2026102811,spec['group']]))
    return dict(matrix_xy=[[float(r.uniform(.75,1.25)),float(r.uniform(-.2,.2))],
        [float(r.uniform(-.2,.2)),float(r.uniform(.75,1.25))]],bias_xy=r.uniform(-.2,.2,2).tolist(),deadzone_xy=[0.,0.])
def noise(spec):
    validate_spec(spec);v=np.random.default_rng(np.random.SeedSequence([spec['seed'],2026102812])).normal(0,.05,(500,3)).astype('<f4')
    v.flags.writeable=False;return v


def checked(path):
    path=Path(path).resolve();m=io.read(path);v=dict(m);mid=v.pop('manifest_id')
    io.require(path.name=='manifest.json' and path.parent.parent==OUTPUT.resolve() and io.digest(v)==mid and m['config']==config(),'frozen native ownership')
    for n,h in m['source_sha256'].items():io.require(io.sha(ROOT/n)==h,'native source changed '+n)
    return m


def prepare():
    q=io.read(VALIDATION/'complete.json');io.require(q['integrity']=='PASSED' and not io.git('status','--porcelain','--untracked-files=no'),'clean verified freeze')
    io.require(io.read(CONFIG)==config() and io.read(SEEDS)==registry() and not list(OUTPUT.glob('*/manifest.json')),'one-shot exact config')
    for n,h in q['source_sha256'].items():io.require(io.sha(ROOT/n)==h and io.git('ls-files','--error-unmatch',n)==n,'committed checked source')
    from src.analysis.response_action_io_v1 import verify_runtime
    verify_runtime(io.read(RUNTIME));io.require(shutil.disk_usage(ROOT).free>=4*1024**3,'four GiB reserve')
    old=io.read(QUERY/'inventory.json');io.require(io.read(QUERY/'receipt.json')['integrity']=='PASSED' and old['status']=='NO_REGISTERED_COLLISION','independent prior seed query')
    verify_unchanged(ROOT,old)
    # New declarations are expected; rerun both parsers on all other sources.
    own={CONFIG.resolve(),PROTOCOL.resolve(),SEEDS.resolve()}
    scope=scan(ROOT,164000,164999,paths=[p for p in discover(ROOT) if p.resolve() not in own]);ind=audit_inventory(ROOT,scope)
    io.require(scope['status']=='NO_REGISTERED_COLLISION' and ind['integrity']=='PASSED','source-bound independent inventory')
    head=io.git('rev-parse','HEAD');names=set(io.git('ls-files','src','scripts','tests').splitlines())|set(q['source_sha256'])
    names|={p.relative_to(ROOT).as_posix() for p in (CONFIG,PROTOCOL,SEEDS,VALIDATION/'complete.json',RUNTIME)}
    m=dict(experiment_run_id='occam_window_host_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+head[:12],
        source_git_commit=head,source_sha256={n:io.sha(ROOT/n) for n in sorted(names)},config=config(),online_LLM_API_calls=0)
    m['manifest_id']=io.digest(m);out=OUTPUT/m['experiment_run_id'];out.mkdir(parents=True,exist_ok=False)
    io.write(out/'manifest.json',m);io.write(out/'seed_scope.json',scope);io.write(out/'seed_scope_audit.json',ind);return out/'manifest.json'

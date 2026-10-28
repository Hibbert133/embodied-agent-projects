"""New frozen-bank, own-history qualification; old TRAIN and QUAL stay immutable."""
from pathlib import Path
from datetime import datetime,timezone
import gzip,shutil
import numpy as np
from src.analysis import response_qualification_io_v1 as io
from src.analysis.episode_seed_inventory_v2 import discover,scan,verify_unchanged
from src.analysis.episode_seed_inventory_audit_v2 import audit as seed_audit
from src.probe.occam_qualification_program_v1 import PROGRAMS,PROGRAM_ALIASES,program_spec
ROOT=io.ROOT;BASE=ROOT/'outputs/occam_reference_qualification_v1';OUTPUT=BASE/'qualification_v1';VALIDATION=BASE/'freeze_validation_v1'
CONFIG=ROOT/'configs/movement_task/occam_reference_qualification_v1.json'
PROTOCOL=ROOT/'docs/protocols/occam_reference_qualification_v1_zh.md';SEEDS=ROOT/'docs/protocols/occam_reference_qualification_seeds_v1.json'
RUNTIME=ROOT/'outputs/response_action/validation_v1/runtime_lock.json';PHASES=('NATIVE','QUAL')
KEYS=('cohort','group','task','seed','context','planned_boundary','program');IDENTITY=('experiment_run_id','manifest_id','source_git_commit')
TRAIN=ROOT/'outputs/occam_reference_train_v3/development_v1/occam_reference_train_v3_20261028T071949Z_c92356173d9e'
DELIVERY=ROOT/'outputs/occam_reference_train_v3/learning_delivery_v1/complete.json'
MODEL_HASHES={'META_FINAL':'f09a294a09ef2883fb6a8b4f7ffdc07da4281a6be6ce238af9ff60809caaaa2d',
    'MATCHED_ERM_FINAL':'0f01c0e37e9a2795718040d96827670d2fec5a0c98ed2829e8b7ede05255a755'}


def population(phase):
    io.require(phase in PHASES,'registered independent qualification phase')
    groups,start=(1,175000) if phase=='NATIVE' else (9,175100)
    return [dict(cohort=phase,group=g,task=t,seed=start+3*g+i,context=c,planned_boundary=(16,32,64)[g%3],program=p)
        for g in range(groups) for i,t in enumerate(io.TASKS) for c in ('UNCHANGED','CHANGED') for p in PROGRAMS]


def validate_spec(spec):io.require(type(spec) is dict and set(spec)==set(KEYS) and spec in population(spec.get('cohort')),'exact frozen deployment program')
def key(spec):return tuple(spec[k] for k in KEYS)


def registry():return dict(protocol='OCCAM_REFERENCE_QUALIFICATION_V1',native_episode_seed_range=[175000,175002],
    QUAL_episode_seed_range=[175100,175126],reserved_episode_seed_ranges=[[175003,175099],[175127,177999]],
    operator_nonce=2026102871,noise_namespace=2026102872,bootstrap_seed=2026102873,
    global_rng_seed_numpy=2026102864,global_rng_seed_python=2026102865)


def initial_fault():return dict(matrix_xy=[[1.,0.],[0.,1.]],bias_xy=[.12,-.08],deadzone_xy=[0.,0.])


def destination(spec):
    validate_spec(spec)
    if spec['context']=='UNCHANGED':return initial_fault()
    r=np.random.default_rng(np.random.SeedSequence([registry()['operator_nonce'],PHASES.index(spec['cohort']),spec['group']]))
    return dict(matrix_xy=[[float(r.uniform(.75,1.25)),float(r.uniform(-.2,.2))],[float(r.uniform(-.2,.2)),float(r.uniform(.75,1.25))]],
        bias_xy=r.uniform(-.2,.2,2).tolist(),deadzone_xy=[0.,0.])


def noise(spec):
    validate_spec(spec);v=np.random.default_rng(np.random.SeedSequence([spec['seed'],registry()['noise_namespace']])).normal(0,.05,(500,3)).astype('<f4')
    v.flags.writeable=False;return v


def limits(phase):
    n=len(population(phase));groups=1 if phase=='NATIVE' else 9
    return dict(executions=n,control_steps=n*500,controlled_resets=n,all_resets=n*51,physical_frames=n*28000,
        actual_policy_queries_max=n*500,audit_policy_queries_max=n*500,
        model_window_queries_max=groups*72*31,online_filter_updates_max=groups*36*31,
        c4_c8_fit_attempts_max=groups*24,c4_c8_optimizer_nfev_max=groups*24*64,
        audit_c4_c8_refits_max=groups*24,audit_solve_max=groups*36*32,
        new_neural_or_response_training=0,online_LLM_API_calls=0)


def sources():
    receipt=io.read(DELIVERY);train=io.read(TRAIN/'learning/complete.json');audit=io.read(TRAIN/'learning/model_audit.json')
    io.require(receipt['integrity']=='PASSED_FROZEN_TRAINING_AND_INDEPENDENT_MATHEMATICS_ONLY' and train['integrity']==audit['integrity']=='PASSED','fixed complete training and mathematics')
    hashes={DELIVERY.relative_to(ROOT).as_posix():io.sha(DELIVERY),
        (TRAIN/'learning/complete.json').relative_to(ROOT).as_posix():io.sha(TRAIN/'learning/complete.json'),
        (TRAIN/'learning/model_audit.json').relative_to(ROOT).as_posix():io.sha(TRAIN/'learning/model_audit.json')}
    norm=TRAIN/'learning/normalization.json';hashes[norm.relative_to(ROOT).as_posix()]=io.sha(norm)
    for label,h in MODEL_HASHES.items():
        p=TRAIN/'learning'/(label+'_raw.json');io.require(io.sha(p)==h==train['checkpoints'][label]['raw_sha256'],'preassigned model bank, never best-checkpoint selection')
        hashes[p.relative_to(ROOT).as_posix()]=h
    io.require(io.sha(ROOT/io.C8)==io.C8_SHA,'original C8 nominal source unchanged');hashes[io.C8]=io.C8_SHA
    return hashes


def provider(spec):
    validate_spec(spec);p=program_spec(spec['program'])
    from src.probe.occam_qualification_provider_v1 import TrainedProvider,FixedRateProvider
    if p['kind'] in ('FIXED','FIXED_GLOBAL'):return FixedRateProvider(p['rate'])
    if p['kind']=='LEGACY':return None
    path=TRAIN/'learning'/(p['bank']+'_raw.json');io.require(io.sha(path)==MODEL_HASHES[p['bank']],'unchanged deployed bank')
    return TrainedProvider(io.read(path),adapt=p['adapt'])


def nominal(spec):
    validate_spec(spec)
    if program_spec(spec['program'])['kind']!='LEGACY':return None
    io.require(io.sha(ROOT/io.C8)==io.C8_SHA,'fixed original C8 source');return io.read(ROOT/io.C8)['joint'][spec['task']]


def execution():return dict(worker_wall_seconds=210,termination_wait_seconds=5,resource_sample_interval_seconds=.25,
    worker_private_commit_cap_bytes=2*1024**3,admission_available_commit_bytes=4*1024**3,
    initial_disk_bytes=4*1024**3,phase_disk_bytes=2*1024**3,live_available_commit_bytes=512*1024**2,live_disk_bytes=512*1024**2,
    phase_wall_seconds_max=dict(NATIVE=10800,QUAL=43200),one_complete_case_per_process=True,no_retries=True,
    full_runtime_hash_check_each_worker=True)


def config():return dict(protocol='OCCAM_REFERENCE_QUALIFICATION_V1',scope='STANDARD_REFERENCE_OWN_HISTORY_NOT_NEW_ACQUISITION_OR_NOVELTY',
    populations={p:population(p) for p in PHASES},limits={p:limits(p) for p in PHASES},
    complete_limits=dict(executions=1740,control_steps=870000,controlled_resets=1740,all_resets=88740,physical_frames=48720000,
        online_filter_updates_max=11160,c4_c8_fit_attempts_max=240,c4_c8_optimizer_nfev_max=15360,audit_c4_c8_refits_max=240,audit_solve_max=11520),
    isolated_execution=execution(),model_sha256=dict(MODEL_HASHES),program_aliases=dict(PROGRAM_ALIASES),beta=0.,history_steps=8,window_steps=16,
    process_global_rng={k:registry()[k] for k in ('global_rng_seed_numpy','global_rng_seed_python')},
    per_execution_steps=500,noise_sigma=.05,fixed_low_level_policy=True,global_rng_seed_numpy=2026102864,global_rng_seed_python=2026102865,
    primary_program='META_ADAPT__CONTINUE',primary_comparators=['PI_0125__CONTINUE','PI_0500__CONTINUE','PI_2000__CONTINUE','PI_8000__CONTINUE',
        'GLOBAL_PI_0125','GLOBAL_PI_2000','GLOBAL_PI_8000','ERM_ADAPT__CONTINUE','DIRECT_C8','MOVE_INTEGRAL'],
    task_gate='all ten whole-group paired bootstrap95 upper bounds strictly below zero; success changes fully disclosed',
    predictive_gate='on own factual windows only: primary model minus frozen TRAIN constant MSE whole-group95 upper below zero and each task point below zero; no missing task',
    prediction_constant=io.read(TRAIN/'learning/normalization.json')['target_mean'],
    group_bootstrap=dict(independent_groups=9,boundary_strata=3,replicates=10000,seed=2026102873),
    no_beta_or_model_selection=True,probability_calibration_qualification=False,online_LLM_API_calls=0,
    new_neural_or_response_training=0,final_A_method_qualification=False,publication_goal_complete=False)


def checked(path):
    from src.analysis.occam_qualification_case_io_v1 import check_manifest
    m=check_manifest(path)
    for n,h in {**m['source_sha256'],**m['input_sha256']}.items():io.require(io.sha(ROOT/n)==h,'immutable complete source/input '+n)
    return m


def prepare():
    from src.analysis.occam_qualification_case_io_v1 import require_science_resources,runtime_bindings
    require_science_resources(initial=True);q=io.read(VALIDATION/'complete.json')
    io.require(q['integrity']=='PASSED' and not io.git('status','--porcelain','--untracked-files=no'),'committed full implementation freeze')
    io.require(io.read(CONFIG)==config() and io.read(SEEDS)==registry() and not list(OUTPUT.glob('*/manifest.json')),'one frozen allocation only')
    for n,h in q['source_sha256'].items():io.require(io.sha(ROOT/n)==h and io.git('ls-files','--error-unmatch',n)==n,'verified committed source '+n)
    for n,h in q['input_sha256'].items():io.require(io.sha(ROOT/n)==h,'unchanged validation/source input '+n)
    for n,h in io.read(VALIDATION/'source_reuse.json')['source_sha256'].items():io.require(io.sha(ROOT/n)==h,'source-bound reused checks '+n)
    for n,h in sources().items():io.require(q['input_sha256'][n]==h,'frozen model/input source')
    from src.analysis.response_action_io_v1 import verify_runtime
    verify_runtime(io.read(RUNTIME))
    with gzip.open(BASE/'seed_precheck_v1/inventory.json.gz','rt',encoding='utf8') as f:prior=__import__('json').load(f)
    io.require(prior['status']=='NO_REGISTERED_COLLISION' and io.read(BASE/'seed_precheck_v1/audit.json')['integrity']=='PASSED','initial independent seed scan');verify_unchanged(ROOT,prior)
    own={CONFIG.resolve(),PROTOCOL.resolve(),SEEDS.resolve()}
    scope=scan(ROOT,175000,177999,[p for p in discover(ROOT) if p.resolve() not in own]);audit=seed_audit(ROOT,scope)
    io.require(scope['status']=='NO_REGISTERED_COLLISION' and audit['integrity']=='PASSED','current complete independent seed audit')
    require_science_resources(initial=True);head=io.git('rev-parse','HEAD');names=set(io.git('ls-files','src','scripts','tests').splitlines())|set(q['source_sha256'])
    m=dict(experiment_run_id='occam_reference_qualification_v1_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+head[:12],
        source_git_commit=head,source_sha256={n:io.sha(ROOT/n) for n in sorted(names)},
        input_sha256={**q['input_sha256'],(VALIDATION/'complete.json').relative_to(ROOT).as_posix():io.sha(VALIDATION/'complete.json')},native_runtime_bindings=runtime_bindings(),
        config=config(),online_LLM_API_calls=0)
    m['manifest_id']=io.digest(m);out=OUTPUT/m['experiment_run_id'];out.mkdir(parents=True,exist_ok=False)
    io.write(out/'manifest.json',m);io.write(out/'seed_scope.json',scope);io.write(out/'seed_scope_audit.json',audit);return out/'manifest.json'


def phase_gate(path,phase):
    from src.analysis.occam_qualification_case_io_v1 import require_science_resources
    m=checked(path);io.require(phase in PHASES,'registered phase');require_science_resources(initial=False)
    if phase=='QUAL':
        for name in ('process_audit.json','audit.json'):
            r=io.read(Path(path).parent/'native'/name);io.require(r['integrity'] in ('PASSED','PASSED_ISOLATED_PROCESS_AND_BYTE_CONTINUITY_ONLY'),'both complete Native gates')
    return m

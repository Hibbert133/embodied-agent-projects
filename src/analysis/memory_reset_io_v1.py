"""Independent standard memory-reset qualification; no learned controller."""
from pathlib import Path
from datetime import datetime,timezone
import shutil
import numpy as np
from src.analysis import response_qualification_io_v1 as io
from src.analysis.memory_reset_seed_scope_v1 import inventory
from src.probe.memory_reset_program_v1 import PROGRAMS,NATIVE_PROGRAMS
ROOT=io.ROOT;BASE=ROOT/'outputs/memory_reset';OUTPUT=BASE/'qualification_v1';VALIDATION=BASE/'validation_v1'
CONFIG=ROOT/'configs/movement_task/memory_reset_qualification_v1.json'
PROTOCOL=ROOT/'docs/protocols/memory_reset_qualification_v1_zh.md'
SEEDS=ROOT/'docs/protocols/memory_reset_seeds_v1.json'
KEYS=('cohort','group','task','seed','context','planned_boundary','program')
IDENTITY=('experiment_run_id','manifest_id','source_git_commit')
OWN=('src/probe/controller_memory_transition_v1.py','src/probe/memory_reset_program_v1.py',
    'src/analysis/memory_reset_seed_scope_v1.py','src/analysis/memory_reset_io_v1.py',
    'src/analysis/memory_reset_host_v1.py','src/analysis/memory_reset_collect_v1.py',
    'src/analysis/memory_reset_audit_v1.py','src/analysis/memory_reset_streaming_audit_v1.py',
    'src/analysis/memory_reset_statistics_v1.py','src/analysis/memory_reset_statistics_audit_v1.py',
    'scripts/run_memory_reset_v1.py','scripts/audit_memory_reset_v1.py','scripts/report_memory_reset_v1.py',
    'scripts/plot_memory_reset_v1.py','tests/test_memory_reset_v1.py')


def population(cohort):
    io.require(cohort in ('SOFTWARE_NATIVE','QUAL'),'registered cohort')
    native=cohort=='SOFTWARE_NATIVE';groups=3 if native else 9;start=73200 if native else 73000
    return [dict(cohort=cohort,group=g,task=t,seed=start+3*g+i,context=c,planned_boundary=(16,32,64)[g%3],program=p)
        for g in range(groups) for i,t in enumerate(io.TASKS) for c in ('UNCHANGED','CHANGED') for p in (NATIVE_PROGRAMS if native else PROGRAMS)]

def validate_spec(spec):io.require(spec in population(spec.get('cohort')),'registered immutable execution')

def limits(cohort):
    io.require(cohort in ('SOFTWARE_NATIVE','QUAL'),'registered cost phase');n=90 if cohort=='SOFTWARE_NATIVE' else 540
    return dict(executions=n,control_steps=n*500,controlled_resets=n,all_resets=n*51,physical_frames=n*28000,
                c4_c8_fit_attempts=0 if cohort=='SOFTWARE_NATIVE' else 216)

def registry():return dict(protocol='memory_reset_qualification_v1',QUAL_episode_seed_range=[73000,73026],
    QUAL_reserved_episode_seed_range=[73027,73199],native_episode_seed_range=[73200,73208],
    native_reserved_episode_seed_range=[73209,73999],QUAL_operator_nonce=202610231,QUAL_noise_namespace=202610232,
    native_operator_nonce=202610233,native_noise_namespace=202610234,bootstrap_seed=202610235)

def initial_fault():return dict(matrix_xy=[[1.,0.],[0.,1.]],bias_xy=[.12,-.08],deadzone_xy=[0.,0.])

def namespace(spec):return 202610234 if spec['cohort']=='SOFTWARE_NATIVE' else 202610232

def destination(spec):
    validate_spec(spec)
    if spec['context']=='UNCHANGED':return initial_fault()
    nonce=202610233 if spec['cohort']=='SOFTWARE_NATIVE' else 202610231
    r=np.random.default_rng(np.random.SeedSequence([nonce,spec['group']]))
    return dict(matrix_xy=[[float(r.uniform(.75,1.25)),float(r.uniform(-.2,.2))],
                           [float(r.uniform(-.2,.2)),float(r.uniform(.75,1.25))]],
                bias_xy=r.uniform(-.2,.2,2).tolist(),deadzone_xy=[0.,0.])

def noise(spec):
    r=np.random.default_rng(int(np.random.SeedSequence([spec['seed'],namespace(spec)]).generate_state(1)[0]))
    v=r.normal(0,.05,(500,3)).astype('<f4');v.flags.writeable=False;return v

def source_models():
    io.require(io.sha(ROOT/io.C8)==io.C8_SHA,'frozen C8 nominal source changed')
    return io.read(ROOT/io.C8)['joint'],{io.C8:io.C8_SHA}

def config():return dict(protocol='MEMORY_RESET_QUALIFICATION_V1',classification='STANDARD_COUNTERMECHANISM_NOT_NEW_ALGORITHM',
    populations={p:population(p) for p in ('SOFTWARE_NATIVE','QUAL')},limits={p:limits(p) for p in ('SOFTWARE_NATIVE','QUAL')},
    combined_limits=dict(executions=630,control_steps=315000,controlled_resets=630,all_resets=32130,physical_frames=17640000,
                         c4_c8_fit_attempts=216,audit_c4_c8_refits_max=216),
    per_execution_steps=500,noise_sigma=.05,control_period_s=.0125,RAW_task_PI_time_constant_s=.5,legacy_C8_model_sha256=io.C8_SHA,
    relocation_P=8.,relocation_D_displacement=16.,relocation_integral_gain=.32,relocation_integral_limit=.5,
    relocation_command_limit=.5,movement_step_limit=64,measurement_steps=8,task_reserve=100,
    qualification=dict(primary='RAW_RESET_I',comparator='RAW_CONTINUE',full_population_loss_group_CI95_upper_below_zero=True,
        success_change_fully_disclosed_no_hidden_noninferiority_gate=True,secondary_cannot_replace_primary=True,
        reference_or_component_gain_does_not_qualify_full_new_algorithm=True),
    bootstrap=dict(replicates=10000,seed=202610235,unit='Whole independent group stratified by boundary, 3 groups per stratum',
        quantiles='Exact linear interpolation at 1/40 and 39/40 on integer group totals, then divide by 54; strict sign'),
    direct_reset='At live boundary zero only task integral; no physical step/reset, measurement, policy query or controller/gain change',
    moved_reset='Same complete actual 8-step window admission as measured reference update; otherwise KEEP from actual state',
    no_op='Saved and consumed identity memory transition, exact full physical and fixed-policy trace equality with RAW',
    primary_loss='Actual whole-program steps on success; 500 on failure/stop. Acquisition included exactly once',
    native_gate='All 90 exact records, no-op equality, continuity and budgets; at least one consumed direct reset and one post-move reset. Not a task-benefit gate',
    failure='One native then one QUAL. Error stops and retains partial. No retries, replacement, extension, tuning or main-candidate swap',
    new_response_training=0,new_policy_training=0,new_online_LLM_API_calls=0,publication_goal_complete=False,no_safety_or_bumpless_guarantee=True)

def seed_scope():return inventory(ROOT,{p.relative_to(ROOT).as_posix() for p in (CONFIG,PROTOCOL,SEEDS)})

def checked(path):
    path=Path(path).resolve();v=io.read(path);body=dict(v);mid=body.pop('manifest_id')
    io.require(path.name=='manifest.json' and path.parent.parent==OUTPUT.resolve() and io.digest(body)==mid and v['config']==config(),'owned frozen manifest')
    for n,h in {**v['source_sha256'],**v['model_input_sha256']}.items():io.require(io.sha(ROOT/n)==h,'frozen source changed '+n)
    return v

def prepare():
    qa=io.read(VALIDATION/'complete.json');io.require(qa['integrity']=='PASSED' and not io.git('status','--porcelain','--untracked-files=no'),'clean checked freeze')
    io.require(not list(OUTPUT.glob('*/manifest.json')) and io.read(CONFIG)==config() and io.read(SEEDS)==registry(),'one frozen allocation')
    for n,h in qa['source_sha256'].items():io.require(io.sha(ROOT/n)==h and io.git('ls-files','--error-unmatch',n)==n,'committed checked source')
    from src.analysis.response_action_io_v1 import verify_runtime
    verify_runtime(io.read(VALIDATION/'runtime_lock.json'));io.require(shutil.disk_usage(ROOT).free>=4*1024**3,'four GiB storage reserve')
    scope=seed_scope();_,inputs=source_models();head=io.git('rev-parse','HEAD')
    names=set(io.git('ls-files','src','scripts','tests').splitlines())|set(OWN)|{p.relative_to(ROOT).as_posix() for p in (CONFIG,SEEDS,PROTOCOL)}
    names|={(VALIDATION/n).relative_to(ROOT).as_posix() for n in ('complete.json','runtime_lock.json')}
    v=dict(experiment_run_id='memory_reset_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+head[:12],
        source_git_commit=head,source_sha256={n:io.sha(ROOT/n) for n in sorted(names)},model_input_sha256=inputs,
        config=config(),classification='STANDARD_COUNTERMECHANISM_ONLY',publication_goal_complete=False)
    v['manifest_id']=io.digest(v);out=OUTPUT/v['experiment_run_id'];out.mkdir(parents=True,exist_ok=False)
    io.write(out/'manifest.json',v);io.write(out/'seed_scope.json',scope);return out/'manifest.json'

def phase_gate(path,cohort):
    m=checked(path);io.require(cohort in ('SOFTWARE_NATIVE','QUAL'),'registered phase')
    if cohort=='QUAL':
        r=io.read(Path(path).parent/'software_native/audit.json')
        io.require(r['integrity']=='PASSED' and r['native_software_contract']=='PASSED','native software gate required')
    io.require(shutil.disk_usage(ROOT).free>=4*1024**3,'storage reserve');return m

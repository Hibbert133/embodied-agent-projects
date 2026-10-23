"""Independent standard acquisition/reference qualification; no method learning."""
from pathlib import Path
from datetime import datetime,timezone
import re,shutil
import numpy as np
from src.analysis import response_qualification_io_v1 as io
from src.probe.acquisition_reference_program_v1 import PROGRAMS
ROOT=io.ROOT;BASE=ROOT/'outputs/acquisition_reference';OUTPUT=BASE/'qualification_v1';VALIDATION=BASE/'validation_v1'
CONFIG=ROOT/'configs/movement_task/acquisition_reference_qualification_v1.json'
PROTOCOL=ROOT/'docs/protocols/acquisition_reference_qualification_v1_zh.md'
SEEDS=ROOT/'docs/protocols/acquisition_reference_seeds_v1.json'
KEYS=('cohort','group','task','seed','context','planned_boundary','program')
IDENTITY=('experiment_run_id','manifest_id','source_git_commit')
OWN=('src/probe/relocation_reference_update_v1.py','src/probe/acquisition_reference_operation_v1.py','src/probe/acquisition_reference_program_v1.py',
    'src/analysis/acquisition_reference_io_v1.py','src/analysis/acquisition_reference_host_v1.py','src/analysis/acquisition_reference_collect_v1.py',
    'src/analysis/acquisition_reference_audit_v1.py','src/analysis/acquisition_reference_statistics_v1.py','src/analysis/acquisition_reference_statistics_audit_v1.py',
    'scripts/run_acquisition_reference_v1.py','scripts/audit_acquisition_reference_v1.py','scripts/report_acquisition_reference_v1.py','scripts/figure_acquisition_reference_v1.py',
    'tests/test_acquisition_reference_v1.py')


def population(cohort):
    io.require(cohort in ('SOFTWARE_NATIVE','QUAL'),'registered cohort');groups=1 if cohort=='SOFTWARE_NATIVE' else 9;start=67200 if cohort=='SOFTWARE_NATIVE' else 67000
    return [{'cohort':cohort,'group':g,'task':t,'seed':start+3*g+i,'context':c,'planned_boundary':(16,32,64)[g%3],'program':p}
        for g in range(groups) for i,t in enumerate(io.TASKS) for c in ('UNCHANGED','CHANGED') for p in PROGRAMS]
def validate_spec(spec):io.require(spec in population(spec.get('cohort')),'registered immutable execution')
def limits(cohort):
    n=60 if cohort=='SOFTWARE_NATIVE' else 540
    return {'executions':n,'control_steps':n*500,'controlled_resets':n,'all_resets':n*51,'physical_frames':n*28000,'c4_c8_fit_attempts':24 if cohort=='SOFTWARE_NATIVE' else 216}
def registry():return {'protocol':'acquisition_reference_qualification_v1','QUAL_episode_seed_range':[67000,67026],'QUAL_reserved_episode_seed_range':[67027,67099],
    'future_reserved_episode_seed_range':[67100,67199],'native_episode_seed_range':[67200,67202],'native_reserved_episode_seed_range':[67203,67299],
    'QUAL_noise_namespace':150002,'QUAL_operator_nonce':150001,'native_noise_namespace':150012,'native_operator_nonce':150011,'bootstrap_seed':202610701}
def initial_fault():return {'matrix_xy':[[1.,0.],[0.,1.]],'bias_xy':[.12,-.08],'deadzone_xy':[0.,0.]}
def destination(spec):
    validate_spec(spec)
    if spec['context']=='UNCHANGED':return initial_fault()
    nonce=150011 if spec['cohort']=='SOFTWARE_NATIVE' else 150001;r=np.random.default_rng(np.random.SeedSequence([nonce,spec['group']]))
    return {'matrix_xy':[[float(r.uniform(.75,1.25)),float(r.uniform(-.2,.2))],[float(r.uniform(-.2,.2)),float(r.uniform(.75,1.25))]],'bias_xy':r.uniform(-.2,.2,2).tolist(),'deadzone_xy':[0.,0.]}
def noise(spec):
    namespace=150012 if spec['cohort']=='SOFTWARE_NATIVE' else 150002
    r=np.random.default_rng(int(np.random.SeedSequence([spec['seed'],namespace]).generate_state(1)[0]));v=r.normal(0,.05,(500,3)).astype('<f4');v.flags.writeable=False;return v
def source_models():
    io.require(io.sha(ROOT/io.C8)==io.C8_SHA,'frozen C8 nominal source changed');return io.read(ROOT/io.C8)['joint'],{io.C8:io.C8_SHA}
def config():return {'protocol':'ACQUISITION_REFERENCE_QUALIFICATION_V1','classification':'STANDARD_ACTION_AND_REFERENCE_BRANCH_NOT_NEW_ALGORITHM',
    'populations':{p:population(p) for p in ('SOFTWARE_NATIVE','QUAL')},'limits':{p:limits(p) for p in ('SOFTWARE_NATIVE','QUAL')},
    'combined_limits':{'executions':600,'control_steps':300000,'controlled_resets':600,'all_resets':30600,'physical_frames':16800000,'c4_c8_fit_attempts':240,'audit_c4_c8_refits_max':240},
    'per_execution_steps':500,'noise_sigma':.05,'control_period_s':.0125,'RAW_task_PI_time_constant_s':.5,'legacy_C8_model_sha256':io.C8_SHA,
    'relocation_P':8.,'relocation_D_displacement':16.,'relocation_integral_gain':.32,'relocation_integral_limit':.5,
    'relocation_command_limit':.5,'movement_step_limit':64,'measurement_steps':8,'task_reserve':100,
    'qualification':{'acquisition_reference':'LOCAL_PID_KEEP','acquisition_comparator':'FIXED_PD_KEEP','window_point_minimum':.5,'full_windows_each_task_context_minimum':3,
        'window_paired_group_bootstrap95_lower_above_zero':True,'primary_update':'LOCAL_PID_REFERENCE_RESET','primary_update_comparator':'LOCAL_PID_KEEP',
        'primary_update_paired_group_bootstrap95_upper_below_zero':True,'primary_update_actual_adoptions_each_task_minimum':1,
        'CARRY_is_fixed_secondary_no_selection_or_replacement':True,'full_cost_gain_over_RAW_C8_integral_is_not_claimed_by_action_or_branch_qualification':True},
    'bootstrap':{'replicates':10000,'seed':202610701,'unit':'Whole independent group stratified by planned boundary, 3 groups per stratum',
        'quantiles':'Exact linear interpolation at 1/40 and 39/40 on integer group totals, then divide by 54; strict sign at zero'},
    'reference_admission':'Live full actual SelectedAnchorWindow, or registered NO_PROBE reference after actual ready relocation; else keep. Standard offset, not qualified physical identification',
    'primary_loss':'Full actual total steps on success; 500 on task/fit/software stop. All acquisition included once; no future-outcome substitution',
    'failure':'One native cohort and one QUAL cohort. Error stops and preserves partial. No retries/replacements/append/tuning. QUAL blocked if native contract fails.',
    'new_response_training':0,'new_policy_training':0,'new_online_LLM_API_calls':0,'publication_goal_complete':False,'no_safety_or_bumpless_guarantee':True}


def seed_scope():
    # Same exhaustive walker, with a new declared range and no global patching.
    old=ROOT/'src/analysis/memory_acquisition_io_v1.py';text=old.read_text(encoding='utf-8');begin=text.index('def seed_scope():');end=text.index('\n\ndef checked(',begin)
    body=text[begin:end].replace('65099','67299').replace('65000','67000')
    namespace={'ROOT':ROOT,'CONFIG':CONFIG,'PROTOCOL':PROTOCOL,'SEEDS':SEEDS,'io':io,'re':re}
    exec(compile(body,str(old)+'::independent-range-walker','exec'),namespace);result=namespace['seed_scope']();result['walker_source_sha256']=io.sha(old);return result


def checked(path):
    path=Path(path).resolve();v=io.read(path);body=dict(v);mid=body.pop('manifest_id')
    io.require(path.name=='manifest.json' and path.parent.parent==OUTPUT.resolve() and io.digest(body)==mid and v['config']==config(),'owned frozen manifest')
    for n,h in {**v['source_sha256'],**v['model_input_sha256']}.items():io.require(io.sha(ROOT/n)==h,'frozen source changed '+n)
    return v
def prepare():
    qa=io.read(VALIDATION/'complete.json');io.require(qa['integrity']=='PASSED' and not io.git('status','--porcelain','--untracked-files=no'),'clean checked freeze')
    io.require(not list(OUTPUT.glob('*/manifest.json')) and io.read(CONFIG)==config() and io.read(SEEDS)==registry(),'one allocation and frozen config')
    for n,h in qa['source_sha256'].items():io.require(io.sha(ROOT/n)==h and io.git('ls-files','--error-unmatch',n)==n,'committed checked source')
    from src.analysis.response_action_io_v1 import verify_runtime
    verify_runtime(io.read(VALIDATION/'runtime_lock.json'));io.require(shutil.disk_usage(ROOT).free>=4*1024**3,'four GiB storage reserve')
    scope=seed_scope();_,inputs=source_models();head=io.git('rev-parse','HEAD')
    names=set(io.git('ls-files','src','scripts','tests').splitlines())|set(OWN)|{p.relative_to(ROOT).as_posix() for p in (CONFIG,SEEDS,PROTOCOL)}
    names|={(VALIDATION/n).relative_to(ROOT).as_posix() for n in ('complete.json','runtime_lock.json')}
    v={'experiment_run_id':'acquisition_reference_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+head[:12],
        'source_git_commit':head,'source_sha256':{n:io.sha(ROOT/n) for n in sorted(names)},'model_input_sha256':inputs,'config':config(),'classification':'STANDARD_REFERENCE_ONLY','publication_goal_complete':False}
    v['manifest_id']=io.digest(v);out=OUTPUT/v['experiment_run_id'];out.mkdir(parents=True,exist_ok=False);io.write(out/'manifest.json',v);io.write(out/'seed_scope.json',scope);return out/'manifest.json'
def phase_gate(path,cohort):
    m=checked(path);io.require(cohort in ('SOFTWARE_NATIVE','QUAL'),'registered phase')
    if cohort=='QUAL':
        r=io.read(Path(path).parent/'software_native/audit.json');io.require(r['integrity']=='PASSED' and r['native_software_contract']=='PASSED','native software gate required')
    io.require(shutil.disk_usage(ROOT).free>=4*1024**3,'storage reserve');return m

"""One-shot full-task action-ranking reference allocation and independent entry gates."""
from datetime import datetime,timezone
from pathlib import Path
import re
import shutil
import numpy as np
from src.analysis import observable_history_io_v1 as io
from src.analysis import command_contrast_io_v1 as sources
from src.probe.response_action_program_v1 import Program,CONTROLS,PI_STYLES,LOCKED_PI
from src.probe.response_action_rank_v1 import WEIGHTS

ROOT=io.ROOT;COHORTS=('SOFTWARE_NATIVE','DEV','QUAL');GAINS={'push-v3':10.,'reach-v3':5.,'door-open-v3':25.}
OUTPUT=ROOT/'outputs/response_action/development_v1';VALIDATION=ROOT/'outputs/response_action/validation_v1'
CONFIG=ROOT/'configs/movement_task/response_action_execution_v1.json'
PROTOCOL=ROOT/'docs/protocols/response_action_execution_v1_zh.md';SEEDS=ROOT/'docs/protocols/response_action_seed_registry_v1.json'
KEYS=('cohort','case_id','unit_id','group','task','seed','context','style','time_constant_s','regularization_weight')
REQUIRED=tuple('src/'+p for p in ('probe/response_action_rank_v1.py','probe/response_action_program_v1.py',
    'analysis/response_action_io_v1.py','analysis/response_action_host_v1.py','analysis/response_action_collect_v1.py',
    'analysis/response_action_audit_v1.py','analysis/response_action_rank_audit_v1.py','analysis/response_action_statistics_v1.py',
    'analysis/response_action_statistics_audit_v1.py'))+(
    'scripts/run_response_action_v1.py','scripts/audit_response_action_v1.py','scripts/audit_response_action_statistics_v1.py','tests/test_response_action_rank_v1.py',
    'tests/test_response_action_program_v1.py','tests/test_response_action_pipeline_v1.py')
runtime_fingerprints=sources.runtime_fingerprints;verify_runtime=sources.verify_runtime;VERSIONS=sources.VERSIONS


def program_id(style,ti=None,weight=None):return style+('_W'+str(float(weight)) if weight is not None else '_T'+str(float(ti)) if ti is not None else '')
def spec_id(s):return program_id(s['style'],s['time_constant_s'],s['regularization_weight'])


def programs(cohort,selection=None):
    io.require(cohort in COHORTS,'registered phase')
    p=[Program(s) for s in CONTROLS]+[Program(s,LOCKED_PI[s]) for s in PI_STYLES]
    if cohort=='QUAL':io.require(type(selection) in (int,float) and selection in WEIGHTS,'locked F20 weight')
    p += [Program('F20_RANK',regularization_weight=w) for w in ((selection,) if cohort=='QUAL' else WEIGHTS)]
    return p+[Program('KINEMATIC_RANK',regularization_weight=1.)]


def population(cohort,selection=None):
    groups,start,noise,nonce={'SOFTWARE_NATIVE':(1,64200,130012,130011),'DEV':(6,64000,130002,130001),'QUAL':(9,64100,130004,130003)}[cohort]
    cases=[]
    for g in range(groups):
        for i,task in enumerate(GAINS):
            for context in (('CHANGED',) if cohort=='SOFTWARE_NATIVE' else ('UNCHANGED','CHANGED')):
                unit=f'{cohort}/{g:02d}/{task}/{context}'
                for p in programs(cohort,selection):
                    cases.append({'cohort':cohort,'case_id':unit+'/'+program_id(p.style,p.time_constant_s,p.regularization_weight),
                        'unit_id':unit,'group':g,'task':task,'seed':start+g*3+i,'context':context,'style':p.style,
                        'time_constant_s':p.time_constant_s,'regularization_weight':p.regularization_weight,
                        'planned_boundary':(16,32,64)[g%3],'noise_namespace':noise,'operator_nonce':nonce,'maximum_steps':500})
    return cases


def validate_spec(spec):
    io.require(type(spec) is dict and spec.get('cohort') in COHORTS,'strict allocated case')
    w=spec.get('regularization_weight') if spec.get('style')=='F20_RANK' else WEIGHTS[0]
    io.require(spec in population(spec['cohort'],w if spec['cohort']=='QUAL' else None),'case outside frozen population')


def limits(cohort):
    n,fits={'SOFTWARE_NATIVE':(36,60),'DEV':(432,720),'QUAL':(540,864)}[cohort]
    return {'executions':n,'control_steps':500*n,'controlled_resets':n,'factory_resets':50*n,'all_resets':51*n,
        'physical_frames':28000*n,'online_c4_c8_fit_attempts':fits,'independent_audit_c4_c8_refits':fits,
        'response_model_forward_evaluations':{'SOFTWARE_NATIVE':44280,'DEV':531360,'QUAL':265680}[cohort],
        'kinematic_proxy_evaluations':{'SOFTWARE_NATIVE':14760,'DEV':177120,'QUAL':265680}[cohort],
        'independent_rank_raw_coefficient_forecasts':{'SOFTWARE_NATIVE':22140,'DEV':265680,'QUAL':132840}[cohort],
        'new_response_predictor_training':0,'new_policy_training':0,'new_api_calls':0}


def expected_config():
    return {'protocol':'response_action_execution_v1','source_diagnostic_commit':'0d006c08831f9812fa2f170ddd50b49523f751d9',
        'scope':'ENGINEERING_CONTROL_INTERFACE_DEVELOPMENT_THEN_INDEPENDENT_OWN_HISTORY_TASK_QUALIFICATION',
        'groups':{'SOFTWARE_NATIVE':1,'DEV':6,'QUAL':9},'tasks':list(GAINS),'contexts':['UNCHANGED','CHANGED'],
        'registered_programs':[p.to_dict() for p in programs('DEV')],
        'limits':{c:limits(c) for c in COHORTS},'combined_limits':{k:sum(limits(c)[k] for c in COHORTS) for k in limits('DEV')},
        'per_execution_steps':500,'movement_steps':64,'noise_sigma':.05,'control_period_s':.0125,
        'fixed_policy_gains_per_m':GAINS,'locked_PI_time_constants_s':LOCKED_PI,'rank_weights':list(WEIGHTS),
        'rank_model':'FEEDBACK8 task-matching LINEAR_F20; full saved conditional model, actual sent command input; no inverse or nominal-plant interpretation',
        'rank_candidates':['BASELINE','X_PLUS','X_MINUS','Y_PLUS','Y_MINUS'],'candidate_xy_offset':.25,
        'rank_reference':'0.01 * clip(original float32 policy action,-1,1).XY metres; provisional mocap-shaped tracking reference, not measured hand response',
        'rank_score':'squared XY prediction-reference distance + weight*(0.01 metre)^2*squared XY candidate-minus-bounded-C8 command distance',
        'rank_start':'After actual C8 at step8; use real last three public observations, one policy query and saved selection per actual task step',
        'rank_precision':'All five bounded commands rounded to float32 BEFORE prediction and selection; keep clipped duplicate labels',
        'rank_ties':'First ordered candidate; baseline wins exact ties','rank_model_forward_evaluations_per_step':10,
        'kinematic':'Same five C8-based candidates, reference and score; prediction0.01*sentXY, fixed weight1; no learned predictor fee',
        'baseline_behavior':'All eight old programs unchanged, including four old locked PI references; no new time-constant selection',
        'initial_fault':{'matrix_xy':[[1.,0.],[0.,1.]],'bias_xy':[.12,-.08],'deadzone_xy':[0.,0.]},
        'change':'Private affine update at actual completed16/32/64 if alive; same world/RNG/noise/clock; no ranker boundary input',
        'selection':'One global F20 weight minimizing complete DEV cutoff-loss sum; tie largest weight; no task/context selection',
        'development_gate':'Selected F20 full DEV mean loss strictly below every one of eight baselines and KINEMATIC_RANK; otherwise stop without QUAL',
        'primary_controls':['DIRECT_C8','MOVE_INTEGRAL','RAW_TASK_PI_T0.5','KINEMATIC_RANK_W1.0'],
        'qualification_gate':'All four co-primary paired whole-group bootstrap95 upper bounds<0; selected F20 point mean below all nine controls; full success changes disclosed',
        'bootstrap':{'replicates':10000,'DEV_seed':202610400,'QUAL_seed':202610401,'unit':'WHOLE_GROUP_STRATIFIED_BY_BOUNDARY'},
        'loss':'Actual total control steps on success;500 on invalid/stop/task failure; C8 and movement already counted once',
        'early_end':'Retain all assignments; no forced change/movement/command after early success; unavailable phases null with reasons',
        'native_contract':'All allocated executions audited; every rank program has a real plan on each task; PI styles have actual plans; no task-gain requirement',
        'failure':'Software/response numerical or validation errors stop one-shot phase with incomplete allocation preserved; invalid C4/C8 stops case at loss500; no substitute/retry/append',
        'source_costs':'Full C8 bank and complete historical predictor FIT parent/training fees plus previous PI tuning disclosed; source steps separately amortized, not hidden or double-charged',
        'new_api_calls':0,'new_response_predictor_training':0,'new_policy_training':0,'retry':False,'append_samples':False,
        'disk_free_floor_bytes':4*1024**3,'runtime_emergency_free_floor_bytes':512*1024**2,
        'source_nominal_c8_sha256':io.C8_SHA,'source_predictors_index_sha256':sources.INDEX_SHA,
        'expected_runtime_versions':VERSIONS,'no_safety_guarantee':True,'no_algorithmic_novelty_claim':True}


def registry():
    return {'protocol':'response_action_execution_v1','DEV_episode_seed_range':[64000,64017],'DEV_reserved_episode_seed_range':[64018,64099],
        'QUAL_episode_seed_range':[64100,64126],'QUAL_reserved_episode_seed_range':[64127,64199],
        'native_episode_seed_range':[64200,64202],'native_reserved_episode_seed_range':[64203,64299],
        'noise_namespaces':[130002,130004,130012],'operator_nonces':[130001,130003,130011],
        'bootstrap_seeds':[202610400,202610401],'reuse':'Only explicit same-unit paired programs/context; no across-phase seed reuse'}


def noise(seed,namespace):
    io.require(namespace in (130002,130004,130012),'registered immutable initial tape')
    key=int(np.random.SeedSequence([seed,namespace]).generate_state(1)[0]);t=np.random.default_rng(key).normal(0,.05,(500,3)).astype('<f4');t.flags.writeable=False;return t
def initial_fault():return expected_config()['initial_fault']
def destination(spec):
    validate_spec(spec)
    if spec['context']=='UNCHANGED':return initial_fault()
    r=np.random.default_rng(np.random.SeedSequence([spec['operator_nonce'],spec['group']]))
    return {'matrix_xy':[[float(r.uniform(.75,1.25)),float(r.uniform(-.2,.2))],[float(r.uniform(-.2,.2)),float(r.uniform(.75,1.25))]],
        'bias_xy':r.uniform(-.2,.2,2).tolist(),'deadzone_xy':[0.,0.]}


def seed_scope():
    # Reuse the existing exhaustive registry walker with a distinct proposed range;
    # no process-global monkeypatch and no access to old raw trajectories.
    old=ROOT/'src/analysis/task_passive_io_v1.py'
    text=old.read_text(encoding='utf-8');start=text.index('def seed_scope():');end=text.index('\n\ndef source_models():',start)
    body=text[start:end].replace('63299','64299').replace('63000','64000').replace('63099','64099').replace('63100','64100').replace('63199','64199').replace('63200','64200')
    namespace={'ROOT':ROOT,'CONFIG':CONFIG,'PROTOCOL':PROTOCOL,'SEEDS':SEEDS,'io':io,'re':re}
    exec(compile(body,str(old)+'::new-range-walker','exec'),namespace)
    result=namespace['seed_scope']();result['walker_source_sha256']=io.sha(old);return result


def source_models():
    banks,nominal,inputs=sources.source_models();rank={}
    for task,models in banks.items():
        key=f'FEEDBACK8/{task}/LINEAR_F20';model,sha=models[key];rank[task]=(key,sha,model)
    previous=ROOT/'outputs/task_passive/development_v1/task_passive_20261022T032948Z_67fefc4da922/selection.json'
    locked=io.read(previous)['selected_time_constants_s'];io.require(locked==LOCKED_PI,'old locked passive parameters changed')
    inputs[previous.relative_to(ROOT).as_posix()]=io.sha(previous)
    return nominal,rank,inputs


def check_storage():io.require(shutil.disk_usage(ROOT).free>=4*1024**3,'NEEDS_STORAGE: four GiB reserve before environment construction')
def verify_checks():
    v=io.read(VALIDATION/'complete.json');io.require(v['integrity']=='PASSED','source-bound checks required')
    for n,h in v['python_source_sha256'].items():io.require(io.sha(ROOT/n)==h,'checked source changed '+n)
    for n,h in v['receipt_sha256'].items():io.require(io.sha(VALIDATION/n)==h,'check receipt changed '+n)
    io.require(not io.git('status','--porcelain','--untracked-files=no'),'clean committed freeze required')
    for n in (*REQUIRED,CONFIG.relative_to(ROOT).as_posix(),PROTOCOL.relative_to(ROOT).as_posix(),SEEDS.relative_to(ROOT).as_posix()):io.require(io.git('ls-files','--error-unmatch',n)==n,'required code not committed')
    return v


def prepare():
    io.require(not list(OUTPUT.glob('*/manifest.json')),'one allocation only; retain every previous attempt')
    verify_checks();io.require(io.read(CONFIG)==expected_config() and io.read(SEEDS)==registry(),'config drift');check_storage()
    scope=seed_scope();_,_,inputs=source_models();verify_runtime(io.read(VALIDATION/'runtime_lock.json'))
    head=io.git('rev-parse','HEAD');now=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    names=set(io.git('ls-files','src','scripts','tests').splitlines())|set(REQUIRED)|{CONFIG.relative_to(ROOT).as_posix(),PROTOCOL.relative_to(ROOT).as_posix(),SEEDS.relative_to(ROOT).as_posix()}
    value={'experiment_run_id':'response_action_'+now+'_'+head[:12],'source_git_commit':head,'config':expected_config(),
        'input_sha256':inputs,'implementation_sha256':{n:io.sha(ROOT/n) for n in sorted(names)},'validation_sha256':io.sha(VALIDATION/'complete.json'),
        'runtime_lock_sha256':io.sha(VALIDATION/'runtime_lock.json'),'seed_scope_sha256':io.digest(scope),'new_api_calls':0,'novel_algorithm':False}
    value['manifest_id']=io.digest(value);folder=OUTPUT/value['experiment_run_id'];folder.mkdir(parents=True,exist_ok=False)
    io.write(folder/'manifest.json',value);io.write(folder/'seed_scope.json',scope);return folder/'manifest.json'


def load_manifest(path):
    path=Path(path).resolve();io.require(path.name=='manifest.json' and path.parent.parent==OUTPUT.resolve(),'owned manifest path')
    value=io.read(path);body=dict(value);identifier=body.pop('manifest_id');io.require(io.digest(body)==identifier and value['config']==expected_config(),'manifest identity/config drift')
    for n,h in {**value['input_sha256'],**value['implementation_sha256']}.items():io.require(io.sha(ROOT/n)==h,'frozen source changed '+n)
    io.require(io.sha(VALIDATION/'complete.json')==value['validation_sha256'] and io.sha(VALIDATION/'runtime_lock.json')==value['runtime_lock_sha256'],'validation/runtime receipt changed')
    return value


def phase_gate(path,cohort):
    m=load_manifest(path);io.require(cohort in COHORTS,'registered phase');check_storage()
    verify_runtime(io.read(VALIDATION/'runtime_lock.json'))
    if cohort!='SOFTWARE_NATIVE':
        a=io.read(Path(path).parent/'software_native/audit.json')
        io.require(a['integrity']=='PASSED' and a['native_software_contract']=='PASSED','native software gate required')
    if cohort=='QUAL':
        from src.analysis.response_action_statistics_v1 import verify_selection
        verify_selection(path)
    return m

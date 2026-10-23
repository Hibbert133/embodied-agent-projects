"""Frozen independent command-contrast allocation, costs, source and storage gates."""
from datetime import datetime,timezone
from pathlib import Path
import importlib.metadata
import re
import shutil
import sys
import uuid
import numpy as np
from src.analysis import observable_history_io_v1 as io
from src.probe import command_contrast_v1 as core
from src.probe.linear_command_preflight_v1 import LinearCommandModel

ROOT=io.ROOT
OUTPUT=ROOT/'outputs/command_contrast/qualification_v1'
PREPARATION=ROOT/'outputs/command_contrast/preparation_v1'
VALIDATION=ROOT/'outputs/command_contrast/validation_v1'
CONFIG=ROOT/'configs/movement_task/command_contrast_qualification_v1.json'
PROTOCOL=ROOT/'docs/protocols/command_contrast_qualification_v1_zh.md'
SEEDS=ROOT/'docs/protocols/command_contrast_seed_registry_v1.json'
SOURCE=ROOT/'outputs/response_training_controls/development_v1/training_controls_20261021T191002Z_a7a33756b1c7'
INDEX_SHA='b76a5e0260b6f0de174697a99c739501c4baed20255f89c533fdd82f538bcf78'
POLICIES={'push-v3':'SawyerPushV3Policy','reach-v3':'SawyerReachV3Policy','door-open-v3':'SawyerDoorOpenV3Policy'}
CONTEXTS=('NOMINAL','RANDOM')
PROGRAMS=('FEEDBACK8','BALANCED8')
VERSIONS={'numpy':'2.2.6','scipy':'1.15.3','mujoco':'3.3.0','gymnasium':'1.3.0','metaworld':'3.1.1'}
REQUIRED=('src/probe/command_contrast_v1.py','src/analysis/command_contrast_io_v1.py',
    'src/analysis/command_contrast_host_v1.py','src/analysis/command_contrast_collect_v1.py',
    'src/analysis/command_contrast_audit_v1.py','src/analysis/command_contrast_statistics_v1.py',
    'scripts/run_command_contrast_qualification_v1.py','scripts/audit_command_contrast_qualification_v1.py',
    'scripts/report_command_contrast_qualification_v1.py','tests/test_command_contrast_v1.py',
    'tests/test_command_contrast_host_v1.py','tests/test_command_contrast_pipeline_v1.py')


def population():
    cases=[]
    for group in range(9):
        target=core.TARGETS[group//3]; boundary=(16,32,64)[group%3]
        maximum=3 if target=='COLD_STEP2' else boundary+(65 if target=='POST_MOVE_MEAS0' else 73)
        for task_index,task in enumerate(POLICIES):
            for context in CONTEXTS:
                for program in PROGRAMS:
                    unit=f'CC/{group:02d}/{task}/{context}/{program}'
                    for branch in core.BRANCHES:
                        cases.append({'cohort':'QUAL','case_id':unit+'/'+branch,'unit_id':unit,'group':group,'task':task,
                            'seed':61000+3*group+task_index,'context':context,'measurement_program':program,
                            'target':target,'planned_boundary':boundary,'action_id':branch,'maximum_steps':maximum,
                            'noise_namespace':110002,'operator_nonce':110001,'measurement_nonce':110003})
    return cases


def software_population():
    return [{'cohort':'SOFTWARE_NATIVE','case_id':f'CC_NATIVE/{i:02d}/{task}/'+action,'unit_id':f'CC_NATIVE/{i:02d}/{task}',
             'group':i,'task':task,'seed':62050+i,'context':'RANDOM','measurement_program':'FEEDBACK8',
             'target':'COLD_STEP2','planned_boundary':16,'action_id':action,'maximum_steps':3,
             'noise_namespace':110012,'operator_nonce':110011,'measurement_nonce':110013}
            for i,task in enumerate(POLICIES) for action in core.BRANCHES]


def validate_spec(spec):
    io.require(type(spec) is dict and spec in population()+software_population(),'only registered complete case specifications')


def expected_config():
    return {'protocol':'command_contrast_qualification_v1','scope':'INDEPENDENT_FIXED_MODEL_ACTION_CONTRAST_DEVELOPMENT',
        'source_result_commit':'721d20e18391642b8283ec7cc82593a51bb916ec','models_index_sha256':INDEX_SHA,
        'population':population(),'native_software_population':software_population(),'per_execution_hard_control_cap':500,'planned_per_execution_cap':137,
        'limits':{'groups':9,'units':108,'executions':540,'control_steps':38820,'controlled_resets':540,
            'factory_resets':27000,'all_resets':27540,'physical_frames':13964100,
            'online_c4_c8_fit_attempts':720,'independent_audit_c4_c8_refits':720,'predictor_training_fits':0},
        'native_software_limits':{'executions':15,'control_steps':45,'controlled_resets':15,'factory_resets':750,
            'all_resets':765,'physical_frames':382725,'c4_c8_fit_attempts':0},
        'noise_sigma':.05,'new_api_calls':0,'policy_training':0,'new_response_predictor_training':0,
        'target_stages':list(core.TARGETS),'branches':list(core.BRANCHES),'xy_offset_before_float32':.25,
        'send_precision':'IEEE float32 rounded BEFORE prediction and saved selection',
        'source_programs':list(PROGRAMS),'predictors':['H10','F20','F43'],'source_banks':list(PROGRAMS),
        'first_branch':'BASELINE; save all five commands/six predictions before its query result',
        'subsequent_branches':'Actual controlled initial replay; validate same real prefix; consume prior saved plan only',
        'initial_faults':'NOMINAL identity; RANDOM fixed affine from new group nonce. No within-execution change.',
        'primary':'MATCHED_F20_MINUS_ZERO_PAIRED_UNIT_MEAN_XY_CONTRAST_MSE',
        'secondary':['MATCHED_F20_MINUS_H10','MATCHED_F20_MINUS_F43'],
        'weighting':'Four nonbaseline direction labels/XY within unit; paired units within whole group; nine groups equally',
        'bootstrap':{'replicates':10000,'seed':202610380,'unit':'NINE_WHOLE_GROUPS_STRATIFIED_BY_TARGET_STAGE'},
        'eligibility':'All five real branches reach saved point with identical prefixes; early success/invalid/absent points remain registered missing',
        'empirical_gate':'All cases/record audits complete; nine groups and three tasks have paired units; primary upper95<0; F20 mean below ZERO,H10,F43',
        'gate_scope':'Only realized eligible command contrasts in this static family, not confidence/safety/inverse/task/deployment qualification',
        'retry':False,'append_samples':False,'candidate_selection':'NONE; fixed F20 candidate/all references retained',
        'disk_free_floor_bytes':2*1024**3,'runtime_emergency_free_floor_bytes':512*1024**2,
        'expected_runtime_versions':VERSIONS,'source_nominal_c8_sha256':io.C8_SHA}


def noise(seed,namespace=110002):
    io.require(namespace in (110002,110012),'registered initial immutable noise stream')
    key=int(np.random.SeedSequence([seed,namespace]).generate_state(1)[0])
    tape=np.random.default_rng(key).normal(0,.05,(500,3)).astype('<f4'); tape.flags.writeable=False
    return tape


def fault(spec):
    validate_spec(spec)
    if spec['context']=='NOMINAL': return {'matrix_xy':[[1.,0.],[0.,1.]],'bias_xy':[0.,0.],'deadzone_xy':[0.,0.]}
    rng=np.random.default_rng(np.random.SeedSequence([spec['operator_nonce'],spec['group']]))
    return {'matrix_xy':[[float(rng.uniform(.75,1.25)),float(rng.uniform(-.2,.2))],
                         [float(rng.uniform(-.2,.2)),float(rng.uniform(.75,1.25))]],
            'bias_xy':rng.uniform(-.2,.2,2).tolist(),'deadzone_xy':[0.,0.]}


def measurement(spec):
    rng=np.random.default_rng(np.random.SeedSequence([spec['measurement_nonce'],spec['group']]))
    commands=np.asarray([[.4,0,0,-1],[0,.4,0,-1],[-.4,0,0,-1],[0,-.4,0,-1]]*2,np.float32)
    return commands[rng.permutation(8)].tolist()


def source_models():
    io.require(io.sha(SOURCE/'training/models.json')==INDEX_SHA and io.sha(ROOT/io.C8)==io.C8_SHA,'fixed predictors/nominal source changed')
    index=io.read(SOURCE/'training/models.json')['models']; banks={task:{} for task in POLICIES}
    inputs={SOURCE/'training/models.json',ROOT/io.C8,SOURCE/'delivery_v1/costs_and_provenance.json'}
    for key,entry in index.items():
        if entry['kind']!='LINEAR': continue
        p=SOURCE/'training'/entry['file']; io.require(io.sha(p)==entry['sha256'],'saved linear source changed')
        model=LinearCommandModel.from_saved(io.read(p)); io.require(key==f"{entry['source']}/{model.task}/LINEAR_{model.feature}",'model mapping')
        banks[model.task][key]=(model,entry['sha256']); inputs.add(p)
    io.require(sum(map(len,banks.values()))==18 and all(len(v)==6 for v in banks.values()),'all frozen linear references')
    return banks,io.read(ROOT/io.C8)['joint'],{p.relative_to(ROOT).as_posix():io.sha(p) for p in sorted(inputs)}


def registry():
    return {'protocol':'command_contrast_qualification_v1','episode_seed_range':[61000,61026],
            'reserved_episode_seed_range':[61027,61999],'groups':9,'unique_task_seeds':27,
            'native_software_episode_seed_range':[62050,62052],'native_software_reserved_episode_seed_range':[62053,62099],
            'noise_namespace':110002,'operator_generator_nonce':110001,'measurement_generator_nonce':110003,
            'bootstrap_seed':202610380,'reuse':'Only registered same-unit branches and explicitly correlated program/context pairings'}


def seed_scope():
    own={p.relative_to(ROOT).as_posix() for p in (CONFIG,PROTOCOL,SEEDS)}; inputs={}; collisions=[]
    overlap=lambda lo,hi:any(lo<=b and a<=hi for a,b in ((61000,61999),(62050,62099)))
    def visit(value,name,key=''):
        if isinstance(value,dict):
            for field,v in value.items():
                if 'seed' in field.lower() and not any(s in field.lower() for s in ('noise','namespace','bootstrap','generator','generation','nonce','initialization','sampling')):
                    if type(v) is int and overlap(v,v): collisions.append([name,key+field,v])
                    if isinstance(v,list) and all(type(x) is int for x in v):
                        if len(v)==2 and v[0]<=v[1] and overlap(*v): collisions.append([name,key+field,v])
                        elif len(v)!=2 and any(overlap(x,x) for x in v): collisions.append([name,key+field,'LIST_OVERLAP'])
                visit(v,name,key+field+'.')
            if type(value.get('seed_start')) is int:
                lo=value['seed_start']; hi=value.get('seed_end',lo+value.get('num_seeds',1)-1)
                if type(hi) is int and overlap(lo,hi): collisions.append([name,key,[lo,hi]])
        elif isinstance(value,list):
            for item in value: visit(item,name,key)
    files=set((ROOT/'configs').rglob('*.json'))|set((ROOT/'outputs').rglob('manifest.json'))|set((ROOT/'docs/protocols').glob('*seed*.json'))
    for path in sorted(files):
        name=path.relative_to(ROOT).as_posix()
        if name not in own: inputs[name]=io.sha(path); visit(io.read(path),name)
    for path in sorted((ROOT/'docs/protocols').glob('*.md')):
        name=path.relative_to(ROOT).as_posix()
        if name in own: continue
        inputs[name]=io.sha(path)
        for line in path.read_text(encoding='utf-8').splitlines():
            if re.search('seed|种子|预留|保留',line,re.I):
                for lo,hi in re.findall(r'\b(\d{4,6})\s*(?:--|–|\.\.|-)\s*(\d{4,6})\b',line):
                    if overlap(int(lo),int(hi)): collisions.append([name,lo,hi])
    io.require(not collisions,'used/reserved range overlap: '+str(collisions[:3]))
    return {'integrity':'PASSED_NO_REGISTERED_COLLISION','proposed_episode_range':[61000,61026],
            'proposed_reservation':[61027,61999],'native_software_episode_range':[62050,62052],
            'native_software_reservation':[62053,62099],'inputs_sha256':inputs,'own_registry_files':sorted(own),'collisions':collisions}


def check_storage():
    io.require(shutil.disk_usage(ROOT).free>=2*1024**3,'NEEDS_STORAGE: 2 GiB working/retention/Git reserve required before any environment construction')


def runtime_fingerprints():
    versions={name:importlib.metadata.version(name) for name in VERSIONS}
    io.require(versions==VERSIONS,'native dependency versions differ from reviewed source')
    files={Path(sys.executable).resolve()}
    for name in VERSIONS:
        distribution=importlib.metadata.distribution(name)
        for item in distribution.files or ():
            p=Path(distribution.locate_file(item)).resolve()
            if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo'): files.add(p)
    return {'versions':versions,'python_version':sys.version,'file_sha256':{str(p):io.sha(p) for p in sorted(files)}}


def verify_runtime(lock):
    io.require({n:importlib.metadata.version(n) for n in VERSIONS}==lock['versions']==VERSIONS,'dependency version drift')
    io.require(lock['python_version']==sys.version,'Python runtime changed')
    for name,digest in lock['file_sha256'].items(): io.require(io.sha(Path(name))==digest,'runtime file changed: '+name)


def verify_checks():
    checked=io.read(VALIDATION/'complete.json'); io.require(checked['integrity']=='PASSED','source-bound checks required')
    for name,digest in checked['python_source_sha256'].items(): io.require(io.sha(ROOT/name)==digest,'tested source changed: '+name)
    for name,digest in checked['receipt_sha256'].items(): io.require(io.sha(VALIDATION/name)==digest,'check receipt changed')
    io.require(not io.git('status','--porcelain','--untracked-files=no'),'clean committed tracked freeze required')
    for name in (*REQUIRED,CONFIG.relative_to(ROOT).as_posix(),PROTOCOL.relative_to(ROOT).as_posix(),SEEDS.relative_to(ROOT).as_posix()):
        io.require(io.git('ls-files','--error-unmatch',name)==name,'uncommitted required scientific implementation')
    return checked


def prepare():
    """Read-only preparation can fail for storage; it creates no environment."""
    io.require(not list(OUTPUT.glob('*/manifest.json')),'one scientific allocation only; do not replace a failed/complete run')
    checked=verify_checks(); io.require(io.read(CONFIG)==expected_config() and io.read(SEEDS)==registry(),'frozen config/registry changed')
    scope=seed_scope(); _,_,inputs=source_models()
    now=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'); commit=io.git('rev-parse','HEAD')
    PREPARATION.mkdir(parents=True,exist_ok=True)
    receipt={'source_git_commit':commit,'configuration_sha256':io.sha(CONFIG),'seed_scope':scope,
        'source_input_sha256':inputs,'free_bytes':shutil.disk_usage(ROOT).free,'required_free_bytes':2*1024**3,
        'new_environment_creations':0,'new_environment_steps':0,'new_api_calls':0,'new_predictor_fits':0,
        'native_software_executed':False,'scientific_executions':0}
    if receipt['free_bytes']<receipt['required_free_bytes']:
        receipt['status']='NEEDS_STORAGE_NO_SIMULATION_STARTED'
        target=PREPARATION/(now+'_'+uuid.uuid4().hex[:8]+'.json'); io.write(target,receipt)
        return None,target
    lock=io.read(VALIDATION/'runtime_lock.json'); verify_runtime(lock)
    names=set(io.git('ls-files','src','scripts','tests').splitlines())|set(REQUIRED)|{CONFIG.relative_to(ROOT).as_posix(),PROTOCOL.relative_to(ROOT).as_posix(),SEEDS.relative_to(ROOT).as_posix()}
    value={'experiment_run_id':'command_contrast_'+now+'_'+commit[:12],'source_git_commit':commit,
        'config':expected_config(),'input_sha256':inputs,'implementation_sha256':{n:io.sha(ROOT/n) for n in sorted(names)},
        'runtime_lock_sha256':io.sha(VALIDATION/'runtime_lock.json'),'validation_sha256':io.sha(VALIDATION/'complete.json'),
        'seed_scope_sha256':io.digest(scope),'new_api_calls':0,'physical_qualification':False,'task_benefit':False}
    value['manifest_id']=io.digest(value); folder=OUTPUT/value['experiment_run_id']; folder.mkdir(parents=True,exist_ok=False)
    io.write(folder/'manifest.json',value)
    io.write(folder/'model_lock.json',{'manifest_id':value['manifest_id'],'locked_source_input_sha256':inputs,
        'locked_before_any_native_execution':True,'linear_predictors':18,'new_predictor_fits':0})
    receipt['status']='PREPARED_FOR_NATIVE_SOFTWARE_ONLY'; receipt['manifest']=str(folder/'manifest.json')
    target=PREPARATION/(now+'_'+uuid.uuid4().hex[:8]+'.json'); io.write(target,receipt)
    return folder/'manifest.json',target


def load_manifest(path):
    path=Path(path).resolve(); io.require(path.name=='manifest.json' and path.parent.parent==OUTPUT.resolve(),'owned manifest path required')
    value=io.read(path); body=dict(value); identifier=body.pop('manifest_id')
    io.require(io.digest(body)==identifier and value['config']==expected_config(),'manifest/configuration drift')
    for name,digest in {**value['input_sha256'],**value['implementation_sha256']}.items(): io.require(io.sha(ROOT/name)==digest,'frozen source changed: '+name)
    io.require(io.sha(VALIDATION/'runtime_lock.json')==value['runtime_lock_sha256'],'runtime lock changed')
    io.require(io.read(path.parent/'model_lock.json')['locked_source_input_sha256']==value['input_sha256'],'model lock changed')
    return value


def phase_gate(path,cohort):
    io.require(cohort in ('SOFTWARE_NATIVE','QUAL'),'registered collection phase')
    manifest=load_manifest(path); check_storage()
    io.require(not io.git('status','--porcelain','--untracked-files=no'),'clean frozen scientific checkout before physical work')
    io.git('merge-base','--is-ancestor',manifest['source_git_commit'],'HEAD')
    io.require(not io.git('ls-files','--others','--exclude-standard','src','scripts','tests','configs/movement_task'),
               'uncommitted scientific implementation is not allowed')
    if cohort=='QUAL':
        native=Path(path).parent/'software_native'; receipt=io.read(native/'audit.json')
        io.require(receipt['integrity']=='PASSED' and receipt['native_software_contract']=='PASSED' and receipt['executions']==15,'complete native software contract before scientific cohort')
        io.require(receipt['manifest_id']==manifest['manifest_id'] and receipt['source_git_commit']==manifest['source_git_commit']
                   and receipt['auditor_sha256']==io.sha(ROOT/'src/analysis/command_contrast_audit_v1.py')
                   and receipt['completion_sha256']==io.sha(native/'completion.json'),'native audit provenance drift')
        for name,digest in io.read(native/'completion.json')['artifact_sha256'].items(): io.require(io.sha(native/name)==digest,'native contract records changed')
    verify_runtime(io.read(VALIDATION/'runtime_lock.json'))
    return manifest

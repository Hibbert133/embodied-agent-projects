"""Independent allocation and freeze gates for task-time passive references.

No environment is constructed by preparation, selection, or this module.
"""
from datetime import datetime,timezone
from pathlib import Path
import re
import shutil
import uuid
import numpy as np
from src.analysis import observable_history_io_v1 as io
from src.analysis.command_contrast_io_v1 import runtime_fingerprints,verify_runtime,VERSIONS
from src.probe.task_passive_program_v1 import Program,CONTROLS,PI_STYLES
from src.probe.task_passive_pi_v1 import TIME_CONSTANTS,GAINS

ROOT=io.ROOT
OUTPUT=ROOT/'outputs/task_passive/development_v1'
VALIDATION=ROOT/'outputs/task_passive/validation_v1'
CONFIG=ROOT/'configs/movement_task/task_passive_execution_v1.json'
PROTOCOL=ROOT/'docs/protocols/task_passive_execution_v1_zh.md'
SEEDS=ROOT/'docs/protocols/task_passive_seed_registry_v1.json'
COHORTS=('SOFTWARE_NATIVE','DEV','QUAL')
KEYS=('cohort','case_id','unit_id','group','task','seed','context','style','time_constant_s')
REQUIRED=('src/probe/task_passive_pi_v1.py','src/probe/task_passive_program_v1.py',
    'src/analysis/task_passive_io_v1.py','src/analysis/task_passive_host_v1.py',
    'src/analysis/task_passive_collect_v1.py','src/analysis/task_passive_audit_v1.py',
    'src/analysis/task_passive_statistics_v1.py','scripts/run_task_passive_v1.py',
    'scripts/audit_task_passive_v1.py','scripts/report_task_passive_v1.py',
    'tests/test_task_passive_pi_v1.py','tests/test_task_passive_program_v1.py',
    'tests/test_task_passive_host_v1.py','tests/test_task_passive_pipeline_v1.py')


def program_id(style,ti): return style if ti is None else style+'_T'+str(float(ti))


def programs(cohort,selection=None):
    io.require(cohort in COHORTS,'registered cohort')
    values=[Program(s) for s in CONTROLS]
    if cohort=='QUAL':
        io.require(type(selection) is dict and set(selection)==set(PI_STYLES),'four locked passive references')
        values += [Program(s,selection[s]) for s in PI_STYLES]
    else:
        constants=TIME_CONSTANTS if cohort=='DEV' else (TIME_CONSTANTS[0],TIME_CONSTANTS[-1])
        values += [Program(s,ti) for s in PI_STYLES for ti in constants]
    return values


def population(cohort,selection=None):
    io.require(cohort in COHORTS,'registered cohort')
    groups,start,noise,operator={'SOFTWARE_NATIVE':(1,63200,120012,120011),
        'DEV':(6,63000,120002,120001),'QUAL':(9,63100,120004,120003)}[cohort]
    result=[]
    for g in range(groups):
        for i,task in enumerate(GAINS):
            for context in (('CHANGED',) if cohort=='SOFTWARE_NATIVE' else ('UNCHANGED','CHANGED')):
                unit=f'{cohort}/{g:02d}/{task}/{context}'
                for p in programs(cohort,selection):
                    result.append({'cohort':cohort,'case_id':unit+'/'+program_id(p.style,p.time_constant_s),
                        'unit_id':unit,'group':g,'task':task,'seed':start+3*g+i,'context':context,
                        'style':p.style,'time_constant_s':p.time_constant_s,'planned_boundary':(16,32,64)[g%3],
                        'noise_namespace':noise,'operator_nonce':operator,'maximum_steps':500})
    return result


def validate_spec(spec):
    io.require(type(spec) is dict and spec.get('cohort') in COHORTS,'strict registered case')
    selected={s:TIME_CONSTANTS[0] for s in PI_STYLES}
    if spec.get('style') in PI_STYLES: selected[spec['style']]=spec.get('time_constant_s')
    io.require(spec in population(spec['cohort'],selected if spec['cohort']=='QUAL' else None),'unallocated case')


def limits(cohort):
    n={'SOFTWARE_NATIVE':36,'DEV':720,'QUAL':432}[cohort]
    fits={'SOFTWARE_NATIVE':54,'DEV':1080,'QUAL':648}[cohort]
    return {'executions':n,'control_steps':n*500,'controlled_resets':n,'factory_resets':n*50,
        'all_resets':n*51,'physical_frames':n*(51*500+500*5),
        'online_c4_c8_fit_attempts':fits,'independent_audit_c4_c8_refits':fits,
        'response_predictor_training':0,'policy_training':0,'new_api_calls':0}


def expected_config():
    return {'protocol':'task_passive_execution_v1','scope':'STRONG_ENGINEERING_REFERENCE_DEVELOPMENT_AND_INDEPENDENT_TASK_QUALIFICATION',
        'source_result_commit':'4a6faadfafd218cb6ee9697650c6d59948088930',
        'population':{c:population(c) for c in ('SOFTWARE_NATIVE','DEV')},
        'qualification':{'groups':9,'contexts':['UNCHANGED','CHANGED'],'program_styles':list(CONTROLS+PI_STYLES),
            'parameters':'Four time constants locked from complete DEV before QUAL; every style retained'},
        'limits':{c:limits(c) for c in COHORTS},
        'combined_limits':{k:sum(limits(c)[k] for c in COHORTS) for k in limits('DEV')},
        'per_execution_steps':500,'movement_steps':64,'noise_sigma':.05,'control_period_s':.0125,
        'fixed_policy_gains_per_m':GAINS,'task_pi_time_constants_s':list(TIME_CONSTANTS),
        'integral_limit_command':2.,'raw_error':'Unbounded original float32 policy XY divided by fixed P; instantaneous policy target only',
        'pi_order':'Bounded saved base + clip(I + dt B P e / Ti, -2,2); final clip and float32; I=actual sendXY-baseXY only after receipt',
        'movement':'All MOVE variants retain C8 through boundary and execute identical old LOCAL_PID; task PI begins afterwards',
        'direct_pi':'Starts after C8 at step8; no reset at hidden change; raw PI starts at step0',
        'initial_fault':{'matrix_xy':[[1.,0.],[0.,1.]],'bias_xy':[.12,-.08],'deadzone_xy':[0.,0.]},
        'change':'Private host updates only affine coefficients before command at planned boundary if still alive; unchanged world/tape/clock',
        'selection':'Per style minimum complete DEV sum deadline_loss; ties largest Ti. Global primary minimum sum; ties PI_STYLES order',
        'development_entry_gate':'Complete audited DEV; selected primary mean loss strictly below DIRECT_C8 and MOVE_INTEGRAL',
        'qualification_gate':'Complete audited nine groups; both primary loss differences have upper paired whole-group bootstrap95 <0',
        'primary_comparisons':['LOCKED_PRIMARY_MINUS_DIRECT_C8','LOCKED_PRIMARY_MINUS_MOVE_INTEGRAL'],
        'secondary':'All 28 paired program differences and all 3-task x 2-context cells; no task-wise selection',
        'bootstrap':{'replicates':10000,'DEV_seed':202610390,'QUAL_seed':202610391,'unit':'WHOLE_GROUP_STRATIFIED_BY_BOUNDARY'},
        'loss':'Actual control steps on success; 500 on failure/invalid fit; includes C8 and actual movement once',
        'source_costs':'All C8 users pay complete 480-source-step bank; all selected PI styles additionally disclose complete DEV tuning population, full and amortized; no duplicate FIT subset fee',
        'native_contract':'All cases audited; each of four PI styles at both endpoint Ti has at least one actual PI step; all three tasks retained; common C8/MOVE prefixes verified',
        'early_end':'Do not force boundary/change or movement after success. Retain all initial units; absent phases recorded, never zero-filled as observations',
        'retry':False,'append_samples':False,'new_api_calls':0,'new_response_predictor_training':0,'new_policy_training':0,
        'disk_free_floor_bytes':4*1024**3,'runtime_emergency_free_floor_bytes':512*1024**2,
        'source_nominal_c8_sha256':io.C8_SHA,'expected_runtime_versions':VERSIONS,
        'no_safety_guarantee':True,'no_algorithmic_novelty_claim':True}


def registry():
    return {'protocol':'task_passive_execution_v1','DEV_episode_seed_range':[63000,63017],
        'DEV_reserved_episode_seed_range':[63018,63099],'QUAL_episode_seed_range':[63100,63126],
        'QUAL_reserved_episode_seed_range':[63127,63199],'native_episode_seed_range':[63200,63202],
        'native_reserved_episode_seed_range':[63203,63299],
        'noise_namespaces':[120002,120004,120012],'operator_nonces':[120001,120003,120011],
        'bootstrap_seeds':[202610390,202610391],'reuse':'Only explicit within-cohort task/context/program pairings; no DEV/QUAL reuse'}


def noise(seed,namespace):
    io.require(namespace in (120002,120004,120012),'immutable registered initial noise domain')
    key=int(np.random.SeedSequence([seed,namespace]).generate_state(1)[0])
    a=np.random.default_rng(key).normal(0,.05,(500,3)).astype('<f4'); a.flags.writeable=False; return a


def initial_fault(): return expected_config()['initial_fault']


def destination(spec):
    validate_spec(spec)
    if spec['context']=='UNCHANGED': return initial_fault()
    r=np.random.default_rng(np.random.SeedSequence([spec['operator_nonce'],spec['group']]))
    return {'matrix_xy':[[float(r.uniform(.75,1.25)),float(r.uniform(-.2,.2))],
        [float(r.uniform(-.2,.2)),float(r.uniform(.75,1.25))]],'bias_xy':r.uniform(-.2,.2,2).tolist(),'deadzone_xy':[0.,0.]}


def seed_scope():
    own={p.relative_to(ROOT).as_posix() for p in (CONFIG,PROTOCOL,SEEDS)}; inputs={}; collisions=[]
    overlap=lambda lo,hi:lo<=63299 and 63000<=hi
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
    for p in sorted(files):
        name=p.relative_to(ROOT).as_posix()
        if name not in own: inputs[name]=io.sha(p); visit(io.read(p),name)
    for p in sorted((ROOT/'docs/protocols').glob('*.md')):
        name=p.relative_to(ROOT).as_posix()
        if name in own: continue
        inputs[name]=io.sha(p)
        for line in p.read_text(encoding='utf-8').splitlines():
            if re.search('seed|种子|预留|保留',line,re.I):
                for lo,hi in re.findall(r'\b(\d{4,6})\s*(?:--|–|\.\.|-)\s*(\d{4,6})\b',line):
                    if overlap(int(lo),int(hi)): collisions.append([name,lo,hi])
    io.require(not collisions,'used/reserved seed overlap: '+str(collisions[:3]))
    return {'integrity':'PASSED_NO_REGISTERED_COLLISION','proposed_ranges':[[63000,63099],[63100,63199],[63200,63299]],
        'inputs_sha256':inputs,'own_registry_files':sorted(own),'collisions':collisions}


def source_models():
    io.require(io.sha(ROOT/io.C8)==io.C8_SHA,'frozen nominal C8 source changed')
    return io.read(ROOT/io.C8)['joint'],{io.C8:io.C8_SHA}


def check_storage():
    io.require(shutil.disk_usage(ROOT).free>=4*1024**3,'NEEDS_STORAGE: four GiB reserve before environment construction')


def verify_checks():
    checked=io.read(VALIDATION/'complete.json'); io.require(checked['integrity']=='PASSED','source-bound validation required')
    for n,h in checked['python_source_sha256'].items(): io.require(io.sha(ROOT/n)==h,'tested source changed: '+n)
    for n,h in checked['receipt_sha256'].items(): io.require(io.sha(VALIDATION/n)==h,'check receipt changed')
    io.require(not io.git('status','--porcelain','--untracked-files=no'),'clean committed tracked freeze required')
    for n in (*REQUIRED,*(p.relative_to(ROOT).as_posix() for p in (CONFIG,PROTOCOL,SEEDS))):
        io.require(io.git('ls-files','--error-unmatch',n)==n,'uncommitted required implementation')
    return checked


def prepare():
    io.require(not list(OUTPUT.glob('*/manifest.json')),'one allocation only; preserve previous attempts')
    verify_checks(); io.require(io.read(CONFIG)==expected_config() and io.read(SEEDS)==registry(),'configuration drift')
    check_storage(); scope=seed_scope(); _,inputs=source_models(); verify_runtime(io.read(VALIDATION/'runtime_lock.json'))
    commit=io.git('rev-parse','HEAD'); now=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    names=set(io.git('ls-files','src','scripts','tests').splitlines())|set(REQUIRED)|{p.relative_to(ROOT).as_posix() for p in (CONFIG,PROTOCOL,SEEDS)}
    value={'experiment_run_id':'task_passive_'+now+'_'+commit[:12],'source_git_commit':commit,
        'config':expected_config(),'input_sha256':inputs,'implementation_sha256':{n:io.sha(ROOT/n) for n in sorted(names)},
        'runtime_lock_sha256':io.sha(VALIDATION/'runtime_lock.json'),'validation_sha256':io.sha(VALIDATION/'complete.json'),
        'seed_scope_sha256':io.digest(scope),'new_api_calls':0,'novel_algorithm':False,'task_benefit_established':False}
    value['manifest_id']=io.digest(value); folder=OUTPUT/value['experiment_run_id']; folder.mkdir(parents=True,exist_ok=False)
    io.write(folder/'manifest.json',value); io.write(folder/'seed_scope.json',scope)
    return folder/'manifest.json'


def load_manifest(path):
    path=Path(path).resolve(); io.require(path.name=='manifest.json' and path.parent.parent==OUTPUT.resolve(),'owned manifest required')
    v=io.read(path); body=dict(v); identifier=body.pop('manifest_id')
    io.require(io.digest(body)==identifier and v['config']==expected_config(),'manifest/config drift')
    for n,h in {**v['input_sha256'],**v['implementation_sha256']}.items(): io.require(io.sha(ROOT/n)==h,'frozen source changed: '+n)
    for filename,k in (('runtime_lock.json','runtime_lock_sha256'),('complete.json','validation_sha256')):
        io.require(io.sha(VALIDATION/filename)==v[k],'validation/runtime changed')
    return v


def phase_gate(path,cohort):
    io.require(cohort in COHORTS,'registered cohort'); v=load_manifest(path); check_storage()
    io.require(not io.git('status','--porcelain','--untracked-files=no'),'clean tracked checkout before physical execution')
    io.git('merge-base','--is-ancestor',v['source_git_commit'],'HEAD')
    io.require(not io.git('ls-files','--others','--exclude-standard','src','scripts','tests','configs/movement_task'),'uncommitted scientific code')
    if cohort!='SOFTWARE_NATIVE':
        p=Path(path).parent/'software_native'; a=io.read(p/'audit.json')
        io.require(a['integrity']=='PASSED' and a['native_software_contract']=='PASSED' and a['executions']==36,'native contract required')
        io.require(a['completion_sha256']==io.sha(p/'completion.json') and a['auditor_sha256']==io.sha(ROOT/'src/analysis/task_passive_audit_v1.py'),'native audit binding')
        for n,h in io.read(p/'completion.json')['artifact_sha256'].items(): io.require(io.sha(p/n)==h,'native bytes changed')
    if cohort=='QUAL':
        from src.analysis.task_passive_statistics_v1 import verify_selection
        verify_selection(path)
    verify_runtime(io.read(VALIDATION/'runtime_lock.json')); return v

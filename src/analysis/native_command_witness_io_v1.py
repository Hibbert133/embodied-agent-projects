"""Small native collector qualification; no response training or new controller."""
from datetime import datetime,timezone
from pathlib import Path
import re,shutil
from contextlib import contextmanager,ExitStack
from unittest.mock import patch
import numpy as np
from src.analysis import response_qualification_io_v1 as io
ROOT=io.ROOT;BASE=ROOT/'outputs/native_command_witness';OUTPUT=BASE/'qualification_v1';VALIDATION=BASE/'validation_v1'
CONFIG=ROOT/'configs/movement_task/native_command_witness_v1.json';PROTOCOL=ROOT/'docs/protocols/native_command_witness_v1_zh.md'
SEEDS=ROOT/'docs/protocols/native_command_witness_seeds_v1.json'
KEYS=('group','task','seed','context','planned_boundary','program')
IDENTITY=('experiment_run_id','manifest_id','source_git_commit')
OWN=('src/analysis/native_command_witness_io_v1.py','src/analysis/native_command_witness_host_v1.py',
    'src/analysis/native_command_witness_collect_v1.py','src/analysis/native_command_witness_audit_v1.py',
    'scripts/run_native_command_witness_v1.py','scripts/report_native_command_witness_v1.py','tests/test_native_command_witness_v1.py')
DEPENDENCIES=('src/probe/nominal_command_target_v1.py','src/probe/acquisition_reference_program_v1.py',
    'src/probe/acquisition_reference_operation_v1.py','src/probe/local_reprobe_v1.py','src/probe/task_memory_option_v1.py',
    'src/probe/task_passive_pi_v1.py','src/analysis/paired_probe_host_v1.py','src/probe/lifecycle_ledger.py',
    'src/analysis/acquisition_reference_audit_v1.py','src/analysis/short_probe_journal_audit_v1.py',
    'src/analysis/command_target_sources_v1.py','scripts/analyze_acquisition_support_v1.py')


def population():
    return [{'group':g,'task':task,'seed':70000+3*g+i,'context':c,'planned_boundary':(16,32,64)[g],
        'program':'LOCAL_PID_KEEP'} for g in range(3) for i,task in enumerate(io.TASKS) for c in ('UNCHANGED','CHANGED')]


def validate_spec(v):io.require(v in population(),'frozen native assignment required')


@contextmanager
def forbid_fitting(receipt):
    import scipy.optimize
    from src.probe import cold_start_response,short_joint_reference_v1,operator_identification
    receipt['attempted_fits']=0
    def denied(*args,**kwargs):receipt['attempted_fits']+=1;raise RuntimeError('Fitting forbidden in native collector qualification')
    with ExitStack() as stack:
        for obj,name in ((np.linalg,'lstsq'),(scipy.optimize,'least_squares'),(cold_start_response,'least_squares'),
            (short_joint_reference_v1,'least_squares'),(operator_identification,'least_squares')):stack.enter_context(patch.object(obj,name,denied))
        yield


def initial_fault():return {'matrix_xy':[[1.,0.],[0.,1.]],'bias_xy':[.12,-.08],'deadzone_xy':[0.,0.]}


def destination(v):
    validate_spec(v)
    if v['context']=='UNCHANGED':return initial_fault()
    r=np.random.default_rng(np.random.SeedSequence([2026102302,v['group']]))
    return {'matrix_xy':[[float(r.uniform(.75,1.25)),float(r.uniform(-.2,.2))],[float(r.uniform(-.2,.2)),float(r.uniform(.75,1.25))]],
        'bias_xy':r.uniform(-.2,.2,2).tolist(),'deadzone_xy':[0.,0.]}


def noise(v):
    validate_spec(v);key=int(np.random.SeedSequence([v['seed'],2026102301]).generate_state(1)[0])
    result=np.random.default_rng(key).normal(0,.05,(500,3)).astype('<f4');result.flags.writeable=False;return result


def registry():return {'protocol':'NATIVE_COMMAND_WITNESS_V1','episode_seed_range':[70000,70008],
    'reserved_episode_seed_range':[70009,70099],'noise_namespace':2026102301,'operator_nonce':2026102302,
    'not_response_TRAIN_CAL_or_QUAL':True}


def config():return {'protocol':'NATIVE_COMMAND_WITNESS_V1','classification':'NATIVE_MEASUREMENT_AND_EXECUTION_CONFORMANCE_ONLY',
    'population':population(),'limits':{'executions':18,'control_steps':9000,'controlled_resets':18,'factory_resets':900,
        'all_resets':918,'physical_frames':504000,'new_model_fits':0,'audit_refits':0,'online_LLM_API_calls':0},
    'per_case_step_cap':500,'noise_sigma':.05,'control_period_s':.0125,'fixed_program':'LOCAL_PID_KEEP',
    'initial_target':[0.,.6,.2],'workspace_low':[-.5,.4,.05],'workspace_high':[.5,1.,.5],'action_scale':.01,
    'private_values':'Mocap position/quaternion, applied action, native signature; evaluation-only, not training or policy input',
    'public_export':'Task, initial observation, executed sent-command history, observed responses, public nominal summary only',
    'native_gate':{'all_18_completed_records':True,'exact_applied_action_and_target_recurrence':True,
        'one_actual_complete_measurement_per_task_context':True,'no_new_fit_or_API_or_restore':True},
    'no_power_task_gain_prediction_safety_or_novelty_claim':True,'publication_goal_complete':False}


def seed_scope():
    own={p.relative_to(ROOT).as_posix() for p in (CONFIG,PROTOCOL,SEEDS)};inputs={};collisions=[]
    overlap=lambda lo,hi:lo<=70099 and 70000<=hi
    def visit(v,name,path=''):
        if type(v) is dict:
            for k,w in v.items():
                if 'seed' in k.lower() and not any(t in k.lower() for t in ('noise','namespace','bootstrap','generator','generation','nonce','initialization','sampling')):
                    if type(w) is int and overlap(w,w):collisions.append([name,path+k,w])
                    if type(w) is list and all(type(n) is int for n in w):
                        if len(w)==2 and w[0]<=w[1] and overlap(*w):collisions.append([name,path+k,w])
                        elif len(w)!=2 and any(overlap(n,n) for n in w):collisions.append([name,path+k,'LIST'])
                visit(w,name,path+k+'.')
            if type(v.get('seed_start')) is int:
                lo=v['seed_start'];hi=v.get('seed_end',lo+v.get('num_seeds',1)-1)
                if type(hi) is int and overlap(lo,hi):collisions.append([name,path,[lo,hi]])
        elif type(v) is list:
            for w in v:visit(w,name,path)
    files=set((ROOT/'configs').rglob('*.json'))|set((ROOT/'outputs').rglob('manifest.json'))|set((ROOT/'docs/protocols').glob('*seed*.json'))
    for p in sorted(files):
        n=p.relative_to(ROOT).as_posix()
        if n not in own and BASE not in p.parents:inputs[n]=io.sha(p);visit(io.read(p),n)
    for p in sorted((ROOT/'docs/protocols').glob('*.md')):
        n=p.relative_to(ROOT).as_posix()
        if n in own:continue
        inputs[n]=io.sha(p)
        for line in p.read_text(encoding='utf-8').splitlines():
            if re.search('seed|种子|预留|保留',line,re.I):
                for lo,hi in re.findall(r'\b(\d{4,6})\s*(?:--|–|\.\.|-)\s*(\d{4,6})\b',line):
                    if overlap(int(lo),int(hi)):collisions.append([n,lo,hi])
    io.require(not collisions,'registered seed overlap '+str(collisions[:3]))
    return {'integrity':'PASSED_NO_REGISTERED_COLLISION','range':[70000,70099],'inputs_sha256':inputs,'collisions':collisions}


def checked(path):
    path=Path(path).resolve();m=io.read(path);body=dict(m);mid=body.pop('manifest_id')
    io.require(path.parent.parent==OUTPUT.resolve() and path.name=='manifest.json' and io.digest(body)==mid and m['config']==config(),'native witness manifest')
    for n,h in m['source_sha256'].items():io.require(io.sha(ROOT/n)==h,'frozen source changed '+n)
    for n,h in m['installed_source_sha256'].items():io.require(io.sha(Path(n))==h,'installed native source changed '+n)
    return m


def prepare():
    qa=io.read(VALIDATION/'complete.json');io.require(qa['integrity']=='PASSED' and not io.git('status','--porcelain','--untracked-files=no'),'clean checked freeze')
    io.require(not list(OUTPUT.glob('*/manifest.json')) and io.read(CONFIG)==config() and io.read(SEEDS)==registry(),'single allocation')
    io.require(shutil.disk_usage(ROOT).free>=2*1024**3,'two GiB storage reserve')
    for n,h in qa['source_sha256'].items():io.require(io.sha(ROOT/n)==h and io.git('ls-files','--error-unmatch',n)==n,'committed checked native source')
    from src.analysis.response_action_io_v1 import verify_runtime
    from src.analysis.command_target_sources_v1 import package_sources
    verify_runtime(io.read(VALIDATION/'runtime_lock.json'));scope=seed_scope();head=io.git('rev-parse','HEAD')
    m={'experiment_run_id':'native_command_witness_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+head[:12],
        'source_git_commit':head,'source_sha256':qa['source_sha256'],'installed_source_sha256':package_sources(),'config':config(),
        'native_only_not_model_training':True,'publication_goal_complete':False}
    m['manifest_id']=io.digest(m);out=OUTPUT/m['experiment_run_id'];out.mkdir(parents=True,exist_ok=False)
    io.write(out/'manifest.json',m);io.write(out/'seed_scope.json',scope);return out/'manifest.json'

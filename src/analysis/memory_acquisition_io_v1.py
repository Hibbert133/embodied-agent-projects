"""New native software cohort only; no trained model, selector or reidentification."""
from pathlib import Path
from datetime import datetime,timezone
import re,shutil
import numpy as np
from src.analysis import response_qualification_io_v1 as io
from src.probe.memory_acquisition_program_v1 import ACTIONS
ROOT=io.ROOT;BASE=ROOT/'outputs/memory_acquisition';OUTPUT=BASE/'qualification_v1';VALIDATION=BASE/'validation_v1'
CONFIG=ROOT/'configs/movement_task/memory_acquisition_native_v1.json'
PROTOCOL=ROOT/'docs/protocols/memory_acquisition_native_v1_zh.md'
SEEDS=ROOT/'docs/protocols/memory_acquisition_native_seeds_v1.json'
KEYS=('group','task','seed','context','planned_boundary','action')
IDENTITY=('experiment_run_id','manifest_id','source_git_commit')
OWN=('src/probe/memory_acquisition_program_v1.py','src/analysis/memory_acquisition_io_v1.py',
    'src/analysis/memory_acquisition_host_v1.py','src/analysis/memory_acquisition_collect_v1.py','src/analysis/memory_acquisition_audit_v1.py',
    'scripts/run_memory_acquisition_native_v1.py','scripts/audit_memory_acquisition_native_v1.py',
    'scripts/report_memory_acquisition_native_v1.py','tests/test_memory_acquisition_native_v1.py')


def population():return [{ 'group':g,'task':t,'seed':65000+3*g+i,'context':c,'planned_boundary':b,'action':a}
    for g,b in enumerate((16,32,64)) for i,t in enumerate(io.TASKS) for c in ('UNCHANGED','CHANGED') for a in ACTIONS]
def validate_spec(spec):io.require(spec in population(),'unregistered native software case')
def limits():return {'executions':54,'control_steps':27000,'controlled_resets':54,'all_resets':2754,'physical_frames':1512000,'parameter_fits':0}
def registry():return {'protocol':'memory_acquisition_native_v1','native_episode_seed_range':[65000,65008],
    'reserved_episode_seed_range':[65009,65099],'noise_namespace':140002,'operator_nonce':140001,'purpose':'Native software contract only; not TRAIN/CAL/TEST'}
def config():return {'protocol':'MEMORY_ACQUISITION_NATIVE_V1','classification':'NATIVE_SOFTWARE_CONTRACT_NOT_METHOD_QUALIFICATION',
    'population':population(),'limits':limits(),'per_execution_steps':500,'source_policy':'RAW_TASK_PI_T0.5',
    'actions':list(ACTIONS),'tail_action':'KEEP','short_validation_steps':8,'reposition_limit':64,'warm_probe_steps':8,
    'task_reserve_steps':100,'noise_sigma':.05,'initial_fault':initial_fault(),'support':'one-hot deterministic first arm; KEEP only; no cross-action off-policy value identification',
    'native_gate':'all allocated cases audited; real movement and post-movement task command on each task; at least one complete warm window; zero continuity violations',
    'failure':'software error stops once, keep partial; early task success and unavailable/incomplete measurement retained; no retry/extension/replacement',
    'new_parameter_fits':0,'new_response_training':0,'new_policy_training':0,'online_LLM_API_calls':0,
    'new_model_or_task_gain_claim':False,'safety_guarantee':False,'publication_goal_complete':False}
def initial_fault():return {'matrix_xy':[[1.,0.],[0.,1.]],'bias_xy':[.12,-.08],'deadzone_xy':[0.,0.]}
def destination(spec):
    validate_spec(spec)
    if spec['context']=='UNCHANGED':return initial_fault()
    r=np.random.default_rng(np.random.SeedSequence([140001,spec['group']]))
    return {'matrix_xy':[[float(r.uniform(.75,1.25)),float(r.uniform(-.2,.2))],[float(r.uniform(-.2,.2)),float(r.uniform(.75,1.25))]],
        'bias_xy':r.uniform(-.2,.2,2).tolist(),'deadzone_xy':[0.,0.]}
def noise(seed):
    r=np.random.default_rng(int(np.random.SeedSequence([seed,140002]).generate_state(1)[0]));v=r.normal(0,.05,(500,3)).astype('<f4');v.flags.writeable=False;return v


def seed_scope():
    own={p.relative_to(ROOT).as_posix() for p in (CONFIG,PROTOCOL,SEEDS)};inputs={};collisions=[]
    overlap=lambda a,b:a<=65099 and 65000<=b
    def visit(v,name,key=''):
        if isinstance(v,dict):
            for k,w in v.items():
                if 'seed' in k.lower() and not any(s in k.lower() for s in ('noise','namespace','bootstrap','generator','generation','nonce','initialization','sampling')):
                    if type(w) is int and overlap(w,w):collisions.append([name,key+k,w])
                    if type(w) is list and all(type(n) is int for n in w):
                        if len(w)==2 and w[0]<=w[1] and overlap(*w):collisions.append([name,key+k,w])
                        elif len(w)!=2 and any(overlap(n,n) for n in w):collisions.append([name,key+k,'LIST'])
                visit(w,name,key+k+'.')
            if type(v.get('seed_start')) is int:
                a=v['seed_start'];b=v.get('seed_end',a+v.get('num_seeds',1)-1)
                if type(b) is int and overlap(a,b):collisions.append([name,key,[a,b]])
        elif type(v) is list:
            for w in v:visit(w,name,key)
    files=set((ROOT/'configs').rglob('*.json'))|set((ROOT/'outputs').rglob('manifest.json'))|set((ROOT/'docs/protocols').glob('*seed*.json'))
    for p in sorted(files):
        n=p.relative_to(ROOT).as_posix()
        if n not in own:inputs[n]=io.sha(p);visit(io.read(p),n)
    for p in sorted((ROOT/'docs/protocols').glob('*.md')):
        n=p.relative_to(ROOT).as_posix()
        if n in own:continue
        inputs[n]=io.sha(p)
        for line in p.read_text(encoding='utf-8').splitlines():
            if re.search('seed|种子|预留|保留',line,re.I):
                for a,b in re.findall(r'\b(\d{4,6})\s*(?:--|–|\.\.|-)\s*(\d{4,6})\b',line):
                    if overlap(int(a),int(b)):collisions.append([n,a,b])
    io.require(not collisions,'seed allocation collision '+str(collisions[:3]))
    return {'integrity':'PASSED_NO_REGISTERED_COLLISION','proposed_range':[65000,65099],'inputs_sha256':inputs,'collisions':collisions}


def checked(path):
    path=Path(path).resolve();v=io.read(path);body=dict(v);mid=body.pop('manifest_id')
    io.require(path.name=='manifest.json' and path.parent.parent==OUTPUT.resolve() and io.digest(body)==mid and v['config']==config(),'owned immutable manifest')
    for n,h in v['source_sha256'].items():io.require(io.sha(ROOT/n)==h,'frozen source changed '+n)
    return v
def prepare():
    io.require(not list(OUTPUT.glob('*/manifest.json')),'one software allocation only');qa=io.read(VALIDATION/'complete.json')
    io.require(qa['integrity']=='PASSED' and not io.git('status','--porcelain','--untracked-files=no'),'clean checked freeze required')
    for n,h in qa['source_sha256'].items():io.require(io.sha(ROOT/n)==h and io.git('ls-files','--error-unmatch',n)==n,'checked source must be committed')
    io.require(io.read(CONFIG)==config() and io.read(SEEDS)==registry() and shutil.disk_usage(ROOT).free>=4*1024**3,'config or storage reserve')
    from src.analysis.response_action_io_v1 import verify_runtime
    verify_runtime(io.read(VALIDATION/'runtime_lock.json'));scope=seed_scope();head=io.git('rev-parse','HEAD')
    names=set(io.git('ls-files','src','scripts','tests').splitlines())|set(OWN)|{p.relative_to(ROOT).as_posix() for p in (CONFIG,SEEDS,PROTOCOL)}
    names|={(VALIDATION/n).relative_to(ROOT).as_posix() for n in ('complete.json','runtime_lock.json')}
    v={'experiment_run_id':'memory_acquisition_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+head[:12],
        'source_git_commit':head,'config':config(),'source_sha256':{n:io.sha(ROOT/n) for n in sorted(names)},
        'native_software_only':True,'new_API_calls':0,'publication_goal_complete':False}
    v['manifest_id']=io.digest(v);out=OUTPUT/v['experiment_run_id'];out.mkdir(parents=True,exist_ok=False)
    io.write(out/'manifest.json',v);io.write(out/'seed_scope.json',scope);return out/'manifest.json'

"""Independent known-packet response study: allocations, budgets and frozen gates."""
from pathlib import Path
from datetime import datetime,timezone
import re,shutil
import numpy as np
from src.analysis import response_qualification_io_v1 as io
ROOT=io.ROOT;BASE=ROOT/'outputs/latent_response';OUTPUT=BASE/'qualification_v1';VALIDATION=BASE/'validation_v1'
CONFIG=ROOT/'configs/movement_task/latent_response_qualification_v1.json';PROTOCOL=ROOT/'docs/protocols/latent_response_qualification_v1_zh.md'
SEEDS=ROOT/'docs/protocols/latent_response_seeds_v1.json'
SPLITS=('SOFTWARE','TRAIN','CAL','QUAL')
KEYS=('split','group','task','seed','initial_kind','context','boundary','packet_kind')
IDENTITY=('experiment_run_id','manifest_id','source_git_commit')
TRAIN_PYTHON=Path('C:/Users/Administrator/Documents/ChatGPT/robotic agent/.venv-history-training-cpu22/Scripts/python.exe')
TRAIN_RUNTIME=ROOT/'outputs/observable_history_transfer/runtime_v1/environment.json'
NATIVE=ROOT/'outputs/native_command_witness/qualification_v1/native_command_witness_20261022T172319Z_9c64ab52ca23'
OWN=('src/probe/latent_response_query_v1.py','src/probe/latent_response_model_v1.py','src/probe/latent_response_packet_v1.py',
    'src/analysis/latent_response_io_v1.py','src/analysis/latent_response_host_v1.py','src/analysis/latent_response_collect_v1.py',
    'src/analysis/latent_response_record_audit_v1.py','src/analysis/latent_response_training_v1.py','src/analysis/latent_response_model_audit_v1.py',
    'src/analysis/latent_response_evaluation_v1.py','src/analysis/latent_response_statistics_audit_v1.py',
    'scripts/run_latent_response_v1.py','scripts/train_latent_response_v1.py','scripts/report_latent_response_v1.py','tests/test_latent_response_v1.py')


def population(split):
    io.require(split in SPLITS,'registered split');groups,start={'SOFTWARE':(3,71000),'TRAIN':(36,71100),'CAL':(9,71400),'QUAL':(18,71600)}[split]
    return [{'split':split,'group':g,'task':task,'seed':start+3*g+i,'initial_kind':initial,'context':ctx,
        'boundary':(16,32,64)[g%3],'packet_kind':packet}
        for g in range(groups) for i,task in enumerate(io.TASKS)
        for initial in (('NOMINAL','BIASED') if split=='QUAL' else ('BIASED',) if split=='SOFTWARE' else ('NOMINAL' if g%2==0 else 'RANDOM',))
        for ctx in ('UNCHANGED','CHANGED') for packet in (('RANDOM32',) if split=='TRAIN' else ('FIXED8','RANDOM8'))]


def validate_spec(v):io.require(v in population(v.get('split')),'frozen response assignment')
def nonce(split,base):return base+SPLITS.index(split)


def affine(g,key):
    r=np.random.default_rng(np.random.SeedSequence([key,g]));return {'matrix_xy':[[float(r.uniform(.75,1.25)),float(r.uniform(-.2,.2))],
        [float(r.uniform(-.2,.2)),float(r.uniform(.75,1.25))]],'bias_xy':r.uniform(-.2,.2,2).tolist(),'deadzone_xy':[0.,0.]}


def initial_fault(v):
    validate_spec(v)
    if v['initial_kind']=='RANDOM':return affine(v['group'],nonce(v['split'],2026102400))
    return {'matrix_xy':[[1.,0.],[0.,1.]],'bias_xy':[.12,-.08] if v['initial_kind']=='BIASED' else [0.,0.],'deadzone_xy':[0.,0.]}


def destination(v):return initial_fault(v) if v['context']=='UNCHANGED' else affine(v['group'],nonce(v['split'],2026102404))


def noise(v):
    validate_spec(v);key=int(np.random.SeedSequence([v['seed'],nonce(v['split'],2026102410)]).generate_state(1)[0])
    tape=np.random.default_rng(key).normal(0,.05,(500,3)).astype('<f4');tape.flags.writeable=False;return tape


def packet(v):
    validate_spec(v)
    if v['packet_kind']=='FIXED8':return np.asarray([[.4,0,0,0],[0,.4,0,0],[-.4,0,0,0],[0,-.4,0,0]]*2,np.float32).tolist()
    length=32 if v['packet_kind']=='RANDOM32' else 8
    r=np.random.default_rng(np.random.SeedSequence([v['seed'],nonce(v['split'],2026102420)]));out=np.zeros((length,4),np.float32);out[:,:2]=r.uniform(-.8,.8,(length,2));return out.tolist()


def limits(split):
    n=len(population(split));cap=160 if split=='TRAIN' else 136
    return {'executions':n,'control_steps':n*cap,'per_case_control_cap':cap,'controlled_resets':n,'factory_resets':50*n,'all_resets':51*n,'physical_frames':n*25500+5*n*cap}


def registry():return {'protocol':'LATENT_RESPONSE_QUALIFICATION_V1','software_episode_seed_range':[71000,71008],
    'train_episode_seed_range':[71100,71207],'cal_episode_seed_range':[71400,71426],'qual_episode_seed_range':[71600,71653],
    'reserved_episode_seed_ranges':[[71009,71099],[71208,71399],[71427,71599],[71654,71999]],
    'operator_nonce_base':2026102400,'changed_operator_nonce_base':2026102404,'noise_namespace_base':2026102410,
    'packet_generator_base':2026102420,'neural_initialization_seed_base':2026102430,'neural_sampling_seed_base':2026102434,'bootstrap_seed':2026102440}


def config():
    ls={s:limits(s) for s in SPLITS}
    return {'protocol':'LATENT_RESPONSE_QUALIFICATION_V1','classification':'STANDARD_PREDICTOR_COMPONENT_NOT_ACQUISITION_INNOVATION',
        'populations':{s:population(s) for s in SPLITS},'limits':ls,
        'combined_limits':{k:sum(v[k] for v in ls.values()) for k in ('executions','control_steps','controlled_resets','factory_resets','all_resets','physical_frames')},
        'actor':'FIXED_RAW_PI_T0.5_THEN_LOCAL_PID_THEN_EXOGENOUS_PACKET_NO_TASK_TAIL','noise_sigma':.05,
        'packet_horizon':8,'TRAIN_packet_length':32,'history_frames':16,'context_dimensions':723,'direct_ridge_dimensions':756,
        'models':['SS_SENT','SS_NO_SENT','SS_CURRENT_SENT','DIRECT_MLP_H8','DIRECT_RIDGE_H8','PERSIST_ZERO','HISTORY_LINEAR10','QUADRATIC_STATE20'],
        'neural':{'latent':8,'hidden':32,'activation':'tanh','updates':5000,'batch_trajectories':32,'optimizer':'Adam','lr':.001,
            'betas':[.9,.999],'eps':1e-8,'weight_decay':0.,'gradient_clipping':None,'early_stopping':False,'threads':1,'dtype':'float32',
            'SS_parameters':24130,'DIRECT_MLP_parameters':25272,'same_SS_initialization_and_all_sampling_schedules':True},
        'training':{'minimum_available_trajectories_per_task':24,'minimum_complete_entry_packets_per_task':16,'ridge':.001,
            'normalization':'TRAIN_ONLY_TRAJECTORY_THEN_WINDOW_THEN_REAL_FRAME_EQUAL_WEIGHT','neural_target_unit_m':.01,
            'sampling':'UNIFORM_AVAILABLE_TRAJECTORY_THEN_UNIFORM_START_0_TO_MIN(PACKET_RESPONSES_MINUS_1,24)',
            'partial_targets':'CONTIGUOUS_ACTUAL_PREFIX_MASK_NO_INVENTED_RESPONSES','fitted_models':21,'deterministic_zero_models':3,
            'neural_trainings':12,'neural_optimizer_updates':60000,'ridge_linear_systems':30,'audit_ridge_systems':30,'audit_neural_retrains':0,
            'training_hard_timeout_seconds':7200,'retry':False},
        'qualification':{'principal':'SS_SENT','co_primary_full_allocation_comparators':['SS_NO_SENT','DIRECT_MLP_H8'],
            'both_group_bootstrap95_upper_strictly_below_zero':True,'full_H8_point_mean_below':['DIRECT_RIDGE_H8','PERSIST_ZERO','SS_CURRENT_SENT'],
            'full_H1_point_mean_below':['HISTORY_LINEAR10','QUADRATIC_STATE20'],'all_24_task_initial_context_program_cells_complete_minimum':3,
            'all_18_groups_have_complete_packet':True,'any_invalid_forecast_blocks_promotion':True,
            'missing_or_invalid_packet_loss_m':1.,'loss_cap_m':1.,'statistic_unit_m':1e-9,'rounding':'DECIMAL80_HALF_EVEN',
            'task_utility_not_inferred_from_prediction':True},
        'bootstrap':{'replicates':10000,'seed':2026102440,'unit':'18_WHOLE_GROUPS_6_PER_BOUNDARY','quantiles':'EXACT_INTEGER_NANOMETRE_GROUP_TOTALS_LINEAR_1/40_39/40'},
        'CAL':'EMPIRICAL_DESCRIPTIVE_0.5_0.9_0.95_ONLY_NO_SELECTION_OR_THRESHOLD_FIT',
        'new_C4_C8_fits':0,'new_online_LLM_API_calls':0,'private_mocap_true_fault_actual_noise_only_for_evaluation_not_training':True,
        'no_task_correction_or_acquisition_policy_training':True,'publication_goal_complete':False}


def checked(path):
    path=Path(path).resolve();m=io.read(path);body=dict(m);mid=body.pop('manifest_id')
    io.require(path.name=='manifest.json' and path.parent.parent==OUTPUT.resolve() and io.digest(body)==mid and m['config']==config(),'owned latent-response manifest')
    for n,h in m['source_sha256'].items():io.require(io.sha(ROOT/n)==h,'frozen source changed '+n)
    for n,h in m['input_sha256'].items():io.require(io.sha(ROOT/n)==h,'frozen prerequisite/runtime changed '+n)
    return m


def phase_gate(path,split):
    m=checked(path);root=Path(path).parent;io.require(split in SPLITS,'phase')
    if split=='TRAIN':io.require(io.read(root/'software/audit.json')['software_contract']=='PASSED','native software contract before TRAIN')
    if split=='CAL':
        audit=io.read(root/'training/audit.json');io.require(audit['integrity']=='PASSED' and audit['models_sha256']==io.sha(root/'training/models.json'),'unchanged audited model before CAL')
    if split=='QUAL':
        lock=io.read(root/'model_lock.json');io.require(lock['status']=='FROZEN_BEFORE_QUAL','independent QUAL lock')
        for n,h in lock['artifact_sha256'].items():io.require(io.sha(root/n)==h,'TRAIN/CAL/model lock changed')
    return m


def seed_scope():
    own={p.relative_to(ROOT).as_posix() for p in (CONFIG,PROTOCOL,SEEDS)};inputs={};collisions=[]
    overlap=lambda lo,hi:lo<=71999 and 71000<=hi
    def visit(v,name,path=''):
        if type(v) is dict:
            for k,w in v.items():
                if 'seed' in k.lower() and not any(t in k.lower() for t in ('noise','namespace','bootstrap','generator','generation','nonce','initialization','sampling')):
                    if type(w) is int and overlap(w,w):collisions.append([name,path+k,w])
                    if type(w) is list and all(type(x) is int for x in w):
                        if len(w)==2 and w[0]<=w[1] and overlap(*w):collisions.append([name,path+k,w])
                        elif len(w)!=2 and any(overlap(x,x) for x in w):collisions.append([name,path+k,'LIST'])
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
    io.require(not collisions,'used/reserved seed range '+str(collisions[:3]));return {'integrity':'PASSED_NO_REGISTERED_COLLISION','range':[71000,71999],'inputs_sha256':inputs,'collisions':collisions}


def prepare():
    qa=io.read(VALIDATION/'complete.json');io.require(qa['integrity']=='PASSED' and not io.git('status','--porcelain','--untracked-files=no'),'clean checked freeze')
    io.require(not list(OUTPUT.glob('*/manifest.json')) and io.read(CONFIG)==config() and io.read(SEEDS)==registry(),'one allocation')
    native=io.read(NATIVE/'native/audit.json');io.require(native['integrity']==native['native_contract']=='PASSED','actual native prerequisite')
    io.require(shutil.disk_usage(ROOT).free>=4*1024**3,'four GiB scientific storage reserve')
    for n,h in qa['source_sha256'].items():io.require(io.sha(ROOT/n)==h and io.git('ls-files','--error-unmatch',n)==n,'committed tested source')
    from src.analysis.response_action_io_v1 import verify_runtime
    verify_runtime(io.read(VALIDATION/'runtime_lock.json'));scope=seed_scope();head=io.git('rev-parse','HEAD')
    inputs={p.relative_to(ROOT).as_posix():io.sha(p) for p in (NATIVE/'manifest.json',NATIVE/'native/audit.json',TRAIN_RUNTIME)}
    m={'experiment_run_id':'latent_response_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+head[:12],
        'source_git_commit':head,'source_sha256':qa['source_sha256'],'input_sha256':inputs,'config':config(),
        'training_python':str(TRAIN_PYTHON),'training_runtime':io.read(TRAIN_RUNTIME),'publication_goal_complete':False}
    m['manifest_id']=io.digest(m);out=OUTPUT/m['experiment_run_id'];out.mkdir(parents=True,exist_ok=False);io.write(out/'manifest.json',m);io.write(out/'seed_scope.json',scope);return out/'manifest.json'

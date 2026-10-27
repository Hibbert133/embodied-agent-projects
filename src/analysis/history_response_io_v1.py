"""Fresh allocations for a standard, known-packet response-contrast pilot."""
from pathlib import Path
from datetime import datetime,timezone
import re,shutil
import numpy as np
from src.analysis import response_qualification_io_v1 as io
ROOT=io.ROOT;BASE=ROOT/'outputs/history_response';OUTPUT=BASE/'development_v1';VALIDATION=BASE/'freeze_validation_v1'
CONFIG=ROOT/'configs/movement_task/history_response_v1.json';PROTOCOL=ROOT/'docs/protocols/history_response_v1_zh.md';SEEDS=ROOT/'docs/protocols/history_response_seeds_v1.json'
SPLITS=('SOFTWARE','TRAIN','CAL','QUAL');ROLES=('ZERO','PLUS','MINUS')
KEYS=('split','group','task','seed','context','boundary','acquisition_action','packet_kind');IDENTITY=('experiment_run_id','manifest_id','source_git_commit')

def population(split):
    io.require(split in SPLITS,'registered paired packet split');groups,start={'SOFTWARE':(3,112000),'TRAIN':(9,112100),'CAL':(3,112200),'QUAL':(9,112300)}[split]
    return [dict(split=split,group=g,task=task,seed=start+3*g+i,context=context,boundary=(16,32,64)[g%3],acquisition_action=action,packet_kind=role)
        for g in range(groups) for i,task in enumerate(io.TASKS) for context in ('UNCHANGED','CHANGED') for action in ('IN_TASK','MOVE') for role in ROLES]

def validate_spec(v):io.require(v in population(v.get('split')),'frozen paired packet assignment')
def family_key(v):return tuple(v[k] for k in KEYS if k!='packet_kind')
def nonce(split,base):return base+SPLITS.index(split)

def initial_fault(v):
    validate_spec(v);return dict(matrix_xy=[[1.,0.],[0.,1.]],bias_xy=[.12,-.08],deadzone_xy=[0.,0.])

def destination(v):
    if v['context']=='UNCHANGED':return initial_fault(v)
    validate_spec(v);r=np.random.default_rng(np.random.SeedSequence([nonce(v['split'],2026102900),v['group']]))
    return dict(matrix_xy=[[float(r.uniform(.75,1.25)),float(r.uniform(-.2,.2))],[float(r.uniform(-.2,.2)),float(r.uniform(.75,1.25))]],bias_xy=r.uniform(-.2,.2,2).tolist(),deadzone_xy=[0.,0.])

def noise(v):
    validate_spec(v);r=np.random.default_rng(np.random.SeedSequence([v['seed'],nonce(v['split'],2026102910)]))
    tape=r.normal(0,.05,(500,3)).astype('<f4');tape.flags.writeable=False;return tape

def packets(v):
    validate_spec(v);r=np.random.default_rng(np.random.SeedSequence([v['seed'],nonce(v['split'],2026102920)]))
    plus=np.zeros((16,4),np.float32);plus[:,:2]=(2*r.integers(0,2,(16,2))-1)*np.float32(.4)
    minus=plus.copy();minus[:,:2]*=-1
    return {'ZERO':np.zeros((16,4),np.float32).tolist(),'PLUS':plus.tolist(),'MINUS':minus.tolist()}

def case_cap(v):return v['boundary']+24+(64 if v['acquisition_action']=='MOVE' else 0)

def limits(split):
    pop=population(split);n=len(pop);steps=sum(case_cap(v) for v in pop)
    return dict(executions=n,families=n//3,control_steps=steps,maximum_case_control_cap=152,controlled_resets=n,factory_resets=50*n,all_resets=51*n,physical_frames=25500*n+5*steps)

def config():
    ls={s:limits(s) for s in SPLITS}
    return dict(protocol='HISTORY_RESPONSE_V1',classification='STANDARD_PUBLIC_CONTEXT_COMPONENT_NOT_ACQUISITION_METHOD_OR_PAPER',
        populations={s:population(s) for s in SPLITS},limits=ls,combined_limits={k:sum(v[k] for v in ls.values()) for k in ('executions','families','control_steps','controlled_resets','factory_resets','all_resets','physical_frames')},
        actor='UNCHANGED_FIXED_RAW_PI_T0.5_OPTIONAL_LOCAL_PID_COMMON8_KNOWN16_NO_TASK_TAIL',
        roles=list(ROLES),packets='ZERO_SYMMETRIC_RADEMACHER_XY0.4_Z_GRIP0_LENGTH16',common_measure_steps=8,history_transitions=16,noise_sigma=.05,
        forecast='ALL3_CONTRASTS_FROM_ZERO_ENTRY_BEFORE_ANY_FAMILY_PACKET_OUTCOME',
        models=['ZERO','INSTANT','FIR','STATE_KERNEL','HISTORY_NN','HISTORY_KERNEL'],selected_model='HISTORY_KERNEL',
        ridge=.001,target_unit_m=.01,FIR_lags=16,context_kernel='EXP_NEG_HALF_MEAN_SQUARED_TRAIN_STANDARDIZED_DISTANCE',
        descriptors=dict(STATE='CURRENT_PUBLIC39_PLUS_CARRIED_INTEGRAL2',HISTORY='STATE41_PLUS16x(SENT_COMMAND4_AND_HAND_DXYZ_DIV0.01)'),
        dimensions=dict(STATE=41,HISTORY=153),nearest_neighbour_reference='NEAREST_PUBLIC_HISTORY_CENTER_WITH_PREFIT_FIR_ON8_NEAREST_TRAIN_FAMILIES',
        training=dict(complete_three_role_H16_families_only=True,minimum_complete_families_per_task=12,minimum_available_groups_per_task=3,all9_groups_have_complete_family=True,
            target='FACTUAL_PLUS_MINUS_ODD_RESPONSE_DIV0.01',linear_pair_objective_odd_reduction='EVEN_TERM_IS_PARAMETER_INDEPENDENT_NOT_DISCARDED_FROM_EVALUATION',
            weights='EQUAL_AVAILABLE_GROUP_THEN_FAMILY_THEN16_H',normalization='WEIGHTED_TRAIN_INPUT_RMS_AND_CONTEXT_CENTERED_SD_ZERO_SD_TO1',
            no_true_parameter_noise_private_state_features_or_labels=True,no_old_population_fitting_or_tuning=True),
        fits=dict(global_ridge_systems=6,context_dual_systems=6,nearest_center_ridge_systems_max=108,main_solve_max=120,
            independent_augmented_lstsq_max=114,independent_eigendecompositions=6,neural_updates=0,C4_C8_fits=0),
        calibration=dict(groups=3,purpose='SAVED_FORECAST_AND_RECORD_READINESS_NO_MODEL_OR_THRESHOLD_SELECTION',fixed_model='HISTORY_KERNEL'),
        qualification=dict(groups=9,selected_model='HISTORY_KERNEL',co_primary=['ZERO','INSTANT','FIR','STATE_KERNEL','HISTORY_NN'],
            every_group_bootstrap95_upper_below_zero=True,each_task_and_H8_H16_point_mean_below_all_references=True,
            all9_groups_have_complete_family=True,minimum_complete_pairs_per_task_context_anchor=3,any_invalid_forecast_blocks_promotion=True,
            unavailable_or_invalid_endpoint_loss_m=1.,loss_cap_m=1.,statistic_unit_m=1e-9,rounding='DECIMAL80_HALF_EVEN',
            no_full_task_utility_or_inverse_qualification=True),
        bootstrap=dict(replicates=10000,seed=2026102960,unit='9_WHOLE_GROUPS_3_PER_BOUNDARY',quantiles='LINEAR_0.025_0.975'),
        software_gate='ALL_NATIVE_RECORDS_EXACT_AND_AT_LEAST_ONE_COMPLETE_FAMILY_EACH_TASK_ANCHOR',
        forbidden=['ENV_CAPTURE_OR_RESTORE','FUTURE_POLICY_COMMANDS_AS_KNOWN','TRUE_FAULT_NOISE_PRIVATE_TRAINING_INPUT_OR_LABEL','QUAL_TUNING','SAMPLE_EXTENSION'],
        online_LLM_API_calls=0,new_forward_model_used_for_control=False,old_negative_versions_reopened=False,algorithm_novelty_established=False,publication_goal_complete=False)


def registry():return dict(protocol='HISTORY_RESPONSE_V1',software_episode_seed_range=[112000,112008],train_episode_seed_range=[112100,112126],
    cal_episode_seed_range=[112200,112208],qual_episode_seed_range=[112300,112326],
    reserved_episode_seed_ranges=[[112009,112099],[112127,112199],[112209,112299],[112327,112999]],
    changed_operator_namespace_base=2026102900,noise_namespace_base=2026102910,packet_namespace_base=2026102920,bootstrap_seed=2026102960)

def seed_scope():
    own={p.relative_to(ROOT).as_posix() for p in (CONFIG,PROTOCOL,SEEDS)};inputs={};collisions=[]
    def overlap(lo,hi):return lo<=112999 and 112000<=hi
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
        for line in p.read_text('utf8').splitlines():
            if re.search('seed|种子|预留|保留',line,re.I):
                for lo,hi in re.findall(r'\b(\d{4,6})\s*(?:--|–|\.\.|-)\s*(\d{4,6})\b',line):
                    if overlap(int(lo),int(hi)):collisions.append([n,lo,hi])
    io.require(not collisions,'used/reserved paired packet seeds '+str(collisions[:3]))
    return dict(integrity='PASSED_NO_REGISTERED_COLLISION',range=[112000,112999],inputs_sha256=inputs,collisions=collisions)

def checked(path):
    path=Path(path).resolve();m=io.read(path);copy=dict(m);mid=copy.pop('manifest_id')
    io.require(path.parent.parent==OUTPUT and mid==io.digest(copy) and m['config']==config() and io.read(CONFIG)==config(),'owned immutable paired packet manifest')
    for n,h in {**m['source_sha256'],**m['input_sha256']}.items():io.require(io.sha(ROOT/n)==h,'immutable paired packet source/input '+n)
    return m

def phase_gate(path,split):
    m=checked(path);out=Path(path).parent;io.require(split in SPLITS,'registered physical phase')
    if split=='TRAIN':io.require(io.read(out/'software/audit.json')['software_contract']=='PASSED','native software gate before TRAIN')
    if split in ('CAL','QUAL'):
        audit=io.read(out/'training/audit.json');io.require(audit['integrity']=='PASSED' and audit['models_sha256']==io.sha(out/'training/models.json'),'immutable audited learned models')
    if split=='QUAL':
        lock=io.read(out/'model_lock.json');io.require(lock['status']=='FROZEN_BEFORE_QUAL','independent qualification lock')
        for n,h in lock['artifact_sha256'].items():io.require(io.sha(out/n)==h,'locked TRAIN/CAL artifacts')
    return m

def prepare(sources):
    frozen=io.read(VALIDATION/'complete.json');io.require(frozen['integrity']=='PASSED' and not io.git('status','--porcelain','--untracked-files=no'),'clean fully checked paired packet freeze')
    io.require(not list(OUTPUT.glob('*/manifest.json')) and io.read(CONFIG)==config() and io.read(SEEDS)==registry(),'one frozen physical population')
    io.require(shutil.disk_usage(ROOT).free>=4*1024**3,'four GiB storage reserve before physical allocation')
    tracked=set(io.git('ls-files').splitlines())
    for n,h in frozen['source_sha256'].items():io.require(io.sha(ROOT/n)==h and n in tracked,'committed tested science source')
    scope=seed_scope();head=io.git('rev-parse','HEAD');runtime=ROOT/'outputs/correction_scope/freeze_validation_v1/runtime_lock.json'
    from src.analysis.response_action_io_v1 import verify_runtime
    verify_runtime(io.read(runtime));m=dict(experiment_run_id='history_response_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+head[:12],source_git_commit=head,
        config=config(),source_sha256={n:io.sha(ROOT/n) for n in sources},input_sha256={runtime.relative_to(ROOT).as_posix():io.sha(runtime)},publication_goal_complete=False)
    m['manifest_id']=io.digest(m);out=OUTPUT/m['experiment_run_id'];out.mkdir(parents=True,exist_ok=False);io.write(out/'manifest.json',m);io.write(out/'seed_scope.json',scope);return out/'manifest.json'

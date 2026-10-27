"""Fresh, bounded qualification of a standard public joint-observer reference."""
from pathlib import Path
from datetime import datetime,timezone
from copy import deepcopy
import shutil
import numpy as np
from src.analysis import response_qualification_io_v1 as io
ROOT=io.ROOT;BASE=ROOT/'outputs/graybox_response';OUTPUT=BASE/'qualification_v1';VALIDATION=BASE/'freeze_validation_v1'
CONFIG=ROOT/'configs/movement_task/graybox_response_v1.json';PROTOCOL=ROOT/'docs/protocols/graybox_response_v1_zh.md';SEEDS=ROOT/'docs/protocols/graybox_response_seeds_v1.json'
SPLITS=('SOFTWARE','NOMINAL','TRAIN','CAL','QUAL');ROLES=('ZERO','PLUS','MINUS');KEYS=('split','group','task','seed','context','boundary','acquisition_action','packet_kind')
IDENTITY=('experiment_run_id','manifest_id','source_git_commit');Q_CHOICES=(0.,.001,.01)

def population(split):
    io.require(split in SPLITS,'registered graybox phase')
    groups,start={'SOFTWARE':(3,113000),'NOMINAL':(9,113050),'TRAIN':(9,113100),'CAL':(3,113200),'QUAL':(9,113300)}[split]
    if split=='NOMINAL':return [dict(split=split,group=g,task=t,seed=start+3*g+i,context='KNOWN_NOMINAL',boundary=0,acquisition_action='NOMINAL',packet_kind='NOMINAL') for g in range(groups) for i,t in enumerate(io.TASKS)]
    return [dict(split=split,group=g,task=t,seed=start+3*g+i,context=c,boundary=(16,32,64)[g%3],acquisition_action=p,packet_kind=r)
        for g in range(groups) for i,t in enumerate(io.TASKS) for c in ('UNCHANGED','CHANGED') for p in ('IN_TASK','MOVE') for r in ROLES]

def validate_spec(v):io.require(v in population(v.get('split')),'exact frozen graybox assignment')
def family_key(v):return tuple(v[k] for k in KEYS if k!='packet_kind')
def nonce(v,base):return base+SPLITS.index(v['split'])

def initial_fault(v):
    validate_spec(v);return dict(matrix_xy=[[1.,0.],[0.,1.]],bias_xy=[0.,0.] if v['split']=='NOMINAL' else [.12,-.08],deadzone_xy=[0.,0.])

def destination(v):
    if v['context'] in ('UNCHANGED','KNOWN_NOMINAL'):return initial_fault(v)
    validate_spec(v);r=np.random.default_rng(np.random.SeedSequence([nonce(v,2026103000),v['group']]))
    return dict(matrix_xy=[[float(r.uniform(.75,1.25)),float(r.uniform(-.2,.2))],[float(r.uniform(-.2,.2)),float(r.uniform(.75,1.25))]],bias_xy=r.uniform(-.2,.2,2).tolist(),deadzone_xy=[0.,0.])

def noise(v):
    validate_spec(v);r=np.random.default_rng(np.random.SeedSequence([v['seed'],nonce(v,2026103010)]))
    tape=r.normal(0,.05,(500,3)).astype('<f4');tape.flags.writeable=False;return tape

def packets(v):
    validate_spec(v);n=80 if v['split']=='NOMINAL' else 16;r=np.random.default_rng(np.random.SeedSequence([v['seed'],nonce(v,2026103020)]))
    plus=np.zeros((n,4),np.float32);plus[:,:2]=(2*r.integers(0,2,(n,2))-1)*np.float32(.4)
    if v['split']=='NOMINAL':return {'NOMINAL':plus.astype(float).tolist()}
    minus=plus.copy();minus[:,:2]*=-1
    return dict(ZERO=np.zeros((16,4),np.float32).tolist(),PLUS=plus.astype(float).tolist(),MINUS=minus.astype(float).tolist())

def case_cap(v):return 80 if v['split']=='NOMINAL' else v['boundary']+24+(64 if v['acquisition_action']=='MOVE' else 0)
def limits(split):
    pop=population(split);n=len(pop);steps=sum(case_cap(v) for v in pop)
    return dict(executions=n,control_steps=steps,controlled_resets=n,factory_resets=50*n,all_resets=51*n,physical_frames=25500*n+5*steps)

def registry():
    return dict(protocol='GRAYBOX_RESPONSE_V1',software_episode_seed_range=[113000,113008],nominal_episode_seed_range=[113050,113076],
        train_episode_seed_range=[113100,113126],cal_episode_seed_range=[113200,113208],qual_episode_seed_range=[113300,113326],
        reserved_episode_seed_ranges=[[113009,113049],[113077,113099],[113127,113199],[113209,113299],[113327,113999]],
        changed_operator_namespace_base=2026103000,noise_namespace_base=2026103010,packet_namespace_base=2026103020,bootstrap_seed=2026103060)

def config():
    ll={s:limits(s) for s in SPLITS}
    return dict(protocol='GRAYBOX_RESPONSE_V1',classification='STANDARD_JOINT_STATE_PARAMETER_OBSERVER_REFERENCE_NOT_NEW_ACQUISITION_ALGORITHM',
        populations={s:population(s) for s in SPLITS},limits=ll,combined_limits={k:sum(x[k] for x in ll.values()) for k in next(iter(ll.values()))},
        noise_sigma=.05,one_controlled_initial_reset=True,physical_state_RNG_and_clock_continuous=True,full_task_tail_evaluated=False,
        actor='UNCHANGED_RAW_PI_T0.5_OPTIONAL_LOCAL_PID_COMMON8_KNOWN16',nominal_actor='KNOWN_IDENTITY_CHANNEL_RADEMACHER_XY0.4_80_NO_POLICY',
        models=['ZERO','INSTANT','FIR','RLS_ARX','GRAY_FIXED','GRAY_JOINT'],cal_candidates=['GRAY_Q0','GRAY_Q1','GRAY_Q2'],q_choices=list(Q_CHOICES),
        selected_model='GRAY_JOINT',nominal_grid=dict(rho=[0.,.5,.9],kappa=[.05,.2,.8],observation_variance=1e-6,acceleration_variance=6.25e-8),
        nominal_gate=dict(all27_registered_including_short=True,minimum40step_traces_per_task=6,
            grid_uses_all_nonempty_actual_traces=True,RLS_uses_all_traces_with_at_least3_steps=True,missing_reasons_retained=True),
        training_gate=dict(all9_groups_have_complete_family=True,minimum_complete_families_per_task=12,minimum_available_groups_per_task=3),
        fit_budget=dict(nominal_grid_candidate_passes=27,nominal_axis_choices=6,primary_ridge_systems=9,independent_augmented_LS=9,
            independent_nominal_grid_candidate_passes=27,independent_RLS_replay_linear_solves_max=288,neural_updates=0,legacy_C4_C8_fits=0),
        RLS=dict(features='CURRENT_XY_PREVIOUS_XY_TWO_REAL_DISPLACEMENTS_XY_INTERCEPT',unit=.01,forgetting=.98,ridge=.001),
        calibration='MIN_EXACT_COMPLETE_ALLOCATION_EQUAL_GROUP_ENDPOINT_LOSS_H8_H16_AMONG3_Q_STABLE_INDEX_TIES_ZERO_INVALID_BEFORE_QUAL_NO_OTHER_SELECTION',
        qualification=dict(co_primary=['ZERO','INSTANT','FIR','RLS_ARX','GRAY_FIXED'],all5_group_bootstrap95_upper_negative=True,
            all_task_H8_H16_points_below_all=True,all9_groups_have_complete_family=True,minimum_complete_pairs_per_task_context_anchor=3,
            zero_invalid_candidate_forecasts=True,unavailable_invalid_or_short_endpoint_loss_m=1.,loss_cap_m=1.,unit_nm=1,bootstrap_replicates=10000,bootstrap_seed=2026103060),
        no_true_fault_noise_private_state_training_inputs_or_labels=True,no_future_outcome_inputs=True,no_old_population_fitting=True,
        online_LLM_API_calls=0,new_model_used_for_control=False,publication_goal_complete=False)

def seed_scope():
    from src.analysis.episode_seed_inventory_v2 import discover,scan,verify_unchanged
    from src.analysis.episode_seed_inventory_audit_v2 import audit
    owned={p.resolve() for p in (CONFIG,PROTOCOL,SEEDS)};paths=[p for p in discover(ROOT) if p.resolve() not in owned]
    result=scan(ROOT,113000,113999,paths);verify_unchanged(ROOT,result);independent=audit(ROOT,result)
    io.require(result['status']=='NO_REGISTERED_COLLISION','new used/reserved seed conflict or undecidable metadata')
    required={p.relative_to(ROOT).as_posix() for p in paths};io.require(required<=set(result['sources']),'complete explicit external source discovery')
    return dict(integrity='PASSED_NO_REGISTERED_COLLISION',inventory=result,independent_audit=independent,
        exact_self_registration_exclusions={p.relative_to(ROOT).as_posix():io.sha(p) for p in sorted(owned)},
        exclusions_owner='THIS_CURRENT_GRAYBOX_PROTOCOL_ONLY_NO_FOLDER_EXCLUSION',seed_reservation_created_by_query=False)

def checked(path):
    path=Path(path).resolve();m=io.read(path);v=dict(m);mid=v.pop('manifest_id')
    io.require(path.parent.parent==OUTPUT and mid==io.digest(v) and m['config']==config() and io.read(CONFIG)==config() and io.read(SEEDS)==registry(),'immutable graybox manifest/config/registry')
    for n,h in {**m['source_sha256'],**m['input_sha256']}.items():io.require(io.sha(ROOT/n)==h,'immutable graybox input '+n)
    return m

def phase_model(path,split):
    if split not in ('CAL','QUAL'):return None,None
    root=Path(path).parent;bank=deepcopy(io.read(root/'training/models.json')['bank'])
    if split=='QUAL':bank['selected_q_index']=io.read(root/'model_lock.json')['selected_q_index']
    return bank,io.digest(bank)

def phase_gate(path,split):
    m=checked(path);root=Path(path).parent;io.require(split in SPLITS,'registered phase')
    if split in ('NOMINAL','TRAIN'):io.require(io.read(root/'software/audit.json')['software_contract']=='PASSED','native software gate')
    if split=='TRAIN':io.require(io.read(root/'nominal/audit.json')['integrity']=='PASSED' and io.read(root/'nominal/audit.json')['nominal_contract']=='PASSED','audited sufficient complete nominal source')
    if split in ('CAL','QUAL'):
        v=io.read(root/'training/audit.json');io.require(v['integrity']=='PASSED' and v['models_sha256']==io.sha(root/'training/models.json'),'audited frozen learned bank')
    if split=='QUAL':
        lock=io.read(root/'model_lock.json');io.require(lock['status']=='FROZEN_BEFORE_QUAL','locked calibration choice')
        for n,h in lock['artifact_sha256'].items():io.require(io.sha(root/n)==h,'immutable locked artifact '+n)
    return m

def prepare(sources):
    frozen=io.read(VALIDATION/'complete.json');io.require(frozen['integrity']=='PASSED' and not io.git('status','--porcelain','--untracked-files=no'),'committed checked collector freeze')
    io.require(not list(OUTPUT.glob('*/manifest.json')) and io.read(CONFIG)==config() and io.read(SEEDS)==registry(),'one frozen physical population')
    io.require(shutil.disk_usage(ROOT).free>=4*1024**3,'four GiB available before sampling')
    tracked=set(io.git('ls-files').splitlines())
    for n,h in frozen['source_sha256'].items():io.require(n in tracked and io.sha(ROOT/n)==h,'frozen checked tracked source '+n)
    scope=seed_scope();head=io.git('rev-parse','HEAD');runtime=ROOT/'outputs/correction_scope/freeze_validation_v1/runtime_lock.json'
    from src.analysis.response_action_io_v1 import verify_runtime
    verify_runtime(io.read(runtime));m=dict(experiment_run_id='graybox_response_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+head[:12],source_git_commit=head,
        config=config(),source_sha256={n:io.sha(ROOT/n) for n in sources},input_sha256={runtime.relative_to(ROOT).as_posix():io.sha(runtime)},publication_goal_complete=False)
    m['manifest_id']=io.digest(m);out=OUTPUT/m['experiment_run_id'];out.mkdir(parents=True,exist_ok=False);io.write(out/'manifest.json',m);io.write(out/'seed_scope.json',scope);return out/'manifest.json'

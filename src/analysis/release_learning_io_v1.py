"""Fresh, disjoint physical/learning allocation; no oracle data for the actor."""
from functools import lru_cache
from pathlib import Path
from datetime import datetime,timezone
import shutil
import numpy as np
from src.analysis import response_qualification_io_v1 as io
from src.analysis.memory_reset_seed_scope_v1 import inventory
from src.probe import release_learning_programs_v1 as p
ROOT=io.ROOT;BASE=ROOT/'outputs/information_release_learning';OUTPUT=BASE/'development_v1';VALIDATION=BASE/'validation_v1'
CONFIG=ROOT/'configs/movement_task/information_release_learning_v1.json'
PROTOCOL=ROOT/'docs/protocols/release_learning_closed_draft_v1_zh.md'
SEEDS=BASE/'design_v1/closed_seed_plan.json'
COHORTS=('SOFTWARE_NATIVE','TAIL_TRAIN','TAIL_SELECT','GATE_TRAIN','CAL','DEV','QUAL')
GROUPS=dict(zip(COHORTS,(3,18,9,18,9,9,18)))
STARTS=dict(zip(COHORTS,(74000,74100,74200,74300,74400,74500,74600)))
KEYS=('cohort','group','task','seed','context','planned_boundary','program')
IDENTITY=('experiment_run_id','manifest_id','source_git_commit')
GRID=tuple((w,r) for w in (.5,1.,2.) for r in (.001,.01,.1))
PRIMARY=('RAW','DIRECT_C8','MOVE_INTEGRAL','DIRECT_RISK','TRAIN_BEST_PROGRAM','REFERENCE_NO_PROBE','FORCE_MASKED','RELEASE_ALWAYS')


def programs(cohort):
    io.require(cohort in COHORTS,'registered cohort')
    return p.NATIVE if cohort=='SOFTWARE_NATIVE' else p.TAIL if cohort.startswith('TAIL_') else p.GATE if cohort=='GATE_TRAIN' else p.CAL if cohort=='CAL' else p.EVALUATION


@lru_cache(None)
def population(cohort):
    io.require(cohort in COHORTS,'registered immutable population')
    return tuple(dict(cohort=cohort,group=g,task=t,seed=STARTS[cohort]+3*g+i,context=c,planned_boundary=(16,32,64)[g%3],program=program)
        for g in range(GROUPS[cohort]) for i,t in enumerate(io.TASKS) for c in ('UNCHANGED','CHANGED') for program in programs(cohort))


def validate_spec(spec):io.require(spec in population(spec.get('cohort')),'strict frozen execution allocation')


def limits(cohort):
    n=len(population(cohort));fits=4*GROUPS[cohort]*6 if cohort in ('DEV','QUAL') else 0
    return dict(executions=n,control_steps=500*n,controlled_resets=n,factory_resets=50*n,all_resets=51*n,
        physical_frames=28000*n,c4_c8_fit_attempts=fits,audit_c4_c8_refits=fits)


def namespace(spec):return 2026102362+100*COHORTS.index(spec['cohort'])
def exposure_seed(spec):return [spec['seed'],2026102363+100*COHORTS.index(spec['cohort']),programs(spec['cohort']).index(spec['program'])]
def initial_fault():return dict(matrix_xy=[[1.,0.],[0.,1.]],bias_xy=[.12,-.08],deadzone_xy=[0.,0.])


def destination(spec):
    validate_spec(spec)
    if spec['context']=='UNCHANGED':return initial_fault()
    rng=np.random.default_rng(np.random.SeedSequence([2026102361+100*COHORTS.index(spec['cohort']),spec['group']]))
    return dict(matrix_xy=[[float(rng.uniform(.75,1.25)),float(rng.uniform(-.2,.2))],[float(rng.uniform(-.2,.2)),float(rng.uniform(.75,1.25))]],
        bias_xy=rng.uniform(-.2,.2,2).tolist(),deadzone_xy=[0.,0.])


def noise(spec):
    r=np.random.default_rng(int(np.random.SeedSequence([spec['seed'],namespace(spec)]).generate_state(1)[0]))
    value=r.normal(0,.05,(500,3)).astype('<f4');value.flags.writeable=False;return value


def registry():return dict(protocol='INFORMATION_RELEASE_LEARNING_V1',episode_seed_ranges={c:[STARTS[c],STARTS[c]+3*GROUPS[c]-1] for c in COHORTS},
    allocation_state='UNUSED_CLOSED_DRAFT_NOT_EXECUTED',
    reserved_episode_seed_range=[74700,77999],operator_nonce_start=2026102361,noise_namespace_start=2026102362,exposure_nonce_start=2026102363,
    bootstrap_seed=2026102370)


def source_models():
    io.require(io.sha(ROOT/io.C8)==io.C8_SHA,'unchanged frozen C8 source');return io.read(ROOT/io.C8)['joint'],{io.C8:io.C8_SHA}


def config():
    return dict(protocol='INFORMATION_RELEASE_LEARNING_V1',classification='FRESH_LEARNED_MECHANISM_DEVELOPMENT_AND_CONDITIONAL_OWN_HISTORY_QUAL',
        collection_status='CLOSED_BEFORE_COLLECTION',algorithm_distinction='FAILED_STANDARD_DR_HEAD_REPARAMETERIZATION',
        groups=GROUPS,programs={c:list(programs(c)) for c in COHORTS},limits={c:limits(c) for c in COHORTS},
        combined_limits={k:sum(limits(c)[k] for c in COHORTS) for k in limits('DEV')},noise_sigma=.05,control_period_s=.0125,per_execution_steps=500,
        source_prefix='RAW_PI_T0.5; legacy C8/INTEGRAL have their original independent C8 prefix',
        common_information='same entire public prefix, endpoint, task memory, elapsed cost, phase counts, exit reason; no release bit as a feature',
        post_features=dict(common=159,full=213),pre_features=93,predicted_risk_decimal_places=6,
        group_weight='each eligible independent group equal; each factual execution equal within group',
        receiver=dict(width_ridge_grid=GRID,centers=64,common_models_per_setting=4,matched_common_residual_models_per_setting=4,signal_residual_models_per_setting=4,
            main_closed_form_fits=108,independent_refits=108,capacity='same shared base plus one64-center residual in either nonempty view; common residual uses same factual rows',
            selection='whole TAIL_SELECT paired-view factual prediction MSE; first grid index within1e-6 of minimum',selection_tolerance=1e-6),
        precritic=dict(width_ridge_grid=GRID,centers=32,main_closed_form_fits=90,independent_refits=90,
            nuisance='fixed TAIL-only receiver risks; GATE groups excluded by construction; no GATE nuisance fitting',
            effect_targets='standard AIPW M,D signed and unclipped; known terminal/empty structural equality',
            direct_control='same GATE factual Y, same public H, same RBF capacity and CAL selection budget'),
        release=dict(probability=.5,host_rng='PCG64 separate private namespace; consume once after durable SIGNAL_SEAL; never before acquisition',
            case_failure='stop scientific phase and retain incomplete run; no recollection, unseen-data tuning or population extension'),
        CAL='five actually executed complete arms; bank recommendations saved before CAL outcomes; selection is evaluator-only, not final deployment',
        primary_comparators=PRIMARY,
        DEV_gate='full-population mean LEARNED_EFFECT strictly below all eight primary comparators and no greater than every other registered comparator; actual use of both nonempty exposure choices and different executed post-gains needed',
        QUAL_gate='same eight full-population paired loss contrasts; all one-sided whole-group stratified bootstrap upper quantile159/160 strictly below0; no secondary replacement, no worse full-population mean than other registered controls',
        bootstrap=dict(replicates=10000,seed=2026102370,unit='whole independent group, stratified by16/32/64',upper_quantile=[159,160],nominal_familywise_alpha=.05),
        primary_loss='actual full control steps if success, otherwise500, all acquisition included exactly once',
        success='fully disclose every paired change, no hidden noninferiority threshold',new_response_model_training=0,new_low_level_policy_training=0,
        new_online_LLM_API_calls=0,publication_goal_complete=False,novelty_established=False,no_physical_safety_guarantee=True)


def checked(path):
    path=Path(path).resolve();m=io.read(path);body=dict(m);mid=body.pop('manifest_id')
    io.require(path.name=='manifest.json' and path.parent.parent==OUTPUT.resolve() and io.digest(body)==mid and m['config']==config(),'owned immutable study manifest')
    for n,h in {**m['source_sha256'],**m['model_input_sha256']}.items():io.require(io.sha(ROOT/n)==h,'frozen study input changed '+n)
    return m


def prepare():
    io.require(config()['collection_status']=='AUTHORIZED_FROZEN_COLLECTION','Closed draft: M/D ridge heads are a standard DR program-risk reparameterization; a distinct mechanism and new protocol are required')
    qa=io.read(VALIDATION/'complete.json');io.require(qa['integrity']=='PASSED' and not io.git('status','--porcelain','--untracked-files=no'),'clean checked source freeze')
    io.require(not list(OUTPUT.glob('*/manifest.json')) and io.read(CONFIG)==config() and io.read(SEEDS)==registry(),'one new registered population')
    for n,h in qa['source_sha256'].items():io.require(io.sha(ROOT/n)==h,'tested source changed '+n)
    from src.analysis.response_action_io_v1 import verify_runtime
    verify_runtime(io.read(VALIDATION/'runtime_lock.json'));io.require(shutil.disk_usage(ROOT).free>=6*1024**3,'six GiB storage reserve')
    own={p.relative_to(ROOT).as_posix() for p in (CONFIG,PROTOCOL,SEEDS)}
    scope=inventory(ROOT,own,74000,77999);_,inputs=source_models();head=io.git('rev-parse','HEAD')
    names=set(io.git('ls-files','src','scripts','tests').splitlines())|own|{(VALIDATION/'complete.json').relative_to(ROOT).as_posix(),(VALIDATION/'runtime_lock.json').relative_to(ROOT).as_posix()}
    m=dict(experiment_run_id='release_learning_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+head[:12],source_git_commit=head,
        config=config(),source_sha256={n:io.sha(ROOT/n) for n in sorted(names)},model_input_sha256=inputs,publication_goal_complete=False)
    m['manifest_id']=io.digest(m);out=OUTPUT/m['experiment_run_id'];out.mkdir(parents=True,exist_ok=False)
    io.write(out/'manifest.json',m);io.write(out/'seed_scope.json',scope);return out/'manifest.json'


def phase_gate(path,cohort):
    io.require(config()['collection_status']=='AUTHORIZED_FROZEN_COLLECTION','This draft was rejected before any physical collection; do not bypass the research distinction gate')
    m=checked(path);root=Path(path).parent;io.require(cohort in COHORTS,'registered sequential cohort')
    if cohort!='SOFTWARE_NATIVE':
        previous=COHORTS[COHORTS.index(cohort)-1];r=io.read(root/previous.lower()/'audit.json')
        io.require(r['integrity']=='PASSED','previous complete record audit')
    if cohort=='TAIL_TRAIN':io.require(io.read(root/'software_native/audit.json')['native_software_contract']=='PASSED','complete native software gate')
    if cohort=='TAIL_SELECT':
        r=io.read(root/'models/receiver_bank_audit.json');io.require(r['integrity']=='PASSED' and r['source_bank_sha256']==io.sha(root/'models/receiver_bank.json'),'TRAIN-only bank frozen before SELECT outcomes')
    if cohort in ('GATE_TRAIN','CAL','DEV','QUAL'):
        r=io.read(root/'models/receiver_audit.json');io.require(r['integrity']=='PASSED' and r['receiver_artifact_sha256']==io.sha(root/'models/receiver_freeze.json'),'fixed receiver audited before new outcomes')
    if cohort in ('CAL','DEV','QUAL'):
        r=io.read(root/'models/pre_bank_audit.json');io.require(r['integrity']=='PASSED' and r['source_bank_sha256']==io.sha(root/'models/pre_bank.json'),'pre-risk banks audited before calibration')
    if cohort in ('DEV','QUAL'):
        r=io.read(root/'models/policy_lock_audit.json');io.require(r['integrity']=='PASSED' and r['policy_lock_sha256']==io.sha(root/'models/policy_lock.json'),'independently audited policy lock before own-history deployment')
    if cohort=='QUAL':
        r=io.read(root/'dev/statistics_audit.json');io.require(r['integrity']=='PASSED' and r['DEV_gate']=='PASSED'
            and r['statistics_sha256']==io.sha(root/'dev/statistics.json'),'strict complete independently audited DEV gate; negative stops this version')
    io.require(shutil.disk_usage(ROOT).free>=4*1024**3,'four GiB collection storage reserve');return m

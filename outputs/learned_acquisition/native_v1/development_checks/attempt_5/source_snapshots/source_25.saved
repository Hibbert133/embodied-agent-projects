"""Independent A1 allocation, immutable sources and real full-cost budgets."""
from pathlib import Path
from datetime import datetime,timezone
import shutil
import numpy as np
from src.analysis import response_qualification_io_v1 as io
from src.analysis.memory_reset_seed_scope_v1 import inventory
from src.probe.correction_scope_model_v1 import ACTIONS,RATES,TASKS,KINDS
ROOT=io.ROOT
BASE=ROOT/'outputs/correction_scope'
OUTPUT=BASE/'development_v1'
VALIDATION=BASE/'freeze_validation_v1'
CONFIG=ROOT/'configs/movement_task/correction_scope_development_v1.json'
PROTOCOL=ROOT/'docs/protocols/correction_scope_development_v1_zh.md'
SEEDS=ROOT/'docs/protocols/correction_scope_seeds_v1.json'
COHORTS=('NATIVE','TRAIN','CAL','TEST')
KEYS=('cohort','group','task','seed','context','planned_boundary','acquisition_action','time_constant_s')
IDENTITY=('experiment_run_id','manifest_id','source_git_commit')


def population(cohort):
    io.require(cohort in COHORTS,'registered A1 split')
    groups,start={'NATIVE':(3,80000),'TRAIN':(9,80100),'CAL':(3,80200),'TEST':(9,80300)}[cohort]
    rates=(.125,8.) if cohort=='NATIVE' else RATES
    return [dict(cohort=cohort,group=g,task=t,seed=start+3*g+i,context=c,planned_boundary=(16,32,64)[g%3],acquisition_action=a,time_constant_s=r)
        for g in range(groups) for i,t in enumerate(TASKS) for c in ('UNCHANGED','CHANGED') for a in ACTIONS for r in rates]


def validate_spec(spec):io.require(type(spec) is dict and set(spec)==set(KEYS) and spec in population(spec.get('cohort')),'unregistered factual A1 execution')
def case_key(spec):return tuple(spec[k] for k in KEYS)
def unit_key(spec):return tuple(spec[k] for k in ('cohort','group','task','context'))


def limits(cohort):
    n=len(population(cohort))
    return dict(executions=n,control_steps=500*n,controlled_resets=n,all_resets=51*n,physical_frames=28000*n,
        initial_C4_C8_fits=0,new_response_fits=0,new_policy_training=0,online_LLM_API_calls=0)


def registry():return dict(protocol='CORRECTION_SCOPE_DEVELOPMENT_V1',
    native_episode_seed_range=[80000,80008],TRAIN_episode_seed_range=[80100,80126],
    CAL_episode_seed_range=[80200,80208],TEST_episode_seed_range=[80300,80326],
    reserved_episode_seed_ranges=[[80009,80099],[80127,80199],[80209,80299],[80327,80999]],
    operator_nonce=202610261,noise_namespace=202610262,bootstrap_seed=202610263)


def initial_fault():return dict(matrix_xy=[[1.,0.],[0.,1.]],bias_xy=[.12,-.08],deadzone_xy=[0.,0.])


def destination(spec):
    validate_spec(spec)
    if spec['context']=='UNCHANGED':return initial_fault()
    ordinal=COHORTS.index(spec['cohort']);r=np.random.default_rng(np.random.SeedSequence([202610261,ordinal,spec['group']]))
    return dict(matrix_xy=[[float(r.uniform(.75,1.25)),float(r.uniform(-.2,.2))],
        [float(r.uniform(-.2,.2)),float(r.uniform(.75,1.25))]],bias_xy=r.uniform(-.2,.2,2).tolist(),deadzone_xy=[0.,0.])


def noise(spec):
    v=np.random.default_rng(np.random.SeedSequence([spec['seed'],202610262])).normal(0,.05,(500,3)).astype('<f4')
    v.flags.writeable=False;return v


def config():
    total={k:sum(limits(c)[k] for c in COHORTS) for k in ('executions','control_steps','controlled_resets','all_resets','physical_frames')}
    return dict(protocol='CORRECTION_SCOPE_DEVELOPMENT_V1',classification='A1_PREDICTIVE_SUBSTRATE_NOT_COMPLETE_ALGORITHM',
        populations={c:population(c) for c in COHORTS},limits={c:limits(c) for c in COHORTS},combined_limits=total,
        controller='Fixed policy, RAW task PI0.5 common prefix, carry integral, change rate only after actual acquisition',
        working_forward_model='Observed XY displacement prediction .01*sent XY; deliberately explicit unqualified working model, no inverse',
        noise_sigma=.05,physical_period_s=.0125,per_execution_steps=500,
        targets='Executed successor query histogram and error-weighted histogram over first8/32 tail steps, mean squared working-model error, observed fraction, actual return memory',
        query_bins='Four XY command sign quadrants x three max-absolute XY amplitude levels x public object-hand distance <=0.1m proxy',
        short_windows='Normalize by actual executed length, save actual count; no padding or invented trajectories',
        models=list(KINDS),ridge=.01,rbf_centers_max=64,normalization_floor=.05,
        learning_budget=dict(multitarget_ridge_fits=8,independent_multitarget_lstsq_refits=8,
            neural_updates=0,response_model_training=0,low_level_policy_training=0),
        calibration='Per stage/kind/family90% empirical absolute prediction-error radius on separate CAL, no model or threshold selection',
        primary_gate=dict(stage='PRE',horizon=32,model='FULL_RBF',families=['occupancy_32','error_32','joint_32'],
            comparators=['PERSISTENCE','COMMAND_RBF','RATE_BLIND_RBF','FULL_LINEAR'],
            group_bootstrap_CI95_upper_strictly_below_zero_for_all=True,
            joint_also_better_than_same_model_marginal_product=True,
            all_task_context_boundary_panels_have_factual_targets=True,
            no_secondary_substitution=True),
        bootstrap=dict(replicates=10000,seed=202610263,unit='Whole independent group, stratified by boundary; all six task/context units and arms remain together'),
        complete_task_loss='Actual total control steps on success,500 on failure; acquisition already included once',
        failure='One native/train/cal/test allocation only; software/integrity error stops, partial records retained, no retry/replacement/extension/tuning',
        new_online_LLM_API_calls=0,old_QUAL_tuning=False,task_gain_qualified=False,algorithm_novelty_established=False,publication_goal_complete=False)


def seed_scope():return inventory(ROOT,{p.relative_to(ROOT).as_posix() for p in (CONFIG,PROTOCOL,SEEDS)},80000,80999)


def checked(path):
    path=Path(path).resolve();m=io.read(path);v=dict(m);mid=v.pop('manifest_id')
    io.require(path.name=='manifest.json' and path.parent.parent==OUTPUT.resolve() and io.digest(v)==mid and m['config']==config(),'frozen A1 manifest ownership')
    for n,h in m['source_sha256'].items():io.require(io.sha(ROOT/n)==h,'frozen source changed '+n)
    return m


def prepare():
    q=io.read(VALIDATION/'complete.json');io.require(q['integrity']=='PASSED' and not io.git('status','--porcelain','--untracked-files=no'),'clean verified A1 freeze')
    io.require(io.read(CONFIG)==config() and io.read(SEEDS)==registry() and not list(OUTPUT.glob('*/manifest.json')),'one exact new A1 allocation')
    for n,h in q['source_sha256'].items():io.require(io.sha(ROOT/n)==h and io.git('ls-files','--error-unmatch',n)==n,'committed verified source')
    from src.analysis.response_action_io_v1 import verify_runtime
    verify_runtime(io.read(VALIDATION/'runtime_lock.json'));io.require(shutil.disk_usage(ROOT).free>=4*1024**3,'four GiB initial storage reserve')
    scope=seed_scope();head=io.git('rev-parse','HEAD')
    names=set(io.git('ls-files','src','scripts','tests').splitlines())|set(q['source_sha256'])
    names|={p.relative_to(ROOT).as_posix() for p in (CONFIG,PROTOCOL,SEEDS,VALIDATION/'complete.json',VALIDATION/'runtime_lock.json')}
    m=dict(experiment_run_id='correction_scope_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+head[:12],
        source_git_commit=head,source_sha256={n:io.sha(ROOT/n) for n in sorted(names)},config=config(),online_LLM_API_calls=0)
    m['manifest_id']=io.digest(m);out=OUTPUT/m['experiment_run_id'];out.mkdir(parents=True,exist_ok=False)
    io.write(out/'manifest.json',m);io.write(out/'seed_scope.json',scope);return out/'manifest.json'


def phase_gate(path,cohort):
    m=checked(path);io.require(cohort in COHORTS,'registered phase')
    if cohort!='NATIVE':
        previous={'TRAIN':'native','CAL':'train','TEST':'cal'}[cohort]
        audit=io.read(Path(path).parent/previous/'audit.json');io.require(audit['integrity']=='PASSED','previous complete audit required')
    if cohort in ('CAL','TEST'):
        audit=io.read(Path(path).parent/'learning/model_audit.json');io.require(audit['integrity']=='PASSED','independent frozen model audit required')
        io.require(io.sha(Path(path).parent/'learning/bank.json')==audit['bank_sha256'],'bank changed after independent audit')
    if cohort=='TEST':
        cal=io.read(Path(path).parent/'learning/calibration.json');io.require(cal['integrity']=='PASSED','separate CAL required')
        io.require(cal['bank_sha256']==io.sha(Path(path).parent/'learning/bank.json'),'CAL bank changed')
    io.require(shutil.disk_usage(ROOT).free>=2*1024**3,'two GiB phase storage reserve');return m

"""Freeze-bound constructed verification, with no native collection or fitting."""
from pathlib import Path
from datetime import datetime,timezone
from time import perf_counter_ns
from contextlib import ExitStack
from unittest.mock import patch
import argparse,inspect,sys,traceback
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis import response_qualification_io_v1 as io
from scripts.run_latent_response_v1 import readonly_guard
ROOT=io.ROOT;BASE=ROOT/'outputs/information_release';OUTPUT=BASE/'reference_v1';VALIDATION=BASE/'validation_v1'
CONFIG='configs/movement_task/information_release_prototype_v1.json'
PROTOCOL='docs/protocols/information_release_prototype_v1_zh.md'
DESIGN='docs/research/information_release_mechanism_v1_zh.md'
PRIOR='docs/research/information_release_prior_art_v1_zh.md'
OWN=('src/probe/information_release_v1.py','src/probe/information_release_features_v1.py','src/probe/information_release_acquisition_v1.py',
    'src/analysis/information_release_targets_v1.py','src/analysis/information_release_census_v1.py',
    'src/analysis/information_release_independent_audit_v1.py','scripts/verify_information_release_v1.py','tests/test_information_release_v1.py')


def config():return dict(protocol='INFORMATION_RELEASE_PROTOTYPE_V1',classification='CONSTRUCTED_SOFTWARE_VERIFICATION_NOT_ROBOT_EXPERIMENT',
    acquisition_actions=['CONTINUE','VALIDATE8','MOVE_MEASURE'],rates_s=[.125,.5,2.,8.],integral='CARRY_UNCHANGED_AT_RATE_CHANGE',
    common='REAL_BEFORE_AND_RETURN_MEMORY_ENDPOINTS_COST_DURATION_PHASES_REASON',signal='SUPPLEMENTAL_ACTUAL_TRACE_ONLY',
    empty_signal='IDENTICAL_MODEL_VIEWS_NO_EXPOSURE_BIT',prototype_cases=18,prototype_release_views=36,algebra_settings=36,algebra_assignment_rows=72,
    raw_policy='FIXED_UNMODIFIED',feature_shapes=dict(common=[123],trace=[72,86],trace_mask=[72]),
    new_environment_steps=0,new_all_resets=0,new_physical_frames=0,new_scientific_model_fits=0,new_online_LLM_API_calls=0,
    new_episode_seed_allocations=0,physical_randomization_authenticated=False,receiver_trained=False,precritic_trained=False,
    novelty_established=False,robot_benefit_established=False,publication_goal_complete=False)


def prepare():
    io.require(io.git('branch','--show-current')=='codex/information-release-mechanism-v1' and not io.git('status','--porcelain','--untracked-files=no'),'committed clean prototype freeze')
    io.require(not list(OUTPUT.glob('*/manifest.json')),'one constructed verification after freeze')
    qa=io.read(VALIDATION/'complete.json');io.require(qa['integrity']=='PASSED' and io.read(ROOT/CONFIG)==config(),'checked exact prototype')
    for n,h in qa['source_sha256'].items():io.require(io.sha(ROOT/n)==h,'validated source changed '+n)
    names=set(io.git('ls-files','src','scripts','tests').splitlines())|set(OWN)|{CONFIG,PROTOCOL,DESIGN,PRIOR}
    names|={(VALIDATION/'complete.json').relative_to(ROOT).as_posix()}
    head=io.git('rev-parse','HEAD');m=dict(source_git_commit=head,config=config(),source_sha256={n:io.sha(ROOT/n) for n in sorted(names)},
        experiment_run_id='information_release_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+head[:12],
        old_parent_commit='742ac1832e78076485966b16903486ac878143fe',publication_goal_complete=False)
    m['manifest_id']=io.digest(m);out=OUTPUT/m['experiment_run_id'];out.mkdir(parents=True,exist_ok=False);io.write(out/'manifest.json',m)
    return out/'manifest.json'


def checked(path):
    path=Path(path).resolve();m=io.read(path);body=dict(m);mid=body.pop('manifest_id')
    io.require(path.name=='manifest.json' and path.parent.parent==OUTPUT.resolve() and io.digest(body)==mid and m['config']==config(),'owned versioned constructed manifest')
    for n,h in m['source_sha256'].items():io.require(io.sha(ROOT/n)==h,'frozen source changed '+n)
    return m


def execute(phase,path):
    m=checked(path);out=Path(path).parent;receipt={};start=perf_counter_ns()
    identity={k:m[k] for k in ('experiment_run_id','manifest_id','source_git_commit')}
    try:
        with readonly_guard(receipt):
            if phase=='run':
                from src.analysis.information_release_census_v1 import save
                result=save(out/'constructed_records.json')
            else:
                from src.analysis.information_release_independent_audit_v1 import audit_file
                from src.probe import information_release_v1,information_release_features_v1,information_release_acquisition_v1
                from src.analysis import information_release_targets_v1,information_release_census_v1
                disabled=[]
                def deny(*args,**kw):raise RuntimeError('Main signal-release generation/math disabled during independent audit')
                with ExitStack() as stack:
                    for module in (information_release_v1,information_release_features_v1,information_release_acquisition_v1,information_release_targets_v1,information_release_census_v1):
                        for name,fn in inspect.getmembers(module,inspect.isfunction):
                            if fn.__module__==module.__name__:stack.enter_context(patch.object(module,name,deny));disabled.append(module.__name__+'.'+name)
                    result=audit_file(out/'constructed_records.json')
                result['main_functions_disabled']=disabled
        io.require(not any(receipt['blocked_operations'].values()) and receipt['network']=={'attempted_network_calls':0},'strict zero new interaction/fit/network')
        result.update(identity);result.update(integrity='PASSED',analysis_wall_ns=perf_counter_ns()-start)
        if phase=='audit':result['constructed_records_sha256']=io.sha(out/'constructed_records.json')
        io.write(out/(phase+'_receipt.json'),result);return result
    except Exception:
        io.write(out/(phase+'_failure.json'),dict(**identity,traceback=traceback.format_exc(),analysis_wall_ns=perf_counter_ns()-start));raise
    finally:io.write(out/(phase+'_guard.json'),receipt)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=('prepare','run','audit'));p.add_argument('--manifest',type=Path);args=p.parse_args()
    if args.phase=='prepare':print(prepare(),flush=True)
    else:
        io.require(args.manifest is not None,'frozen manifest required');print(execute(args.phase,args.manifest),flush=True)

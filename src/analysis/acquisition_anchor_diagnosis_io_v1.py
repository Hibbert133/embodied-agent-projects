"""Immutable old native population for post-hoc zero-interaction diagnostics."""
from pathlib import Path
from datetime import datetime,timezone
from src.analysis import response_qualification_io_v1 as io
ROOT=io.ROOT
SOURCE=ROOT/'outputs/memory_acquisition/qualification_v1/memory_acquisition_20261022T112439Z_1d658fea08fc'
BASE=ROOT/'outputs/acquisition_anchor_diagnosis'
CONFIG=ROOT/'configs/movement_task/acquisition_anchor_diagnosis_v1.json'
PROTOCOL=ROOT/'docs/protocols/acquisition_anchor_diagnosis_v1_zh.md'
OWN=('src/analysis/acquisition_anchor_diagnosis_io_v1.py','src/analysis/acquisition_anchor_diagnosis_v1.py',
    'src/analysis/acquisition_anchor_diagnosis_audit_v1.py','scripts/analyze_acquisition_anchor_v1.py',
    'scripts/audit_acquisition_anchor_v1.py','scripts/report_acquisition_anchor_v1.py','scripts/figure_acquisition_anchor_v1.py',
    'tests/test_acquisition_anchor_diagnosis_v1.py')


def config():return {'protocol':'POST_HOC_ACQUISITION_ANCHOR_DIAGNOSIS_V1','source_result_commit':'49fc002fa41cb0f2e4cb80e3e2f2bf45d283d74e',
    'source_executions':54,'source_steps':8836,'assigned_move_cases':18,'source_task_failures':8,
    'step_bins':[[1,8],[9,16],[17,32],[33,64]],'late_actual_relocation_steps':8,
    'required_strata':'All three tasks, both contexts, all three boundary groups and all assigned actions',
    'aggregation':'Within-trajectory first; whole group means, no timestep-as-independent inference',
    'command_balance':'Evaluator-only e=-M^-1*b/8 for identity correction, zero deadzone, zero measured motion, unclipped input; not physical equilibrium',
    'new_environment_steps':0,'new_resets':0,'new_physical_frames':0,'new_model_fits':0,'new_online_LLM_API_calls':0,
    'threshold_or_control_tuning':False,'new_task_seed_allocation':None,'publication_goal_complete':False}


def sources():
    from src.analysis.memory_acquisition_io_v1 import checked
    checked(SOURCE/'manifest.json');out=SOURCE/'native';a=io.read(out/'audit.json');c=io.read(out/'completion.json');closure=io.read(out/'closure.json')
    io.require(a['integrity']=='PASSED' and a['native_software_contract']=='PASSED' and a['collection_completion_sha256']==io.sha(out/'completion.json'),'audited complete source')
    for n,h in c['artifact_sha256'].items():io.require(io.sha(out/n)==h,'original native artifact changed '+n)
    for n,h in closure['receipt_sha256'].items():io.require(io.sha(out/n)==h,'original result receipt changed '+n)
    names=[SOURCE/'manifest.json',SOURCE/'seed_scope.json',out/'completion.json',out/'audit.json',out/'audit_guard.json',out/'closure.json',out/'index_receipt.json']
    names += [out/n for n in c['artifact_sha256']]+[out/n for n in closure['receipt_sha256']]
    names += [ROOT/'src/probe/physical_reprobe_v1.py',ROOT/'src/probe/local_reprobe_v1.py',ROOT/'src/probe/task_memory_option_v1.py']
    return {p.relative_to(ROOT).as_posix():io.sha(p) for p in sorted(set(names))}


def checked(path):
    path=Path(path).resolve();v=io.read(path);body=dict(v);mid=body.pop('manifest_id')
    io.require(path.name=='manifest.json' and path.parent.parent==(BASE/'analysis_v1').resolve() and io.digest(body)==mid,'owned analysis manifest')
    io.require(v['config']==config() and io.read(CONFIG)==config(),'frozen posthoc scope')
    for n,h in {**v['source_sha256'],**v['analysis_source_sha256']}.items():io.require(io.sha(ROOT/n)==h,'immutable source changed '+n)
    return v


def prepare():
    qa=io.read(BASE/'validation_v1/complete.json');io.require(qa['integrity']=='PASSED','checked source required')
    io.require(not io.git('status','--porcelain','--untracked-files=no') and not list((BASE/'analysis_v1').glob('*/manifest.json')),'one clean committed analysis')
    for n,h in qa['source_sha256'].items():io.require(io.sha(ROOT/n)==h and io.git('ls-files','--error-unmatch',n)==n,'committed checked source')
    head=io.git('rev-parse','HEAD');v={'run_id':'anchor_diagnosis_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+head[:12],
        'analysis_git_commit':head,'source_sha256':sources(),'analysis_source_sha256':qa['source_sha256'],
        'config':config(),'validation_sha256':io.sha(BASE/'validation_v1/complete.json'),'classification':'POST_HOC_DESCRIPTIVE_ONLY'}
    v['manifest_id']=io.digest(v);out=BASE/'analysis_v1'/v['run_id'];out.mkdir(parents=True,exist_ok=False);io.write(out/'manifest.json',v);return out/'manifest.json'

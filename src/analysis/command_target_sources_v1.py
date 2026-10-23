"""Immutable complete source cohorts and bounded per-execution readers."""
from pathlib import Path
from datetime import datetime,timezone
import importlib.util
from src.analysis import response_qualification_io_v1 as io
ROOT=io.ROOT;BASE=ROOT/'outputs/command_target_diagnostic';OUTPUT=BASE/'analysis_v2';VALIDATION=BASE/'validation_v2'
CONFIG=ROOT/'configs/movement_task/command_target_diagnostic_reader_v2.json'
PROTOCOL=ROOT/'docs/protocols/command_target_diagnostic_reader_repair_v2_zh.md'
FAILED=BASE/'analysis_v1/command_target_20261022T163258Z_90131875242d'
RECENT=ROOT/'outputs/acquisition_reference/qualification_v1/acquisition_reference_20261022T133659Z_dc7058a8f6d5'
OLD=ROOT/'outputs/selected_response/qualification_v1/selected_response_20261019T152657Z_6db2a7662590'
IDENTITY=('experiment_run_id','manifest_id','source_git_commit')
OWN=('src/probe/nominal_command_target_v1.py','src/analysis/command_target_sources_v1.py','src/analysis/command_target_diagnostic_v1.py',
    'src/analysis/command_target_audit_v1.py','scripts/analyze_command_target_v1.py','scripts/audit_command_target_v1.py',
    'scripts/report_command_target_v1.py','tests/test_command_target_v1.py')
DEPENDENCIES=('src/analysis/response_qualification_io_v1.py','src/analysis/short_probe_journal_audit_v1.py',
    'scripts/analyze_acquisition_support_v1.py','src/analysis/paired_probe_host_v1.py',
    'docs/protocols/command_target_diagnostic_v1_zh.md','configs/movement_task/command_target_diagnostic_v1.json')


def cohorts():
    return [('OLD_NOMINAL_TRAIN',OLD/'train',OLD/'train_audit/record_audit.json',1152,75641),
        ('RECENT_SOFTWARE_NATIVE',RECENT/'software_native',RECENT/'software_native/audit.json',60,10633),
        ('RECENT_QUAL',RECENT/'qual',RECENT/'qual/audit.json',540,65854)]


def package_sources():
    package=Path(importlib.util.find_spec('metaworld').origin).parent
    files=[package/'sawyer_xyz_env.py',*(package/'envs'/f'sawyer_{task}_v3.py' for task in ('push','reach','door'))]
    files.append(ROOT/'src/analysis/paired_probe_host_v1.py')
    return {str(p.resolve()):io.sha(p) for p in files}


def source_hashes():
    result={}
    for label,folder,audit_path,n,steps in cohorts():
        audit=io.read(audit_path);io.require(audit['integrity']=='PASSED' and audit['executions']==n,'complete audited source '+label)
        key='collection_artifact_sha256' if label=='OLD_NOMINAL_TRAIN' else 'artifact_sha256'
        for name,h in audit[key].items():io.require(io.sha(folder/name)==h,'source artifact changed '+label+'/'+name);result[(folder/name).relative_to(ROOT).as_posix()]=h
        for p in (audit_path,folder/'completion.json',folder.parent/'manifest.json'):result[p.relative_to(ROOT).as_posix()]=io.sha(p)
        summary=io.read(folder/'summary.json');io.require(summary.get('completed_executions',summary.get('executions'))==n and summary.get('controlled_steps',summary.get('control_steps'))==steps,'full source counts')
    failure=io.read(FAILED/'failure.json')
    for name,h in failure['partial_artifact_sha256'].items():io.require(io.sha(FAILED/name)==h,'preserved failed partial output')
    for p in (FAILED/'manifest.json',FAILED/'failure.json',*(FAILED/n for n in failure['partial_artifact_sha256'])):result[p.relative_to(ROOT).as_posix()]=io.sha(p)
    return result


def config():return {'protocol':'COMMAND_TARGET_SOURCE_DIAGNOSTIC_V1','classification':'POST_HOC_DESCRIPTIVE_ONLY','source_executions':1752,'source_steps':152128,
    'reader_version':2,'added_legacy_raw_phases':['TASK','APPROACH'],'phase_labels_preserved_without_remapping':True,
    'failed_attempt_manifest_sha256':io.sha(FAILED/'manifest.json'),'failed_attempt_receipt_sha256':io.sha(FAILED/'failure.json'),
    'cohorts':[{ 'name':name,'executions':n,'steps':steps} for name,_,_,n,steps in cohorts()],
    'public_reference':'Declared installed reset/box/scale prior plus past sent commands, identity input,zero noise; not actual state or a distribution mean',
    'oracle_replays':'Saved applied action and true-parameter zero-noise action; evaluation only, fixed recorded commands, no new hand trajectory',
    'reset_prior':[0.,.6,.2],'workspace_lower':[-.5,.4,.05],'workspace_upper':[.5,1.,.5],'action_scale':.01,
    'measurement_canonical_program':'LOCAL_PID_KEEP','step_bins':[[1,8],[9,16],[17,32],[33,64]],
    'new_environment_creations':0,'new_resets':0,'new_environment_steps':0,'new_physical_frames':0,'new_fits':0,'new_online_LLM_API_calls':0,
    'no_threshold_model_or_old_comparison_changes':True,'no_safety_prediction_or_task_qualification':True,'publication_goal_complete':False}


class GroupedJournal:
    def __init__(self,rows,key_names,identity):self.rows=iter(rows);self.keys=key_names;self.identity=identity;self.count=0;self.stamp=-1;self.pending=None
    def _next(self):
        value=next(self.rows,None)
        if value is None:return None
        io.require(value['sequence']==self.count and value['saved_ns']>=self.stamp,'source global sequence/time')
        io.require(all(value[k]==v for k,v in self.identity.items()),'source journal identity')
        self.count+=1;self.stamp=value['saved_ns'];return value
    def take_case(self,case):
        key=tuple(case[k] for k in self.keys);first=self.pending if self.pending is not None else self._next();self.pending=None
        io.require(first is not None and tuple(first[k] for k in self.keys)==key,'missing or unordered source case')
        result=[first]
        while True:
            value=self._next()
            if value is None:break
            if tuple(value[k] for k in self.keys)!=key:self.pending=value;break
            result.append(value)
        return result
    def finish(self):io.require(self.pending is None and self._next() is None,'extra unassigned source events')


def cases(label,folder):
    summary=io.read(folder/'summary.json');identity={k:summary[k] for k in IDENTITY}
    keys=('unit','task','seed','variant') if label=='OLD_NOMINAL_TRAIN' else ('cohort','group','task','seed','context','planned_boundary','program')
    journal=GroupedJournal(io.rows(folder/'events.jsonl.gz'),keys,identity);count=steps=0
    for case in io.rows(folder/'cases.jsonl.gz'):
        chunk=journal.take_case(case);initial=[e for e in chunk if e['event']=='CONTROLLED_INITIAL'];io.require(len(initial)==1,'one actual initial observation')
        physical=[e for e in chunk if e['event']=='STEP_COMPLETE'];io.require(len(physical)==case['total_steps'],'source physical step denominator')
        if label!='OLD_NOMINAL_TRAIN':
            io.require(chunk[-1]['event']=='CASE_COMPLETE' and chunk[-1]['case_record_sha256']==io.digest(case),'source complete case digest')
        count+=1;steps+=len(physical)
        yield case,chunk,initial[0]['observation']
    journal.finish();expected=next((n,s) for name,_,_,n,s in cohorts() if name==label)
    io.require((count,steps)==expected,'complete source population was not traversed')


def checked(path):
    path=Path(path).resolve();v=io.read(path);body=dict(v);mid=body.pop('manifest_id')
    io.require(path.name=='manifest.json' and path.parent.parent==OUTPUT.resolve() and io.digest(body)==mid and v['config']==config(),'owned diagnostic manifest')
    for n,h in v['analysis_source_sha256'].items():io.require(io.sha(ROOT/n)==h,'frozen analysis source changed '+n)
    for n,h in v['input_sha256'].items():io.require(io.sha(ROOT/n)==h,'original source changed '+n)
    for n,h in v['installed_source_sha256'].items():io.require(io.sha(Path(n))==h,'installed actuator/reset source changed '+n)
    return v


def prepare():
    qa=io.read(VALIDATION/'complete.json');io.require(qa['integrity']=='PASSED' and not io.git('status','--porcelain','--untracked-files=no'),'clean checked diagnostic freeze')
    io.require(not list(OUTPUT.glob('*/manifest.json')) and io.read(CONFIG)==config(),'one complete fixed diagnostic run')
    for n,h in qa['source_sha256'].items():io.require(io.sha(ROOT/n)==h,'source-bound diagnostic checks')
    head=io.git('rev-parse','HEAD');v={'experiment_run_id':'command_target_reader_v2_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+head[:12],
        'analysis_git_commit':head,'analysis_source_sha256':qa['source_sha256'],'input_sha256':source_hashes(),'installed_source_sha256':package_sources(),
        'config':config(),'classification':'POST_HOC_SOURCE_DERIVED_REFERENCE_NOT_MEASURED_PRIVATE_STATE','publication_goal_complete':False}
    v['manifest_id']=io.digest(v);out=OUTPUT/v['experiment_run_id'];out.mkdir(parents=True,exist_ok=False);io.write(out/'manifest.json',v);return out/'manifest.json'

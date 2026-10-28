"""Complete QUAL result export and Git-only recovery; no scientific execution."""
from contextlib import contextmanager, redirect_stdout, redirect_stderr
from pathlib import Path
from time import perf_counter_ns
import argparse
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'outputs/occam_first_window_diagnostic_v1/tools'))
import run_first_window_v1 as gate
from outputs.occam_reference_qualification_v1.delivery_tools_v1 import qualification_bundle_v1 as b
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA

TOOLS=Path(__file__).parent;FREEZE=TOOLS/'freeze_v1/complete.json'
DOC=ROOT/'docs/protocols/occam_qualification_result_delivery_v1_zh.md'
RUN=gate.RUN;OUT=b.c.BASE/'qual_delivery_v1'
RUN_NAME=RUN.relative_to(ROOT).as_posix();INDEX=(OUT/'bundle_index.json').relative_to(ROOT).as_posix()
REPORT=ROOT/'reports/occam_reference_qualification_v1_zh.md'
CHILD=('accounting.json','accounting_progress.jsonl.gz','bootstrap.json','case.json','events.jsonl.gz','receipt.json',
       'request.json','result.json','rng_initialization.json','start.json','stderr.log','stdout.log','witnesses.jsonl.gz')
ENV=('mujoco','metaworld','gym','gymnasium','torch')
REQUIRED_SIDE=('statistics_v1/statistics.json','statistics_v1/independent_audit.json','statistics_v1/bootstrap_indices.json.gz',
               'pipeline_v1/complete.json','report_v1/complete.json','report_v1/source_manifest.json',
               'report_v1/all_1740_allocated_cases.csv','report_v1/all_complete_task_failures.csv',
               'report_v1/all_unresolved_or_unstarted_cases.csv','report_v1/all_1566_qualified_cases.csv',
               'report_v1/all_29_programs.csv','report_v1/all_522_task_condition_boundary_cells.csv',
               'report_v1/all_primary_comparisons.csv','report_v1/all_adaptation_and_meta_ablations.csv','report_v1/all_costs.json')


def git(*args):return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT)


def zeros():return dict(environment_steps=0,resets=0,physical_frames=0,policy_queries=0,model_predictions=0,posterior_updates=0,fits=0,online_LLM_API_calls=0)


@contextmanager
def offline(*, original_tree_forbidden=False, allow_git_reads=False):
    counts=dict(scientific_import_attempts=0,network_or_process_attempts=0,original_record_read_attempts=0);active=[True]
    original=(b.c.BASE/'qualification_v1').resolve()
    b.require(not any(n==e or n.startswith(e+'.') for n in sys.modules for e in ENV),'no environment/model modules imported')
    def hook(event,args):
        if not active[0]:return
        if event=='import' and any(args[0]==e or args[0].startswith(e+'.') for e in ENV):
            counts['scientific_import_attempts']+=1;raise RuntimeError('offline result delivery forbids scientific execution')
        forbidden=event in ('os.system','os.exec','os.posix_spawn','socket.connect','socket.connect_ex','socket.bind','socket.getaddrinfo')
        if event=='subprocess.Popen':
            command=args[1] if len(args)>1 else None
            allowed=allow_git_reads and type(command) in (list,tuple) and Path(command[0]).stem=='git'
            allowed=allowed and any(x in command for x in ('show','rev-parse'))
            forbidden=not allowed
        if forbidden:counts['network_or_process_attempts']+=1;raise RuntimeError('offline result delivery forbids network or unregistered process')
        if original_tree_forbidden and event=='open' and isinstance(args[0],(str,bytes)):
            value=args[0].decode() if isinstance(args[0],bytes) else args[0];path=Path(value).resolve()
            if path==original or original in path.parents:
                counts['original_record_read_attempts']+=1;raise RuntimeError('archive-only recovery forbids original scientific trees')
    sys.addaudithook(hook)
    try:yield counts
    finally:active[0]=False


def complete_gate():
    # In particular do not read a live result prefix or allocate an export folder.
    b.require(all((RUN/n).is_file() for n in (*gate.GATES,*REQUIRED_SIDE)) and REPORT.is_file(), 'whole original experiment, report and statistics must finish first')
    m,audit,stats=gate.admit(RUN);b.ready(RUN/'manifest.json','QUAL')
    report=b.c.read(RUN/'report_v1/complete.json');source=b.c.read(RUN/'report_v1/source_manifest.json')
    b.require(report['integrity']=='COMPLETE_REPORT' and report['scientific_population_complete'] is True
              and report['allocated']==1740 and report['unresolved']==0 and report['manifest_id']==m['manifest_id'], 'complete original Chinese report')
    b.require(source['report_sha256']==b.c.sha(REPORT) and source['manifest_id']==m['manifest_id'],'report bytes bound')
    for name,h in source['source_sha256'].items():b.require(b.c.sha(ROOT/name)==h,'report original sources '+name)
    b.require(report['task_qualification']==stats['task_qualified'] and report['predictive_qualification']==stats['prediction']['qualified'], 'negative and positive original gates retained')
    return m


def paths_for_export():
    paths={p for p in (RUN/'qual').rglob('*') if p.is_file()}
    for name in ('statistics_v1','pipeline_v1','report_v1','entry_attempts_v1'):
        paths|={p for p in (RUN/name).rglob('*') if p.is_file()}
    paths|={RUN/n for n in ('manifest.json','seed_scope.json','seed_scope_audit.json')}
    paths|={RUN/'native'/n for n in ('summary.json','completion.json','process_audit.json','audit.json')}
    paths.add(REPORT)
    return sorted(paths)


def validate_index(index):
    b.require(index['schema']=='OCCAM_QUALIFICATION_ZIP_ALIASES_V1' and index['delivery_scope']=='FULL_INDEPENDENT_QUAL_RESULT_V1'
              and index['phase']=='QUAL' and index['executions']==1566 and index['manifest_id']==gate.MID
              and index['source_git_commit']==gate.SCIENCE,'exact complete independent qualification result')
    files=index['files'];aliases=index['aliases'];b.validate_ranges(files,aliases)
    expected_children={RUN_NAME+'/qual/case_%04d/'%i+n for i in range(1,1567) for n in CHILD}
    actual_children={n for n in files if n.startswith(RUN_NAME+'/qual/case_')}
    b.require(actual_children==expected_children and len(aliases)==3132,'every one of 1566 cases and all 13 files')
    b.require(set(aliases)=={RUN_NAME+'/qual/case_%04d/'%i+n for i in range(1,1567) for n in ('events.jsonl.gz','witnesses.jsonl.gz')},'only exact original gzip member aliases')
    for name in (*REQUIRED_SIDE,'manifest.json','seed_scope.json','seed_scope_audit.json'):
        b.require(RUN_NAME+'/'+name in files,'complete result sidecar '+name)
    b.require(REPORT.relative_to(ROOT).as_posix() in files,'original Chinese report retained')
    for name in files:
        b.safe_name(name);b.require(name.startswith(RUN_NAME+'/') or name==REPORT.relative_to(ROOT).as_posix(),'only owned result source files')
    seen=set();total=0
    for number,part in enumerate(index['parts'],1):
        expected='outputs/occam_reference_qualification_v1/qual_delivery_v1/bundle_parts/part_%03d.bin'%number
        b.require(part['path']==expected and expected not in seen and 0<part['bytes']<=4*1024**2,'ordered owned bounded committed parts')
        seen.add(expected);total+=part['bytes']
    b.require(total==index['bundle_bytes']>0,'whole ZIP length from complete parts')


def checked_freeze():
    f=b.c.read(FREEZE);b.require(f['integrity']=='PASSED_FULL_QUAL_RESULT_DELIVERY_SOFTWARE_ONLY','frozen result exporter')
    for name,h in f['source_sha256'].items():b.require(b.c.sha(ROOT/name)==h,'immutable engineering source '+name)
    b.require(not git('status','--porcelain','--untracked-files=no').strip(),'committed result exporter checkout')
    for name in (*f['source_sha256'],FREEZE.relative_to(ROOT).as_posix()):
        b.require(git('show','HEAD:'+name)==(ROOT/name).read_bytes(),'actual committed exporter '+name)
    return f


def export(restore):
    # This is a separately committed software freeze, not a change to science.
    f=checked_freeze();m=complete_gate();start=perf_counter_ns();paths=paths_for_export()
    total=sum(p.stat().st_size for p in paths)
    b.require(not OUT.exists() and shutil.disk_usage(OUT.parent).free>=3*total+512*1024**2,'reserve original-size restoration, ZIP, shards and overhead')
    OUT.mkdir(exist_ok=False)
    try:
        with offline() as guard:
            aliases=b.member_aliases(ROOT,RUN/'qual',b.c.read(RUN/'qual/member_index.json'))
            target=OUT/'qual_records.zip';index=b.bundle(ROOT,paths,aliases,target)
            index.update(delivery_scope='FULL_INDEPENDENT_QUAL_RESULT_V1',phase='QUAL',executions=1566,
                manifest_id=m['manifest_id'],source_git_commit=m['source_git_commit'],software_freeze_sha256=b.c.sha(FREEZE))
            parts=OUT/'bundle_parts';parts.mkdir();items=[]
            with target.open('rb') as stream:
                for raw in iter(lambda:stream.read(4*1024**2),b''):
                    p=parts/('part_%03d.bin'%(len(items)+1));p.write_bytes(raw)
                    items.append(dict(path=p.relative_to(ROOT).as_posix(),bytes=len(raw),sha256=b.c.sha(p)))
            index['parts']=items;validate_index(index);b.c.write(OUT/'bundle_index.json',index)
            def scan(raw,name):
                text=raw.decode('utf8');b.require(find_secret_rule(text) is None and not any(v.search(text) for v in EXTRA.values()),'decoded credential pattern '+name)
            result=b.recover(ROOT,target,index,Path(restore),scan=scan)
            b.require(not any(guard.values()),'zero forbidden export attempts')
            complete_gate()
            b.c.write(OUT/'local_restoration.json',result)
            b.c.write(OUT/'complete.json',dict(integrity='PASSED_FULL_QUAL_RESULT_EXPORT_AND_LOCAL_RESTORATION',manifest_id=m['manifest_id'],
                original_files=len(index['files']),aliases=len(index['aliases']),executions=1566,
                bundle_index_sha256=b.c.sha(OUT/'bundle_index.json'),guard=dict(guard),counters=zeros(),
                scientific_results_unchanged=True,original_raw_and_zip_retained_local=True,wall_ns=perf_counter_ns()-start,publication_goal_complete=False))
    except BaseException as error:
        b.c.write(OUT/'failure.json',dict(type=type(error).__name__,message=str(error),no_retry_or_overwrite=True,wall_ns=perf_counter_ns()-start));raise
    return result


def describe_recovery(result,archive_only):
    return dict(**{k:v for k,v in result.items() if k!='all_files_byte_identical'},
                all_files_byte_identical=None if archive_only else result['all_files_byte_identical'],
                original_raw_files_required=not archive_only,original_raw_byte_comparison=not archive_only,
                size_and_SHA_against_committed_index=True)


def recover_from_git(source,destination,receipt,*,archive_only):
    start=perf_counter_ns();b.require(re.fullmatch('[0-9a-f]{40}',source) is not None,'literal full containing commit SHA')
    raw=git('show',source+':'+INDEX);index=json.loads(raw);validate_index(index)
    destination=Path(destination).resolve();target=destination.with_suffix('.zip');oids={}
    b.require(not destination.exists() and not target.exists() and not Path(receipt).exists(),'new recovery outputs only')
    parent=next(p for p in (destination.parent,*destination.parents) if p.exists())
    b.require(shutil.disk_usage(parent).free>=sum(v['bytes'] for v in index['files'].values())+index['bundle_bytes']+512*1024**2,'restoration and ZIP space reserve')
    with offline(original_tree_forbidden=archive_only,allow_git_reads=True) as guard:
        with target.open('xb') as stream:
            for part in index['parts']:
                name=part['path'];data=git('show',source+':'+name)
                b.require(len(data)==part['bytes'] and hashlib.sha256(data).hexdigest()==part['sha256'],'committed shard bytes')
                stream.write(data);oids[name]=git('rev-parse',source+':'+name).decode().strip()
        def scan(raw,name):
            text=raw.decode('utf8');b.require(find_secret_rule(text) is None and not any(p.search(text) for p in EXTRA.values()),'recovered credential pattern '+name)
        result=b.recover(destination if archive_only else ROOT,target,index,destination,scan=scan)
        b.require(not any(guard.values()),'zero forbidden recovery attempts')
    result=describe_recovery(result,archive_only)
    proof=dict(integrity='PASSED_ACTUAL_GIT_FULL_QUAL_RESULT_RESTORATION',containing_commit=source,science_source_commit=index['source_git_commit'],
        manifest_id=index['manifest_id'],phase='QUAL',executions=1566,index_sha256=hashlib.sha256(raw).hexdigest(),part_git_oids=oids,
        result=result,archive_only=archive_only,guard=guard,destination=str(destination),assembled_zip=str(target),
        full_fresh_clone_not_performed=True,counters=zeros(),wall_ns=perf_counter_ns()-start,publication_goal_complete=False)
    b.c.write(receipt,proof);return dict(integrity=proof['integrity'],files=result['files'],archive_only=archive_only)


def freeze():
    FREEZE.parent.mkdir(exist_ok=False);start=perf_counter_ns()
    source={p.relative_to(ROOT).as_posix():b.c.sha(p) for p in sorted(TOOLS.glob('*.py'))+[DOC]}
    prior=ROOT/'outputs/occam_reference_qualification_v1/delivery_tools_v1'
    previous=b.c.read(prior/'validation_v1/complete.json')
    b.require(previous['integrity']=='PASSED_FROZEN_OFFLINE_EXPORT_SOFTWARE_ONLY' and previous['unit_tests']==13,'source-bound prior generic bundle checks')
    for name,h in previous['source_sha256'].items():b.require(b.c.sha(ROOT/name)==h,'original tested bundler unchanged '+name)
    for name in ('qualification_bundle_v1.py','test_qualification_bundle_v1.py','validation_v1/complete.json'):
        source[(prior/name).relative_to(ROOT).as_posix()]=b.c.sha(prior/name)
    for name,h in gate.read(gate.FREEZE)['source_sha256'].items():
        b.require(b.c.sha(ROOT/name)==h,'tested terminal gate unchanged '+name);source[name]=h
    log=io.StringIO()
    with offline(),redirect_stdout(log),redirect_stderr(log):
        suite=unittest.defaultTestLoader.discover(str(TOOLS),pattern='test_qual_result_delivery_v1.py')
        result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    (FREEZE.parent/'unit_tests.log').write_text(log.getvalue(),encoding='utf8',newline='\n')
    b.require(result.wasSuccessful() and result.testsRun>=8,'complete constructed result-delivery checks')
    for name,h in source.items():
        b.require(b.c.sha(ROOT/name)==h,'source unchanged during pure checks')
        if name.endswith('.py'):compile((ROOT/name).read_bytes(),name,'exec')
    m=b.c.read(RUN/'manifest.json')
    for name,h in {**m['source_sha256'],**m['input_sha256']}.items():b.require(b.c.sha(ROOT/name)==h,'scientific source unchanged '+name)
    b.c.write(FREEZE,dict(integrity='PASSED_FULL_QUAL_RESULT_DELIVERY_SOFTWARE_ONLY',source_sha256=source,unit_tests=result.testsRun,
        prior_bundle_checks_source_bound_reused=13,frozen_scientific_source_files_unchanged=len(m['source_sha256']),
        manifest_sha256=b.c.sha(RUN/'manifest.json'),QUAL_outcomes_read=False,records_exported=0,actual_Git_restoration_performed=False,
        original_byte_and_archive_only_modes_both_pending_real_data=True,counters=zeros(),wall_ns=perf_counter_ns()-start,publication_goal_complete=False))
    return dict(integrity='PASSED_FULL_QUAL_RESULT_DELIVERY_SOFTWARE_ONLY',tests=result.testsRun)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=('freeze','export','recover'))
    p.add_argument('--restore');p.add_argument('--source');p.add_argument('--receipt');p.add_argument('--archive-only',action='store_true');x=p.parse_args()
    if x.command=='freeze':value=freeze()
    elif x.command=='export':p.error('--restore required') if x.restore is None else None;value=export(x.restore)
    else:
        if any(v is None for v in (x.restore,x.source,x.receipt)):p.error('--restore, --source, --receipt required')
        value=recover_from_git(x.source,x.restore,x.receipt,archive_only=x.archive_only)
    print(json.dumps(value),flush=True)

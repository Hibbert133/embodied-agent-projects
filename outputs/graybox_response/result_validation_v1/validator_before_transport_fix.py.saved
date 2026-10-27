"""Verify saved terminal results, costs, raw restoration and exact owned index."""
from pathlib import Path
from time import perf_counter_ns
import shutil,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import graybox_response_io_v1 as a
from src.analysis.release_learning_guard_v1 import read_only
from scripts.archive_action_response import members
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
io=a.io

def validate(path):
    start=perf_counter_ns();m=a.checked(path);root=path.parent;out=a.BASE/'result_validation_v1';out.mkdir(exist_ok=False);guard={}
    io.require(io.git('rev-parse','HEAD')==m['source_git_commit'] and not io.git('status','--porcelain','--untracked-files=no') and not io.git('diff','--cached','--name-only'),'terminal source still clean frozen HEAD')
    freeze=io.read(a.VALIDATION/'complete.json');reuse=io.read(a.VALIDATION/'source_reuse.json')
    io.require(freeze['integrity']==reuse['integrity']=='PASSED' and freeze['unique_test_total']==reuse['unique_tests']==2408,'frozen source-bound checks')
    for mapping in (freeze['source_sha256'],reuse['source_sha256']):
        for n,h in mapping.items():io.require(io.sha(ROOT/n)==h,'unchanged checked source '+n)
    for n,h in freeze['receipt_sha256'].items():io.require(io.sha(a.VALIDATION/n)==h,'unchanged freeze receipt '+n)
    all_cases=io.read(root/'presentation/all_case_outcomes.json');io.require(len(all_cases)==891,'entire new allocation')
    io.require([{k:r[k] for k in a.KEYS} for r in all_cases]==[s for split in a.SPLITS for s in a.population(split)],'same exact frozen assignment order')
    failures=list((root/'pipeline_control').glob('*failure.json'));finished=(root/'pipeline_control/completion.json').exists();io.require(bool(failures)!=finished,'one terminal result or preserved failure')
    total=dict(executions=0,completed_executions=0,control_steps=0,all_resets=0,physical_frames=0,fixed_policy_queries=0);artifact_hashes={}
    with read_only(guard):
        for split in a.SPLITS:
            folder=root/split.lower()
            if not (folder/'summary.json').exists():continue
            s=io.read(folder/'summary.json');done=io.read(folder/'completion.json');cc=list(io.rows(folder/'cases.jsonl.gz'))
            for n,h in done['artifact_sha256'].items():io.require(io.sha(folder/n)==h,'immutable raw '+split+'/'+n)
            io.require(len(cc)==s['executions'] and sum(c['total_steps'] for c in cc)<=s['control_steps'],'all physical case records and partial cost')
            io.require(s['network_guard']==dict(attempted_network_calls=0) and s['fitting_guard']==dict(attempted_fits=0) and s['new_offline_model_fits']==s['online_LLM_API_calls']==0,'no bank fit or online network during native collection')
            ledger=s['lifecycle']['counts'];failed=io.read(folder/'failed_case.json') if (folder/'failed_case.json').exists() else None
            values=dict(executions=len(cc)+int(failed is not None),completed_executions=len(cc),control_steps=s['control_steps'],all_resets=ledger.get('reset_attempts',0),physical_frames=ledger.get('simulation_frames_completed',0),
                fixed_policy_queries=sum(c['policy_queries'] for c in cc)+(failed or {}).get('policy_queries',0))
            for k,v in values.items():total[k]+=v
            if (folder/'audit.json').exists():
                r=io.read(folder/'audit.json');io.require(r['integrity']=='PASSED' and r['native_target_updates_bit_exact'] and r['artifact_sha256']==done['artifact_sha256'],'independent raw/native audit '+split)
                io.require(r['trajectory_audit_sha256']==io.sha(folder/'trajectory_audit.json'),'immutable trajectory audit '+split)
                op=r['read_only_guard']['operation_counts'];io.require(all(op[k]==0 for k in ('environment_creations','resets','simulation','lstsq_attempts','cold_fit_attempts','cold_estimator_entries')) and r['read_only_guard']['network']==dict(attempted_network_calls=0),'read-only record audit '+split)
                io.require(op['solve_attempts']==r['independent_inference_counts'].get('independent_RLS_batch_solves',0),'charged independent inference solves '+split)
            elif finished:raise ValueError('Missing independent audit '+split)
            if finished:io.require(len(cc)==a.limits(split)['executions'] and ledger['reset_attempts']==a.limits(split)['all_resets'] and s['control_steps']<=a.limits(split)['control_steps'] and ledger['simulation_frames_completed']<=a.limits(split)['physical_frames'],'whole allocated phase cost '+split)
        io.require(io.read(root/'presentation/costs.json')['total']==total,'independently reconstructed complete costs')
        if finished:
            io.require(total['executions']==891 and total['all_resets']==45441 and total['control_steps']<=82800 and total['physical_frames']<=23134500,'full one-shot population budget')
            training=io.read(root/'training/completion.json');ta=io.read(root/'training/audit.json')
            io.require(training['actual_counts']['ridge_solve_attempts']==9 and training['actual_counts']['nominal_grid_candidate_evaluations']==27 and training['guard']['operation_counts']['solve_attempts']==9,'main actual training costs')
            io.require(ta['integrity']=='PASSED' and ta['models_sha256']==io.sha(root/'training/models.json') and ta['independent_augmented_LS']==9 and ta['guard']['operation_counts']['lstsq_attempts']==9 and ta['independent_counts']['independent_nominal_grid_passes']==27,'independent training and costs')
            lock=io.read(root/'model_lock.json');io.require(lock['locked_monotonic_ns']<io.read(root/'qual/summary.json')['started_monotonic_ns'],'choice before QUAL')
            for n,h in lock['artifact_sha256'].items():io.require(io.sha(root/n)==h,'locked source '+n)
            for split,expected in (('cal',1728),('qual',3888)):
                folder=root/(split+'_evaluation');r=io.read(folder/'result.json');s=io.read(folder/'audit.json')
                io.require(s['integrity']=='PASSED' and s['result_sha256']==io.sha(folder/'result.json') and s['score_sha256']==io.sha(folder/'endpoint_scores.json') and r['endpoint_rows']==expected,'complete independent saved-outcome scores '+split)
            q=io.read(root/'qual_evaluation/result.json');io.require(q['selected_q_index']==lock['selected_q_index'] and q['status']==('QUALIFIED_RESPONSE_CONTRAST_COMPONENT_ONLY' if all(q['gates'].values()) else 'CLOSED_NEGATIVE'),'locked actual qualification')
        archive=a.BASE/'archives_v1'/root.name;catalog=io.read(archive/'catalog.json')
        for item in catalog['files']:
            idx=ROOT/item['index'];io.require(io.sha(idx)==item['index_sha256'],'part index');value,_=members(idx)
            io.require(value['source_sha256']==item['sha256']==io.sha(ROOT/item['source'])==io.sha(Path(item['actual_restore']['target'])),'original, all parts and actual restoration identical')
        report=ROOT/'reports/graybox_response_v1_zh.md';r=io.read(root/'presentation/report_receipt.json');io.require(r['report_sha256']==io.sha(report) and r['raw_files_actually_restored']==len(catalog['files']),'checked report and restoration count')
        io.require(all(v==0 for v in r['guard']['operation_counts'].values()) and r['guard']['network']==dict(attempted_network_calls=0),'read-only report generator')
        if (root/'qual_evaluation/result.json').exists():
            visual=io.read(root/'presentation/figure_visual_check.json');io.require(visual['inspection']=='ACTUAL_RENDER_VIEWED' and visual['png_sha256']==io.sha(root/'presentation/qualification.png'),'actual scientific figure inspected')
    external=Path(__file__).parent;tools=root/'presentation_tools';tools.mkdir(exist_ok=False)
    for n in ('build_graybox_response_report_v1.py','validate_graybox_response_delivery_v1.py','verify_graybox_collector_commit_v1.py','plot_graybox_response_v1.py'):(tools/n).write_bytes((external/n).read_bytes().replace(b'\r\n',b'\n'))
    review=ROOT/'docs/research/graybox_event_learning_review_v1_zh.md';review.write_bytes((external/review.name).read_bytes())
    process=external/'graybox_native_process_v1'
    for p in process.iterdir():shutil.copyfile(p,root/'pipeline_control'/('process_'+p.name))
    proof=io.read(external/('graybox_collector_postcommit_'+m['source_git_commit'][:12]+'.json'));io.require(proof['integrity']=='PASSED' and proof['object_count']==50 and proof['commit']==m['source_git_commit'],'exact collector freeze object proof');io.write(out/'freeze_postcommit_proof.json',proof)
    io.write(out/'source_reuse.json',dict(integrity='PASSED',unique_tests=2408,new_unique_tests_at_result=0,source_sha256={**reuse['source_sha256'],**freeze['source_sha256']},
        no_old_simulation_tests_repeated=True,full_tracked_secret_scan_reused_sha256=io.sha(a.VALIDATION/'full_tracked_secret_scan.json')))
    io.write(out/'integrity.json',dict(integrity='PASSED',full_pipeline_finished=finished,all891_registered=True,terminal_failures=[p.name for p in failures],actual_costs=total,
        raw_files_actually_restored=len(catalog['files']),original_raw_retained=True,read_only_guard=guard,source_manifest_sha256=io.sha(path)))
    names={p.relative_to(ROOT).as_posix() for base in (root,archive,out) for p in base.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.gz','.pyc','.pyo') and p.stat().st_size<=8*1024**2}
    names|={report.relative_to(ROOT).as_posix(),review.relative_to(ROOT).as_posix(),(a.BASE/'archives_v1/.gitattributes').relative_to(ROOT).as_posix()}
    def stage(label):
        nonlocal names
        names|={p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()};spec=out/(label+'.nul');names.add(spec.relative_to(ROOT).as_posix());spec.write_bytes(b'\0'.join(n.encode() for n in sorted(names))+b'\0')
        io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+spec.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    def check():
        actual=index_bytes(names)
        for n in actual:
            data=(ROOT/n).read_bytes()
            if b'\0' not in data:
                for label,pattern in EXTRA.items():io.require(pattern.search(data.decode('utf8',errors='replace')) is None,'new indexed credential '+label+' '+n)
        io.require(not io.git('diff','--check') and not io.git('diff','--cached','--check'),'ordinary and staged differences');return actual
    compiled=[]
    for n in names:
        if n.endswith('.py'):compile((ROOT/n).read_bytes(),n,'exec');compiled.append(n)
    io.write(out/'new_tool_compile.json',dict(integrity='PASSED',compiled=compiled,no_new_dependencies=True,pip_check_reused_sha256=io.sha(a.VALIDATION/'dependencies.json')))
    stage('owned_initial');actual=check();io.write(out/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=actual,basic_and_extra_secrets_checked_on_actual_index=True))
    io.write(out/'complete.json',dict(integrity='PASSED',source_manifest_sha256=io.sha(path),report_sha256=io.sha(report),costs_sha256=io.sha(root/'presentation/costs.json'),
        source_unchanged=True,unique_test_total=2408,new_tests_at_result=0,new_physics=0,new_model_fits=0,online_LLM_API_calls=0,publication_goal_complete=False,
        receipt_sha256={p.name:io.sha(p) for p in out.iterdir() if p.is_file()},wall_ns=perf_counter_ns()-start))
    stage('owned_final');check();print(dict(integrity='PASSED',owned_objects=len(names),actual=total,restored=len(catalog['files'])),flush=True)

if __name__=='__main__':validate(Path(sys.argv[1]).resolve())

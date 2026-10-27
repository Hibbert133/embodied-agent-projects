"""Terminal source/cost/restoration/index validation; no scientific re-execution."""
from pathlib import Path
from time import perf_counter_ns
import shutil,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import graybox_qualification_io_v2 as a
from src.analysis.release_learning_guard_v1 import read_only
from scripts.archive_action_response import members
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
io=a.io

def validate(path):
    start=perf_counter_ns();m=a.checked(path);root=path.parent;out=a.BASE/'result_validation_v2';out.mkdir(exist_ok=False);guard={}
    io.require(io.git('rev-parse','HEAD')==m['source_git_commit'] and not io.git('status','--porcelain','--untracked-files=no') and not io.git('diff','--cached','--name-only'),'clean frozen supplement HEAD')
    freeze=io.read(a.VALIDATION/'complete.json');reuse=io.read(a.VALIDATION/'source_reuse.json');io.require(freeze['integrity']==reuse['integrity']=='PASSED' and freeze['unique_test_total']==reuse['unique_tests']==2428,'source-bound checks')
    for mapping in (freeze['source_sha256'],reuse['source_sha256']):
        for n,h in mapping.items():io.require(io.sha(ROOT/n)==h,'unchanged checked source '+n)
    for n,h in freeze['receipt_sha256'].items():io.require(io.sha(a.VALIDATION/n)==h,'unchanged freeze receipt '+n)
    cases=io.read(root/'presentation/all_case_outcomes.json');io.require(len(cases)==432 and [{k:r[k] for k in a.KEYS} for r in cases]==[s for split in a.SPLITS for s in a.population(split)],'all original unspent assignments, same order')
    failures=list((root/'pipeline_control').glob('*failure.json'));finished=(root/'pipeline_control/completion.json').exists();io.require(bool(failures)!=finished,'terminal complete or recorded failure')
    totals=dict(executions=0,completed_executions=0,control_steps=0,all_resets=0,physical_frames=0,fixed_policy_queries=0)
    with read_only(guard):
        contract=a.source_contract();io.require(contract['source_sha256']==io.read(root/'existing_source_contract.json')['source_sha256'],'original failed source, model and public records preserved')
        for split in a.SPLITS:
            folder=root/split.lower()
            if not (folder/'summary.json').exists():continue
            s=io.read(folder/'summary.json');done=io.read(folder/'completion.json');cc=list(io.rows(folder/'cases.jsonl.gz'));failed=io.read(folder/'failed_case.json') if (folder/'failed_case.json').exists() else None
            for n,h in done['artifact_sha256'].items():io.require(io.sha(folder/n)==h,'immutable raw '+split+'/'+n)
            io.require(s['executions']==len(cc) and sum(c['total_steps'] for c in cc)<=s['control_steps'],'all complete and partial case cost')
            io.require(s['new_offline_model_fits']==s['online_LLM_API_calls']==0 and s['fitting_guard']==dict(attempted_fits=0) and s['network_guard']==dict(attempted_network_calls=0),'no new bank fits or API')
            ledger=s['lifecycle']['counts'];values=dict(executions=len(cc)+int(failed is not None),completed_executions=len(cc),control_steps=s['control_steps'],all_resets=ledger.get('reset_attempts',0),physical_frames=ledger.get('simulation_frames_completed',0),fixed_policy_queries=sum(c['policy_queries'] for c in cc)+(failed or {}).get('policy_queries',0))
            for k,v in values.items():totals[k]+=v
            if (folder/'audit.json').exists():
                r=io.read(folder/'audit.json');io.require(r['integrity']=='PASSED' and r['native_target_updates_bit_exact'] and r['artifact_sha256']==done['artifact_sha256'],'independent native/record audit')
                io.require(io.sha(folder/'trajectory_audit.json')==r['trajectory_audit_sha256'],'immutable audit detail')
                op=r['read_only_guard']['operation_counts'];io.require(all(op[k]==0 for k in ('environment_creations','resets','simulation','lstsq_attempts','cold_fit_attempts','cold_estimator_entries')) and r['read_only_guard']['network']==dict(attempted_network_calls=0),'read-only independent audit')
                io.require(op['solve_attempts']==r['independent_inference_counts'].get('independent_RLS_batch_solves',0),'all independent inference solves charged')
            elif finished:raise ValueError('missing independent audit '+split)
            if finished:io.require(len(cc)==a.limits(split)['executions'] and s['control_steps']<=a.limits(split)['control_steps'] and ledger['reset_attempts']==a.limits(split)['all_resets'] and ledger['simulation_frames_completed']<=a.limits(split)['physical_frames'],'whole population and costs '+split)
        cost=io.read(root/'presentation/costs.json');io.require(totals==cost['new_total'],'independently reconstructed new costs')
        inherited=a.config()['imported_source_costs_separate'];io.require(cost['combined_actual']=={k:inherited[k]+totals[k] for k in ('executions','control_steps','all_resets','physical_frames')},'inherited cost counted once')
        combined=io.read(root/'presentation/combined_original_allocation_register.json');io.require(len(combined)==891 and len({tuple(c[k] for k in a.KEYS) for c in combined})==891,'891 unique original allocations')
        if finished:
            io.require(totals['executions']==432 and totals['all_resets']==22032 and totals['control_steps']<=40320 and totals['physical_frames']<=11217600,'entire supplement budget')
            lock=io.read(root/'model_lock.json');io.require(lock['locked_monotonic_ns']<io.read(root/'qual/summary.json')['started_monotonic_ns'],'lock before QUAL actual collection')
            for n,h in lock['artifact_sha256'].items():io.require(io.sha(root/n)==h,'frozen CAL choice artifact '+n)
            for split,rows in (('cal',1728),('qual',3888)):
                folder=root/(split+'_evaluation');r=io.read(folder/'result.json');s=io.read(folder/'audit.json')
                io.require(s['integrity']=='PASSED' and s['result_sha256']==io.sha(folder/'result.json') and s['score_sha256']==io.sha(folder/'endpoint_scores.json') and r['endpoint_rows']==rows,'whole allocation independent scores '+split)
            qual=io.read(root/'qual_evaluation/result.json');io.require(qual['selected_q_index']==lock['selected_q_index'] and qual['status']==('QUALIFIED_RESPONSE_CONTRAST_COMPONENT_ONLY' if all(qual['gates'].values()) else 'CLOSED_NEGATIVE'),'preassigned candidate qualification')
        archive=a.BASE/'archives_v2'/root.name;catalog=io.read(archive/'catalog.json')
        for item in catalog['files']:
            idx=ROOT/item['index'];value,_=members(idx);io.require(io.sha(idx)==item['index_sha256'] and value['source_sha256']==item['sha256']==io.sha(ROOT/item['source'])==io.sha(Path(item['actual_restore']['target'])),'original, parts and actual restoration exact')
        report=ROOT/'reports/graybox_qualification_v2_zh.md';r=io.read(root/'presentation/report_receipt.json');io.require(io.sha(report)==r['report_sha256'] and r['raw_files_actually_restored']==len(catalog['files']),'report and restoration count')
        io.require(all(v==0 for v in r['guard']['operation_counts'].values()) and r['guard']['network']==dict(attempted_network_calls=0),'read-only report')
        if (root/'qual_evaluation/result.json').exists():
            visual=io.read(root/'presentation/figure_visual_check.json');io.require(visual['inspection']=='ACTUAL_RENDER_VIEWED' and visual['png_sha256']==io.sha(root/'presentation/qualification.png'),'actual rendered scientific figure inspected')
    external=Path(__file__).parent;tools=root/'presentation_tools';tools.mkdir(exist_ok=False)
    for n in ('build_graybox_qualification_report_v2.py','validate_graybox_qualification_delivery_v2.py','verify_graybox_qualification_freeze_v2.py','plot_graybox_qualification_v2.py'):(tools/n).write_bytes((external/n).read_bytes())
    review=ROOT/'docs/research/correction_scope_validity_policy_review_v3_zh.md';review.write_bytes((external/review.name).read_bytes())
    for p in (external/'graybox_qualification_native_process_v2').iterdir():shutil.copyfile(p,root/'pipeline_control'/('process_'+p.name))
    proof=io.read(external/('graybox_qualification_freeze_postcommit_'+m['source_git_commit'][:12]+'.json'));io.require(proof['integrity']=='PASSED' and proof['object_count']==30,'exact committed entry freeze');io.write(out/'freeze_postcommit_proof.json',proof)
    io.write(out/'integrity.json',dict(integrity='PASSED',actual_new_costs=totals,all432_original_unspent_assignments_registered=True,combined_original_allocations=891,
        all_original_source_hashes_unchanged=True,full_pipeline_finished=finished,failures=[p.name for p in failures],raw_files_actually_restored=len(catalog['files']),read_only_guard=guard))
    io.write(out/'source_reuse.json',dict(integrity='PASSED',unique_tests=2428,new_tests_at_result=0,source_sha256={**reuse['source_sha256'],**freeze['source_sha256']},old_simulation_tests_repeated=False,
        full_tracked_secret_scan_reused_sha256=io.sha(a.VALIDATION/'full_tracked_secret_scan.json')))
    names={p.relative_to(ROOT).as_posix() for base in (root,archive,out) for p in base.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.gz','.pyc','.pyo') and p.stat().st_size<=8*1024**2}
    names|={report.relative_to(ROOT).as_posix(),review.relative_to(ROOT).as_posix(),(a.BASE/'archives_v2/.gitattributes').relative_to(ROOT).as_posix()}
    def stage(label):
        nonlocal names
        names|={p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()};spec=out/(label+'.nul');names.add(spec.relative_to(ROOT).as_posix());spec.write_bytes(b'\0'.join(n.encode() for n in sorted(names))+b'\0')
        io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+spec.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    def check():
        actual=index_bytes(names)
        for n in actual:
            data=(ROOT/n).read_bytes()
            if b'\0' not in data:
                for label,regex in EXTRA.items():io.require(regex.search(data.decode('utf8',errors='replace')) is None,'indexed secret '+label+' '+n)
        io.require(not io.git('diff','--check') and not io.git('diff','--cached','--check'),'ordinary/staged diff');return actual
    compiled=[]
    for n in names:
        if n.endswith('.py'):compile((ROOT/n).read_bytes(),n,'exec');compiled.append(n)
    io.write(out/'new_tools_compile.json',dict(integrity='PASSED',compiled=compiled,no_new_dependencies=True,source_bound_pip_check=io.sha(a.VALIDATION/'dependencies.json')))
    stage('owned_initial');actual=check();io.write(out/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=actual,basic_and_extra_actual_index_secret_scan=True))
    io.write(out/'complete.json',dict(integrity='PASSED',source_manifest_sha256=io.sha(path),report_sha256=io.sha(report),costs_sha256=io.sha(root/'presentation/costs.json'),
        full_tracked_secret_scan_source_bound=io.sha(a.VALIDATION/'full_tracked_secret_scan.json'),unique_test_total=2428,new_unit_tests_at_result=0,new_physics=0,new_primary_model_fits=0,
        online_LLM_API_calls=0,original_failure_and_raw_restorations_retained=True,publication_goal_complete=False,wall_ns=perf_counter_ns()-start))
    stage('owned_final');check();print(dict(integrity='PASSED',owned_objects=len(names),actual_new_costs=totals,restored=len(catalog['files'])),flush=True)

if __name__=='__main__':validate(Path(sys.argv[1]).resolve())

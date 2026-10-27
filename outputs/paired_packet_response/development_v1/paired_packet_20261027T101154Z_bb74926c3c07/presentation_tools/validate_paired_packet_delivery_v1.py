"""Validate existing science/transport, stage only owned delivery paths."""
from pathlib import Path
from time import perf_counter_ns
import subprocess,sys,shutil
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import paired_packet_io_v1 as a
from src.analysis.response_action_io_v1 import verify_runtime
from scripts.archive_action_response import members
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
io=a.io


def validate(path):
    start=perf_counter_ns();m=a.checked(path);run=path.parent;out=a.BASE/'result_validation_v1';out.mkdir(exist_ok=False)
    assert io.git('rev-parse','HEAD')==m['source_git_commit'] and not io.git('status','--porcelain','--untracked-files=no') and not io.git('diff','--cached','--name-only')
    complete=io.read(a.VALIDATION/'complete.json');reuse=io.read(a.VALIDATION/'source_reuse.json');assert complete['unique_test_total']==reuse['unique_tests']==2265
    for mapping in (complete['source_sha256'],reuse['source_sha256']):
        for n,h in mapping.items():assert io.sha(ROOT/n)==h,n
    for n,h in complete['receipt_sha256'].items():assert io.sha(a.VALIDATION/n)==h,n
    verify_runtime(io.read(ROOT/'outputs/correction_scope/freeze_validation_v1/runtime_lock.json'))
    totals=dict(executions=0,control_steps=0,all_resets=0,physical_frames=0,fixed_policy_queries=0,independent_policy_queries=0);phase={}
    failures=list((run/'pipeline_control').glob('*failure.json'));finished=(run/'pipeline_control/completion.json').exists();assert bool(failures)!=finished
    for split in a.SPLITS:
        folder=run/split.lower()
        if not (folder/'summary.json').exists():continue
        summary=io.read(folder/'summary.json');done=io.read(folder/'completion.json')
        for n,h in done['artifact_sha256'].items():assert io.sha(folder/n)==h
        cases=list(io.rows(folder/'cases.jsonl.gz'));assert len(cases)==summary['executions'];assert sum(c['total_steps'] for c in cases)<=summary['control_steps']
        audit=io.read(folder/'audit.json') if (folder/'audit.json').exists() else None
        if audit:
            assert audit['integrity']=='PASSED' and audit['native_target_updates_bit_exact'] and audit['artifact_sha256']==done['artifact_sha256']
            assert all(v==0 for v in audit['read_only_guard']['operation_counts'].values()) and audit['read_only_guard']['network']['attempted_network_calls']==0
            assert audit['trajectory_audit_sha256']==io.sha(folder/'trajectory_audit.json')
        assert summary['network_guard']==dict(attempted_network_calls=0) and summary['fitting_guard']==dict(attempted_fits=0)
        assert summary['new_model_fits']==summary['online_LLM_API_calls']==0
        failed=io.read(folder/'failed_case.json') if (folder/'failed_case.json').exists() else None
        phase[split]=dict(executions=len(cases)+int(failed is not None),control_steps=summary['control_steps'],all_resets=summary['lifecycle']['counts']['reset_attempts'],physical_frames=summary['lifecycle']['counts']['simulation_frames_completed'],
            fixed_policy_queries=sum(c['policy_queries'] for c in cases)+(failed or {}).get('policy_queries',0),independent_policy_queries=0 if audit is None else audit['extra_independent_policy_queries'])
        for k,v in phase[split].items():totals[k]+=v
        if finished:assert len(cases)==a.limits(split)['executions'] and audit is not None
    if finished:
        assert totals['executions']==864 and totals['control_steps']<=80640 and totals['all_resets']==44064 and totals['physical_frames']<=22435200
        train=io.read(run/'training/training_receipt.json');ta=io.read(run/'training/audit.json');assert train['receipt']['operation_counts']['solve_attempts']==57 and ta['receipt']['operation_counts']['lstsq_attempts']==57
        assert ta['models_sha256']==io.sha(run/'training/models.json')
        lock=io.read(run/'model_lock.json');assert lock['locked_unix_ns']<io.read(run/'qual/summary.json')['started_unix_ns']
        for n,h in lock['artifact_sha256'].items():assert io.sha(run/n)==h
        for split in ('CAL','QUAL'):
            result=io.read(run/(split.lower()+'_evaluation')/'result.json');audit=io.read(run/(split.lower()+'_evaluation')/'audit.json')
            assert audit['integrity']=='PASSED' and audit['result_sha256']==io.sha(run/(split.lower()+'_evaluation')/'result.json')
            assert result['endpoint_rows']==a.limits(split)['families']*30
            assert all(v==0 for v in audit['read_only_guard']['operation_counts'].values()) and audit['read_only_guard']['network']['attempted_network_calls']==0
        qual=io.read(run/'qual_evaluation/result.json');assert qual['selected_model']==lock['selected_model']
        assert qual['status']==('QUALIFIED_RESPONSE_CONTRAST_COMPONENT_ONLY' if all(qual['gates'].values()) else 'CLOSED_NEGATIVE')
    presentation=run/'presentation';report=ROOT/'reports/paired_packet_response_v1_zh.md';r=io.read(presentation/'report_receipt.json');assert r['report_sha256']==io.sha(report)
    assert all(v==0 for v in r['guard']['operation_counts'].values()) and r['guard']['network']['attempted_network_calls']==0
    cost=io.read(presentation/'costs.json')['total']
    for k,v in totals.items():assert cost[k]==v,(k,v,cost[k])
    archive=a.BASE/'archives_v1'/run.name;catalog=io.read(archive/'catalog.json');restored=0
    for item in catalog['files']:
        idx=ROOT/item['index'];assert item['index_sha256']==io.sha(idx);value,parts=members(idx)
        assert value['source_sha256']==item['sha256']==io.sha(ROOT/item['source']);assert io.sha(Path(item['actual_restore']['target']))==item['sha256'];restored+=1
    assert restored==4*len(phase)
    tools=run/'presentation_tools';tools.mkdir(exist_ok=False);external=Path(__file__).parent
    for n in ('build_paired_packet_report_v1.py','validate_paired_packet_delivery_v1.py','plot_paired_packet_results_v1.py'):
        p=external/n
        if p.exists():(tools/n).write_bytes(p.read_bytes().replace(b'\r\n',b'\n'))
    freezeproof=io.read(external/'paired_packet_freeze_commit_proof_v1.json');assert freezeproof['commit']==m['source_git_commit'] and len(freezeproof['objects'])==60
    io.write(out/'freeze_postcommit_proof.json',freezeproof)
    io.write(out/'source_reuse.json',dict(integrity='PASSED',unique_tests=2265,new_unique_tests_at_result=0,source_sha256={**reuse['source_sha256'],**complete['source_sha256']},old_simulation_tests_repeated=False,
        freeze_receipt_sha256=io.sha(a.VALIDATION/'complete.json'),full_tracked_secret_scan_reused_sha256=io.sha(a.VALIDATION/'tracked_secret_scan.json')))
    io.write(out/'supplementary_integrity.json',dict(integrity='PASSED',entire_allocated_population_accounted=True,totals=totals,full_pipeline_finished=finished,
        all_original_failures_retained=[p.name for p in failures],actual_raw_files_restored=restored,freeze_code_and_original_raw_unchanged=True,no_new_physics_or_fits_in_delivery=True,online_LLM_API_calls=0))
    names={p.relative_to(ROOT).as_posix() for p in run.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.gz','.pyc','.pyo')}
    names|={p.relative_to(ROOT).as_posix() for p in archive.rglob('*') if p.is_file()};names|={report.relative_to(ROOT).as_posix()};names|={p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()}
    def stage(selected,label):
        p=out/(label+'.nul');selected=set(selected)|{p.relative_to(ROOT).as_posix()};p.write_bytes(b'\0'.join(n.encode() for n in sorted(selected))+b'\0')
        io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+p.relative_to(ROOT).as_posix(),'--pathspec-file-nul');return selected
    def check(selected):
        actual=index_bytes(selected)
        for n in actual:
            data=(ROOT/n).read_bytes()
            if b'\0' not in data:
                for label,pattern in EXTRA.items():assert pattern.search(data.decode('utf8',errors='replace')) is None,(label,n)
        assert not io.git('diff','--check') and not io.git('diff','--cached','--check');return actual
    names=stage(names,'owned_initial');compile_receipt=[]
    for n in names:
        if n.endswith('.py'):compile((ROOT/n).read_bytes(),n,'exec');compile_receipt.append(n)
    io.write(out/'compile_new_tools.json',dict(integrity='PASSED',compiled=compile_receipt,no_new_dependencies=True,reused_pip_check_sha256=io.sha(a.VALIDATION/'dependencies.json')))
    names=stage(names|{p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()},'owned_checked');actual=check(names)
    io.write(out/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=actual,basic_and_extra_secret_scan_on_actual_index=True))
    io.write(out/'complete.json',dict(integrity='PASSED',source_manifest_sha256=io.sha(path),report_sha256=io.sha(report),costs_sha256=io.sha(presentation/'costs.json'),source_unchanged=True,
        full_tracked_secret_scan_reused_sha256=io.sha(a.VALIDATION/'tracked_secret_scan.json'),actual_index_new_secret_scans=True,original_raw_and_restoration_preserved=True,
        unique_test_total=2265,new_unit_tests_at_result=0,new_physics=0,new_model_fits=0,online_LLM_API_calls=0,publication_goal_complete=False,wall_ns=perf_counter_ns()-start))
    names=stage(names|{p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()},'owned_final');check(names)
    print(dict(integrity='PASSED',owned_paths=len(names),restored_raw_files=restored,totals=totals),flush=True)


if __name__=='__main__':validate(Path(sys.argv[1]).resolve())

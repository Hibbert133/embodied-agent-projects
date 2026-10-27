"""Frozen original bytes, exact math audit, all tables, real restoration and index."""
from pathlib import Path
from time import perf_counter_ns
import sys,math
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import packet_structure_sources_v1 as a
from scripts.archive_action_response import members
from src.analysis.response_action_io_v1 import verify_runtime
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
io=a.io


def validate(path):
    start=perf_counter_ns();m=a.checked(path);run=path.parent;analysis=run/'analysis';out=a.BASE/'result_validation_v1';out.mkdir(exist_ok=False)
    assert io.git('rev-parse','HEAD')==m['analysis_git_commit'] and not io.git('status','--porcelain','--untracked-files=no') and not io.git('diff','--cached','--name-only')
    qa=io.read(a.VALIDATION/'complete.json');reuse=io.read(a.VALIDATION/'source_reuse.json');assert qa['unique_test_total']==reuse['unique_tests']==2286 and qa['new_unique_tests']==21
    for mapping in (qa['source_sha256'],reuse['source_sha256'],m['input_sha256']):
        for n,h in mapping.items():assert io.sha(ROOT/n)==h,n
    for n,h in qa['receipt_sha256'].items():assert io.sha(a.VALIDATION/n)==h
    verify_runtime(io.read(ROOT/'outputs/correction_scope/freeze_validation_v1/runtime_lock.json'))
    done=io.read(analysis/'completion.json');audit=io.read(analysis/'audit.json');pipeline=io.read(run/'pipeline_control/completion.json')
    assert pipeline['status']=='COMPLETED_POST_HOC_STRUCTURE_ANALYSIS' and audit['integrity']=='PASSED' and audit['main_numeric_implementation_disabled']
    for n,h in done['artifact_sha256'].items():assert io.sha(analysis/n)==h,n
    assert audit['analysis_completion_sha256']==io.sha(analysis/'completion.json')
    assert done['cases']==audit['cases']==864 and done['family_horizon_rows']==audit['family_horizon_rows']==4608 and done['saved_prediction_rows']==audit['registered_prediction_slots']==23040
    assert done['counters']==audit['counters'] and done['counters']['observed_three_role_decompositions']==3570 and done['counters']['saved_prediction_arithmetic_decompositions']==8950
    for r in (done,audit):
        assert all(v==0 for v in r['guard']['operation_counts'].values()) and r['guard']['network']['attempted_network_calls']==0
        assert r['new_model_fits']==r['new_model_predictions']==r['online_LLM_API_calls']==0
    assert io.read(a.SOURCE/'qual_evaluation/result.json')['status']=='CLOSED_NEGATIVE'
    obs=io.read(analysis/'observed_panels.json');pred=io.read(analysis/'prediction_panels.json');assert len(obs)==2428 and len(pred)==12140
    p=next(r for r in pred if r['method']=='FIR' and r['level']==['split','horizon'] and r['strata']==dict(split='QUAL',horizon=16))
    assert math.isclose(p['floor_fraction_of_group_mean_mse'],0.007064379268096839,rel_tol=1e-12)
    presentation=run/'presentation';r=io.read(presentation/'report_receipt.json');assert r['report_sha256']==io.sha(ROOT/'reports/packet_structure_diagnosis_v1_zh.md')
    assert all(v==0 for v in r['guard']['operation_counts'].values()) and r['guard']['network']['attempted_network_calls']==0
    costs=io.read(presentation/'costs.json');assert all(costs[k]==0 for k in ('new_environment_creations','new_resets','new_control_steps','new_physical_frames','new_policy_queries','new_model_fits','new_model_predictions','online_LLM_API_calls'))
    assert costs['primary_descriptive_counters']==done['counters'] and costs['independent_descriptive_counters']==audit['counters']
    assert io.read(presentation/'research_decision.json')['new_collection_unlocked'] is False
    fig=io.read(presentation/'figure_receipt.json');view=io.read(presentation/'figure_visual_check.json');assert view['integrity']=='PASSED' and view['figure_receipt_sha256']==io.sha(presentation/'figure_receipt.json')
    for n,h in fig['output_sha256'].items():assert io.sha(presentation/n)==h
    for n,h in fig['source_panels_sha256'].items():assert io.sha(analysis/n)==h
    catalog=io.read(a.BASE/'archives_v1'/run.name/'catalog.json');large=set()
    for row in catalog['files']:
        index=ROOT/row['index'];assert io.sha(index)==row['index_sha256'];v,parts=members(index)
        assert v['source_sha256']==row['sha256']==io.sha(ROOT/row['source'])==io.sha(Path(row['actual_restoration']['target']))
        assert v['source_size']==row['size'];large.add(row['source'])
    assert len(large)==3
    tools=run/'presentation_tools';tools.mkdir(exist_ok=False);external=Path(__file__).parent
    for n in ('build_packet_structure_report_v1.py','plot_packet_structure_v1.py','archive_packet_structure_tables_v1.py','validate_packet_structure_delivery_v1.py'):(tools/n).write_bytes((external/n).read_bytes().replace(b'\r\n',b'\n'))
    io.write(out/'freeze_postcommit_byte_proof.json',io.read(external/'packet_structure_freeze_commit_proof_v1.json'))
    io.write(out/'source_reuse.json',dict(integrity='PASSED',unique_tests=2286,new_unique_tests_at_result=0,source_sha256={**reuse['source_sha256'],**qa['source_sha256']},
        prior_receipt_sha256=io.sha(a.VALIDATION/'complete.json'),old_simulation_tests_repeated=False,full_tracked_secret_scan_reused_sha256=io.sha(a.VALIDATION/'tracked_secret_scan.json')))
    names={p.relative_to(ROOT).as_posix() for p in run.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo') and p.relative_to(ROOT).as_posix() not in large}
    names|={p.relative_to(ROOT).as_posix() for p in (a.BASE/'archives_v1').rglob('*') if p.is_file()};names|={p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()};names.add('reports/packet_structure_diagnosis_v1_zh.md')
    def stage(selected,label):
        p=out/(label+'.nul');selected=set(selected)|{p.relative_to(ROOT).as_posix()};p.write_bytes(b'\0'.join(n.encode() for n in sorted(selected))+b'\0')
        io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+p.relative_to(ROOT).as_posix(),'--pathspec-file-nul');return selected
    def check(selected):
        actual=index_bytes(selected)
        for n in actual:
            data=(ROOT/n).read_bytes()
            if b'\0' not in data:
                for label,pattern in EXTRA.items():assert not pattern.search(data.decode('utf8',errors='replace')),(label,n)
        assert not io.git('diff','--check') and not io.git('diff','--cached','--check');return actual
    names=stage(names,'owned_initial');actual=check(names)
    for n in names:
        if n.endswith('.py'):compile((ROOT/n).read_bytes(),n,'exec')
    io.write(out/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=actual,basic_and_extra_actual_index_secrets=True))
    io.write(out/'complete.json',dict(integrity='PASSED',source_manifest_sha256=io.sha(path),analysis_completion_sha256=io.sha(analysis/'completion.json'),independent_audit_sha256=io.sha(analysis/'audit.json'),
        all864_cases_registered=True,all4608_horizon_slots_registered=True,all23040_saved_prediction_slots_registered=True,source_closed_negative_and_all_original_scores_unchanged=True,
        all3_large_tables_parts_and_actual_restores_verified=True,compiled_new_presentation_tools=True,reused_dependency_receipt_sha256=io.sha(a.VALIDATION/'dependencies.json'),
        full_tracked_secret_scan_reused_sha256=io.sha(a.VALIDATION/'tracked_secret_scan.json'),new_index_secrets_checked=True,ordinary_and_staged_diff='PASSED',
        unique_test_total=2286,new_unique_tests_at_result=0,new_physics=0,new_model_fits=0,new_predictions=0,online_LLM_API_calls=0,publication_goal_complete=False,wall_ns=perf_counter_ns()-start))
    names=stage(names|{p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()},'owned_final');check(names)
    print(dict(integrity='PASSED',owned_paths=len(names),large_tables_restored=len(large),source_closed_negative_retained=True,new_physics=0),flush=True)


if __name__=='__main__':validate(Path(sys.argv[1]).resolve())

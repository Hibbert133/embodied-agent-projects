"""Finish a failed delivery-only byte check; never rerun a scientific stage."""
from pathlib import Path
from time import perf_counter_ns
import sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import history_response_io_v1 as a
from src.analysis.release_learning_guard_v1 import read_only
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
io=a.io

def finish(path):
    start=perf_counter_ns();m=a.checked(path);run=path.parent;out=a.BASE/'result_validation_v1';external=Path(__file__).parent
    assert io.git('rev-parse','HEAD')==m['source_git_commit'] and not io.git('diff','--name-only')
    names={x.decode('utf8') for x in (out/'owned_checked.nul').read_bytes().split(b'\0') if x}
    assert set(io.git('diff','--cached','--name-only').splitlines())==names
    original=external/'history_response_pipeline_attempt01.log';copy=run/'pipeline_control/terminal_output.log'
    assert original.read_bytes()==copy.read_bytes() and b'\r\n' in copy.read_bytes()
    io.write(out/'validation_attempt01_failure.json',dict(status='FAILED_INDEX_DISK_BYTE_CHECK',path=copy.relative_to(ROOT).as_posix(),
        failure='Git text EOL filter maps original CRLF to LF',original_terminal_sha256=io.sha(original),disk_copy_sha256=io.sha(copy),
        scientific_records_models_statistics_and_code_unchanged=True,failed_attempt_elapsed_time_not_captured=True,new_physics=0,new_model_fits=0,online_LLM_API_calls=0))
    attribute=run/'pipeline_control/.gitattributes'
    with attribute.open('x',encoding='utf8',newline='\n') as f:f.write('terminal_output.log binary\n')
    tools=run/'presentation_tools';script=tools/Path(__file__).name
    script.write_bytes(Path(__file__).read_bytes())
    report=ROOT/'reports/history_response_v1_zh.md';receipt=run/'presentation/report_receipt.json';rr=io.read(receipt);old_sha=io.sha(report)
    paragraph='\n交付字节审计首次因Git对终端日志的CRLF→LF过滤失败；失败回执、原始外部日志及逐字节副本全部保留。只为该终端日志设置binary属性，未改科学记录、模型或分数；随后重新核对实际索引。首次交付检查耗时未完整捕获，不填虚构零值。\n'
    with report.open('a',encoding='utf8',newline='\n') as f:f.write(paragraph)
    rr.update(initial_text_report_sha256=old_sha,report_sha256=io.sha(report),delivery_only_wording_revision=True);io.write(receipt,rr,exclusive=False)
    guard={}
    with read_only(guard):
        for split in a.SPLITS:
            folder=run/split.lower();done=io.read(folder/'completion.json')
            for n,h in done['artifact_sha256'].items():assert io.sha(folder/n)==h
        assert io.read(run/'qual_evaluation/result.json')['status']=='CLOSED_NEGATIVE'
        for p in tools.glob('*.py'):compile(p.read_bytes(),str(p),'exec')
    io.write(out/'delivery_repair_receipt.json',dict(integrity='READY_FOR_INDEX_CHECK',guard=guard,source_code_sha256=io.sha(script),
        original_terminal_bytes_preserved=True,terminal_sha256=io.sha(copy),line_ending_conversion_not_applied_to_disk=True,
        initial_validation_failure_retained=True,source_qualification_unchanged='CLOSED_NEGATIVE',new_scientific_stages=0,
        measured_external_report_execution_wall_s=4.6877118,measured_external_plot_execution_wall_s=5.8514934,
        initial_validation_elapsed_s=None,initial_validation_elapsed_missing_reason='NOT_CAPTURED_BEFORE_EXCEPTION',wall_ns=perf_counter_ns()-start))
    names|={attribute.relative_to(ROOT).as_posix(),script.relative_to(ROOT).as_posix()}
    def stage(selected,label):
        p=out/(label+'.nul');selected=set(selected)|{p.relative_to(ROOT).as_posix()};p.write_bytes(b'\0'.join(n.encode() for n in sorted(selected))+b'\0')
        io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+p.relative_to(ROOT).as_posix(),'--pathspec-file-nul');return selected
    def scan(selected):
        actual=index_bytes(selected)
        for n in actual:
            data=(ROOT/n).read_bytes()
            if b'\0' not in data:assert not any(p.search(data.decode('utf8',errors='replace')) for p in EXTRA.values()),n
        assert not io.git('diff','--check') and not io.git('diff','--cached','--check');return actual
    names=stage(names|{p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()},'owned_repair_checked');actual=scan(names)
    io.write(out/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=actual,basic_and_extra_secret_scan_on_actual_index=True,terminal_bytes_preserved=True))
    io.write(out/'complete.json',dict(integrity='PASSED',source_manifest_sha256=io.sha(path),report_sha256=io.sha(report),costs_sha256=io.sha(run/'presentation/costs.json'),source_unchanged=True,
        full_tracked_secret_scan_reused_sha256=io.sha(a.VALIDATION/'tracked_secret_scan.json'),actual_index_new_secret_scans=True,ordinary_and_staged_diff='PASSED',
        all16_original_gzip_files_and_actual_restorations_retained=True,initial_delivery_failure_retained=True,late_preflight_coverage_gap_disclosed=True,
        unique_test_total=2318,new_unit_tests_at_result=0,new_physics=0,new_model_fits=0,online_LLM_API_calls=0,publication_goal_complete=False,wall_ns=perf_counter_ns()-start))
    names=stage(names|{p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()},'owned_final');actual=scan(names)
    print(dict(integrity='PASSED',owned_objects=len(actual),source_qualification='CLOSED_NEGATIVE',original_log_bytes_preserved=True))

if __name__=='__main__':finish(Path(sys.argv[1]).resolve())

"""Retain both byte-check failures and complete checks after scoped renormalize."""
from pathlib import Path
from time import perf_counter_ns
import sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import history_response_io_v1 as a
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
io=a.io;start=perf_counter_ns();path=Path(sys.argv[1]).resolve();m=a.checked(path);run=path.parent;out=a.BASE/'result_validation_v1'
assert io.git('rev-parse','HEAD')==m['source_git_commit'] and not io.git('diff','--name-only')
names={x.decode() for x in (out/'owned_repair_checked.nul').read_bytes().split(b'\0') if x}
assert set(io.git('diff','--cached','--name-only').splitlines())==names
copy=run/'pipeline_control/terminal_output.log';original=Path(__file__).parent/'history_response_pipeline_attempt01.log';assert copy.read_bytes()==original.read_bytes()
io.write(out/'validation_attempt02_failure.json',dict(status='FAILED_INDEX_DISK_BYTE_CHECK',path=copy.relative_to(ROOT).as_posix(),
    error='Previously staged LF blob was cached after adding binary attribute; explicit path-only git add --renormalize required',
    original_log_sha256=io.sha(copy),observed_failed_process_wall_s=8.553328,scientific_stages_repeated=0))
tool=run/'presentation_tools'/Path(__file__).name;tool.write_bytes(Path(__file__).read_bytes());compile(tool.read_bytes(),str(tool),'exec');names.add(tool.relative_to(ROOT).as_posix())
report=ROOT/'reports/history_response_v1_zh.md';text=report.read_text('utf8')
old='只为该终端日志设置binary属性，未改科学记录、模型或分数；随后重新核对实际索引。'
assert old in text;text=text.replace(old,'只为该终端日志设置binary属性；第二次检查仍发现旧索引缓存，随后仅对该路径执行git add --renormalize。两次失败均保留，未改科学记录、模型或分数。')
report.write_text(text,encoding='utf8',newline='\n');rrpath=run/'presentation/report_receipt.json';rr=io.read(rrpath);rr['report_sha256']=io.sha(report);io.write(rrpath,rr,exclusive=False)
def stage(selected,label):
    p=out/(label+'.nul');selected=set(selected)|{p.relative_to(ROOT).as_posix()};p.write_bytes(b'\0'.join(n.encode() for n in sorted(selected))+b'\0')
    io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+p.relative_to(ROOT).as_posix(),'--pathspec-file-nul');return selected
def scan(selected):
    actual=index_bytes(selected)
    for n in actual:
        data=(ROOT/n).read_bytes()
        if b'\0' not in data:assert not any(p.search(data.decode('utf8',errors='replace')) for p in EXTRA.values()),n
    assert not io.git('diff','--check') and not io.git('diff','--cached','--check');return actual
names=stage(names|{p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()},'owned_repair_v2_checked');actual=scan(names)
io.write(out/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=actual,basic_and_extra_secret_scan_on_actual_index=True,original_terminal_bytes_preserved=True))
io.write(out/'complete.json',dict(integrity='PASSED',source_manifest_sha256=io.sha(path),report_sha256=io.sha(report),costs_sha256=io.sha(run/'presentation/costs.json'),source_unchanged=True,
    full_tracked_secret_scan_reused_sha256=io.sha(a.VALIDATION/'tracked_secret_scan.json'),actual_index_new_secret_scans=True,ordinary_and_staged_diff='PASSED',
    all16_original_gzip_files_and_actual_restorations_retained=True,both_delivery_byte_failures_retained=True,late_preflight_coverage_gap_disclosed=True,
    unique_test_total=2318,new_unit_tests_at_result=0,new_physics=0,new_model_fits=0,online_LLM_API_calls=0,publication_goal_complete=False,wall_ns=perf_counter_ns()-start))
names=stage(names|{p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()},'owned_final');actual=scan(names)
print(dict(integrity='PASSED',owned_objects=len(actual),original_log_bytes_preserved=True,new_scientific_stages=0))

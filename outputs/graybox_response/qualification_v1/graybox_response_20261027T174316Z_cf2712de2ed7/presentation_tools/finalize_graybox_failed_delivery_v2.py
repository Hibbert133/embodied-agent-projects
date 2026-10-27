"""Retain the failed byte check, repair transport attributes, verify delivery."""
from pathlib import Path
from time import perf_counter_ns
import sys,shutil
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import graybox_response_io_v1 as a
from src.analysis.release_learning_guard_v1 import read_only
from scripts.archive_action_response import members
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
io=a.io;start=perf_counter_ns();path=Path(sys.argv[1]).resolve();m=a.checked(path);root=path.parent;out=a.BASE/'result_validation_v1';guard={}
assert io.git('rev-parse','HEAD')==m['source_git_commit'] and not (out/'complete.json').exists()
original=Path(__file__).parent/'validate_graybox_response_delivery_v1.py';report=ROOT/'reports/graybox_response_v1_zh.md'
shutil.copyfile(original,out/'validator_before_transport_fix.py.saved');shutil.copyfile(report,out/'report_before_delivery_fix.md.saved')
io.write(out/'attempt01_failure.json',dict(integrity='FAILED',stage='ACTUAL_INDEX_BYTE_CHECK',exception='ValueError: index and disk differ pipeline_control/process_stdout.log.bin',
    cause='Git core.autocrlf=input normalized textual CRLF in a byte-exact .bin log without scoped binary attributes',
    validator_sha256=io.sha(original),report_sha256=io.sha(report),raw_native_log_unchanged=True,no_additional_physics_or_fits=True,full_validator_terminal_output_saved=False))
text=report.read_text('utf8').replace('完整边际分层（mm），三任务×条件×获取位置×时点×H8/H16的全部联合分层已保存在 `qual_evaluation/panels.json` 与 `presentation/qual_all_panels.csv`：','本次 CAL／QUAL 均未启动，尚无边际或联合资格评分文件：')
text=text.replace('主求解最多9，独立增广 LS 最多9，另27遍独立标量名义网格。','主求解实际9，独立增广 LS 已执行9，另27遍独立标量名义网格。审计随后在结束预算检查时读取尚未发布的上下文计数，触发 KeyError；原失败回执保留这些实际次数。数值比较未先报错，不等于独立审计已完整通过。')
text=text.replace('评分用Decimal／Fraction。','评分器实现了Decimal／Fraction，但本轮仅通过构造检查，尚未对 CAL／QUAL 执行评分。')
text=text.replace('没有自动重试、扩样或换种子。','失败在训练独立审计末尾发生，具体为在 read_only 上下文退出前访问 operation_counts；未产生完成审计回执。没有自动重试、扩样或换种子。')
with report.open('w',encoding='utf8',newline='\n') as f:f.write(text)
io.write(root/'presentation/report_revision_v2.json',dict(integrity='PASSED',report_sha256=io.sha(report),original_report_sha256=io.sha(out/'report_before_delivery_fix.md.saved'),
    correction='Disclose technical audit failure and distinguish unexecuted scoring from implemented scoring; no scientific result changed'))
(root/'pipeline_control/.gitattributes').write_bytes(b'*.bin binary\n')
with read_only(guard):
    freeze=io.read(a.VALIDATION/'complete.json');reuse=io.read(a.VALIDATION/'source_reuse.json')
    for mapping in (freeze['source_sha256'],reuse['source_sha256']):
        for n,h in mapping.items():assert io.sha(ROOT/n)==h,n
    for n,h in freeze['receipt_sha256'].items():assert io.sha(a.VALIDATION/n)==h,n
    integrity=io.read(out/'integrity.json');assert integrity['integrity']=='PASSED' and not integrity['full_pipeline_finished'] and integrity['actual_costs']==io.read(root/'presentation/costs.json')['total']
    assert integrity['actual_costs']['executions']==459 and integrity['actual_costs']['control_steps']==31017 and integrity['actual_costs']['all_resets']==23409 and integrity['actual_costs']['physical_frames']==11859585
    cases=io.read(root/'presentation/all_case_outcomes.json');assert len(cases)==891 and sum(c['record_status']=='COMPLETED' for c in cases)==459 and sum(c['record_status']=='NOT_STARTED' for c in cases)==432
    assert not (root/'cal').exists() and not (root/'qual').exists() and not (root/'training/audit.json').exists()
    failure=io.read(root/'pipeline_control/training_audit_failure.json');frames=[f for f in failure['partial_counters'] if f['module']=='src.analysis.graybox_response_training_audit_v1'];assert len(frames)==1
    assert frames[0]['guard']['operation_counts']['lstsq_attempts']==9 and frames[0]['counter']['independent_nominal_grid_passes']==27 and frames[0]['guard']['zero_new_physical_interactions']
    catalog=io.read(a.BASE/'archives_v1'/root.name/'catalog.json');assert len(catalog['files'])==13
    for item in catalog['files']:
        index=ROOT/item['index'];value,_=members(index);assert io.sha(index)==item['index_sha256'] and value['source_sha256']==item['sha256']==io.sha(ROOT/item['source'])==io.sha(Path(item['actual_restore']['target']))
    assert io.sha(root/'pipeline_control/process_stdout.log.bin')==io.sha(Path(__file__).parent/'graybox_native_process_v1/stdout.log.bin')
for n in ('finalize_graybox_failed_delivery_v2.py','verify_graybox_result_commit_v1.py'):(root/'presentation_tools'/n).write_bytes((Path(__file__).parent/n).read_bytes())
names={n.decode() for n in (out/'owned_initial.nul').read_bytes().split(b'\0') if n}
names|={(root/'pipeline_control/.gitattributes').relative_to(ROOT).as_posix()}|{p.relative_to(ROOT).as_posix() for base in (out,root/'presentation',root/'presentation_tools') for p in base.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
compiled=[]
for n in names:
    if n.endswith('.py'):compile((ROOT/n).read_bytes(),n,'exec');compiled.append(n)
def stage(label,renormalize=False):
    global names
    names|={p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()};p=out/(label+'.nul');names.add(p.relative_to(ROOT).as_posix());p.write_bytes(b'\0'.join(n.encode() for n in sorted(names))+b'\0')
    io.git('-c','maintenance.auto=false','-c','gc.auto=0','add',*(['--renormalize'] if renormalize else []),'--pathspec-from-file='+p.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
def check():
    actual=index_bytes(names)
    for n in actual:
        data=(ROOT/n).read_bytes()
        if b'\0' not in data:
            for label,pattern in EXTRA.items():assert pattern.search(data.decode('utf8',errors='replace')) is None,(label,n)
    assert not io.git('diff','--check') and not io.git('diff','--cached','--check');return actual
stage('owned_repaired');stage('owned_renormalized',True);actual=check()
io.write(out/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=actual,basic_and_extra_actual_index_secret_scan=True,scoped_binary_log_attribute=True,failed_check_retained=True))
io.write(out/'complete.json',dict(integrity='PASSED',source_manifest_sha256=io.sha(path),report_sha256=io.sha(report),costs_sha256=io.sha(root/'presentation/costs.json'),
    source_unchanged=True,scientific_status='PIPELINE_FAILED_RETAINED_NO_CAL_OR_QUAL',unique_test_total=2408,new_unit_tests_at_result=0,
    new_physics=0,new_model_fits=0,online_LLM_API_calls=0,raw_and_restoration_retained=True,read_only_guard=guard,new_tools_compiled=compiled,
    full_tracked_secret_scan_reused_sha256=io.sha(a.VALIDATION/'full_tracked_secret_scan.json'),publication_goal_complete=False,wall_ns=perf_counter_ns()-start))
stage('owned_final');check();print(dict(integrity='PASSED',scientific_status='FAILED_RETAINED_NO_QUAL',owned_objects=len(names)),flush=True)

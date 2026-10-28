from pathlib import Path
import shutil,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import occam_resource_process_v2 as p
from src.analysis import response_qualification_io_v1 as io
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
from outputs.information_release.validation_v1.validate_freeze import index_bytes
out=ROOT/'outputs/research_archive/occam_resource_software_failure_v2';source='ada1bad9ef9255f9824280108923ba49e07d8c78'
assert io.git('rev-parse','HEAD')==source and not io.git('status','--porcelain','--untracked-files=no')
remote=p.read(out/'remote_receipt.json');local=p.read(out/'local_receipt.json');assert remote['integrity']==local['integrity']=='PASSED'
assert local['source_local_commit']==source and remote['remote_after']==local['archive_commit']=='a6e9fe67f20f480829e0fcf44e9269ff23364d8a'
for name in ('build_occam_resource_failure_v2_archive.py','finalize_occam_resource_failure_v2_archive.py','create_occam_resource_failure_v2_delivery.py','verify_occam_core_commit_v1.py'):
    shutil.copyfile(Path(__file__).parent/name,out/name)
for head,label in ((source,'result_committed_bytes.json'),('1b80c23e7abe8e150840323bd06393852b3c9ae7','freeze_committed_bytes.json')):
    proof=Path(__file__).parent/('occam_core_postcommit_'+head[:12]+'.json');assert p.read(proof)['commit']==head and p.read(proof)['integrity']=='PASSED';shutil.copyfile(proof,out/label)
catalog=p.read(out/'catalog.json');changed=io.git('diff','--name-only','86294a578e8d94d2b410598f6a897b805e4f708b',source).splitlines()
rows=[r for r in catalog['files'] if r['path'] in changed];assert len(rows)==len(changed)==86 and all(r['published'] for r in rows)
p.write(out/'phase_selection.json',dict(integrity='PASSED',source_local_commit=source,phase_files=86,published=86,omitted=0,files=rows))
log=ROOT/'Research_Log.md';before=log.read_bytes()
assert __import__('subprocess').check_output(['git','show','HEAD:Research_Log.md'],cwd=ROOT)==before
with log.open('a',encoding='utf8',newline='\n') as f:
    f.write('''
## 2026-10-28｜资源软件资格v2失败闭合与归档

- 已完成：保持原八类契约／预算，独立冻结本机主机名窄放行。35项实际模拟
  检查通过（33项契约回归、2项新增），累计2621项唯一来源绑定检查；
  编译和两个依赖环境检查通过。旧v1源码和全部记录不变。
- 一次v2实际资格：7个软件进程，前6项符合预期，第7项CPython的可选
  Windows版本查询尝试启动ver，被守卫在后代创建前阻止；第8项未启动、
  指标null。v2关闭，不续接、不重跑。独立只读失败闭合与字节审计通过，
  **软件资格仍未通过**，不把预期构造异常当机器人任务成功。
- 费用：v2约3.421秒主执行；两版累计14软件进程／约7.306秒主执行。
  新环境／重置／控制步／物理帧／政策查询／科学拟合／在线LLM API均0。
  一次科学入口观测提交余量2.30GiB、磁盘4.43GiB，4GiB提交门未通过。
- 来源：冻结 `1b80c23e7abe8e150840323bd06393852b3c9ae7`；本地失败交付
  `ada1bad9ef9255f9824280108923ba49e07d8c78`；已核对远端
  `a6e9fe67f20f480829e0fcf44e9269ff23364d8a`（同一归档分支），本阶段86项全部发布。
- 报告：[资源软件资格v2失败交付](reports/occam_resource_qualification_v2_zh.md)。
- 下一阶段目标：先核对并独立冻结进程内Windows版本回退，绑定标准库源码
  与系统版本回执，继续禁止后代、连接和DNS，再执行一次软件资格；不修改
  旧失败或科学门槛。真实原生集成／连续性、新科学分配和训练仍未开放。
  A主线机制、独立自身历史的完整任务收益、强对照和消融仍需建立。
''')
assert log.read_bytes().startswith(before)
p.write(out/'complete.json',dict(integrity='PASSED_ARCHIVAL_AND_APPEND_ONLY_STAGE_LOG',source_local_commit=source,
    remote_archive_commit=remote['remote_after'],phase_files=86,phase_published=86,phase_omitted=0,original_records_and_failures_preserved=True,
    new_environment_operations=0,new_fits=0,online_LLM_API_calls=0,science_collection_opened=False,publication_goal_complete=False))
names={n.relative_to(ROOT).as_posix() for n in out.iterdir() if n.is_file()}|{'Research_Log.md'}
def stage(label):
    global names
    names|={n.relative_to(ROOT).as_posix() for n in out.iterdir() if n.is_file()}
    file=out/(label+'.nul');names.add(file.relative_to(ROOT).as_posix());file.write_bytes(b'\0'.join(n.encode() for n in sorted(names))+b'\0')
    io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+file.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
def check():
    actual=index_bytes(names)
    for n in actual:
        data=(ROOT/n).read_bytes()
        if b'\0' in data:continue
        text=data.decode('utf8',errors='replace');assert find_secret_rule(text) is None and not any(x.search(text) for x in EXTRA.values()),n
    assert not io.git('diff','--check') and not io.git('diff','--cached','--check');return actual
stage('owned_checked');actual=check();p.write(out/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=actual,actual_index_basic_extra_scan=True))
stage('owned_final');check();print(dict(integrity='PASSED',owned_files=len(names),remote=remote['remote_after'],log_appended_without_overwrite=True),flush=True)

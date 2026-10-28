from pathlib import Path
from datetime import datetime,timezone
import shutil,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import occam_resource_process_v3 as p
from src.analysis import response_qualification_io_v1 as io
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
from outputs.information_release.validation_v1.validate_freeze import index_bytes
out=ROOT/'outputs/research_archive/occam_resource_qualification_v3';source='74d672beadc830e3cb8e4205bab30689d31c0beb'
assert io.git('rev-parse','HEAD')==source and not io.git('status','--porcelain','--untracked-files=no')
local=p.read(out/'local_receipt.json');remote=p.read(out/'remote_receipt.json');assert local['integrity']==remote['integrity']=='PASSED'
assert local['source_local_commit']==source and remote['remote_after']==local['archive_commit']=='ddc7a759f79e992fc229c47f1b095415f891932e'
for name in ('build_occam_resource_qualification_v3_archive.py','finalize_occam_resource_qualification_v3_archive.py','verify_occam_core_commit_v1.py'):
    shutil.copyfile(Path(__file__).parent/name,out/name)
for head,label in ((source,'result_committed_bytes.json'),('8d201a40f99d19042a61811004008541d3c924df','freeze_committed_bytes.json')):
    proof=Path(__file__).parent/('occam_core_postcommit_'+head[:12]+'.json');assert p.read(proof)['integrity']=='PASSED' and p.read(proof)['commit']==head;shutil.copyfile(proof,out/label)
catalog=p.read(out/'catalog.json');changed=io.git('diff','--name-only','b0f0e5586140852fd771c31700131af1e619dd3f',source).splitlines()
rows=[r for r in catalog['files'] if r['path'] in changed];assert len(rows)==len(changed)==90 and all(r['published'] for r in rows)
p.write(out/'phase_selection.json',dict(integrity='PASSED',source_local_commit=source,published=90,omitted=0,files=rows))
review=ROOT/'docs/research/correction_scope_contribution_review_v5_zh.md';review_out=ROOT/'outputs/research_review/correction_scope_v5';review_out.mkdir(parents=True,exist_ok=False)
p.write(review_out/'sources.json',dict(scope='LITERATURE_AND_DECISION_ONLY',retrieved_UTC=datetime.now(timezone.utc).isoformat(),
    sources=[dict(title='Conformal Policy Control',official='https://proceedings.mlr.press/v306/prinster26a.html',read='https://arxiv.org/html/2603.02196v4',
        version='2026-08-19 v4',read_scope='official abstract; arXiv intro, sections2.1/4.2 and appendixD searched passages; proofs not fully read',
        access_limits='PMLR PDF unsupported MIME, OpenReview verification challenge; read public arXiv author version instead'),
      dict(title='Sequential Conformal Calibration under Recursive Selection',read='https://arxiv.org/html/2610.12937v2',version='2026-10-12 v2 preprint',read_scope='abstract; introduction, problem setup and data-reuse passages'),
      dict(title='Safety Beyond the Training Data',read='https://proceedings.mlr.press/v331/srinivasan26a.html',version='L4DC2026',read_scope='official abstract only'),
      dict(title='Efficient Evaluation of Multi-Task Robot Policies With Active Experiment Selection',read='https://proceedings.mlr.press/v305/anwar25a.html',version='CoRL2025',read_scope='official abstract only')],
    review_sha256=p.sha(review),prior_review_sha256=p.sha(ROOT/'docs/research/correction_scope_contribution_review_v4_zh.md'),
    software_result_sha256=p.sha(ROOT/'outputs/occam_resource_qualification_v3/qualification_v1/audit.json'),
    changed_algorithms_or_thresholds=False,new_environment_operations=0,new_fits=0,online_LLM_API_calls=0,publication_goal_complete=False))
log=ROOT/'Research_Log.md';before=log.read_bytes();assert __import__('subprocess').check_output(['git','show','HEAD:Research_Log.md'],cwd=ROOT)==before
with log.open('a',encoding='utf8',newline='\n') as f:
    f.write('''
## 2026-10-28｜资源软件资格v3通过与贡献复核

- 已完成：原CPython本机版本回退、平台模块哈希绑定、异常后恢复；43项
  实际模拟检查（35契约回归、8新增）通过，累计2629项唯一来源绑定检查。
  编译、两个依赖环境及普通／暂存秘密、差异和字节核对通过。
- 一次正式8进程全部符合期望，独立审计在禁用主runner／资源计算／门及
  Popen后通过。第7项实际抑制1次可选ver，完整依赖核对与零操作守卫回执
  通过；嵌套异常、无回执退出、超时、篡改等期望负例全部保留。
- 费用：v3主执行46.023秒、导入私有提交峰值527.5MiB；三版累计22软件
  进程／53.329秒主执行。新增环境／reset／控制步／帧／政策查询／科学
  拟合／在线LLM API均0。一次科学入口提交余量2.10GiB、磁盘4.42GiB，
  4GiB提交门未通过。软件通过不等于原生连续性、模型或任务资格。
- 来源：冻结 `8d201a40f99d19042a61811004008541d3c924df`；本地结果
  `74d672beadc830e3cb8e4205bab30689d31c0beb`；核对远端
  `ddc7a759f79e992fc229c47f1b095415f891932e`，本阶段90项全部发布。
- 报告：[资源软件资格v3](reports/occam_resource_qualification_v3_zh.md)。
  查新补充：[贡献复核v5](docs/research/correction_scope_contribution_review_v5_zh.md)：
  新增CPC／递归选择校准等直接近邻；风险、支持和稳定性条件不能直接套到
  本任务，限幅／校准门控本身不新。未修改算法、阈值或原科学结论。
- 下一阶段目标：实现并独立冻结原生collector有界生命周期、连续世界／
  随机数／时钟、完整见证、失败会计及新分配费用，资源达门后再实际资格。
  旧TRAIN／预留保持关闭，不用188项绕过完整训练门。标准参考完整训练、
  新获取机制、强对照与独立自身历史完整任务收益／消融仍待完成。
''')
assert log.read_bytes().startswith(before)
p.write(out/'complete.json',dict(integrity='PASSED_SOFTWARE_QUALIFICATION_ARCHIVAL_AND_LOG',source_local_commit=source,
    remote_archive_commit=remote['remote_after'],phase_files=90,phase_published=90,phase_omitted=0,
    original_failures_and_records_preserved=True,new_environment_operations=0,new_fits=0,online_LLM_API_calls=0,
    science_collection_opened=False,publication_goal_complete=False,review_sha256=p.sha(review)))
names={n.relative_to(ROOT).as_posix() for n in out.iterdir() if n.is_file()}|{'Research_Log.md',review.relative_to(ROOT).as_posix(),(review_out/'sources.json').relative_to(ROOT).as_posix()}
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
stage('owned_final');check();print(dict(integrity='PASSED',owned_files=len(names),phase_published=90,remote=remote['remote_after'],log_append_only=True),flush=True)

"""Verified phase publication, append-only research log and retained preflight."""
from datetime import datetime,timezone,timedelta
from pathlib import Path
from time import perf_counter_ns
import hashlib,shutil,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import occam_native_case_io_v1 as c
from src.analysis import response_qualification_io_v1 as io
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
from outputs.information_release.validation_v1.validate_freeze import index_bytes


def main():
    started=perf_counter_ns();source='fbcc0fe9cd7577aa283a9cf334df22505852489b';remote_commit='587128a167e0a4ea909072134693aa33efd5468f'
    assert io.git('rev-parse','HEAD')==source and not io.git('status','--porcelain','--untracked-files=no')
    out=c.BASE/'delivery_v1';out.mkdir(exist_ok=False);archive=ROOT/'outputs/research_archive/occam_isolated_training_freeze_v3'
    remote=c.read(archive/'remote_receipt.json');catalog=c.read(archive/'catalog.json');assert remote['integrity']=='PASSED' and remote['remote_after']==remote_commit
    changed=io.git('diff-tree','--no-commit-id','--name-only','-r',source).splitlines();rows=[r for r in catalog['files'] if r['path'] in changed]
    assert len(rows)==len(changed)==64 and all(r['published'] for r in rows)
    for name in ('build_occam_isolated_training_freeze_v3_archive.py','verify_occam_core_commit_v1.py'):shutil.copyfile(Path(__file__).parent/name,archive/name)
    proof=Path(__file__).parent/'occam_core_postcommit_fbcc0fe9cd75.json';assert c.read(proof)['integrity']=='PASSED';shutil.copyfile(proof,archive/'source_committed_bytes.json')
    c.write(archive/'phase_selection.json',dict(integrity='PASSED',source_local_commit=source,published=64,omitted=0,files=rows,remote_archive_commit=remote_commit))
    c.write(archive/'complete.json',dict(integrity='PASSED_SOFTWARE_FREEZE_PUBLICATION',source_local_commit=source,remote_archive_commit=remote_commit,
        no_scientific_qualification_claim=True,new_environment_operations=0,online_LLM_API_calls=0))
    prepare=c.BASE/'preparation_attempts_v1/attempt_1114731719879100_9590a447af00';failed=c.read(prepare/'complete.json')
    assert failed['integrity']=='FAILED' and failed['failure']['message']=='scientific resource admission rejected: AVAILABLE_COMMIT_BELOW_FLOOR'
    assert not list(c.OUTPUT.glob('*/manifest.json'))
    for name in ('request.json','stdout.log','stderr.log'):assert (prepare/name).is_file()
    sample=c.resources.snapshot(ROOT);decision=c.resources.gate(sample,minimum_commit_bytes=4*1024**3,minimum_disk_bytes=4*1024**3)
    c.write(out/'resource_observation.json',dict(sample=sample,decision=decision,read_only_no_automatic_retry=True))
    now=datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
    log=ROOT/'Research_Log.md';prefix=log.read_bytes();assert b'\n' in prefix and '隔离收集器v3冻结交付'.encode() not in prefix
    entry=f'''

## {now}（北京时间）｜隔离收集器v3冻结交付

- 已完成：一完整案例一进程，完整原生／Python见证保留；任务内环境、RNG、
  噪声／时钟连续，原始gzip逐字节拼接，费用／进程／字节独立审计入口，
  技术失败关闭整轮且不重试。新增显式工厂前全局RNG初始化，不冒称与旧初态相同。
- 检查：32项新增数组及5项新读者回归全部通过，累计2661项唯一来源绑定
  检查；108条跨三任务／三边界的数组流不作为机器人样本。编译、两个依赖
  环境、运行时、秘密／差异／索引／提交字节通过。首次两项写入接口错误
  及开发失败日志、对应源码全部保留；未重复科学模拟／优化器测试。
- 费用：37项正式通过66.905秒，验证入口79.059秒；首次失败65.407秒另记。
  本阶段真实native worker／环境／reset／控制步／帧／实际政策查询／科学
  拟合／Adam／在线LLM API均0，未创建新科学manifest。旧v2的188完整、1部分、
  459未启动保持关闭，其27982步／11475 reset／5877410帧另列。
- 来源：本地冻结 `{source}`；核对远端 `{remote_commit}`，
  同一普通快进归档分支，本阶段64项全部发布。原始大记录和恢复副本保留。
- 资源：验证末次提交余量1.18GiB、磁盘4.34GiB；提交后一次真实prepare
  入口仍因4GiB提交门拒绝，完整栈保留，未启动采集；最新只读观测另存
  delivery_v1/resource_observation.json。未修改分页文件或关闭其他应用。
- 报告：[隔离收集器v3冻结](reports/occam_isolated_training_freeze_v3_zh.md)。
- 下一阶段目标：实际资源达门后一次NATIVE36→双审计→完整TRAIN648→双
  审计→公开数据标准参考训练／数学导出核对，均沿冻结预算及失败闭合。
  NATIVE只含边界16；科学CAL／QUAL、新方法自身历史的完整任务评价另行
  冻结。A主线具体机制、完整风险／DR等强参考、任务收益和消融仍未证明，
  软件通过不等于研究或CCF A目标完成。
'''
    with log.open('ab') as stream:stream.write(entry.encode('utf8'))
    assert log.read_bytes().startswith(prefix)
    c.write(out/'research_log_append.json',dict(integrity='PASSED',old_bytes=len(prefix),old_sha256=hashlib.sha256(prefix).hexdigest(),
        full_sha256=c.sha(log),appended_bytes=len(entry.encode()),verified_push_before_append=True,archive_commit=remote_commit,timestamp_Asia_Shanghai=now))
    report=ROOT/'reports/occam_isolated_training_freeze_v3_zh.md'
    addendum=f'''

## 冻结后的实际交付回执

本地冻结`{source}`，提交64项／4,986,921字节逐项与磁盘一致。
普通快进远端归档`{remote_commit}`已核对，本阶段64项全部发布，未强推或合并。
核对后追加根目录Research_Log，旧内容前缀字节不变。
随后保留一次实际prepare失败回执：AVAILABLE_COMMIT_BELOW_FLOOR，约
0.119秒，实验manifest未创建；没有采集、拟合或调用在线LLM。
最新只读资源观测见delivery_v1/resource_observation.json，仍须实际入口达门，
不根据等待时间或软件测试通过自动开始仿真。
'''
    with report.open('ab') as stream:stream.write(addendum.encode('utf8'))
    c.write(out/'source_freeze_binding.json',dict(integrity='PASSED',source_commit=source,
        source_sha256=c.read(c.FREEZE)['source_sha256'],source_freeze_sha256=c.sha(c.FREEZE),no_code_changes_after_passed_tests=True))
    for name,h in c.read(c.FREEZE)['source_sha256'].items():assert c.sha(ROOT/name)==h,name
    shutil.copyfile(Path(__file__),out/Path(__file__).name)
    names={'Research_Log.md',report.relative_to(ROOT).as_posix()}
    names|={p.relative_to(ROOT).as_posix() for p in archive.iterdir() if p.is_file()}
    names|={p.relative_to(ROOT).as_posix() for p in prepare.iterdir() if p.is_file()}
    def stage(label):
        names.update(p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file())
        spec=out/(label+'.nul');names.add(spec.relative_to(ROOT).as_posix());spec.write_bytes(b'\0'.join(n.encode() for n in sorted(names))+b'\0')
        io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+spec.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    def check():
        actual=index_bytes(names)
        for name in actual:
            raw=(ROOT/name).read_bytes()
            if b'\0' in raw:continue
            text=raw.decode('utf8',errors='replace');assert find_secret_rule(text) is None and not any(x.search(text) for x in EXTRA.values()),name
        assert not io.git('diff','--check') and not io.git('diff','--cached','--check');return actual
    stage('owned_checked');c.write(out/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=check(),actual_index_basic_extra_scan=True))
    c.write(out/'complete.json',dict(integrity='PASSED_SOFTWARE_FREEZE_DELIVERY_ONLY',freeze_commit=source,remote_archive_commit=remote_commit,
        every_freeze_file_published=True,append_only_log=True,failed_prepare_sha256=c.sha(prepare/'complete.json'),scientific_manifest_created=False,
        new_native_workers=0,new_environment_operations=0,new_fits=0,Adam_updates=0,online_LLM_API_calls=0,publication_goal_complete=False,wall_ns=perf_counter_ns()-started))
    stage('owned_final');check();print(dict(integrity='PASSED_SOFTWARE_FREEZE_DELIVERY_ONLY',owned_files=len(names),resource_allowed=decision['allowed']),flush=True)


if __name__=='__main__':main()

"""Append only after the complete Native data archive is verified remotely."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import hashlib,shutil,subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
OUT=ROOT/'outputs/research_archive/occam_qualification_native_v1';SOURCE='1104977105f268baf28b2b53ed1a3f8436c50459'
RUN=ROOT/'outputs/occam_reference_qualification_v1/qualification_v1/occam_reference_qualification_v1_20261028T125131Z_7abaec83b085'


def git(*args):return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT)


def main():
    remote=io.read(OUT/'remote_receipt.json');local=io.read(OUT/'local_receipt.json');catalog=io.read(OUT/'catalog.json')
    assert remote['integrity']==local['integrity']=='PASSED' and remote['remote_after']==local['archive_commit']=='e3b43c1ddaca52a4a9def9cea14f90856fea9ba2'
    assert git('rev-parse','HEAD').decode().strip()==SOURCE and not git('status','--porcelain','--untracked-files=no').strip()
    assert git('ls-remote','--heads','origin','refs/heads/'+remote['branch']).decode().split()[0]==remote['remote_after']
    changed=set(git('diff','--name-only','c745bd4ecdb1ba61768849c93611e64b6c861188',SOURCE).decode().splitlines())
    rows=[r for r in catalog['files'] if r['path'] in changed]
    assert len(rows)==len(changed)==60 and all(r['published'] for r in rows)
    io.write(OUT/'phase_selection.json',dict(integrity='PASSED',source_local_commit=SOURCE,published=60,omitted=0,files=rows,remote_archive_commit=remote['remote_after']))
    for name in ('build_occam_qualification_native_v1_archive.py','log_occam_qualification_native_v1.py'):
        shutil.copyfile(Path(__file__).parent/name,OUT/name)
    for prefix,label in (('de7d3541b7af','data_committed_bytes'),('8f197877f387','original_recovery_committed_bytes'),('1104977105f2','portable_recovery_committed_bytes')):
        p=Path(__file__).parent/('occam_core_postcommit_'+prefix+'.json');assert io.read(p)['integrity']=='PASSED'
        shutil.copyfile(p,OUT/(label+'.json'))
    m=io.read(RUN/'manifest.json');status=io.read(RUN/'qual/status.json')
    for n,h in m['source_sha256'].items():assert io.sha(ROOT/n)==h,n
    n=status.get('completed',status.get('executions'));stamp=datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
    log=ROOT/'Research_Log.md';old=log.read_bytes()
    addition=f'''

## {stamp}（北京时间）｜完整NATIVE174交付与独立归档恢复

- 已完成：29程序×三任务×不变／变化的174次原生执行，两级审计通过；
  173任务成功、1任务失败、0技术失败。唯一失败及全部174均保留在表和
  原始记录中。只有1个独立组，所有29程序数字是描述，不作科学优势推断。
- 真实费用：14894控制步、174受控／8874全部reset、4511470物理帧；固定
  策略13104查询，学习参考274实际窗口、102后验更新，原C4/C8计24估计、
  nfev24。审计130求解、24冷估计、120冷线性求解／24最小二乘另列，无
  额外物理重仿真。旧TRAIN、C8及所有失败人口费用继续单列；在线LLM0。
- 无损数据：2288原文件、348精确压缩成员别名、12个<=4MiB分片，ZIP为
  47099700字节。两次本地ZIP／实际Git恢复均逐原件核对；又在禁止读取
  原NATIVE／QUAL目录时从实际Git恢复2288文件并按提交索引长度／SHA核对，
  原件读取尝试0，该模式不冒称对原件比较。158286行规范gzip秘密扫描；
  别名复用完整规范流扫描，不虚报重复次数。原大文件、ZIP、三个恢复
  副本、所有失败与封存编码别名错误／未完成预回执全部保留。
- 检查：13导出＋3独立于原件恢复工程测试通过，4归档算法AST身份核对；
  它们不加入科学资格数量。新代码编译、基本／补充秘密、普通／暂存差异
  和实际Git索引／磁盘／提交字节均通过。导出、恢复、归档无新环境、
  模型预测、拟合或在线LLM；原科学源码、参数、模型与主比较哈希不变。
- 来源：数据 `de7d3541b7af0f24226f141344b3cb4787ba0526`，对原件恢复证明
  `8f197877f3874bd6033b58f31b283163813fcbaa`，独立于原件的恢复
  `{SOURCE}`。精简归档普通快进后已核对远端
  `{remote['remote_after']}`，本阶段60项全部发布，不合并；仍运行的QUAL
  不在此归档。原始大文件继续本地留存，索引／分片／恢复入口已公开。
  [中文完整原生报告](reports/occam_reference_qualification_native_v1_zh.md)，
  [无需原件的恢复入口](outputs/occam_reference_qualification_v1/native_delivery_v1/archive_only_recovery_zh.md)。
  完整新clone依赖安装未实测，独立恢复读取护栏／索引核对实测已通过。
- 下一阶段：同一冻结QUAL分配当前状态{status['status']}、{n}/1566、
  {status['control_steps']}控制步，仅运维快照。继续同一进程句柄；完整收集后
  双审计和独立整组统计，再交付九组的全部对照、成功率／截止损失、费用
  与失败。技术关闭不重试补样；不根据NATIVE表或QUAL前缀改bank、阈值、
  主程序、动作或种子。无收益封存该接收者版本，不围绕它加门控。
  A的新获取机制、完整Q／DR／普通重加权等强参考、独立完整任务优势及
  消融尚待证明；本次运行、数值与记录交付不完成CCF A目标。
'''
    with log.open('ab') as f:f.write(addition.encode('utf8'))
    assert log.read_bytes()[:len(old)]==old
    io.write(OUT/'complete.json',dict(integrity='PASSED_NATIVE_DATA_PUBLICATION_AND_APPEND_ONLY_LOG',source_local_commit=SOURCE,
        remote_archive_commit=remote['remote_after'],phase_published=60,phase_omitted=0,previous_log_bytes=len(old),
        previous_log_sha256=hashlib.sha256(old).hexdigest(),new_log_sha256=io.sha(log),append_only=True,
        active_science_manifest_id=m['manifest_id'],active_qual_collection_snapshot=status,
        current_scientific_source_files_verified_unchanged=len(m['source_sha256']),
        no_physical_operations_from_archival=True,online_LLM_API_calls=0,publication_goal_complete=False))
    owned={'Research_Log.md'}|{p.relative_to(ROOT).as_posix() for p in OUT.iterdir() if p.is_file()}
    def stage(label):
        p=OUT/(label+'.nul');owned.add(p.relative_to(ROOT).as_posix());p.write_bytes(b'\0'.join(x.encode() for x in sorted(owned))+b'\0')
        git('add','--pathspec-from-file='+p.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    def check():
        actual=index_bytes(owned)
        for name in actual:
            raw=(ROOT/name).read_bytes()
            if b'\0' not in raw:
                text=raw.decode('utf8');assert find_secret_rule(text) is None and not any(r.search(text) for r in EXTRA.values()),name
            if name.endswith('.py'):compile(raw,name,'exec')
        assert not git('diff','--check').strip() and not git('diff','--cached','--check').strip();return actual
    stage('owned_checked');io.write(OUT/'index_disk_proof.json',dict(integrity='PASSED',objects=check(),actual_index_basic_extra_scan=True))
    owned.add((OUT/'index_disk_proof.json').relative_to(ROOT).as_posix());stage('owned_final');check()
    print(dict(integrity='PASSED_APPEND_ONLY_NATIVE_LOG',owned_files=len(owned),published=60,qual_snapshot=status),flush=True)


if __name__=='__main__':main()

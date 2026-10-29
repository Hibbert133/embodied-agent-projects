"""Append the independently verified compact archive; local metadata only."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import hashlib
import shutil
import sys

ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');AUX=Path(__file__).parent
BASE=ROOT/'outputs/stateful_risk_reference_v1';sys.path.insert(0,str(BASE/'tools'))
import run_risk_v1 as r
sys.path.insert(0,str(ROOT/'outputs/train_decision_contract_v1/tools'))
from freeze_contract_v1 import check_index

OUT=ROOT/'outputs/research_archive/stateful_risk_reference_v1'
SOURCE='068277fbb0090f9b3e81facd0dd875958316b661'
ARCHIVE='343554dcbdc516b1211eb2bdd26074c4b8ff836b'


def main():
    remote=r.read(OUT/'remote_receipt.json');pre=r.read(OUT/'prepublication_proof.json');local=r.read(OUT/'local_receipt.json')
    r.need(remote['integrity']==local['integrity']=='PASSED' and remote['remote_after']==local['archive_commit']==pre['archive_commit']==ARCHIVE,'remote result verified')
    r.need(pre['phase_files']==66 and pre['phase_bytes']==4856000 and pre['phase_omitted']==0,'complete published phase scope')
    r.need(r.git('rev-parse','HEAD').decode().strip()==SOURCE and not r.git('status','--porcelain','--untracked-files=no').strip(),'clean completed result')
    r.need(r.git('ls-remote','--heads','origin','refs/heads/'+remote['branch']).decode().split()[0]==ARCHIVE,'remote readback before log')
    totals=[]
    for commit,label in [('c6580006d35d5d0afe0ff5f45c4001e565a22fff','previous_archive_metadata_committed_bytes'),
        ('5503dbca90813531543933d09ceec542b36b0c54','reference_freeze_committed_bytes'),(SOURCE,'reference_result_committed_bytes')]:
        path=AUX/('occam_core_postcommit_'+commit[:12]+'.json');p=r.read(path)
        r.need(p['integrity']=='PASSED' and p['commit']==commit,'actual literal source Git/disk proof')
        totals.append((p['object_count'],p['bytes']));shutil.copyfile(path,OUT/(label+'.json'))
    r.need(sum(n for n,b in totals)==66 and sum(b for n,b in totals)==4856000,'source phase count/bytes')
    for name in ('build_stateful_risk_archive_v1.py','verify_stateful_risk_prepublication_v1.py','log_stateful_risk_archive_v1.py'):
        shutil.copyfile(AUX/name,OUT/name)
    freeze=r.read(r.FREEZE);r.verify(freeze['source_sha256']);r.verify(freeze['input_sha256']);r.verify(freeze['scientific_source_sha256'])
    original=ROOT/'outputs/occam_reference_qualification_v1/qualification_v1/occam_reference_qualification_v1_20261028T125131Z_7abaec83b085/statistics_v1/statistics.json'
    r.need(r.sha(original)=='dccede3a2838fb1ef98c20bab5e89080bcd42c8a53629c1ad22d646ae6fb75bc','original comparisons unchanged')
    log=ROOT/'Research_Log.md';old=log.read_bytes();stamp=datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
    worker=r.read(r.OUT/'worker_complete.json');freeze_scan=r.read(r.FREEZE.parent/'secret_receipt.json');result_scan=r.read(BASE/'presentation_v1/secret_receipt.json')
    addition=f'''

## {stamp}（北京时间）｜A主线标准终止包含风险参考核与查新v11归档

- 冻结`5503dbca90813531543933d09ceec542b36b0c54`：25文件228000字节，
  实际Git／磁盘一致。22项合成测试开发／正式各22执行，不算44项新测试；
  原2695科学检查与编译按1393源码SHA复用。依赖、{freeze_scan['wall_ns']/1e9:.7f}秒
  秘密、基本／EXTRA索引补扫及两差异通过；没有重复仿真测试。
- 冻结前首个检查因新简报使用历史文件名而拒绝。历史简报恢复原Git字节
  e2fb1e0e…，新简报独立命名；工程失败回执保留。没有启动科学worker，
  更没有覆盖历史研究记录或重试已采人口。实际有限表验证仅运行一次。
- 一次worker{worker['wall_ns']/1e9:.7f}秒，五个预定抽象有限表、前四例各五变体。
  C/V/M与K0/K1仅数学选项，20获取单位不修改真实机器人移动。独立展开
  在主核全部10函数禁用时核对50个逐选项有理数等式，非Python断言调用
  总数、独立样本或机器人任务数据。无支持例拒绝，不补epsilon或隐蔽回退。
- 标准DM/DR任一辅助模型正确时的期望恒等式及双失配、返回状态失配、
  终止失败／成功丢弃的完整反例均保存。成功分支n'−n、失败500−n已经
  含获取，不能重复加费；DR伪结局不按物理损失范围裁剪。随机后继终局
  不按首T改标签，真实日志概率条件未被该精确算例证明。
- 只读已审计684案例输出，原271实际静态后继标签保持不变。两种TRAIN
  行为各11个获取中结束案例均成功；没有增益决策，仍须进入未来获取前
  完整风险的终止分支。此事后计数不是旧OCCAM或旧A1失败的因果归因，
  不虚构四T终局、追加样本或读取原始gzip／QUAL结果。
- 本轮明确沿用旧A1的8模型完整风险开发参考；它已处理终止，未声称其
  发生遗漏，未重训／替换任何旧bank。本核只补稀疏后继日志的标准DR语义，
  不等于新的已训练强参考或独立自身历史部署。20次纯表评分与来源IO单列，
  新环境／reset／帧／政策与学习模型查询／拟合／训练／种子／在线LLM均0。
- 查新v11核对TOPLE、AFAPE、COST-Q、NDE联合测试／处置的明示阅读范围。
  十二候选及否决保留；一般完整风险可表达本问题，局部不变结构、支持
  获取或有限资源优势仍需具体新机制及直接强参考。标准式／反例正确
  不完成新颖性、实际任务收益、消融或CCF A目标。
- 结果`{SOURCE}`：22文件53640字节与实际Git／磁盘一致，
  {result_scan['wall_ns']/1e9:.7f}秒秘密、实际索引基本／EXTRA、编译与差异通过。
  推送前66阶段文件4856000字节逐项核对实际归档／来源／磁盘，省略0；
  10837归档文件、57新源对象秘密扫描、4855827新Git字节哈希。普通快进
  远端`{ARCHIVE}`并再读回核对，无强推／合并。旧133分片按精确Git身份
  复用实际恢复证明，本次无新恢复。此条确认后追加，元数据仅本地提交。
- [中文报告](reports/stateful_risk_reference_v1_zh.md)。原十项统计dccede3a…
  不变，原执行／预测通过而任务资格失败的结论不变。完整原始QUAL仍
  本地保留，ZIP／分片／三次恢复待空间。本次不以标准参考、检查或归档
  替代真实研究贡献，A和CCF A完整目标继续未完成。
'''
    with log.open('ab') as stream:stream.write(addition.encode('utf-8'))
    r.need(log.read_bytes()[:len(old)]==old,'append-only existing log')
    r.write(OUT/'complete.json',dict(integrity='PASSED_STANDARD_REFERENCE_ARCHIVE_APPEND_ONLY_LOG',source_local_commit=SOURCE,
        remote_archive_commit=ARCHIVE,phase_published=66,phase_bytes=4856000,phase_omitted=0,
        previous_log_bytes=len(old),previous_log_sha256=hashlib.sha256(old).hexdigest(),new_log_sha256=r.sha(log),append_only=True,
        original_scientific_source_files_unchanged=1393,full_QUAL_raw_delivery_complete=False,counters=r.ZERO,publication_goal_complete=False))
    owned={'Research_Log.md'}|{p.relative_to(ROOT).as_posix() for p in OUT.iterdir() if p.is_file()}
    def stage(label):
        spec=OUT/(label+'.nul');owned.add(spec.relative_to(ROOT).as_posix());spec.write_bytes(b'\0'.join(n.encode() for n in sorted(owned))+b'\0')
        for flags in ((),('--renormalize',)):r.git('add',*flags,'--pathspec-from-file='+spec.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    stage('owned_initial');r.write(OUT/'index_disk_proof.json',dict(integrity='PASSED_LOG_AND_ARCHIVE_METADATA_INDEX',objects=check_index(owned)))
    owned.update(p.relative_to(ROOT).as_posix() for p in OUT.iterdir() if p.is_file());stage('owned_final')
    objects=check_index(owned)
    print(dict(integrity='PASSED_READY_FOR_LOCAL_REFERENCE_ARCHIVE_LOG_COMMIT',files=len(objects),bytes=sum(v['bytes'] for v in objects.values())),flush=True)


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');main()

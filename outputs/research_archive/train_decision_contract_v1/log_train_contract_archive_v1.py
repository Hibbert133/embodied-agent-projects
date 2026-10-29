"""Append verified archive result; retain sources and never recursively push log."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import hashlib
import shutil
import subprocess
import sys

ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');AUX=Path(__file__).parent
BASE=ROOT/'outputs/train_decision_contract_v1';sys.path.insert(0,str(BASE/'tools'))
import run_contract_v1 as r
from freeze_contract_v1 import check_index

OUT=ROOT/'outputs/research_archive/train_decision_contract_v1'
SOURCE='b5cbf5d1aaf7c6069b0b185d3f96d44b6091e9f7'
ARCHIVE='f2c40f44ea60ed8849340e28989f73c06a5f864d'


def main():
    remote=r.read(OUT/'remote_receipt.json');pre=r.read(OUT/'prepublication_proof.json');local=r.read(OUT/'local_receipt.json')
    r.need(remote['integrity']==local['integrity']=='PASSED' and remote['remote_after']==local['archive_commit']==pre['archive_commit']==ARCHIVE,'verified remote target')
    r.need(pre['phase_files']==67 and pre['phase_bytes']==9385298 and pre['phase_omitted']==0,'all phase actual archive bytes')
    r.need(r.git('rev-parse','HEAD').decode().strip()==SOURCE and not r.git('status','--porcelain','--untracked-files=no').strip(),'clean completed source')
    r.need(r.git('ls-remote','--heads','origin','refs/heads/'+remote['branch']).decode().split()[0]==ARCHIVE,'remote independently checked before append')
    totals=[]
    for commit,label in [('35f25bfa601e2e1e3ebdc2a5652eff88c8f82239','previous_archive_metadata_committed_bytes'),
        ('28403b6a106e1c482f5547880489c0987ac5e5f5','contract_freeze_committed_bytes'),(SOURCE,'contract_result_committed_bytes')]:
        path=AUX/('occam_core_postcommit_'+commit[:12]+'.json');proof=r.read(path)
        r.need(proof['integrity']=='PASSED' and proof['commit']==commit,'literal actual Git/disk proof')
        totals.append((proof['object_count'],proof['bytes']));shutil.copyfile(path,OUT/(label+'.json'))
    r.need(sum(n for n,b in totals)==67 and sum(b for n,b in totals)==9385298,'phase count and byte totals')
    for name in ('build_train_contract_archive_v1.py','verify_train_contract_prepublication_v1.py','log_train_contract_archive_v1.py'):
        shutil.copyfile(AUX/name,OUT/name)
    f=r.read(r.FREEZE);r.verify(f['source_sha256']);r.verify(f['input_sha256']);r.verify(f['scientific_source_sha256'])
    source_analysis=r.sha(r.OUT/'statistics.json');source_audit=r.sha(r.OUT/'audit.json')
    log=ROOT/'Research_Log.md';old=log.read_bytes();stamp=datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
    text=f'''

## {stamp}（北京时间）｜A主线TRAIN公开决策与完整后继标签准入审计归档

- 先本地冻结`28403b6a106e1c482f5547880489c0987ac5e5f5`，20文件244795字节，
  实际Git／磁盘一致。22项合成测试开发／正式各执行22，不算44项新测试；
  原2695科学检查与编译按1393源码和输入SHA复用，没有重复仿真。
  依赖、235.6713475秒秘密扫描、索引基本／EXTRA和两差异检查通过。
- 一次worker186.4123833秒完整登记TRAIN648（18独立组）与NATIVE36，
  所有47任务失败保留。TRAIN564对真实前后视图、542返回后存活、
  3296实际窗口；84边界前结束、22获取中结束保留，不补B时状态。
  NATIVE36只验证，不训练；19来源组、36完整分层格及216固定T覆盖格保留。
- 271条实际BLOCK完整事实标签只对应实际T；RANDOM终局属于真实随机后继。
  59条观察到全程同T的RANDOM也可能受未来序列／停止筛选影响，不自动成为
  未加权固定T标签；没有其他三个T、自适应接收者或不同轨迹的反事实补值。
  理论正概率／有限兼容／事实监督准入／因果价值资格分别说明。
- 移动前积分取ACQUISITION_CHOICE.before_memory，返回取TASK_MEMORY_RETURN，
  均先于后续WINDOW_DECISION。保留实际历史、raw_policy、命令、phase、
  控制器、积分和预算；seed／条件／未来行为及完整调度哈希留在元数据。
  独立读取器从已完成命令及实际交付STEP_COMPLETE.after重建，主模块全部
  自定义函数禁用。JSON解码过含私有字段的混合events字节，但真实扰动、
  噪声、oracle执行动作与witness未进入输入；原物理审计复用，不重仿真。
- 八个gzip流读取1216692行、5865095092解码字节，无新增原始大副本。
  冻结回执121240是步／窗口／案例／面板的固定核对记账量，未仪表计数
  assert调用次数，不宣称标量字段数或独立样本数；精确分解另存。全部
  新环境／reset／帧／政策与模型查询／拟合／训练／种子／在线LLM均0。
- 条件配对在移动前的声明输入相同；普通8步任务延续与移动测量后都出现
  差异。不能由此称一般不可识别或纯信息收益，按条件混合分布学习期望
  风险仍可能有效。保留同历史被动适应、完整风险／序贯DR、简单PI和全部
  强参考。当前允许有限事实完整程序风险参考的数据准入，不称新算法。
- 结果`{SOURCE}`：27文件4579651字节与实际Git／磁盘一致，198.0749942秒
  结果秘密扫描通过；随后纯文字计数澄清补充另做实际索引基本／EXTRA、
  编译及差异检查，原冻结分析及先前索引快照保留，未重新读取科学gzip。
  主统计SHA`{source_analysis}`、独立审计SHA`{source_audit}`。
- 推送前67阶段文件9385298字节逐项核对实际归档Git／来源／磁盘，省略0；
  10771归档文件、57新源对象秘密扫描、9382047新Git字节哈希。普通快进
  远端`{ARCHIVE}`再次核对，无合并／强推。旧133分片按精确Git身份复用
  历史实际恢复证明，本次无新恢复。此条远端确认后追加，元数据仅本地提交。
- 完整原始QUAL仍本地保留，ZIP／分片／三次恢复继续待空间，不以小型
  数据准入报告代替。下一训练／采集、更新律和自身历史独立任务资格须
  另行冻结；不复活旧接收者、调整旧QUAL或把测试／监督标签当论文贡献。
  [中文报告](reports/train_decision_contract_v1_zh.md)。尚无合格新机制或
  独立完整任务优势，A和CCF A目标保持完整且未完成。
'''
    with log.open('ab') as stream:stream.write(text.encode('utf-8'))
    r.need(log.read_bytes()[:len(old)]==old,'append-only exact old log bytes')
    r.write(OUT/'complete.json',dict(integrity='PASSED_TRAIN_CONTRACT_ARCHIVE_APPEND_ONLY_LOG',source_local_commit=SOURCE,
        remote_archive_commit=ARCHIVE,phase_published=67,phase_bytes=9385298,phase_omitted=0,
        previous_log_bytes=len(old),previous_log_sha256=hashlib.sha256(old).hexdigest(),new_log_sha256=r.sha(log),append_only=True,
        scientific_source_files_unchanged=1393,full_QUAL_raw_delivery_complete=False,counters=r.ZERO,publication_goal_complete=False))
    owned={'Research_Log.md'}|{p.relative_to(ROOT).as_posix() for p in OUT.iterdir() if p.is_file()}
    def stage(label):
        spec=OUT/(label+'.nul');owned.add(spec.relative_to(ROOT).as_posix());spec.write_bytes(b'\0'.join(n.encode() for n in sorted(owned))+b'\0')
        for flags in ((),('--renormalize',)):r.git('add',*flags,'--pathspec-from-file='+spec.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    stage('owned_initial')
    r.write(OUT/'index_disk_proof.json',dict(integrity='PASSED_APPEND_ONLY_LOG_AND_METADATA_INDEX',objects=check_index(owned)))
    owned.update(p.relative_to(ROOT).as_posix() for p in OUT.iterdir() if p.is_file());stage('owned_final')
    objects=check_index(owned)
    print(dict(integrity='PASSED_READY_FOR_LOCAL_ARCHIVE_LOG_COMMIT',files=len(objects),bytes=sum(v['bytes'] for v in objects.values())),flush=True)


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');main()

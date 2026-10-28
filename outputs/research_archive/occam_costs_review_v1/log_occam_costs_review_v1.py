"""Append the verified compact archive and preserve all frozen science bytes."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import hashlib,json,shutil,subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
OUT=ROOT/'outputs/research_archive/occam_costs_review_v1'
SOURCE='017ba38e7c147cc88ac197218ef1bf69f391b3c6';COSTS='0fd53ae7fb82673ae744f5bca1e7d01f04021cc3'
ARCHIVE='4641010f67defc641b113c950a96aec275a2e83a'
RUN=ROOT/'outputs/occam_reference_qualification_v1/qualification_v1/occam_reference_qualification_v1_20261028T125131Z_7abaec83b085'


def git(*args):return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT)
def read(p):return json.loads(p.read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,value):
    with p.open('x',encoding='utf8',newline='\n') as f:json.dump(value,f,indent=2,ensure_ascii=False);f.write('\n')


def main():
    remote=read(OUT/'remote_receipt.json');local=read(OUT/'local_receipt.json');catalog=read(OUT/'catalog.json')
    assert remote['integrity']==local['integrity']=='PASSED' and remote['remote_after']==local['archive_commit']==ARCHIVE
    assert git('rev-parse','HEAD').decode().strip()==SOURCE and not git('status','--porcelain','--untracked-files=no').strip()
    assert git('ls-remote','--heads','origin','refs/heads/'+remote['branch']).decode().split()[0]==ARCHIVE
    changed=set(git('diff','--name-only','bc588f4b27213f083198d34b16da71eec3e18773',SOURCE).decode().splitlines())
    rows=[r for r in catalog['files'] if r['path'] in changed];assert len(rows)==len(changed)==25 and all(r['published'] for r in rows)
    write(OUT/'phase_selection.json',dict(integrity='PASSED',source_local_commit=SOURCE,published=25,omitted=0,files=rows,remote_archive_commit=ARCHIVE))
    for name in ('build_occam_costs_review_v1_archive.py','log_occam_costs_review_v1.py'):shutil.copyfile(Path(__file__).parent/name,OUT/name)
    total_bytes=0
    for commit,label in ((COSTS,'costs_committed_bytes'),(SOURCE,'review_committed_bytes')):
        path=Path(__file__).parent/('occam_core_postcommit_'+commit[:12]+'.json');proof=read(path)
        assert proof['integrity']=='PASSED' and proof['commit']==commit;total_bytes+=proof['bytes']
        shutil.copyfile(path,OUT/(label+'.json'))
    assert total_bytes==235973
    m=read(RUN/'manifest.json');status=read(RUN/'qual/status.json')
    for n,h in {**m['source_sha256'],**m['input_sha256']}.items():assert sha(ROOT/n)==h,n
    assert not (ROOT/'outputs/occam_qualification_costs_v1/analysis_v1').exists()
    assert not (ROOT/'outputs/occam_first_window_diagnostic_v1/analysis_v1').exists()
    log=ROOT/'Research_Log.md';old=log.read_bytes();stamp=datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
    addition=f'''

## {stamp}（北京时间）｜完整资格成本工具与A查新记录归档

- 完成成本附录工具冻结`{COSTS}`（23项227801字节）及查新v9
  `{SOURCE}`（2项8172字节）。25项235973字节均核对实际Git与磁盘，
  本次全部归档，未导出当前活动QUAL案例或读取部分结局。
- 成本工具25项不同纯构造测试通过，开发23+25、正式25；正式冻结
  1.7431265秒。实际未完实验准入拒绝在任何结局读取和输出目录创建前
  发生。完整数据及原双审计／独立统计／报告管线终态后才运行一次。
  此刻完整成本分析、已冻首窗口诊断均未开始，不称完成真实资格结果。
- 成本口径分开：累计账本取逐例差分、51全部reset和设置帧；失败
  惩罚不生成物理帧；固定窗口不冒充NN声明、冻结反馈不冒充参数更新。
  eig／收集solve是代码重建，包含设置等的case wall不是隔离NN延迟。
  NN共同9000更新、单bank假设5000更新和C8完整3840步／训练3072子集
  不重复相加，旧未知费用不填0，零API的平均延迟为null。
- 查新v9补核三篇原文：partially performative prediction、performative
  control和干预影响下的条件性能监测，阅读范围／假设／未复现均披露。
  “决策引起漂移”“外部漂移共存”“残差触发测量”不足以自动成新贡献；
  政策改变访问分布也不等于改变物理转移矩阵。条件CUSUM、同历史被动
  适应、完整风险／DR、重加权和全部旧强对照要求不删减。
- OpenReview验证页未绕过，后读作者arXiv。文档辅助补扫第一次因
  默认cp1252读取中文失败；原脚本／元数据及哈希保留，仅改为显式UTF8
  复核同一文档，没有重复已过的222.3704035秒全量秘密扫描或科学试验。
- 成本全量秘密扫描225.8698284秒通过；两阶段实际暂存基本／补充秘密、
  普通及暂存差异、索引／磁盘／提交字节通过。原源码／依赖和2695项
  科学检查按不变哈希复用；1393科学源码及输入当前再次核对不变。
  新环境／reset／帧／策略或真实模型查询／拟合／训练／seed／在线LLM0。
- 远端普通快进并再次核对`{ARCHIVE}`，未合并／强推。旧133记录分片
  仅按精确Git身份复用原恢复证明，没有新恢复；原数据、全部失败、
  成本和恢复副本保留。本条只在核对远端之后追加，不递归推送日志元数据。
  [成本中文交付](reports/occam_qualification_costs_freeze_v1_zh.md)，
  [查新v9](docs/research/correction_scope_contribution_review_v9_zh.md)。
- 原一次性QUAL当前{status['status']}、{status['completed']}/1566、
  {status['control_steps']}实际控制步仅运维快照。继续原完整管线；科学
  资格失败则封存接收者，不加获取门、不延长样本。没有新完整资格结论
  或A新机制／独立任务优势，CCF A目标未完成。
'''
    with log.open('ab') as f:f.write(addition.encode('utf8'))
    assert log.read_bytes()[:len(old)]==old
    write(OUT/'complete.json',dict(integrity='PASSED_COSTS_REVIEW_ARCHIVE_APPEND_LOG',source_local_commit=SOURCE,
        cost_tools_commit=COSTS,remote_archive_commit=ARCHIVE,phase_published=25,phase_omitted=0,
        previous_log_bytes=len(old),previous_log_sha256=hashlib.sha256(old).hexdigest(),new_log_sha256=sha(log),append_only=True,
        active_qual_operational_snapshot=status,scientific_source_files_unchanged=1393,new_physics=0,
        new_real_model_queries=0,online_LLM_API_calls=0,publication_goal_complete=False))
    owned={'Research_Log.md'}|{p.relative_to(ROOT).as_posix() for p in OUT.iterdir() if p.is_file()}
    def stage(label):
        p=OUT/(label+'.nul');owned.add(p.relative_to(ROOT).as_posix());p.write_bytes(b'\0'.join(n.encode() for n in sorted(owned))+b'\0')
        git('add','--pathspec-from-file='+p.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    def check():
        objects=index_bytes(owned);assert set(objects)==owned
        for name in objects:
            data=(ROOT/name).read_bytes()
            if name.endswith('.py'):compile(data,name,'exec')
            if b'\0' not in data:
                text=data.decode('utf8');assert find_secret_rule(text) is None and not any(r.search(text) for r in EXTRA.values()),name
        assert not git('diff','--check').strip() and not git('diff','--cached','--check').strip();return objects
    stage('owned_checked');write(OUT/'index_disk_proof.json',dict(integrity='PASSED',objects=check(),actual_index_basic_extra_scan=True))
    owned.add((OUT/'index_disk_proof.json').relative_to(ROOT).as_posix());stage('owned_final');check()
    print(dict(integrity='PASSED_APPEND_ONLY_COSTS_REVIEW_ARCHIVE_LOG',files=len(owned),published=25,qual_snapshot=status),flush=True)


if __name__=='__main__':main()

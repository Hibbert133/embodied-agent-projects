"""Append verified TRAIN-only analysis delivery and live independent-run status."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import hashlib,shutil,subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
OUT=ROOT/'outputs/research_archive/occam_receiver_prefix_v1';SOURCE='4fb646a93bac29fcf2b6422c60a562dad7bddf0d'
RUN=ROOT/'outputs/occam_reference_qualification_v1/qualification_v1/occam_reference_qualification_v1_20261028T125131Z_7abaec83b085'


def git(*args):return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT)


def main():
    remote=io.read(OUT/'remote_receipt.json');local=io.read(OUT/'local_receipt.json');catalog=io.read(OUT/'catalog.json')
    assert remote['integrity']==local['integrity']=='PASSED' and remote['remote_after']==local['archive_commit']=='819afbe3252e8d7fd6a45b9d22699cfd6bed6170'
    assert git('rev-parse','HEAD').decode().strip()==SOURCE and not git('status','--porcelain','--untracked-files=no').strip()
    assert git('ls-remote','--heads','origin','refs/heads/'+remote['branch']).decode().split()[0]==remote['remote_after']
    changed=set(git('diff','--name-only','66556a4e6c5212681b7e2e0943f5e5d809f1dde2',SOURCE).decode().splitlines())
    rows=[r for r in catalog['files'] if r['path'] in changed];assert len(rows)==len(changed)==42 and all(r['published'] for r in rows)
    io.write(OUT/'phase_selection.json',dict(integrity='PASSED',source_local_commit=SOURCE,published=42,omitted=0,files=rows,remote_archive_commit=remote['remote_after']))
    for name in ('build_occam_receiver_prefix_v1_archive.py','log_occam_receiver_prefix_v1.py'):
        shutil.copyfile(Path(__file__).parent/name,OUT/name)
    for prefix,label in (('dc2613875733','frozen_committed_bytes'),('4fb646a93bac','results_committed_bytes')):
        p=Path(__file__).parent/('occam_core_postcommit_'+prefix+'.json');assert io.read(p)['integrity']=='PASSED'
        shutil.copyfile(p,OUT/(label+'.json'))
    m=io.read(RUN/'manifest.json');status=io.read(RUN/'qual/status.json')
    for n,h in m['source_sha256'].items():assert io.sha(ROOT/n)==h,n
    stamp=datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S');log=ROOT/'Research_Log.md';old=log.read_bytes()
    n=status.get('completed',status.get('executions'))
    addition=f'''

## {stamp}（北京时间）｜完整TRAIN四接收者前缀支持核对

- 已完成：先提交 `dc26138757337c79c55b38bd4dfb742c5e62dae8` 软件／输入／
  20合成检查冻结，再对完整648来源／3296窗／18组和四固定接收者回放，
  2592份分析／432分层全部登记；它们不是新机器人执行或独立样本。
- 结果仅作事后训练来源内描述：各542非空来源，META两程序各493首次
  增益分歧／49全观测增益相同；ERM各484／58，各106无决定保留。首次
  分歧即停，不提交不同行为的反馈和后续query；全部接收者任务结果缺失。
  bank已经训练于该来源，即使query只取当时历史也不能称独立前瞻评价；
  全选择匹配不自动证明低层命令／物理状态相同。来源602／46不归给接收者。
- 独立dense／标量／记录／统计复算通过，禁用主provider／前向／更新／
  回放／统计函数，严格公开特征共享。主3027声明／12108候选、440分析端
  更新／求解、44148eig；独立同样声明／候选／标量更新，0求解。成本由
  2168先验会话、1073匹配反馈、1954首次分歧按冻结代码重建；
  eig=3×2168+12×3027+3×440。全分析1790.990秒<原1800秒，无重跑。
- 额外运行诊断单列：两个冻结META bank合成输入计时共2声明／8候选、
  0更新／求解，30eig按代码分支复算而非直接计数；含cProfile，与主墙钟
  重叠，不冒称实时机器人资格。新环境／reset／帧／固定策略查询／神经
  训练／批量拟合／seed／在线LLM0；模型前向和分析递归绝不统称为0。
  原始数据、全部失败、分片、恢复副本、来源费用和原六项比较全部保留。
- 交付：结果 `{SOURCE}`，秘密／补充秘密、差异、索引／磁盘和实际提交
  字节通过；1,393个当前科学来源文件哈希核对不变。远端普通快进后核对
  `{remote['remote_after']}`，本阶段42项全部发布，不合并。旧133记录分片
  按原实际恢复证明及精确Git身份复用。报告：
  [中文完整交付及全部费用](reports/occam_receiver_prefix_support_v1_delivery_zh.md)，
  [详细表](reports/occam_receiver_prefix_support_v1_zh.md)。
- 研究判断：旧R/B终局不能直接变成改变选择／后验之接收者的完整Q标签。
  不由匹配计数宣布统计覆盖或完整Q／DR理论不可用；该强参考及普通重加权
  仍必要。查新v7及补充限定已有置信门、依历史日志证实、方向不确定性／
  主动评价分配的边界，未确立新颖性。首窗口全候选诊断仍DESIGN_ONLY，
  须完整QUAL1566与记录／统计完整性通过后另冻reader，负结果也应诊断；
  没有读运行前缀结局或启动新的物理人口，不以该设计替换新获取机制。
- 下一阶段：继续同一已冻结QUAL句柄，当前{status['status']}、{n}/1566、
  {status['control_steps']}控制步只是运维快照。完整双审计和原十项主比较、
  全部费用／失败独立统计后再交付；不调参、选最好动作或补样重试。若
  不具竞争力，封存此版接收者，不围绕它加门。A的新机制、同权限完整
  风险强参考、独立完整任务优势及消融尚待证明；CCF A目标完整且未完成。
'''
    with log.open('ab') as f:f.write(addition.encode('utf8'))
    assert log.read_bytes()[:len(old)]==old
    io.write(OUT/'complete.json',dict(integrity='PASSED_RECEIVER_PREFIX_PUBLICATION_AND_APPEND_ONLY_LOG',source_local_commit=SOURCE,
        remote_archive_commit=remote['remote_after'],phase_published=42,phase_omitted=0,previous_log_bytes=len(old),
        previous_log_sha256=hashlib.sha256(old).hexdigest(),new_log_sha256=io.sha(log),append_only=True,
        active_science_manifest_id=m['manifest_id'],active_qual_collection_snapshot=status,
        active_science_source_files_verified_unchanged=len(m['source_sha256']),
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
    print(dict(integrity='PASSED_APPEND_ONLY_RECEIVER_PREFIX_LOG',owned_files=len(owned),published=42,qual_snapshot=status),flush=True)


if __name__=='__main__':main()

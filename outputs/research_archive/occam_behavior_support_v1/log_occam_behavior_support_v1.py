"""Append verified archival facts; live qualification source stays immutable."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import hashlib,shutil,subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
OUT=ROOT/'outputs/research_archive/occam_behavior_support_v1';SOURCE='d764e27f5a03edef5a5379455df567b298f87cea'
RUN=ROOT/'outputs/occam_reference_qualification_v1/qualification_v1/occam_reference_qualification_v1_20261028T125131Z_7abaec83b085'


def git(*args):return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT)


def main():
    remote=io.read(OUT/'remote_receipt.json');local=io.read(OUT/'local_receipt.json');catalog=io.read(OUT/'catalog.json')
    assert remote['integrity']==local['integrity']=='PASSED' and remote['remote_after']==local['archive_commit']=='5359d3656dd16fecc27c839b8b378bb8f8cfa8eb'
    assert git('rev-parse','HEAD').decode().strip()==SOURCE and not git('status','--porcelain','--untracked-files=no').strip()
    assert git('ls-remote','--heads','origin','refs/heads/'+remote['branch']).decode().split()[0]==remote['remote_after']
    changed=set(git('diff-tree','--no-commit-id','--name-only','-r',SOURCE).decode().splitlines());rows=[r for r in catalog['files'] if r['path'] in changed]
    assert len(rows)==len(changed)==31 and all(r['published'] for r in rows)
    io.write(OUT/'phase_selection.json',dict(integrity='PASSED',source_local_commit=SOURCE,published=31,omitted=0,files=rows,remote_archive_commit=remote['remote_after']))
    for name in ('build_occam_behavior_support_v1_archive.py','log_occam_behavior_support_v1.py'):
        shutil.copyfile(Path(__file__).parent/name,OUT/name)
    proof=Path(__file__).parent/'occam_core_postcommit_d764e27f5a03.json';assert io.read(proof)['integrity']=='PASSED'
    shutil.copyfile(proof,OUT/'source_committed_bytes.json')
    m=io.read(RUN/'manifest.json');native=io.read(RUN/'native/audit.json');status=io.read(RUN/'qual/status.json')
    assert native['integrity']=='PASSED' and native['counts']['executions']==174
    for n,h in m['source_sha256'].items():assert io.sha(ROOT/n)==h,n
    log=ROOT/'Research_Log.md';old=log.read_bytes();stamp=datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
    addition=f'''

## {stamp}（北京时间）｜A主线：行为支持核对与原生门通过

- 已完成：只读完整TRAIN648轨迹／3296实际窗口／18独立组／108完整分层；
  542非空，84在边界前结束、22获取后无任务窗口、457短窗口全部保留。
  212轨迹实际改变过增益。混合RANDOM_WINDOW／BLOCK_FIXED的工作概率不能
  每窗统一为1/4；448非空轨迹的联合因子不一致只作描述，不是价值估计。
- 验证与边界：24新合成／有限树／严格输入／文件、网络及进程护栏检查，
  独立Fraction联合式／前缀比／整组统计复算通过，主概率与统计在审计时
  禁用。首次正式24项中1个测试作用域错误已保存原源码／日志，修正后
  正式24通过才扫描完整记录；开发18＋20和失败24不当作额外独特检查。
  无新环境、reset、帧、策略查询、模型预测、训练／拟合、滤波、seed或
  在线LLM。动作核不是完整轨迹概率／合法OPE权重，不证明外生性或安全。
- 决定：未来完整Q／DR应先明确目标后继程序、信息集、序贯随机化及支持，
  不能以本检查削弱强参考或把TRAIN学到的接收者再用同一TRAIN独立校准。
  查新v6补充PRC的分布敏感性及CDT的eventually safe／批量条件，未获得
  本机器人适用保证。混合代数、风险门控和普通重加权仍不构成论文区别。
- 来源与交付：本地 `{SOURCE}`，31项／2762483字节实际Git对象逐字节核对；
  秘密／补充秘密／差异／索引与磁盘检查通过。远端普通快进并核对
  `{remote['remote_after']}`；不合并。报告：
  [完整行为支持检查](reports/occam_behavior_support_v1_zh.md)，
  [贡献复核v6](docs/research/correction_scope_contribution_review_v6_zh.md)。
  旧数据、费用、原始大文件、分片、失败和实际恢复副本继续保留。
- 独立新实验：174/174 NATIVE完整收集，两级审计通过，14894控制步／8874
  全部reset／4511470物理帧；完整记录仍在本地，尚未在此归档发布。含621
  实际窗口，独立审计重建102递归更新、28批求解，另记原C4/C8复算费用。
  这些是运维及数值门，不是任务改善。原科学冻结源哈希全部不变。
- 后续同一分配QUAL已启动，当前{status['completed']}/1566、{status['control_steps']}步
  只是运维快照，不择优、补样、重试或调参；继续收集并双审计、整组统计、
  全对照／失败中文交付。数据来源模型和主十项比较不变。无收益封存该版
  接收者，不围绕它加获取门。A的新获取机制、完整风险强参考、独立完整
  任务收益及消融仍待完成；CCF A目标完整且未完成。
'''
    with log.open('ab') as f:f.write(addition.encode('utf8'))
    assert log.read_bytes()[:len(old)]==old
    io.write(OUT/'complete.json',dict(integrity='PASSED_SUPPORT_PUBLICATION_AND_APPEND_ONLY_LOG',source_local_commit=SOURCE,
        remote_archive_commit=remote['remote_after'],phase_published=31,phase_omitted=0,previous_log_bytes=len(old),
        previous_log_sha256=hashlib.sha256(old).hexdigest(),new_log_sha256=io.sha(log),append_only=True,
        active_science_manifest_id=m['manifest_id'],active_qual_collection_snapshot=status,
        active_scientific_source_files_verified_unchanged=len(m['source_sha256']),
        no_physical_operations_from_archival=True,online_LLM_API_calls=0,publication_goal_complete=False))
    owned={'Research_Log.md'}|{p.relative_to(ROOT).as_posix() for p in OUT.iterdir() if p.is_file()}
    def stage(label):
        p=OUT/(label+'.nul');owned.add(p.relative_to(ROOT).as_posix());p.write_bytes(b'\0'.join(n.encode() for n in sorted(owned))+b'\0')
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
    print(dict(integrity='PASSED_APPEND_ONLY_SUPPORT_LOG',owned_files=len(owned),published=31,qual_snapshot=status),flush=True)


if __name__=='__main__':main()

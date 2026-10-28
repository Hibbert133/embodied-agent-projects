"""Append the research log only after the complete phase archive is verified."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import hashlib,shutil,subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import occam_native_case_io_v1 as c
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
OUT=ROOT/'outputs/research_archive/occam_complete_training_v3'


def git(*args):return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT)


def main():
    local=c.read(OUT/'local_receipt.json');remote=c.read(OUT/'remote_receipt.json');source=local['source_local_commit']
    assert local['integrity']==remote['integrity']=='PASSED' and local['archive_commit']==remote['remote_after']
    assert git('rev-parse','HEAD').decode().strip()==source and not git('status','--porcelain','--untracked-files=no').strip()
    assert git('ls-remote','--heads','origin','refs/heads/'+local['archive_branch']).decode().split()[0]==remote['remote_after']
    cat=c.read(OUT/'catalog.json');byname={r['path']:r for r in cat['files']}
    commits=['634b3454fa0dd3aceb901ba565be2d80b854ec40',source,
        '757dac24e6fccc10e3b38b3141b2f33f824a5589','2d6600c61aea7ce947e265f96eb508c32b062db6']
    names=set()
    for commit in commits:names.update(git('diff-tree','--no-commit-id','--name-only','-r',commit).decode().splitlines())
    selected=[byname[name] for name in sorted(names)];assert all(r['published'] for r in selected)
    for r in selected:assert c.sha(ROOT/r['path'])==r['sha256']
    c.write(OUT/'phase_selection.json',dict(integrity='PASSED',source_local_commit=source,commits=commits,
        remote_archive_commit=remote['remote_after'],files=selected,published=len(selected),omitted=0))
    for name in ('build_occam_complete_training_v3_archive.py','log_occam_complete_training_v3.py'):
        shutil.copyfile(Path(__file__).parent/name,OUT/name)
    proof=Path(__file__).parent/('occam_core_postcommit_'+source[:12]+'.json')
    assert c.read(proof)['integrity']=='PASSED' and c.read(proof)['commit']==source
    shutil.copyfile(proof,OUT/'source_committed_bytes.json')
    log=ROOT/'Research_Log.md';old=log.read_bytes();stamp=datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
    addition=f'''

## {stamp}（北京时间）｜完整TRAIN、一次训练与独立数学核对

- 已完成：同一冻结分配NATIVE36和TRAIN648完整结束，两级审计通过；
  TRAIN602成功、46任务失败、0技术失败／未启动。18独立组及三任务／
  两条件／三边界全部保留，84例未到边界、106例无表现窗不填造标签。
  271对活跃行为共同获取后完整状态一致，53对早结束保留，3296实际窗。
- 全部费用：新数据684执行、85789控制步、34884全部reset、17870945帧；
  实际政策78111次，独立审计另78111次。TRAIN采集9172.869秒、完整审计
  1252.287秒；Native及其他入口时间单列。旧v2的27982步／11475全部reset／
  5877410帧和更早来源另列，188项部分人口未参与新训练。
- 一次训练：1000预训练后同状态分叉4000 META／4000匹配ERM，9000 AdamW、
  72000轨迹抽取、66712训练求解，348.025秒；三预定checkpoint全部保留。
  TRAIN-only归一化，542有窗／106无窗完整披露，无择优、续训或重试。
- 独立数学核对：三bank各按固定顺序16条非空TRAIN，另918分析求解／
  89.892秒，递归与批后验最大差3.56e-14以内。它是TRAIN内一致性检查，
  不是独立预测、校准、完整任务收益或48个独立验证样本。在线LLM全程0。
- 原始交付：8450文件／83片；从本地数据提交634b345的实际Git对象恢复，
  全部字节和802542行规范压缩流解码扫描通过。1296单例gzip成员按原聚合
  压缩字节切片恢复，未重编码；原文件、ZIP和两次TRAIN恢复保留本地。
- 来源：数据 `634b3454fa0dd3aceb901ba565be2d80b854ec40`，模型／恢复交付
  `{source}`；远端 `{remote['remote_after']}` 已核对，当前
  交付／导出工具／运行时预检{len(selected)}项全部发布，普通快进、无合并。
  完整秘密扫描通过，模型及新增元数据另做实际暂存基础／补充扫描、差异
  与索引／磁盘／提交对象字节核对，1384项旧源码哈希绑定复用科学检查。
- 报告：[完整TRAIN数据](reports/occam_reference_train_data_v3_zh.md)；
  [固定训练与数学核对](reports/occam_reference_learning_v3_zh.md)。本条在
  已验证push后追加，旧日志字节前缀保持。
- 下一阶段目标：固定三bank，单独冻结独立前瞻预测及自身时序实际部署资格，
  包含META／匹配ERM适应与冻结、强C8／积分／被动适应及完整费用对照，
  不从TRAIN残差选择最终阈值。科学CAL／QUAL尚未开展；A的具体机制、
  完整程序风险／DR等同权限强参考、独立任务优势和消融仍待建立。
  负结果不筛除或复活，CCF A研究目标未完成。
'''
    with log.open('ab') as f:f.write(addition.encode('utf8'))
    assert log.read_bytes()[:len(old)]==old
    c.write(OUT/'complete.json',dict(integrity='PASSED_COMPLETE_TRAINING_ARCHIVE_AND_APPEND_ONLY_LOG',source_local_commit=source,
        remote_archive_commit=remote['remote_after'],phase_published=len(selected),phase_omitted=0,previous_log_bytes=len(old),
        previous_log_sha256=hashlib.sha256(old).hexdigest(),new_log_sha256=c.sha(log),append_only_log_verified=True,
        new_physics_during_archival=0,new_fits_during_archival=0,online_LLM_API_calls=0,publication_goal_complete=False))
    owned={'Research_Log.md'}|{p.relative_to(ROOT).as_posix() for p in OUT.iterdir() if p.is_file()}
    def stage(label):
        p=OUT/(label+'.nul');owned.add(p.relative_to(ROOT).as_posix());p.write_bytes(b'\0'.join(n.encode() for n in sorted(owned))+b'\0')
        git('add','--pathspec-from-file='+p.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    def check():
        actual=index_bytes(owned)
        for name in actual:
            raw=(ROOT/name).read_bytes()
            if b'\0' not in raw:
                text=raw.decode('utf8');assert find_secret_rule(text) is None and not any(p.search(text) for p in EXTRA.values()),name
            if name.endswith('.py'):compile(raw,name,'exec')
        assert not git('diff','--check').strip() and not git('diff','--cached','--check').strip()
        return actual
    stage('owned_checked');c.write(OUT/'index_disk_proof.json',dict(integrity='PASSED',objects=check(),actual_index_basic_extra_scan=True))
    owned.add((OUT/'index_disk_proof.json').relative_to(ROOT).as_posix());stage('owned_final');check()
    print(dict(integrity='PASSED_ARCHIVE_LOG_APPEND',owned_files=len(owned),published=len(selected),remote=remote['remote_after']),flush=True)


if __name__=='__main__':main()

"""Append checked software freeze and archive facts while frozen Native continues."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import hashlib,shutil,subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import occam_qualification_case_io_v1 as c
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
OUT=ROOT/'outputs/research_archive/occam_qualification_freeze_v1';SOURCE='7abaec83b0854f099d6f13f308cc8cd552f50e2b'
RUN=ROOT/'outputs/occam_reference_qualification_v1/qualification_v1/occam_reference_qualification_v1_20261028T125131Z_7abaec83b085'


def git(*args):return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT)


def main():
    remote=c.read(OUT/'remote_receipt.json');local=c.read(OUT/'local_receipt.json');catalog=c.read(OUT/'catalog.json')
    assert remote['integrity']==local['integrity']=='PASSED' and remote['remote_after']==local['archive_commit']=='e41a358311a7d2d33e4be1bc25a60f2853ff6c4d'
    assert git('rev-parse','HEAD').decode().strip()==SOURCE and not git('status','--porcelain','--untracked-files=no').strip()
    assert git('ls-remote','--heads','origin','refs/heads/'+remote['branch']).decode().split()[0]==remote['remote_after']
    changed=set(git('diff-tree','--no-commit-id','--name-only','-r',SOURCE).decode().splitlines());rows=[r for r in catalog['files'] if r['path'] in changed]
    assert len(rows)==len(changed)==212 and all(r['published'] for r in rows)
    c.write(OUT/'phase_selection.json',dict(integrity='PASSED',source_local_commit=SOURCE,published=212,omitted=0,files=rows,remote_archive_commit=remote['remote_after']))
    for name in ('build_occam_qualification_freeze_v1_archive.py','log_occam_qualification_freeze_v1.py'):
        shutil.copyfile(Path(__file__).parent/name,OUT/name)
    proof=Path(__file__).parent/'occam_core_postcommit_7abaec83b085.json';assert c.read(proof)['integrity']=='PASSED'
    shutil.copyfile(proof,OUT/'source_committed_bytes.json')
    status=c.read(RUN/'native/status.json');m=c.read(RUN/'manifest.json')
    log=ROOT/'Research_Log.md';old=log.read_bytes();stamp=datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
    addition=f'''

## {stamp}（北京时间）｜独立自身历史表现参考：冻结与新采集

- 已完成：严格公开模型提供器、连续主机、隔离完整案例进程、两级记录审计、
  独立dense／标量／批后验、整组统计与独立复算、中文报告入口先提交冻结。
  META／匹配ERM的适应与冻结四因素全部保留，不从旧人口选bank或改beta。
- 强参考补齐：三获取×四同前缀固定T／四学习程序共24，再加三条从第0步
  保持增益的全时PI与DIRECT_C8／MOVE_INTEGRAL，共29真实程序。全时0.5与
  已有同一程序按精确别名引用、费用一次。主程序须同时通过十个预定强
  参考的完整截止损失95%差上界<0；数值、前瞻预测与任务收益分别判断。
- 预算冻结：NATIVE174后一次QUAL1566，九独立QUAL组、各时点三组；合计
  1740执行／870000控制步／88740全部reset／48720000帧。在线递归最多11160，
  原C4/C8最多240估计，审计复算／求解另计。历史训练、旧不完整v2、原C8
  名义训练及完整来源费用分别绑定，重叠费用不相加、不按程序数重复乘计。
- 软件检查：最终34新检查＋2661源码绑定复用＝2695不同检查；编译、依赖、
  双种子解析、秘密、差异及索引／磁盘／提交字节通过。原schema比较失败、
  早期正式通过版本、元数据写入／Git换行处理错误和代码快照全部保留。
  旧根属性与科学源码未改，原始日志字节按新子树局部属性保存；数组假句柄
  回调不冒称物理案例。数值源码未因结果改变，所有软件检查无新机器人／
  真实worker／在线LLM。新增原生采集费用从下一项单独开始。
- 来源：本地冻结 `{SOURCE}`；已核对远端 `{remote['remote_after']}`，
  本阶段212项全部发布，普通快进、不合并。报告：
  [资格实现冻结](reports/occam_reference_qualification_freeze_v1_zh.md)，
  [独立协议](docs/protocols/occam_reference_qualification_v1_zh.md)。
- 新分配：`{m['manifest_id']}`，源码{SOURCE[:12]}。一次已启动NATIVE，当前
  {status['completed']}/174、{status['control_steps']}控制步只是此刻运维快照，不能作为完整人口或晋级。
  首个META与ERM适应程序各真实执行四个窗口、三次完整反馈更新；全程
  项目在线LLM0。QUAL尚待本NATIVE完整双审计；未补样、重试或执行旧保留范围。
- 下一阶段目标：继续同一已登记句柄，完整NATIVE双审计后才能同分配QUAL，
  独立前瞻预测／任务门与全部失败中文交付。无收益封存这版接收者，不围绕
  它追加获取门控或改主程序。A的新机制、完整Q／DR／廉价重加权等强参考、
  真正独立任务优势和消融仍待证明；本次软件与标准参考不完成CCF A目标。
'''
    with log.open('ab') as f:f.write(addition.encode('utf8'))
    assert log.read_bytes()[:len(old)]==old
    c.write(OUT/'complete.json',dict(integrity='PASSED_FROZEN_SOFTWARE_PUBLICATION_AND_APPEND_ONLY_LOG',source_local_commit=SOURCE,
        remote_archive_commit=remote['remote_after'],phase_published=212,phase_omitted=0,previous_log_bytes=len(old),
        previous_log_sha256=hashlib.sha256(old).hexdigest(),new_log_sha256=c.sha(log),append_only=True,
        active_science_manifest_id=m['manifest_id'],active_collection_snapshot=status,
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
    stage('owned_checked');c.write(OUT/'index_disk_proof.json',dict(integrity='PASSED',objects=check(),actual_index_basic_extra_scan=True))
    owned.add((OUT/'index_disk_proof.json').relative_to(ROOT).as_posix());stage('owned_final');check()
    print(dict(integrity='PASSED_APPEND_ONLY_FREEZE_LOG',owned_files=len(owned),published=212,collection_snapshot=status),flush=True)


if __name__=='__main__':main()

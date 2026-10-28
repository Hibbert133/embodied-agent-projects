"""Record verified archive and append the finished software phase to the log."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import hashlib,shutil,subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
OUT=ROOT/'outputs/research_archive/occam_first_window_freeze_v1'
SOURCE='bb8fb0715b1b0719ea956051f808026b071a16ae'
ARCHIVE='517f41ce528d951963388e3d52530952253aa4a3'
RUN=ROOT/'outputs/occam_reference_qualification_v1/qualification_v1/occam_reference_qualification_v1_20261028T125131Z_7abaec83b085'


def git(*args):return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT)


def main():
    remote=io.read(OUT/'remote_receipt.json');local=io.read(OUT/'local_receipt.json');catalog=io.read(OUT/'catalog.json')
    assert remote['integrity']==local['integrity']=='PASSED' and remote['remote_after']==local['archive_commit']==ARCHIVE
    assert git('rev-parse','HEAD').decode().strip()==SOURCE and not git('status','--porcelain','--untracked-files=no').strip()
    assert git('ls-remote','--heads','origin','refs/heads/'+remote['branch']).decode().split()[0]==ARCHIVE
    changed=set(git('diff','--name-only','263f1b581548c7d95277cf8acd6dad91da0b2454',SOURCE).decode().splitlines())
    published=[r for r in catalog['files'] if r['path'] in changed]
    assert len(published)==len(changed)==24 and all(r['published'] for r in published)
    io.write(OUT/'phase_selection.json',dict(integrity='PASSED',source_local_commit=SOURCE,remote_archive_commit=ARCHIVE,published=24,omitted=0,files=published))
    for name in ('build_occam_first_window_freeze_v1_archive.py','log_occam_first_window_freeze_v1.py'):
        shutil.copyfile(Path(__file__).parent/name,OUT/name)
    proof=Path(__file__).parent/'occam_core_postcommit_bb8fb0715b1b.json'
    assert io.read(proof)['integrity']=='PASSED';shutil.copyfile(proof,OUT/'frozen_committed_bytes.json')
    m=io.read(RUN/'manifest.json');status=io.read(RUN/'qual/status.json')
    for n,h in {**m['source_sha256'],**m['input_sha256']}.items():assert io.sha(ROOT/n)==h,n
    assert not (ROOT/'outputs/occam_first_window_diagnostic_v1/analysis_v1').exists()
    stamp=datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
    log=ROOT/'Research_Log.md';old=log.read_bytes();n=status.get('completed',status.get('executions'))
    addition=f'''

## {stamp}（北京时间）｜首窗口四候选只读诊断实现冻结

- 已完成：基于先前DESIGN_ONLY稿实现独立版本reader、完整人口及分层
  汇总、严格终态准入、独立literal reader／Fraction复算器，先提交
  `{SOURCE}`。24项软件／协议／测试／回执、276212实际Git字节核对一致。
  **没有本诊断全人口结果**；当前QUAL源码、输入、配置与主比较均不改变。
- 设计范围：原1566执行全登记，1296条同前缀程序／162起点／216完整格；
  Native174另列。核对原生／Python见证、历史／物理前缀、完整任务记忆、
  噪声游标、时钟、保存声明与实际所选首窗；所有失败／早停／短窗／缺失
  保留。只取实际对齐的四固定T窗作事实向量，没有新模型调用或未执行
  轨迹。首窗排序与固定程序终局对应是事后描述，不能贴给自适应接收者。
- 验证：43个不同数组／构造记录测试全部通过，开发40+43及正式43，共
  126次执行而非126新测试。原科学1393文件及全部冻结输入哈希不变；原
  资格2695检查按源码／回执复用，新工具编译和依赖检查通过。全量tracked
  秘密扫描、实际暂存基本／补充秘密、差异、索引／磁盘／实际提交字节
  检查通过，所有执行回执保留；没有重复原仿真测试。
- 准入实测：真实活动run缺终态标志，在读取任何QUAL结局前拒绝，未建
  analysis目录。未来须原1566收集、两级审计、原统计与独立统计完整性及
  pipeline终态均通过后一次分析；负科学门可进入，部分／技术关闭不进入。
  主分析加复算1800秒，新增普通读写、SHA遍历／字节与数组费用另记。
- 新增环境／reset／物理帧／政策查询／模型前向／后验更新／拟合／训练／
  seed／在线LLM API均0；不把项目历史或当前QUAL实际成本归零。原始记录、
  全部负结果、分片、恢复副本及来源费用不变。来源前缀审计的440次分析
  更新属于上一阶段，不能说本工具又做过那些计算。
- 归档：普通快进push后独立核对远端 `{ARCHIVE}`，24项冻结文件全部发布、
  省略0；当前QUAL活动原始文件不在此快照，不合并／强推。旧133记录分片
  按精确Git对象与原实际恢复证明复用，归档不产生新恢复或物理活动。
  [中文交付](reports/occam_first_window_diagnostic_freeze_v1_zh.md)，
  [冻结协议](docs/protocols/occam_first_window_diagnostic_v1_zh.md)。
- 下一阶段：继续同一QUAL句柄，{status['status']}、{n}/1566、
  {status['control_steps']}步仅运维快照。完整原审计／统计后再执行冻结诊断，
  不看中途结局调参、加样本、换主方法或给失败接收者加获取门。A主线的
  具体机制、完整Q／DR与简单重加权强参考、独立完整任务收益、新颖性和
  消融仍待完成；软件冻结与标准参考资格不完成CCF A目标。
'''
    with log.open('ab') as f:f.write(addition.encode('utf8'))
    assert log.read_bytes()[:len(old)]==old
    io.write(OUT/'complete.json',dict(integrity='PASSED_FIRST_WINDOW_FREEZE_ARCHIVE_AND_APPEND_ONLY_LOG',source_local_commit=SOURCE,
        remote_archive_commit=ARCHIVE,phase_published=24,phase_omitted=0,previous_log_bytes=len(old),previous_log_sha256=hashlib.sha256(old).hexdigest(),
        new_log_sha256=io.sha(log),append_only=True,active_science_manifest_id=m['manifest_id'],active_qual_collection_snapshot=status,
        active_science_source_files_verified_unchanged=1393,analysis_started=False,new_environment_interactions=0,online_LLM_API_calls=0,publication_goal_complete=False))
    owned={'Research_Log.md'}|{p.relative_to(ROOT).as_posix() for p in OUT.iterdir() if p.is_file()}
    def stage(label):
        p=OUT/(label+'.nul');owned.add(p.relative_to(ROOT).as_posix());p.write_bytes(b'\0'.join(x.encode() for x in sorted(owned))+b'\0')
        git('add','--pathspec-from-file='+p.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    def check():
        actual=index_bytes(owned)
        for name in actual:
            raw=(ROOT/name).read_bytes()
            if b'\0' not in raw:
                text=raw.decode('utf8');assert find_secret_rule(text) is None and not any(p.search(text) for p in EXTRA.values()),name
            if name.endswith('.py'):compile(raw,name,'exec')
        assert not git('diff','--check').strip() and not git('diff','--cached','--check').strip();return actual
    stage('owned_checked');io.write(OUT/'index_disk_proof.json',dict(integrity='PASSED',objects=check(),actual_index_basic_extra_scan=True))
    owned.add((OUT/'index_disk_proof.json').relative_to(ROOT).as_posix());stage('owned_final');check()
    print(dict(integrity='PASSED_APPEND_ONLY_FIRST_WINDOW_FREEZE_LOG',owned_files=len(owned),published=24,qual_snapshot=status),flush=True)


if __name__=='__main__':main()

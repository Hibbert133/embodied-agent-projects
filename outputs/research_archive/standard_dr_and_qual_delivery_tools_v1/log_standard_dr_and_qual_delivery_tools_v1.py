"""Append verified software-only archive, preserving scientific source bytes."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import hashlib,shutil,subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
OUT=ROOT/'outputs/research_archive/standard_dr_and_qual_delivery_tools_v1'
SOURCE='912799da8cf7be6eed12b2598956663ff7497cc3';ARCHIVE='89c1f0dfdfac50a85beb35533c0f141de336691f'
QUAL_TOOLS='737471225e796cc12018c32b97f87296abe486fd'
RUN=ROOT/'outputs/occam_reference_qualification_v1/qualification_v1/occam_reference_qualification_v1_20261028T125131Z_7abaec83b085'


def git(*args):return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT)


def main():
    remote=io.read(OUT/'remote_receipt.json');local=io.read(OUT/'local_receipt.json');catalog=io.read(OUT/'catalog.json')
    assert remote['integrity']==local['integrity']=='PASSED' and remote['remote_after']==local['archive_commit']==ARCHIVE
    assert git('rev-parse','HEAD').decode().strip()==SOURCE and not git('status','--porcelain','--untracked-files=no').strip()
    assert git('ls-remote','--heads','origin','refs/heads/'+remote['branch']).decode().split()[0]==ARCHIVE
    changed=set(git('diff','--name-only','22a9cc59ed403c520417c6ea53397fcb56884725',SOURCE).decode().splitlines())
    rows=[r for r in catalog['files'] if r['path'] in changed];assert len(rows)==len(changed)==51 and all(r['published'] for r in rows)
    io.write(OUT/'phase_selection.json',dict(integrity='PASSED',source_local_commit=SOURCE,published=51,omitted=0,files=rows,remote_archive_commit=ARCHIVE))
    for name in ('build_standard_dr_and_qual_delivery_tools_v1_archive.py','log_standard_dr_and_qual_delivery_tools_v1.py'):
        shutil.copyfile(Path(__file__).parent/name,OUT/name)
    for prefix,label in (('737471225e79','qual_tools_committed_bytes'),('912799da8cf7','dr_component_committed_bytes')):
        path=Path(__file__).parent/('occam_core_postcommit_'+prefix+'.json');assert io.read(path)['integrity']=='PASSED'
        shutil.copyfile(path,OUT/(label+'.json'))
    m=io.read(RUN/'manifest.json');status=io.read(RUN/'qual/status.json')
    for name,h in {**m['source_sha256'],**m['input_sha256']}.items():assert io.sha(ROOT/name)==h,name
    assert not (ROOT/'outputs/occam_reference_qualification_v1/qual_delivery_v1').exists()
    stamp=datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
    log=ROOT/'Research_Log.md';old=log.read_bytes();n=status.get('completed',status.get('executions'))
    addition=f'''

## {stamp}（北京时间）｜完整结果交付准备与标准DR算子归档

- 已完成两个软件阶段：`{QUAL_TOOLS}` 完整QUAL结果导出／实际Git恢复
  工具，27项235185字节；`{SOURCE}` 标准序贯DR纯数组组件，24项
  228629字节。实际Git／磁盘逐字节核对均通过；本次51项全部归档，
  没有真实QUAL导出／恢复或离策略收益计算，不将软件成功称为真实任务结果。
- 交付工具12不同构造／微型ZIP检查，开发／正式各12；绑定原bundle13
  检查和终态准入43检查。保留1566×13案例文件、3132字节别名及原报告／
  全分配／失败／独立统计／522格／费用的完整性约束，仅归档恢复明确
  不与本地原始文件独立对比。新来源清单CRLF首次暂存失败及原字节保留，
  只规范新元数据LF；没有改科学程序或为换行重复仿真检查。
- DR组件是Jiang与Li2016的标准估计式，不是新算法或已部署强参考。
  34不同检查，开发／正式各34；正式111估计尝试／99返回、99反向审计
  尝试／3组汇总，含故意非法／篡改拒绝。16构造噪声叶节点跨设置复用，
  不是新科学人口。共享Fraction库披露，独立反向递推不调用主估计器。
  完整Q拟合、真实日志支持／来源审计、有效精度和自身历史部署均尚缺。
- 明确边界：16步费用不能改名完整Q；首零权重后不构造目标后缀状态／
  后验；完整源失败保留。支持缺失记null并阻止完整均值，不裁权或把
  超界DR点剪回0–500；估计量范围不是任务损失上限。离线推断可晚于旧
  结果，但特征只能用当时历史且目标／Q训练与评价组独立，ID格式不提供
  真实来源／正性或泄漏证书。旧两头DR重参数化设计继续关闭。
- 新查新v8补足Poke正式方法pp4–6的文字及渲染核对，MDE／OCCAM／GAUGE
  复核有重叠，未冒称四篇新发现。探索改变起点、估计器跟随当前策略
  数据、连续无重置、任务测度变化的需要均已有近邻。Poke全文20MB缓存
  仅本地，远端只存来源SHA／阅读范围；首次16MiB取回失败与MIME限制
  记录保留。新颖性、全部强参考、独立完整任务优势和消融仍缺证据。
- 全量／实际暂存基本与补充秘密、差异、源码编译／依赖、源1393文件
  与输入哈希不变、索引／磁盘及实际提交字节均通过。新环境／reset／
  帧／政策或真实模型查询／拟合／训练／seed／在线LLM为0，普通合成算术
  和读取耗时另记。旧原始记录、失败、分片、恢复副本和费用不变；归档
  对133旧记录分片仅按精确Git身份复用原实际恢复证明，没有新恢复。
- 远端普通快进后再次核对 `{ARCHIVE}`，不合并／强推；活动QUAL原始
  文件没有发布为完整结果。本次已更新Research_Log，只追加新段。
  [DR中文交付](reports/full_program_dr_software_v1_zh.md)，
  [结果交付工具](reports/occam_qualification_result_delivery_tools_v1_zh.md)。
- 下一步继续原一次性QUAL句柄，当前{status['status']}、{n}/1566、
  {status['control_steps']}控制步仅运维快照。完整双审计／原独立统计／
  已冻首窗诊断及完整结果恢复仍优先；不修改原门、加样本或给失败版本
  加获取门。此标准组件不完成A新机制或CCF A研究目标。
'''
    with log.open('ab') as f:f.write(addition.encode('utf8'))
    assert log.read_bytes()[:len(old)]==old
    io.write(OUT/'complete.json',dict(integrity='PASSED_STANDARD_DR_AND_QUAL_TOOLS_ARCHIVE_APPEND_LOG',source_local_commit=SOURCE,
        prior_qual_tools_commit=QUAL_TOOLS,remote_archive_commit=ARCHIVE,phase_published=51,phase_omitted=0,
        previous_log_bytes=len(old),previous_log_sha256=hashlib.sha256(old).hexdigest(),new_log_sha256=io.sha(log),append_only=True,
        active_qual_collection_snapshot=status,scientific_source_files_unchanged=1393,new_real_data_estimation=False,
        new_robot_interactions=0,online_LLM_API_calls=0,publication_goal_complete=False))
    owned={'Research_Log.md'}|{p.relative_to(ROOT).as_posix() for p in OUT.iterdir() if p.is_file()}
    def stage(label):
        p=OUT/(label+'.nul');owned.add(p.relative_to(ROOT).as_posix());p.write_bytes(b'\0'.join(x.encode() for x in sorted(owned))+b'\0')
        git('add','--pathspec-from-file='+p.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    def check():
        actual=index_bytes(owned)
        for name in actual:
            raw=(ROOT/name).read_bytes()
            if name.endswith('.py'):compile(raw,name,'exec')
            if b'\0' not in raw:
                text=raw.decode('utf8');assert find_secret_rule(text) is None and not any(x.search(text) for x in EXTRA.values()),name
        assert not git('diff','--check').strip() and not git('diff','--cached','--check').strip();return actual
    stage('owned_checked');io.write(OUT/'index_disk_proof.json',dict(integrity='PASSED',objects=check(),actual_index_basic_extra_scan=True))
    owned.add((OUT/'index_disk_proof.json').relative_to(ROOT).as_posix());stage('owned_final');check()
    print(dict(integrity='PASSED_APPEND_ONLY_SOFTWARE_ARCHIVE_LOG',files=len(owned),published=51,qual_snapshot=status),flush=True)


if __name__=='__main__':main()

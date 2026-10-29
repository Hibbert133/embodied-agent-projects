"""Append a verified compact publication, then stage local metadata only."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import hashlib
import shutil
import sys

ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');AUX=Path(__file__).parent
sys.path.insert(0,str(ROOT/'outputs/low_rank_risk_recovery_v2/tools'))
import run_saved_v2 as s
r=s.r
sys.path.insert(0,str(ROOT/'outputs/train_decision_contract_v1/tools'))
from freeze_contract_v1 import check_index
OUT=ROOT/'outputs/research_archive/low_rank_risk_pilot_v1'


def main():
    source=sys.argv[1];recovery_freeze=sys.argv[2]
    remote=r.read(OUT/'remote_receipt.json');pre=r.read(OUT/'prepublication_proof.json');local=r.read(OUT/'local_receipt.json')
    archive=remote['remote_after']
    r.need(remote['integrity']==local['integrity']=='PASSED' and archive==local['archive_commit']==pre['archive_commit'],'verified remote archive')
    r.need(r.git('rev-parse','HEAD').decode().strip()==source and not r.git('status','--porcelain','--untracked-files=no').strip(),'clean result source')
    r.need(r.git('ls-remote','--heads','origin','refs/heads/'+remote['branch']).decode().split()[0]==archive,'independent remote readback')
    totals=[]
    commits=[('00d40b1673fb9ffe8d524f211952710fa7731618','previous_archive_metadata_committed_bytes'),
        (s.INITIAL_COMMIT,'pilot_freeze_committed_bytes'),('54c5071687fd4ca1759674446760b193b9640323','first_recovery_freeze_committed_bytes'),
        (recovery_freeze,'recovery_v2_freeze_committed_bytes'),(source,'result_committed_bytes')]
    for commit,label in commits:
        path=AUX/('occam_core_postcommit_'+commit[:12]+'.json');proof=r.read(path)
        r.need(proof['integrity']=='PASSED' and proof['commit']==commit,'actual source object proof')
        totals.append((proof['object_count'],proof['bytes']));shutil.copyfile(path,OUT/(label+'.json'))
    r.need(sum(n for n,b in totals)==pre['phase_files'] and sum(b for n,b in totals)==pre['phase_bytes'] and pre['phase_omitted']==0,'all published phase bytes')
    for name in ('build_low_rank_pilot_archive_v1.py','verify_low_rank_pilot_prepublication_v1.py','log_low_rank_pilot_archive_v1.py'):
        shutil.copyfile(AUX/name,OUT/name)
    f=r.read(s.FREEZE)
    for key in ('source_sha256','input_sha256','scientific_source_sha256'):r.verify(f[key])
    original=ROOT/'outputs/occam_reference_qualification_v1/qualification_v1/occam_reference_qualification_v1_20261028T125131Z_7abaec83b085/statistics_v1/statistics.json'
    r.need(r.sha(original)=='dccede3a2838fb1ef98c20bab5e89080bcd42c8a53629c1ad22d646ae6fb75bc','old comparisons unchanged')
    stats=r.read(s.OUT/'statistics.json');worker=r.read(s.OUT/'worker_complete.json');decision=r.read(s.BASE/'presentation_v1/research_decision.json')
    presentation=r.read(s.BASE/'presentation_v1/presentation_validation.json')
    primary=stats['programs']['RBF_RR2'];full=stats['programs']['RBF_FULL'];catalog=r.read(OUT/'catalog.json')
    log=ROOT/'Research_Log.md';before=log.read_bytes();stamp=datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
    addition=f'''

## {stamp}（北京时间）｜A主线低秩完整风险TRAIN开发及只读恢复归档

- 实现与协议先冻结`{s.INITIAL_COMMIT}`，21文件239436字节；
  原22项数组测试、依赖、秘密、实际索引／磁盘、差异与源码SHA通过。
  来源旧A1 TRAIN54单位／9组／648实际执行，仅48节点有公开PRE；
  原完整CAL／TEST／QUAL未进入本轮数值学习。旧2695科学检查按1393源码复用。
- 唯一主学习运行保存20共享base、180投影解后，在旧NPZ读取时因延迟
  加载cp437被文件守卫拒绝。failure、stderr、人口、缓存、全部模型保留；
  未重训或覆盖。原20主求解／50特征分解及独立20增广LS／20QR／20核eig／
  40秩SVD／20PCA SVD由冻结控制流与保存工件推断，不冒称持久化实测ledger。
- 第一只读恢复冻结54c5071687fd4ca1759674446760b193b9640323，11项数组检查；
  实际因错误截距断言pᵀalpha=0失败，保留全部failure和输出。正确条件为
  1ᵀalpha=0，v2用带权零核反例独立验证，没有更改模型、容差或科学判定。
- 修正后的独立恢复冻结`{recovery_freeze}`，正式12项无拟合检查，
  其中相对v1新增1项，连同原22项共34项独特检查，三次正式执行总45项；
  新增一次编译检查修正了提交前语法括号错误，未触及原worker或重启拟合。
  原模型／输入SHA、原失败与主候选不变。恢复禁止solve／LS／eig／SVD／QR，
  使用20正规方程、60完整谱基和180投影代数证书，双公式保存模型预测与
  旧STATIC两全秩参数核对。原独立LS回执未写出，故原worker仍记失败。
- 一次只读恢复{worker['wall_ns']/1e9:.6f}秒，新增风险拟合／谱分解0，
  360批保存模型预测；来源重新解码及IO单列。全部31程序×54=1674条
  事实分支选择和独立统计重建，非1674次新机器人执行。提前终止6节点
  留在分母，所有{presentation['source_failures']}来源任务失败、558分格、279逐组行及31配对选率面板保留。
- 唯一主候选RBF_RR2：{primary['success']}/54，平均完整截止损失
  {primary['mean_deadline_loss']:.6f}；全秩RBF_FULL为{full['mean_deadline_loss']:.6f}。
  七项预定必要点条件{stats['necessary_development_point_condition']}，
  研究决定`{decision['status']}`。不按次要核／秩挑胜者或加门控救活失败版本。
  预测MSE、数值合法、完整任务损失分别报告，九LOO训练集合重叠不当独立资格。
- 标准核降秩岭、PCA、排序和低秩共享已有研究；本项是事后TRAIN开发，
  不证明新机制、最终自身历史收益或CCF A。旧各负结果和任务资格门不变。
  DIRECT_C8／积分及检测／历史／任务获取／完整风险等最终强对照不能删减。
  新环境／reset／帧／政策查询／响应模型训练／机器人种子／在线LLM全0；
  历史648执行／77563控制步／33048全部重置／16911815帧费用另列。
- 结果提交`{source}`，推送前{pre['phase_files']}阶段文件／
  {pre['phase_bytes']}字节逐项核对实际归档／来源／磁盘，省略0；
  {catalog['selected_files']}项归档，新增Git字节哈希{catalog['new_actual_git_bytes_hashed']}，
  新扫描{catalog['newly_secret_scanned_blob_objects']}对象。普通快进远端
  `{archive}`，独立再读回，无强推／合并。旧133分片按精确Git身份复用
  实际恢复证明，本次无新恢复。确认后追加本条，元数据只本地提交。
- [中文报告](reports/low_rank_risk_pilot_v1_zh.md)。原十项统计dccede3a…
  不变。完整原始QUAL保留本地，ZIP／分片／三次恢复仍待空间。A与CCF A
  完整目标尚未完成，不用检查、标准工程试验或归档代替研究贡献。
'''
    with log.open('ab') as stream:stream.write(addition.encode('utf-8'))
    r.need(log.read_bytes()[:len(before)]==before,'append-only research log')
    r.write(OUT/'complete.json',dict(integrity='PASSED_LOW_RANK_PILOT_ARCHIVE_AND_APPEND_ONLY_LOG',source_local_commit=source,
        remote_archive_commit=archive,phase_published=pre['phase_files'],phase_bytes=pre['phase_bytes'],phase_omitted=0,
        prior_log_bytes=len(before),prior_log_sha256=hashlib.sha256(before).hexdigest(),new_log_sha256=r.sha(log),append_only=True,
        full_QUAL_raw_delivery_complete=False,new_environment_interactions=0,online_LLM_API_calls=0,publication_goal_complete=False))
    owned={'Research_Log.md'}|{p.relative_to(ROOT).as_posix() for p in OUT.iterdir() if p.is_file()}
    def stage(label):
        spec=OUT/(label+'.nul');owned.add(spec.relative_to(ROOT).as_posix());spec.write_bytes(b'\0'.join(n.encode() for n in sorted(owned))+b'\0')
        for flags in ((),('--renormalize',)):r.git('add',*flags,'--pathspec-from-file='+spec.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    stage('owned_initial');r.write(OUT/'index_disk_proof.json',dict(integrity='PASSED_LOG_AND_ARCHIVE_METADATA_INDEX',objects=check_index(owned)))
    owned.update(p.relative_to(ROOT).as_posix() for p in OUT.iterdir() if p.is_file());stage('owned_final');objects=check_index(owned)
    print(dict(integrity='PASSED_READY_FOR_LOCAL_LOW_RANK_ARCHIVE_LOG_COMMIT',files=len(objects),bytes=sum(v['bytes'] for v in objects.values())),flush=True)


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');main()

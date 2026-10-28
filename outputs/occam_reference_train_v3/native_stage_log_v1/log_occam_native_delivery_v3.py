"""Append phase summary only after verified native publication."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
from time import perf_counter_ns
import hashlib,shutil,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import occam_native_case_io_v1 as c
from src.analysis import response_qualification_io_v1 as io
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
from outputs.information_release.validation_v1.validate_freeze import index_bytes


def main():
    start=perf_counter_ns();source='c49b4268eb4e739256fcd7e2d9b3a2fed976198f';remote='fe1bf36891de8f0b38d242fd77d81f966c7896da'
    assert io.git('rev-parse','HEAD')==source and not io.git('status','--porcelain','--untracked-files=no')
    archive=ROOT/'outputs/research_archive/occam_native_qualification_v3';receipt=c.read(archive/'remote_receipt.json');catalog=c.read(archive/'catalog.json')
    assert receipt['integrity']=='PASSED' and receipt['remote_after']==remote
    changed=io.git('diff','--name-only','c92356173d9e99dada69da6a032f880a4f763259',source).splitlines();rows=[r for r in catalog['files'] if r['path'] in changed]
    assert len(changed)==len(rows)==25 and all(r['published'] and io.git('rev-parse',remote+':'+r['path'])==r['oid'] for r in rows)
    for name in ('build_occam_native_v3_archive.py','verify_occam_core_commit_v1.py'):shutil.copyfile(Path(__file__).parent/name,archive/name)
    shutil.copyfile(Path(__file__).parent/'occam_core_postcommit_c49b4268eb4e.json',archive/'source_committed_bytes.json')
    c.write(archive/'phase_selection.json',dict(integrity='PASSED',source_local_commit=source,remote_archive_commit=remote,published=25,omitted=0,files=rows))
    c.write(archive/'complete.json',dict(integrity='PASSED_NATIVE_QUALIFICATION_PUBLICATION',source_local_commit=source,remote_archive_commit=remote,
        native_cases=36,native_record_files=499,native_parts=10,no_model_or_task_qualification_claim=True,new_physics_during_publication=0,online_LLM_API_calls=0))
    out=c.BASE/'native_stage_log_v1';out.mkdir(exist_ok=False)
    run=c.OUTPUT/'occam_reference_train_v3_20261028T071949Z_c92356173d9e';train=c.read(run/'train/status.json')
    c.write(out/'train_progress_snapshot.json',dict(status=train,operational_snapshot_not_complete_training_data=True,expected_executions=648,
        source_manifest_sha256=c.sha(run/'manifest.json'),collector_session_id=20527,no_model_training_started=not (run/'learning').exists()))
    before=(ROOT/'Research_Log.md').read_bytes();assert '原生资格v3与完整记录交付'.encode() not in before
    now=datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
    addition=f'''

## {now}（北京时间）｜原生资格v3与完整记录交付

- 资源已恢复：新入口可提交余量约8.76GiB、磁盘约13.98GiB；原源码／
  运行时／种子范围核对后，一次新分配5bc73a52创建，旧分配不续接。
- 已完成：36/36原生案例，两级独立记录审计通过；18对共同获取轨迹及
  获取后完整原生／Python状态一致，保留全部RNG根，295个实际窗口可追溯。
  这是1组／边界16的基础资格，不外推到全部边界、预测或任务收益。
- 全部结果：35任务成功、1失败、0技术失败，全部分项保留，不据此宣称
  方法优于基线。Native费用5399控制步、1836全部reset、944995物理帧，
  实际政策查询5083，独立审计另5083；采集556.874秒、完整审计82.226秒。
  科学拟合／Adam／在线LLM为0；旧来源费用另列，没有重复收费或旧数据填充。
- 原始交付：499文件／10个分片；从提交d2dc35e的实际Git对象恢复，逐文件
  字节／哈希及91106行gzip扫描通过；保留原始记录、ZIP和两次恢复副本。
  本地交付 `d2dc35e56e174a1e26388068f617f82caf89df34`，恢复证明
  `{source}`；核对远端 `{remote}`，阶段25项全部发布。
- 报告：[原生资格v3](reports/occam_native_qualification_v3_zh.md)。已核对
  push后追加本条，旧日志前缀保留。历史失败、部分人口和全部负结果不变。
- 下一阶段目标：TRAIN已按冻结表开始，当前{train['completed']}/648仅为
  运维进度；全部648及双审计前不能学习。之后按预算训练标准参考／匹配
  ERM并做数学核对；独立科学资格、自身历史完整任务比较另行冻结与执行。
  A主线具体贡献、强完整风险／DR等对照、任务收益与消融仍待证明，CCF A未完成。
'''
    with (ROOT/'Research_Log.md').open('ab') as target:target.write(addition.encode())
    assert (ROOT/'Research_Log.md').read_bytes().startswith(before)
    c.write(out/'append_only_proof.json',dict(integrity='PASSED',prefix_bytes=len(before),prefix_sha256=hashlib.sha256(before).hexdigest(),
        full_sha256=c.sha(ROOT/'Research_Log.md'),push_verified_before_append=True,remote_archive_commit=remote,timestamp_Asia_Shanghai=now))
    for n,h in c.read(c.FREEZE)['source_sha256'].items():assert c.sha(ROOT/n)==h,n
    shutil.copyfile(Path(__file__),out/Path(__file__).name)
    names={'Research_Log.md'}
    for folder in (archive,ROOT/'outputs/research_archive/occam_isolated_training_log_v3'):
        names|={path.relative_to(ROOT).as_posix() for path in folder.iterdir() if path.is_file()}
    def stage(label):
        names.update(path.relative_to(ROOT).as_posix() for path in out.iterdir() if path.is_file())
        spec=out/(label+'.nul');names.add(spec.relative_to(ROOT).as_posix());spec.write_bytes(b'\0'.join(n.encode() for n in sorted(names))+b'\0')
        io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+spec.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    def check():
        actual=index_bytes(names)
        for name in actual:
            raw=(ROOT/name).read_bytes()
            if b'\0' in raw:continue
            text=raw.decode('utf8',errors='replace');assert find_secret_rule(text) is None and not any(rule.search(text) for rule in EXTRA.values()),name
        assert not io.git('diff','--check') and not io.git('diff','--cached','--check');return actual
    stage('owned_checked');c.write(out/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=check(),actual_index_secret_scan=True))
    c.write(out/'complete.json',dict(integrity='PASSED_NATIVE_STAGE_LOG_AND_PUBLICATION',native_source_commit=source,remote_archive_commit=remote,
        immutable_scientific_sources_unchanged=True,append_only_log=True,TRAIN_running=True,TRAIN_snapshot_completed=train['completed'],TRAIN_allocated=648,
        model_training_not_started=True,new_physics_during_log_delivery=0,online_LLM_API_calls=0,publication_goal_complete=False,wall_ns=perf_counter_ns()-start))
    stage('owned_final');check();print(dict(integrity='PASSED_NATIVE_STAGE_LOG_AND_PUBLICATION',owned_files=len(names),train_snapshot=train['completed']),flush=True)


if __name__=='__main__':main()

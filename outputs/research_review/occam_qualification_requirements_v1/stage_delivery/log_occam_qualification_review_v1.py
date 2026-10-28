from datetime import datetime,timezone,timedelta
from pathlib import Path
import hashlib,shutil,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import occam_native_case_io_v1 as c
from src.analysis import response_qualification_io_v1 as io
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
from outputs.information_release.validation_v1.validate_freeze import index_bytes


def main():
    source='d6b38a11d5ccc6c4f253feb4b0a85fd5f7f2683f';remote='92192604a91a5ccd17b22412d7a8c1cca2dcddc5'
    assert io.git('rev-parse','HEAD')==source and not io.git('status','--porcelain','--untracked-files=no')
    archive=ROOT/'outputs/research_archive/occam_qualification_review_v1';r=c.read(archive/'remote_receipt.json');cat=c.read(archive/'catalog.json')
    assert r['integrity']=='PASSED' and r['remote_after']==remote
    changed=io.git('diff-tree','--no-commit-id','--name-only','-r',source).splitlines();rows=[row for row in cat['files'] if row['path'] in changed]
    assert len(changed)==len(rows)==8 and all(row['published'] for row in rows)
    for name in ('build_occam_qualification_review_v1_archive.py','verify_occam_core_commit_v1.py'):shutil.copyfile(Path(__file__).parent/name,archive/name)
    shutil.copyfile(Path(__file__).parent/'occam_core_postcommit_d6b38a11d5cc.json',archive/'source_committed_bytes.json')
    c.write(archive/'phase_selection.json',dict(integrity='PASSED',source_local_commit=source,remote_archive_commit=remote,published=8,omitted=0,files=rows))
    c.write(archive/'complete.json',dict(integrity='PASSED_QUALIFICATION_REQUIREMENTS_PUBLICATION',source_local_commit=source,remote_archive_commit=remote,
        review_only_not_model_qualification=True,new_physics_during_review=0,new_fits=0,online_LLM_API_calls=0))
    out=ROOT/'outputs/research_review/occam_qualification_requirements_v1/stage_delivery';out.mkdir(exist_ok=False)
    now=datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S');log=ROOT/'Research_Log.md';prefix=log.read_bytes()
    assert '独立资格要求与来源审查'.encode() not in prefix
    entry=f'''

## {now}（北京时间）｜独立资格要求与来源审查

- 已完成：重读OCCAM v1相关方法／实验段，核对当前冻结训练、公开投影、
  预测／创新协方差和数学导出接口；将数值、完整训练、独立预测、实际
  部署收益与研究贡献分层。离线支持集MSE不冒称前瞻预测，三checkpoint
  不按结果挑选，完整风险／DR和必要消融仍须补齐。
- 边界：共同协方差缩放是标准代数性质，不作新定理；MSE／合法协方差
  不能单独证明校准，未来beta／尺度须独立冻结。1组Native和TRAIN导出
  一致性不能替代科学资格。没有新采样人口、阈值、训练或求解预算。
- 费用：本次文献／源码核对本身新增环境交互、政策查询、拟合、求解、
  Adam和在线LLM均0；原TRAIN采集继续，费用单列。首次AST键查找检查器
  错误及修复前源码保留，未改变科学代码，不增加单位测试计数。
- 来源：本地 `{source}`；已核对远端 `{remote}`，
  本阶段8项全部发布，随后追加本条。冻结代码／参数／种子／预算不变。
- 清单：[独立资格要求](docs/research/occam_independent_qualification_requirements_v1_zh.md)。
- 下一阶段目标：继续同一个TRAIN648采集，完整双审计后一次既定训练与
  数学核对，再单独冻结预测／自身历史完整任务协议。强对照、A的具体机制、
  独立收益和消融仍待新证据，CCF A目标未完成。
'''
    with log.open('ab') as f:f.write(entry.encode())
    assert log.read_bytes().startswith(prefix)
    c.write(out/'append_only_proof.json',dict(integrity='PASSED',prefix_bytes=len(prefix),prefix_sha256=hashlib.sha256(prefix).hexdigest(),
        full_sha256=c.sha(log),remote_archive_commit=remote,verified_push_before_append=True,timestamp_Asia_Shanghai=now))
    for n,h in c.read(c.FREEZE)['source_sha256'].items():assert c.sha(ROOT/n)==h,n
    shutil.copyfile(Path(__file__),out/Path(__file__).name)
    names={'Research_Log.md'}
    for folder in (archive,ROOT/'outputs/research_archive/occam_native_stage_log_v3'):
        names|={p.relative_to(ROOT).as_posix() for p in folder.iterdir() if p.is_file()}
    def stage(label):
        names.update(p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file());spec=out/(label+'.nul')
        names.add(spec.relative_to(ROOT).as_posix());spec.write_bytes(b'\0'.join(n.encode() for n in sorted(names))+b'\0')
        io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+spec.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    def check():
        actual=index_bytes(names)
        for name in actual:
            raw=(ROOT/name).read_bytes()
            if b'\0' in raw:continue
            text=raw.decode('utf8',errors='replace');assert find_secret_rule(text) is None and not any(rule.search(text) for rule in EXTRA.values()),name
            if name.endswith('.py'):compile(raw,name,'exec')
        assert not io.git('diff','--check') and not io.git('diff','--cached','--check');return actual
    stage('owned_checked');c.write(out/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=check(),actual_index_secret_scan=True))
    c.write(out/'complete.json',dict(integrity='PASSED_REQUIREMENTS_STAGE_LOG',source_local_commit=source,remote_archive_commit=remote,
        append_only_log=True,science_sources_unchanged=True,new_physics_during_delivery=0,new_fits=0,online_LLM_API_calls=0,publication_goal_complete=False))
    stage('owned_final');check();print(dict(integrity='PASSED_REQUIREMENTS_STAGE_LOG',owned_files=len(names)),flush=True)


if __name__=='__main__':main()

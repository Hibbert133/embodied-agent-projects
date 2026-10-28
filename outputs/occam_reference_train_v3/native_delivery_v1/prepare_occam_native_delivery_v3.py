"""Native-only immutable record delivery; no environment, policy or learning."""
from pathlib import Path
from time import perf_counter_ns
from collections import defaultdict
import csv,gzip,hashlib,json,shutil,sys,zipfile
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import occam_native_case_io_v1 as c
from src.analysis import response_qualification_io_v1 as io
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
from outputs.information_release.validation_v1.validate_freeze import index_bytes
RUN=c.OUTPUT/'occam_reference_train_v3_20261028T071949Z_c92356173d9e'
OUT=c.BASE/'native_delivery_v1'
RESTORE=Path(r'C:/Users/Administrator/Documents/ChatGPT/robotic agent/nr01')


def scan_line(raw,name):
    text=raw.decode('utf8');assert find_secret_rule(text) is None and not any(rule.search(text) for rule in EXTRA.values()),name


def verify_bundle(bundle,index,destination):
    """Literal ZIP member reader, exact bytes and decompressed record scanning."""
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=False);expected={r['path']:r for r in index['files']};seen=set();decoded=0
    with zipfile.ZipFile(bundle,'r') as archive:
        for item in archive.infolist():
            name=item.filename;assert name in expected and name not in seen and not item.is_dir();seen.add(name)
            relative=Path(name);assert not relative.is_absolute() and '..' not in relative.parts
            target=(destination/relative).resolve();assert target.is_relative_to(destination.resolve());target.parent.mkdir(parents=True,exist_ok=True)
            h=hashlib.sha256();size=0
            with archive.open(item,'r') as source,target.open('xb') as output:
                for data in iter(lambda:source.read(1024**2),b''):h.update(data);size+=len(data);output.write(data)
            row=expected[name];assert size==row['bytes'] and h.hexdigest()==row['sha256']==c.sha(ROOT/name),name
            if name.endswith('.gz'):
                with gzip.open(target,'rb') as source:
                    for line in source:scan_line(line,name);decoded+=1
            else:scan_line(target.read_bytes(),name)
    assert seen==set(expected)
    return dict(integrity='PASSED',files=len(seen),decoded_gzip_lines=decoded,bundle_sha256=c.sha(bundle),every_original_byte_restored=True,
        new_physics=0,new_policy_queries=0,new_fits=0,online_LLM_API_calls=0)


def main():
    start=perf_counter_ns();OUT.mkdir(exist_ok=False);m=c.check_manifest(RUN/'manifest.json');s=c.read(RUN/'native/summary.json');a=c.read(RUN/'native/audit.json');p=c.read(RUN/'native/process_audit.json')
    assert s['executions']==36 and s['status']=='COLLECTED_FOR_INDEPENDENT_AUDIT' and a['integrity']=='PASSED' and p['integrity']=='PASSED_ISOLATED_PROCESS_AND_BYTE_CONTINUITY_ONLY'
    assert a['counts']['live_behavior_pairs']==18 and a['counts']['observed_window_labels']==295
    files={path for path in (RUN/'native').rglob('*') if path.is_file()}
    files|={RUN/name for name in ('manifest.json','seed_scope.json','seed_scope_audit.json')}
    for command in ('collect','process-audit','audit'):files|={path for path in (RUN/'entry_attempts_v1'/(command+'_NATIVE_attempt01')).rglob('*') if path.is_file()}
    preparation=c.BASE/'preparation_attempts_v1/attempt_1577977939400_a838f7b566c3';files|={path for path in preparation.iterdir() if path.is_file()}
    files|={path for path in (c.BASE/'resume_admission_v1').iterdir() if path.is_file()}
    assert all(not path.is_symlink() for path in files)
    entries=[dict(path=path.relative_to(ROOT).as_posix(),bytes=path.stat().st_size,sha256=c.sha(path)) for path in sorted(files)]
    bundle=OUT/'native_records.zip'
    with zipfile.ZipFile(bundle,'x',allowZip64=True) as archive:
        for row in entries:
            info=zipfile.ZipInfo(row['path'],date_time=(2000,1,1,0,0,0));info.compress_type=zipfile.ZIP_STORED if row['path'].endswith('.gz') else zipfile.ZIP_DEFLATED
            info.external_attr=0o100644<<16
            with (ROOT/row['path']).open('rb') as source,archive.open(info,'w',force_zip64=True) as target:shutil.copyfileobj(source,target,1024**2)
    parts=OUT/'bundle_parts';parts.mkdir();records=[]
    with bundle.open('rb') as source:
        while True:
            data=source.read(4*1024**2)
            if not data:break
            name=parts/('part_%03d.bin'%(len(records)+1));name.write_bytes(data)
            records.append(dict(path=name.relative_to(ROOT).as_posix(),bytes=len(data),sha256=c.sha(name)))
    index=dict(schema='OCCAM_NATIVE_ZIP_PARTS_V1',manifest_id=m['manifest_id'],source_git_commit=m['source_git_commit'],
        source_freeze_sha256=c.sha(c.FREEZE),native_audit_sha256=c.sha(RUN/'native/audit.json'),native_process_audit_sha256=c.sha(RUN/'native/process_audit.json'),
        bundle_sha256=c.sha(bundle),bundle_bytes=bundle.stat().st_size,parts=records,files=entries,only_completed_NATIVE_no_live_TRAIN=True,
        duplicated_gzip_members_are_storage_not_additional_scientific_cases=True)
    c.write(OUT/'bundle_index.json',index);local=verify_bundle(bundle,index,RESTORE);c.write(OUT/'local_restoration.json',local)
    keys=('cohort','group','task','seed','context','planned_boundary','acquisition_action','behavior','success','deadline_loss','total_steps','policy_queries','performance_windows','full_feedback_windows','boundary_applied')
    with (OUT/'all_36_cases.csv').open('x',encoding='utf8',newline='') as target:
        writer=csv.DictWriter(target,fieldnames=keys);writer.writeheader();writer.writerows({k:r[k] for k in keys} for r in s['rows'])
    cells=defaultdict(list)
    for row in s['rows']:cells[(row['task'],row['context'])].append(row)
    table='\n'.join('|'+task+'|'+condition+'|'+str(len(rows))+'|'+str(sum(r['success'] for r in rows))+'|'+str(sum(r['total_steps'] for r in rows))+'|' for (task,condition),rows in sorted(cells.items()))
    failed=[r for r in s['rows'] if not r['success']];assert len(failed)==1
    report=f'''# 标准表现参考v3：原生资格交付

2026-10-28。冻结fbcc0fe，实际分配来源c923561；manifest为
{m['manifest_id']}。36/36完整，进程／字节审计和完整动态／控制审计均通过。
这是独立进程下的基础执行资格，不是模型预测、独立任务收益或CCF A资格。

## 完整人口与失败

|任务|条件|完整案例|任务成功|控制步|
|---|---|---:|---:|---:|
{table}

全部36条程序分项见native_delivery_v1/all_36_cases.csv，含三获取与两行为，
不筛选困难样本。本人口只有1个独立组，干预边界16；没有推断检验、置信
区间、算法胜出或对其他边界的外推。35成功、1任务失败，技术失败0，未
启动0。唯一任务失败：{failed[0]['task']}／{failed[0]['context']}／
{failed[0]['acquisition_action']}／{failed[0]['behavior']}，seed {failed[0]['seed']}，
实际{failed[0]['total_steps']}步，截止损失{failed[0]['deadline_loss']}，完整保留。

## 审计证据与限制

36个实际worker均正常终结，最大私有提交{p['peak_private_commit_bytes']}字节。
跨进程序号和单调钟、nonce／PID／请求／回执／字节、完整费用和原始gzip
成员拼接通过独立核对。进程审计实际禁用主执行器／分类器、主资源公式／
门、主请求／费用检查与Popen，不能把它等同于独立物理重仿真。

完整审计核对18对共同获取轨迹与获取后原生／Python完整见证，保留两个
全局RNG根；动作变换／噪声／最终裁剪、PI、成本与295个实际窗口标签通过。
控制重放共享既有actor，独立标量成本／PI／执行器核对另列，不把共享重放
冒称全面独立实现。新工厂前全局RNG初始化是显式新条件，任务内未重设。
政策裁剪警告原样保留，没有修改固定政策或因此排除案例。

## 全部费用

|项目|实际|冻结上限|
|---|---:|---:|
|完整原生案例／worker|36|36|
|控制步|5399|18000|
|受控初始reset|36|36|
|全部reset|1836|1836|
|物理帧|944995|1008000|
|实际政策查询|5083|18000|
|独立记录审计政策查询|5083|18000|
|在线LLM API、科学拟合、Adam|0|0|

物理帧包含工厂900000、受控reset18000和实际控制26995，获取已包含在
控制步中，不重复收费。采集活跃墙时556.874秒，完整记录审计82.226秒，
进程审计与入口、打包／恢复／归档各自回执另记；审计新增物理交互0。
旧v2的27982步／11475全部reset／5877410帧及更早来源仍另列，旧188项
部分数据未作为新TRAIN。模型尚未训练，不能报告预测或任务收益。

## 原始记录交付与下一步

完整原始Native记录、单例进程回执／日志／进度、聚合流、公开投影、原始
分配和种子证明打包，逐文件SHA-256及4MiB分片见bundle_index.json。
压缩流逐字节保留；重复存储按原36案例只计一次。原ZIP、原始文件和实际
恢复副本留在本地。解压恢复并扫描全部文本与gzip行，后续实际Git分片
恢复回执单列；未将仍变化的TRAIN文件放进原生发布包。

原生双门通过后，按同一冻结分配开始一次TRAIN648。完整TRAIN双审计之前
不得准备学习，保留全部早终止、短窗、任务失败和技术停止；无补样、换种子
或旧数据填充。TRAIN运行情况单独记录，本表仅计已结束的Native费用。
最终科学CAL／QUAL及新接收者自身历史的完整任务评价尚未开展。

A主线仍须提出区别于完整程序风险／DR、CPC、OCCAM、被动适应及任务相关
获取的具体机制，并通过强对照、独立任务收益和消融。一次软件／原生资格
或标准参考训练均不替代CCF A目标。
'''
    (ROOT/'reports/occam_native_qualification_v3_zh.md').write_text(report,encoding='utf8',newline='\n')
    c.write(OUT/'native_costs.json',dict(manifest_id=m['manifest_id'],executions=36,success=35,task_failure=1,technical_failure=0,
        control_steps=5399,all_resets=1836,controlled_resets=36,physical_frames=944995,actual_policy_queries=5083,audit_policy_queries=5083,
        window_labels=295,full_behavior_pairs=18,peak_worker_private_commit_bytes=p['peak_private_commit_bytes'],collection_wall_ns=s['wall_ns'],
        record_audit_wall_ns=a['wall_ns'],online_LLM_API_calls=0,scientific_fits=0,Adam_updates=0,only_NATIVE_costs=True))
    shutil.copyfile(Path(__file__),OUT/Path(__file__).name)
    names={'reports/occam_native_qualification_v3_zh.md'}|{row['path'] for row in records}
    names|={path.relative_to(ROOT).as_posix() for path in OUT.iterdir() if path.is_file() and path.name!='native_records.zip'}
    def stage(label):
        file=OUT/(label+'.nul');names.add(file.relative_to(ROOT).as_posix());file.write_bytes(b'\0'.join(n.encode() for n in sorted(names))+b'\0')
        io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+file.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    def check():
        actual=index_bytes(names)
        for name in actual:
            raw=(ROOT/name).read_bytes()
            if name.endswith('.bin'):assert name in {r['path'] for r in records};continue
            if b'\0' not in raw:scan_line(raw,name)
        assert not io.git('diff','--check') and not io.git('diff','--cached','--check');return actual
    stage('owned_checked');c.write(OUT/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=check(),actual_index_scan=True,ZIP_and_nested_gzip_scan=True))
    c.write(OUT/'complete.json',dict(integrity='PASSED_NATIVE_DATA_DELIVERY_LOCAL_RESTORATION',manifest_id=m['manifest_id'],source_freeze_sha256=c.sha(c.FREEZE),
        native_audit_sha256=c.sha(RUN/'native/audit.json'),process_audit_sha256=c.sha(RUN/'native/process_audit.json'),bundle_index_sha256=c.sha(OUT/'bundle_index.json'),
        files=len(entries),parts=len(records),raw_zip_retained_local=True,raw_native_retained_local=True,new_physics_during_delivery=0,
        new_fits=0,online_LLM_API_calls=0,publication_goal_complete=False,wall_ns=perf_counter_ns()-start))
    names|={path.relative_to(ROOT).as_posix() for path in OUT.iterdir() if path.is_file() and path.name!='native_records.zip'}
    stage('owned_final');check();print(dict(integrity='PASSED_NATIVE_DATA_DELIVERY_LOCAL_RESTORATION',files=len(entries),parts=len(records),bytes=bundle.stat().st_size),flush=True)


if __name__=='__main__':main()

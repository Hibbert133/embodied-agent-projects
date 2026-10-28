from pathlib import Path
from time import perf_counter_ns
import gzip,hashlib,json,subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import occam_training_failure_v2 as d
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
from outputs.information_release.validation_v1.validate_freeze import index_bytes
io=d.io;start=perf_counter_ns();r=io.read(d.OUTPUT/'complete.json')
assert r['integrity']=='PASSED_STREAM_CLOSURE_AND_ACCOUNTING_ONLY' and io.read(d.BASE/'diagnostic_attempt01/complete.json')['integrity']=='PASSED'
q=io.read(d.FREEZE/'complete.json')
for n,h in {**q['source_sha256'],**q['input_sha256']}.items():assert io.sha(ROOT/n)==h,n
out=d.BASE/'result_delivery_v1';out.mkdir();parts=out/'parts';parts.mkdir();restore=out/'restoration_v1';restore.mkdir()
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as file:
        for chunk in iter(lambda:file.read(1024**2),b''):h.update(chunk)
    return h.hexdigest()
def scan(text,name):assert find_secret_rule(text) is None and not any(p.search(text) for p in EXTRA.values()),name
artifacts=[];raw=d.extension.TARGET.parent/'train';completion=io.read(raw/'completion.json')
for name,kind in (('events.jsonl.gz','events'),('witnesses.jsonl.gz','private')):
    original=raw/name;recovered=restore/name;rows=[]
    with original.open('rb') as source,recovered.open('xb') as target:
        ordinal=0
        for chunk in iter(lambda:source.read(4*1024**2),b''):
            ordinal+=1;part=parts/(name+'.part%03d.bin'%ordinal)
            with part.open('xb') as file:file.write(chunk)
            with part.open('rb') as file:target.write(file.read())
            rows.append(dict(path=part.relative_to(ROOT).as_posix(),bytes=len(chunk),sha256=sha(part)))
    original_sha=sha(original);assert sha(recovered)==original_sha==completion['artifact_sha256'][name]
    decoded=hashlib.sha256();size=records=0
    with gzip.open(recovered,'rb') as file:
        for line in file:
            decoded.update(line);size+=len(line);records+=1;scan(line.decode('utf8'),name)
    assert decoded.hexdigest()==r['decoded_source_sha256'][kind] and records==r['source_record_counts'][kind]
    artifacts.append(dict(original_path=original.relative_to(ROOT).as_posix(),original_bytes=original.stat().st_size,original_sha256=original_sha,
        completion_sha256=completion['artifact_sha256'][name],parts=rows,decoded_bytes=size,decoded_sha256=decoded.hexdigest(),decoded_records=records,
        actual_restored_sha256=sha(recovered),full_decoded_secret_scan='EVERY_JSONL_ROW',original_and_restoration_retained_local=True))
io.write(out/'record_parts_index.json',dict(integrity='PASSED',artifacts=artifacts,streamed_memory_bounded_recovery=True))
report=ROOT/'reports/occam_reference_training_partial_failure_v2_zh.md'
text=f'''# 独立表现参考v2：TRAIN技术停止、完整记录交付与零交互诊断

本轮没有完成科学训练。TRAIN在188项完整记录后，第189项初始见证边界
出现“Could not allocate bytes object!”而按冻结协议停止。保留36原生、
188完整TRAIN、1部分和459未启动记录；所有原分配及预留关闭，不续接、
补齐、缩小分母、用部分人口绕过648项训练门或重标未执行轨迹。

这是运行资源相关的技术失败，尚不能称为OCCAM、元学习或A主线的算法负结果。
标准表现网络训练、前瞻预测与完整任务收益资格都未完成；在线LLM API为0。

## 已完成的证据及其范围

原物理冻结a60c1d8、执行e695620；读者修复/续接be387b8；原生数据及修复
已验证远端归档ee1162c，回执本地85eafb5。原生36项完整审计通过：148窗口
标签、18对共同获取一致，审计额外2805次固定政策函数查询且0物理交互。
原v2读者旧噪声常量失败、空的部分导出和全部错误/回执持续保留。

失败诊断在eb0bffc先冻结，再一次执行。逐行原始解压字节、全流连续序号/
时间/身份、分配顺序、CASE_COMPLETE案例哈希与区间、控制步计数、reset/
物理帧整数账本与原完成哈希全部核对。结果{r['integrity']}。
本检查没有重新回放全部政策、PI或实际执行器数值，不构成完整TRAIN审计
通过，不生成可训练公开投影，也不授予训练资格。

新增8项数组检查通过，源码绑定复用2578项，共2586唯一项；本修复及诊断
的环境创建/reset/step/frame、政策查询、求解、模型拟合和优化均0。分析
耗时{r['wall_ns']/1e9:.6f}秒；编译、两环境依赖、秘密、差异及字节核对另存。

## 全部分配与描述性结果

|人口/状态|数量|任务结果如何登记|
|---|---:|---|
|NATIVE完整且已审计|36|只作数据通路资格，非科学训练或任务收益门|
|TRAIN完整记录|188|169成功、19实际任务失败，全部原记录保留|
|TRAIN技术失败部分|1|已重置，0任务控制步；没有最终任务结局，指标null|
|TRAIN未启动|459|观察/任务结局缺失，指标null，不填500|
|全部分配|684|逐项状态表all_684_status.json|

188条只是未平衡的已发生前缀：前5组完整，下一组只有push的8条完整。
它们的169/188只作事后描述，不能当整个648人口成功率、完整程序比较或
接受/拒绝分支的因果效果。没有根据这些结果选增益、任务、模型或checkpoint。

## 失败位置、资源证据与不能区分的原因

第189项为TRAIN/group5/push/CHANGED/边界64/VALIDATE8/RANDOM_WINDOW。
工厂及受控初始reset全部完成，最后保存事件是NOISE_COMMITMENT；任务
命令/策略查询/物理控制步均0，首次INITIAL见证尚未保存，环境关闭标志为真。
主流水线保存了停止栈；失败例没有保留内部完整原生调用栈，具体分配不可定位。

Windows资源耗尽检测器于{r['resource_observation']['event_utc']}报告事件2004：
系统虚拟内存不足。这与失败时刻接近，支持系统提交内存压力参与失败。
之后的内存快照不是失败瞬间峰值；被事件列出的进程也不能直接认定为原因，
不能据此证明Python泄漏或排除其贡献。原系统XML保留本地，报告去除计算机
名/SID的事件与观测并给出原XML哈希；它不是新物理交互或模型训练。

冻结见证的native_hash使用pickle(model,data)。
[MuJoCo3.3.0上游](https://raw.githubusercontent.com/google-deepmind/mujoco/3.3.0/python/mujoco/structs.cc)
的model/data序列化构造bytes；
[pybind11示例版本](https://raw.githubusercontent.com/pybind/pybind11/v2.13.6/include/pybind11/pytypes.h)
在bytes构造失败时有同一报错。此为静态一致性证据，不是本次完整原生栈，
也未证明安装二进制所用的pybind11构建版本或具体分配大小。没有创建环境
或反序列化原生对象重现，没有放宽或删掉原有完整见证。

## 实际费用与历史来源

|本分配阶段|控制步|全部reset|物理帧|
|---|---:|---:|---:|
|NATIVE|3111|1836|933555|
|TRAIN含技术失败尝试|24871|9639|4943855|
|合计|27982|11475|5877410|

第189项单独支付51次reset/25500物理帧/0任务控制步，已经包含在TRAIN
账本中。上限342000控制步/34884全部reset/19152000帧不冒充实际花费。
原生采集内时286.1836872秒；TRAIN采集内时1792.2313232秒；第189项
1.6255088秒。原读者失败子进程2.3622799秒、修复原生审计子进程43.3332258
秒、TRAIN采集子进程1801.2253988秒分别保留；父/子墙钟有重叠，不重复求和。
科学Adam更新、科学Torch求解及模型训练均0。

历史设计来源另列，仍保留原共享/重叠关系，不当作本轮新增：RAW PI选择
DEV720次/90626步/36720reset/18813130帧；旧局部获取资格72次/5939步/
3672reset/1865695帧；旧表现主机36次/4203步/1836reset/939015帧。
见原获取参考及训练协议；当前RAW方法未使用C8名义模型，后续C8基线的
候选特定来源费用仍按原协议单列。v1失败工厂另有1reset尝试/0完成、0步/
0帧，原软件构造Adam与科学训练严格分开。本v2隔离软件为2次构造Adam，
更早核心/v1构造费用分别保留，不说成科学训练或重复实际执行过的更新。

## 保存、恢复及后续判断

大TRAIN事件/私有见证共{sum(len(x['parts']) for x in artifacts)}个4MiB上限分片；
实际恢复压缩流并核对原采集完成哈希，逐行扫描全部解压字节。原始大文件、
原系统事件与实际恢复副本继续留本地。全部684状态、完整案例、部分错误、
两次失败流水线、原生后续审计、监控及贡献复核都保留，没有删除负结果。

下一步先建立系统提交内存观测、完整异常栈和有界/隔离工厂生命周期的软件
资格；资源预检和独立冻结通过前不开始新科学采集。保留原见证强度，不用
关闭校验、裁剪掉困难例或188替代648来绕过停止。后续若收集，需全新未用/
未预留范围和完整额外预算；本交付没有授权或执行新采集。

该失败不提供模型响应或任务收益的科学判断。A方向、新获取机制、强参考
上的完整自身历史任务优势、消融、前瞻验证和CCF A目标仍未完成；VAML、
VE/PVE、OCCAM、MDE、双重控制及其他近邻比较保持完整，工程通过不替代贡献。
'''
with report.open('x',encoding='utf8',newline='\n') as file:file.write(text)
with (ROOT/'reports/occam_reference_train_v2_progress_zh.md').open('a',encoding='utf8',newline='\n') as file:
    file.write('\n## 终止更新：TRAIN技术失败，已关闭\n\n188项完整后，第189项首次见证边界bytes分配失败，剩余459项未启动。\nWindows事件2004支持虚拟内存压力；完整内部原生栈缺失，不能认定唯一原因。\n科学训练未开始，零在线LLM，不续接本人口。详见occam_reference_training_partial_failure_v2_zh.md。\n')
(out/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
tracked=set(io.git('ls-files').splitlines());names=set()
def own(folder,recursive=True):
    for p in (folder.rglob('*') if recursive else folder.iterdir()):
        if p.is_file():
            n=p.relative_to(ROOT).as_posix()
            if n not in tracked:names.add(n)
for folder in (d.OUTPUT,d.BASE/'diagnostic_attempt01',d.a.BASE/'pipeline_reader_v3',d.a.BASE/'monitoring_v1',d.extension.BASE/'native_attempt01',d.extension.TARGET.parent/'native/audit_repair_v3'):own(folder)
own(raw)
names-={(raw/name).relative_to(ROOT).as_posix() for name in ('events.jsonl.gz','witnesses.jsonl.gz')}
for p in (d.extension.TARGET.parent/'native/audit.json',report,ROOT/'reports/occam_reference_train_v2_progress_zh.md',ROOT/'docs/research/correction_scope_contribution_review_v4_zh.md'):
    if p.relative_to(ROOT).as_posix() not in tracked:names.add(p.relative_to(ROOT).as_posix())
def stage(label):
    own(out);names.difference_update(p.relative_to(ROOT).as_posix() for p in restore.rglob('*') if p.is_file())
    p=out/(label+'.nul');names.add(p.relative_to(ROOT).as_posix());p.write_bytes(b'\0'.join(n.encode() for n in sorted(names))+b'\0')
    io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+p.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
def check():
    actual=index_bytes(names)
    for n in actual:
        path=ROOT/n
        if n.endswith('.gz'):
            with gzip.open(path,'rb') as file:
                for line in file:scan(line.decode('utf8'),n)
        else:
            data=path.read_bytes()
            if b'\0' not in data:scan(data.decode('utf8',errors='replace'),n)
    assert not io.git('diff','--check') and not io.git('diff','--cached','--check');return actual
stage('owned_initial');proof=check();io.write(out/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=proof,actual_index_basic_extra_decoded_scan=True,all_train_parts_recovered_and_fully_scanned=True))
for n,h in {**q['source_sha256'],**q['input_sha256']}.items():assert io.sha(ROOT/n)==h,n
io.write(out/'complete.json',dict(integrity='PASSED_TECHNICAL_FAILURE_DELIVERY_NOT_MODEL_QUALIFICATION',source_manifest_id=r['source_manifest_id'],
    source_diag_sha256=io.sha(d.OUTPUT/'complete.json'),TRAIN_complete=188,TRAIN_partial=1,TRAIN_not_started=459,
    whole_allocation_actual_cost=r['whole_allocation_actual_cost'],parts=sum(len(x['parts']) for x in artifacts),
    new_physics_during_delivery=0,policy_queries=0,new_fits=0,online_LLM_API_calls=0,publication_goal_complete=False,wall_ns=perf_counter_ns()-start))
stage('owned_final');check();print(dict(integrity='PASSED',objects=len(names),parts=sum(len(x['parts']) for x in artifacts),new_physics=0),flush=True)

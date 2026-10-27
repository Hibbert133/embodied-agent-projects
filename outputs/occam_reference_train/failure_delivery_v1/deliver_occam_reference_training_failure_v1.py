"""Close and preserve the one-shot technical failure, without collecting again."""
from pathlib import Path
from time import perf_counter_ns
import gzip,shutil,subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import occam_reference_train_io_v1 as a
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
io=a.io;started=perf_counter_ns();path=next(a.OUTPUT.glob('*/manifest.json'));manifest=a.checked(path);native=path.parent/'native';out=a.BASE/'failure_delivery_v1'
pipeline=io.read(a.BASE/'pipeline_v1/complete.json');summary=io.read(native/'summary.json');failed=io.read(native/'failed_execution.json');ledger=summary['lifecycle']['counts']
assert pipeline['integrity']=='FAILED_PARTIAL' and [r['label'] for r in pipeline['processes']]==['native_collect']
assert summary['executions']==summary['control_steps']==0 and ledger=={'reset_attempts':1} and not (path.parent/'train').exists() and not (path.parent/'learning').exists()
assert io.read(out/'diagnostic_final_checks.json')['success'] and io.read(out/'namespace_diagnostic_all_phases.json')['integrity']=='PASSED_DIAGNOSTIC_ONLY'
for p in ('cases.jsonl.gz','witnesses.jsonl.gz'):assert not list(io.rows(native/p))
io.write(path.parent/'CLOSED_TECHNICAL_FAILURE.json',dict(status='CLOSED_TECHNICAL_FAILURE',source_manifest_id=manifest['manifest_id'],source_git_commit=manifest['source_git_commit'],
    no_recollection_or_training_under_v1=True,all_allocated_and_reserved_seeds_remain_closed=True,reason='case phase ownership collides with lifecycle/step phase',
    control_steps=0,physical_frames_completed=0,reset_attempts=1,reset_completed=0,scientific_model_training=0,online_LLM_API_calls=0))
seed=path.parent/'seed_scope.json';packed=path.parent/'seed_scope.json.gz'
with packed.open('xb') as f:
    with gzip.GzipFile(filename='',mode='wb',fileobj=f,mtime=0) as stream:stream.write(seed.read_bytes())
restore=Path(__file__).parent/'occam_reference_training_failed_seed_scope_restored_v1.json';restore.write_bytes(gzip.decompress(packed.read_bytes()));assert io.sha(restore)==io.sha(seed)
io.write(out/'seed_scope_bundle.json',dict(integrity='PASSED',original_path=seed.relative_to(ROOT).as_posix(),original_sha256=io.sha(seed),
    compressed_path=packed.relative_to(ROOT).as_posix(),compressed_sha256=io.sha(packed),actual_restored_sha256=io.sha(restore),original_retained_local=True))
report=ROOT/'reports/occam_reference_training_failure_v1_zh.md';report.write_text(f'''# 独立表现参考v1：原生采集接口失败交付

**未形成训练数据，未开始科学训练。v1已按一次分配规则关闭，不重跑该人口。**
冻结adf4521，执行清单来源{manifest['source_git_commit']}；冻结软件归档05978ab。
运行：{manifest['experiment_run_id']}。这不是OCCAM/元学习的任务负结果，不能
计算任务成功率、预测误差或平均截止损失，也不能将未启动案例填成500步失败。

## 实际发生与费用

|阶段|计划分配|尝试案例|完成案例|实际控制步|完成物理帧|
|---|---:|---:|---:|---:|---:|
|NATIVE|36|1|0|0|0|
|TRAIN|648|0|0|0|0|

环境工厂尝试1次、未返回完整环境；生命周期记录1次GOAL_GENERATION重置尝试、
0次完成，受控初始重置0，模拟请求/帧0。不能把工厂尝试说成没有发生。
失败案例耗时{failed['wall_ns']/1e9:.6f}秒，采集子进程{pipeline['processes'][0]['wall_ns']/1e9:.6f}秒，
整个流程含准备{pipeline['wall_ns']/1e9:.6f}秒。科学模型训练/在线滤波/LLM API均0。
开发与正式软件的2次合成Adam及历史主机4203步/939015帧等费用保持单列，
未被当成新科学训练或免费来源。

## 根因与零交互复现

案例归属头使用phase=NATIVE/TRAIN；LifecycleLedger也使用phase表明真实事件
阶段。第一次LIFECYCLE_RESET_INTENT携带phase=GOAL_GENERATION，冻结wrapped
归属保护发现不同值并拒绝，异常发生在原重置函数委托和事件持久化之前。
部分日志只有CASE_ALLOCATION与FACTORY_INTENT，不假造缺失的重置完成记录。
保护本身正确拒绝冲突；接口的扁平命名空间设计有误。

从冻结源仅提取该小型归属函数，使用真实JsonJournal和内存文本流复现：
NATIVE/TRAIN两头×9个生命周期/命令阶段，18/18均拒绝，写入数0。
将案例字段示意改为cohort后，18/18可同时保存cohort和phase；外来seed/cohort
仍拒绝。此为事后描述性软件诊断，不是已部署v2、环境执行或未执行物理轨迹。
没有执行采集器、环境工厂、重置、控制或拟合。两轮4项诊断测试均通过；
完整新增唯一数为32+4，连同旧2522共2558，共72次本轮测试执行。

现有32项训练/数据/模拟人口检查没有覆盖真正生命周期事件与案例头的命名
冲突，不能以它们通过冒称集成完成。原科学代码/配置/清单和错误不覆盖，
所有部分日志、失败案例、进程退出/费用及原大种子清单留存，清单gzip实际恢复一致。

## 后续判断

修复应隔离案例cohort与事件phase，保持归属拒绝而非关闭保护，并补充真实
生命周期事件经收集器头合并的合成集成测试；还应覆盖CONTROL及各任务/探测
事件，而不只修第一次reset。实现、审计、预算与测试重新冻结后才能以确认
未用/未预留的新范围开始独立v2。当前所有v1分配/预留继续关闭，TRAIN没有
自动开放，不把未使用种子当成失败后可追加人口。

后继不根据此次软件失败改模型、物理、学习目标或收益门槛。科学CAL/QUAL、
强参考独立自身历史完整损失比较、新获取决策机制及CCF A目标仍未完成。

来源：[冻结协议](../docs/protocols/occam_reference_train_v1_zh.md)、
[进程失败记录](../outputs/occam_reference_train/pipeline_v1/complete.json)、
[只读复现](../outputs/occam_reference_train/failure_delivery_v1/namespace_diagnostic_all_phases.json)。
''',encoding='utf8',newline='\n')
shutil.copyfile(__file__,out/Path(__file__).name)
sources=['src/analysis/occam_training_namespace_diagnostic_v1.py','tests/test_occam_training_namespace_diagnostic_v1.py']
for n,h in io.read(out/'diagnostic_final_checks.json')['source_sha256'].items():assert io.sha(ROOT/n)==h
p=subprocess.run([sys.executable,'-m','compileall','-q','src','scripts','tests'],cwd=ROOT,capture_output=True,text=True);io.write(out/'compile.json',dict(returncode=p.returncode,stdout=p.stdout,stderr=p.stderr));assert p.returncode==0
names=set(sources)|{report.relative_to(ROOT).as_posix()}|{p.relative_to(ROOT).as_posix() for p in path.parent.rglob('*') if p.is_file() and p!=seed}
names|={p.relative_to(ROOT).as_posix() for p in (a.BASE/'pipeline_v1').rglob('*') if p.is_file()}
def stage(label):
    global names
    names|={p.relative_to(ROOT).as_posix() for p in out.rglob('*') if p.is_file()};q=out/(label+'.nul');names.add(q.relative_to(ROOT).as_posix());q.write_bytes(b'\0'.join(n.encode() for n in sorted(names))+b'\0')
    io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+q.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
def check():
    actual=index_bytes(names)
    for n in actual:
        data=(ROOT/n).read_bytes()
        if n.endswith('.gz'):data=gzip.decompress(data)
        if b'\0' in data:continue
        text=data.decode('utf8',errors='replace');assert find_secret_rule(text) is None and not any(p.search(text) for p in EXTRA.values()),n
    assert not io.git('diff','--check') and not io.git('diff','--cached','--check');return actual
stage('owned_checked');actual=check();io.write(out/'index_disk_proof.json',dict(integrity='PASSED',actual_index_basic_extra_decoded_scan=True,object_sha256=actual))
io.write(out/'complete.json',dict(integrity='PASSED_FAILURE_DELIVERY_NOT_EXPERIMENT_QUALIFICATION',original_experiment_status='CLOSED_TECHNICAL_FAILURE',
    source_manifest_id=manifest['manifest_id'],source_git_commit=manifest['source_git_commit'],source_sha256={n:io.sha(ROOT/n) for n in sources},
    unique_test_total=2558,control_steps=0,physical_frames=0,reset_attempts=1,completed_resets=0,factory_attempts=1,factory_returns=0,
    scientific_model_training=0,online_LLM_API_calls=0,no_recollection=True,task_success_rate=None,deadline_loss=None,prediction_error=None,
    all_failures_and_partial_records_retained=True,publication_goal_complete=False,wall_ns=perf_counter_ns()-started))
stage('owned_final');check();a.checked(path);print(dict(integrity='PASSED_FAILURE_DELIVERY',objects=len(names),new_control_steps=0,reset_attempts=1),flush=True)

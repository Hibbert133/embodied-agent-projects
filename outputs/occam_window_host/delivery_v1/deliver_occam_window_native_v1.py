"""Deliver one complete native host contract, retaining exact raw bytes/parts."""
from pathlib import Path
from collections import Counter
from time import perf_counter_ns
import gzip,hashlib,json,shutil,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import occam_window_io_v1 as a
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
from outputs.information_release.validation_v1.validate_freeze import index_bytes
io=a.io


def main():
    started=perf_counter_ns();runs=list(a.OUTPUT.glob('*/manifest.json'));io.require(len(runs)==1,'exact native allocation');path=runs[0]
    manifest=a.checked(path);native=path.parent/'native';summary=io.read(native/'summary.json');audit=io.read(native/'audit.json')
    io.require(summary['status']=='COLLECTED_FOR_INDEPENDENT_AUDIT' and audit['integrity']=='PASSED','full audited native contract')
    io.require(not io.git('status','--porcelain','--untracked-files=no'),'clean source checkout')
    out=a.BASE/'delivery_v1';out.mkdir(exist_ok=False);parts=out/'parts';parts.mkdir();exports=out/'verified_gzip_exports';exports.mkdir()
    restore=Path(__file__).parent/'occam_window_native_restoration_v1';restore.mkdir(exist_ok=False)
    shutil.copyfile(__file__,out/Path(__file__).name)
    proof=Path(__file__).parent/'occam_core_postcommit_9087199edac0.json';io.require(io.read(proof)['integrity']=='PASSED','actual frozen commit bytes');shutil.copyfile(proof,out/'freeze_committed_bytes.json')
    part_index=[];raw_names=set()
    for src in sorted(native.glob('*.jsonl.gz')):
        name=src.relative_to(ROOT).as_posix();raw_names.add(name);raw=src.read_bytes();rows=[];rebuilt=bytearray()
        target=parts/src.name;target.mkdir()
        for j,at in enumerate(range(0,len(raw),4*1024**2)):
            data=raw[at:at+4*1024**2];part=target/('part%04d.bin'%j);part.write_bytes(data);rebuilt.extend(part.read_bytes())
            rows.append(dict(path=part.relative_to(ROOT).as_posix(),bytes=len(data),sha256=io.sha(part)))
        restored=restore/src.name;restored.write_bytes(rebuilt);io.require(restored.read_bytes()==raw,'actual full gzip restoration')
        # Small complete gzip exports are a verified remote recovery alternative;
        # local exact parts and originals remain regardless of publication size.
        exported=exports/src.name;exported.write_bytes(raw);io.require(io.sha(exported)==io.sha(src),'export exact source gzip')
        data=gzip.decompress(raw);text=data.decode('utf8');io.require(find_secret_rule(text) is None,'decoded record secret')
        for label,p in EXTRA.items():io.require(p.search(text) is None,'decoded record extra secret '+label)
        part_index.append(dict(original_path=name,original_bytes=len(raw),original_sha256=io.sha(src),parts=rows,
            actual_restored_sha256=io.sha(restored),decoded_bytes=len(data),decoded_sha256=hashlib.sha256(data).hexdigest(),
            verified_gzip_export=exported.relative_to(ROOT).as_posix(),decoded_basic_extra_scan=True,original_retained_local=True))
    io.write(out/'record_parts_index.json',dict(integrity='PASSED',artifacts=part_index))
    seed=path.parent/'seed_scope.json';seed_gz=path.parent/'seed_scope.json.gz'
    with seed_gz.open('xb') as handle:
        with gzip.GzipFile(filename='',mode='wb',fileobj=handle,mtime=0) as stream:stream.write(seed.read_bytes())
    restored_seed=restore/'seed_scope.json';restored_seed.write_bytes(gzip.decompress(seed_gz.read_bytes()));io.require(io.sha(restored_seed)==io.sha(seed),'seed inventory restore')
    io.write(out/'seed_scope_bundle.json',dict(integrity='PASSED',original_path=seed.relative_to(ROOT).as_posix(),original_sha256=io.sha(seed),
        compressed_path=seed_gz.relative_to(ROOT).as_posix(),compressed_sha256=io.sha(seed_gz),actual_restored_sha256=io.sha(restored_seed),original_retained_local=True))
    panels=[]
    for task in ('push-v3','reach-v3','door-open-v3'):
        for context in ('UNCHANGED','CHANGED'):
            for sign in (-1,1):
                rows=[r for r in summary['rows'] if r['task']==task and r['context']==context and r['fixture_sign']==sign]
                panels.append(dict(task=task,context=context,fixture_sign=sign,cases=len(rows),success=sum(r['success'] for r in rows),
                    mean_deadline_loss=sum(r['deadline_loss'] for r in rows)/len(rows),actual_steps=sum(r['total_steps'] for r in rows),
                    performance_windows=sum(r['performance_windows'] for r in rows),full_feedback_windows=sum(r['full_feedback_windows'] for r in rows)))
    counts=audit['counts'];life=summary['lifecycle']['counts'];fees=dict(actual_executions=summary['executions'],allocated_executions=36,
        actual_control_steps=summary['control_steps'],controlled_initial_resets=36,all_resets=life['reset_attempts'],physical_frames=life['simulation_frames_completed'],
        actual_fixed_policy_queries=sum(r['policy_queries'] for r in summary['rows']),actual_online_filter_updates=sum(r['full_feedback_windows'] for r in summary['rows']),
        audit_fixed_policy_queries=counts['audit_fixed_policy_queries'],audit_filter_replays=counts['audit_filter_updates'],independent_batch_solves=counts['independent_batch_solves'],
        scientific_offline_training=0,synthetic_Adam_steps=0,online_LLM_API_calls=0,collection_wall_ns=summary['wall_ns'],audit_wall_ns=audit['wall_ns'],
        first21_development_tests_had_no_operation_counter=True,first21_source_solve_bound=1302,
        subsequent_development_solve_attempts=io.read(a.BASE/'development_validation_v1/development02.json')['guard']['operation_counts']['solve_attempts'],
        prior_27_check_solve_attempts=io.read(a.VALIDATION/'tests.json')['guard']['operation_counts']['solve_attempts'],
        final_31_check_solve_attempts=io.read(a.VALIDATION/'complete.json')['guard']['operation_counts']['solve_attempts'],
        full_backend_flops_not_counted=True,old_core_synthetic_Adam_steps_in_historical_source=1,historical_fees_not_new_interactions=True,
        original_reader_attempt_failed_missing_import=True,prior_failed_reader_inferred_fixed_policy_queries=569,
        prior_failed_reader_inferred_filter_replays=34,prior_failed_reader_inferred_batch_solves=2,
        prior_failed_reader_counts_inferred_not_persisted=True,prior_failed_reader_wall_time_not_instrumented=True,
        v2_failed_reader_measured_solve_attempts=io.read(a.BASE/'audit_repair_v2/attempt01/guard.json')['operation_counts']['solve_attempts'],
        v2_failed_reader_measured_wall_ns=io.read(a.BASE/'audit_repair_v2/attempt01/complete.json')['wall_ns'],
        v2_failed_reader_inferred_fixed_policy_queries=569,v2_failed_reader_inferred_filter_replays=34,v2_failed_reader_inferred_batch_solves=2,
        total_audit_fixed_policy_queries_including_inferred=counts['audit_fixed_policy_queries']+1138,
        total_audit_filter_replays_including_inferred=counts['audit_filter_updates']+68,
        total_audit_batch_solves_including_inferred=counts['independent_batch_solves']+4,
        earlier_filter_inference_33_corrected_to_34_without_overwriting_original=True,
        new_population_loop_regression_tests=4,regression_guard=io.read(a.BASE/'audit_repair_v3/tests01.json')['guard'])
    io.write(out/'costs.json',fees);io.write(out/'panels.json',panels)
    failures=[r for r in summary['rows'] if not r['success']];io.write(out/'all_failures.json',dict(scope='UNTRAINED_SOFTWARE_FIXTURES_NOT_ALGORITHM_FAILURE_COMPARISON',cases=failures))
    table='\n'.join('|{task}|{context}|{fixture_sign:+d}|{success}/{cases}|{mean_deadline_loss:.3f}|{actual_steps}|{performance_windows}|{full_feedback_windows}|'.format(**r) for r in panels)
    report=f'''# OCCAM相关连续表现窗口：原生主机资格报告

**36/36分配已完成并通过独立记录审计；这是未训练构造模型的软件执行资格。**
没有科学离线训练、科学独立任务优势、新颖性/安全或CCF A结论。
冻结提交`{manifest['source_git_commit']}`，运行`{manifest['experiment_run_id']}`。

## 已成立的链路

从真实初始观测连续执行前缀及已分配获取，保存公开完整历史与四候选预测，
消费已保存T并发送PI命令，收到真实窗口结果后才递归更新。共有
{counts.get('live_fixture_pairs',0)}对实际到达选择的构造模型；其中
{counts.get('first_actual_command_different',0)}对的首个实际发送命令不同。
{counts.get('early_end_fixture_pairs',0)}对提前结束，不补样、不虚构选择。
相同单元在选择前的实际移动/噪声/世界见证核对一致。

独立标量逐步和复算成本；float32执行器变换→真实噪声→最后裁剪、积分、
决策在执行之前、manifest与案例闭合、跨案例时钟、重置/帧/噪声游标均通过。
首次读者在第二案例共同见证比较处因遗漏全局导入抛NameError。失败与原源码
保留，另冻1d49623只读修复；v2又因配对变量覆盖流游标，在第三案例前中断，
其守卫和完整异常同样保留。b623f39冻结v3：仅修复该命名冲突及导入，所有
数值/门槛不变；新增4项完整36案例假记录循环回归检查覆盖连续配对、提前
结束和跨案例身份/时钟反例。测试内部物理/数学用stub，不冒充真实原生审计。
同批原始记录由v3完整核对，物理采集没有重跑；异常也持久化守卫与失败。
整段联合高斯条件化独立核对最终后验；程序回放共享原actor和获取原语，
明确不是独立物理重演或一般隐状态充分性证明。

## 反馈含义与限制

窗口费用=实际截止损失增量/500+终端归零的公开位置势差；完整段和加初始
势值后严格恢复完整截止损失。失败未执行惩罚与实际交互分开，只收一次。
这是[标准势函数差分](https://people.eecs.berkeley.edu/~russell/papers/icml99-shaping.pdf)
核账，不能推出短窗贪心最优、模型预测准确或任务收益。
提前成功/终止标签保留，短窗不更新后验。两个构造基函数模型未经科学训练，
先验符号只用于覆盖不同合法选择。下表完整披露，不能从中选优推广。
本实现仅为[OCCAM](https://arxiv.org/html/2406.17620v1)相关受限参考的执行桥，
四T枚举与原论文连续搜索、平台和训练不同，不冒称完整复现。

## 完整人口描述

每格仅3个独立组；表内两程序共享配对种子，不能把步数当独立样本，不做效力或收益宣称。

|任务|条件|构造符号|成功/分配|平均截止损失↓|真实步数|实际窗口|完整反馈更新|
|---|---|---:|---:|---:|---:|---:|---:|
{table}

全部失败保存于all_failures.json并可追溯原始轨迹。获取未发生、锚点未达、
提前结束、短窗均由原记录保留，不补零/移除。采集日志的Gym observation-space
及固定政策裁剪警告保留，不自动修正环境或控制器；本资格不证明声明空间适合学习。

## 实际费用与软件检查

实际{fees['actual_control_steps']}控制步，36受控初始重置、{fees['all_resets']}全部重置、
{fees['physical_frames']}物理帧；实际政策查询{fees['actual_fixed_policy_queries']}次，
在线滤波{fees['actual_online_filter_updates']}次。审计另有
{fees['audit_fixed_policy_queries']}次固定政策函数查询、{fees['audit_filter_replays']}次
滤波回放与{fees['independent_batch_solves']}次整段条件化求解，新增物理交互0。
另计v1和v2失败读者各569次政策函数查询、34次滤波、2次整段求解；这些从
异常位置及记录推得，v1未保存计数器或精确耗时，不冒充实测回执。v2守卫
实测36次线性求解和18.793秒。早期说明的33次滤波漏算预先声明的4步末窗，
已单列更正为34，原错误说明保留，不覆盖或漏计失败费用。
累计审计政策函数查询{fees['total_audit_fixed_policy_queries_including_inferred']}次、
滤波{fees['total_audit_filter_replays_including_inferred']}次、整段求解
{fees['total_audit_batch_solves_including_inferred']}次，推得部分与实测部分分列。
采集{summary['wall_ns']/1e9:.3f}秒，审计{audit['wall_ns']/1e9:.3f}秒。
本阶段科学离线训练、Adam、在线LLM均0；历史核心的1次合成Adam另列，未隐藏。

主机31项和读者4项新增唯一测试通过，旧2487源码绑定复用，共2522；共89次
测试执行。第一次21项纯回调开发测试没有运行时操作计数器，明确保留该限制；
按源程序保守求解上界1302，不把它冒称实测数。后续受守卫检查及正式复核
均无环境创建/重置/推进或联网。完整显式费用见costs.json，不声称计数全部FLOPs。
编译/依赖、秘密扫描及新增实际暂存BASIC/EXTRA/解压扫描、差异、索引/磁盘
和冻结提交字节均核对。原--staged入口实际上扫描工作树；本阶段额外检查
真实索引字节，避免把该入口误称为独立索引审计。
失败日志的Windows换行导致一次索引/磁盘字节不一致；原CRLF字节gzip和哈希
已保存，只规范化文本并为v3日志明确LF。没有改变数值检查或重跑物理人口。

原始大记录和临时恢复副本保留；提交4MiB分片、索引及哈希相同gzip导出，
实际重建与原gzip逐字节相同。种子清单亦压缩、实际恢复并核对。远端归档
是否包含每个大对象由归档目录明确记录，不把紧凑归档说成所有原始数据备份。

## 后续判断

连续主机及费用接口可用于下一份独立科学协议。下一步冻结新的TRAIN行为、
性能网络/归一化、包含终段的元评分和支持顺序、优化费用、CAL规则与独立
自身历史任务比较，不能使用本构造人口选算法或旧QUAL修模型。保留DIRECT_C8、
积分、廉价固定/被动适应、始终获取/获取不更新及其他已登记强参考与消融。
具体获取决策机制、独立完整损失优势和CCF A工作仍未完成。

来源：[冻结协议](../docs/protocols/occam_window_host_v1_zh.md)、
[运行清单](../{path.relative_to(ROOT).as_posix()})、
[独立审计](../{(native/'audit.json').relative_to(ROOT).as_posix()})。
'''
    report_path=ROOT/'reports/occam_window_host_v1_zh.md';report_path.write_text(report,encoding='utf8',newline='\n')
    names={report_path.relative_to(ROOT).as_posix()}|{p.relative_to(ROOT).as_posix() for p in path.parent.rglob('*') if p.is_file() and p.relative_to(ROOT).as_posix() not in raw_names and p!=seed}
    for repair in ('audit_repair_v2','audit_repair_v3'):
        names|={p.relative_to(ROOT).as_posix() for p in (a.BASE/repair).rglob('*') if p.is_file() and io.git('ls-files','--',p.relative_to(ROOT).as_posix())==''}
    def stage(label):
        nonlocal names
        names|={p.relative_to(ROOT).as_posix() for p in out.rglob('*') if p.is_file()}
        q=out/(label+'.nul');names.add(q.relative_to(ROOT).as_posix());q.write_bytes(b'\0'.join(n.encode() for n in sorted(names))+b'\0')
        io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+q.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    def check():
        actual=index_bytes(names)
        for n in actual:
            data=(ROOT/n).read_bytes()
            if n.endswith('.gz'):data=gzip.decompress(data)
            if b'\0' in data:continue
            text=data.decode('utf8',errors='replace');io.require(find_secret_rule(text) is None,'actual index basic secret '+n)
            for label,p in EXTRA.items():io.require(p.search(text) is None,'actual index extra secret '+label+' '+n)
        io.require(not io.git('diff','--check') and not io.git('diff','--cached','--check'),'ordinary and staged diff');return actual
    stage('owned_checked');actual=check();io.write(out/'index_disk_proof.json',dict(integrity='PASSED',actual_index_basic_extra_decoded_scan=True,object_sha256=actual))
    io.write(out/'complete.json',dict(integrity='PASSED',run_id=manifest['experiment_run_id'],frozen_source_commit=manifest['source_git_commit'],native_audit_sha256=io.sha(native/'audit.json'),
        all_36_assignments_retained=True,raw_files_retained=True,actual_restorations_verified=True,online_LLM_API_calls=0,scientific_offline_training=0,
        actual_costs=fees,untrained_host_contract_not_algorithm_gain=True,publication_goal_complete=False,wall_ns=perf_counter_ns()-started))
    stage('owned_final');check();a.checked(path)
    print(dict(integrity='PASSED',objects=len(names),actual_control_steps=fees['actual_control_steps'],live_pairs=counts.get('live_fixture_pairs',0)),flush=True)


if __name__=='__main__':main()

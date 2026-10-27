"""Post-run Chinese report and exact raw transport; no new science operations."""
from pathlib import Path
from collections import Counter
from time import perf_counter_ns
import csv,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import history_response_io_v1 as a
from src.analysis.release_learning_guard_v1 import read_only
from src.probe.history_response_model_v1 import METHODS
from scripts.archive_action_response import split_file,restore
io=a.io

def table(head,rows):return '| '+' | '.join(head)+' |\n| '+' | '.join('---' for _ in head)+' |\n'+''.join('| '+' | '.join(str(x) for x in row)+' |\n' for row in rows)
def write(path,text):
    with path.open('x',encoding='utf8',newline='\n') as f:f.write(text)
def optional(path):return io.read(path) if path.exists() else None


def build(path):
    start=perf_counter_ns();m=a.checked(path);root=path.parent;out=root/'presentation';out.mkdir(exist_ok=False)
    controls=root/'pipeline_control';failures={p.name:io.read(p) for p in controls.glob('*failure.json')}
    io.require((controls/'completion.json').exists() or failures,'terminal pipeline required, not a running observation timeout')
    guard={};phase_rows=[];cases=[];missing=[];costs={};latencies=[];counts=Counter();source_hashes={}
    with read_only(guard):
        for split in a.SPLITS:
            folder=root/split.lower();summary=optional(folder/'summary.json');audit=optional(folder/'audit.json')
            completed=list(io.rows(folder/'cases.jsonl.gz')) if (folder/'completion.json').exists() else []
            failed=optional(folder/'failed_case.json');indexed={tuple(c[k] for k in a.KEYS):c for c in completed}
            if failed is not None:indexed[tuple(failed[k] for k in a.KEYS)]=failed
            for spec in a.population(split):
                c=indexed.get(tuple(spec[k] for k in a.KEYS));status='NOT_STARTED' if c is None else 'FAILED' if c is failed else 'COMPLETED'
                fields=('total_steps','reposition_steps','common_measure_steps','entry_at_calls','packet_steps','complete_packet','reason','success_at_response_horizon','terminated','truncated')
                row=dict(spec,record_status=status,**{k:None if c is None else c.get(k) for k in fields})
                if c is None:row['reason']='NOT_STARTED'
                elif c is failed:row['reason']='EXECUTION_EXCEPTION'
                cases.append(row)
                fr=None if c is None else c.get('forecast_record')
                if fr is not None and fr['canonical']:
                    counts.update(fr['model_compute_counts']);latencies.append(dict(split=split,group=c['group'],task=c['task'],context=c['context'],acquisition_action=c['acquisition_action'],compute_wall_ns=fr['compute_wall_ns'],error=fr['forecast_error']))
            phase_rows.append([split,len(indexed),a.limits(split)['executions'],'未执行' if summary is None else summary['status'],None if summary is None else summary['control_steps'],sum(c['entry_at_calls'] is not None for c in completed),sum(c['complete_packet'] for c in completed)])
            if summary is not None:
                ledger=summary['lifecycle']['counts'];audit_started=any((controls/n).exists() for n in (split+'_audit_intent.json',split+'_record_audit_intent.json'))
                costs[split]=dict(executions=len(indexed),completed_executions=len(completed),control_steps=summary['control_steps'],all_resets=ledger.get('reset_attempts',0),physical_frames=ledger.get('simulation_frames_completed',0),
                    fixed_policy_queries=sum(c.get('policy_queries',0) for c in indexed.values()),independent_policy_queries=audit['extra_independent_policy_queries'] if audit else None if audit_started else 0,
                    independent_saved_forecast_rows=audit['independent_forecast_rows'] if audit else None if audit_started else 0,
                    collection_wall_s=summary['wall_ns']/1e9,record_audit_wall_s=None if audit is None else audit['wall_ns']/1e9,
                    collection_network_guard=summary['network_guard'],collection_fit_guard=summary['fitting_guard'])
                for name in ('summary.json','completion.json','audit.json'):
                    if (folder/name).exists():source_hashes[(folder/name).relative_to(root).as_posix()]=io.sha(folder/name)
            for task in io.TASKS:
                for context in ('UNCHANGED','CHANGED'):
                    for action in ('IN_TASK','MOVE'):
                        for boundary in (16,32,64):
                            rr=[r for r in cases if r['split']==split and r['task']==task and r['context']==context and r['acquisition_action']==action and r['boundary']==boundary]
                            missing.append(dict(split=split,task=task,context=context,acquisition_action=action,boundary=boundary,allocated=len(rr),
                                completed=sum(r['record_status']=='COMPLETED' for r in rr),entries=sum(r['entry_at_calls'] is not None for r in rr),
                                full_packets=sum(r['complete_packet'] is True for r in rr),reasons=dict(Counter(r['reason'] for r in rr))))
        io.require(len(cases)==864,'entire allocated population including all unexecuted cases')
        io.write(out/'all_case_outcomes.json',cases);io.write(out/'full_population_missingness.json',missing);io.write(out/'canonical_forecast_latencies.json',latencies)
        with (out/'all_case_outcomes.csv').open('x',encoding='utf8',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(cases[0]),lineterminator='\n');writer.writeheader();writer.writerows(cases)
        total={k:sum(v[k] for v in costs.values()) for k in ('executions','control_steps','all_resets','physical_frames','fixed_policy_queries')}
        for key in ('independent_policy_queries','independent_saved_forecast_rows'):
            values=[c[key] for c in costs.values()];total[key]=None if any(v is None for v in values) else sum(values)
        train=optional(root/'training/training_receipt.json');audit=optional(root/'training/audit.json');partial=[]
        failure=optional(root/'training/failure.json')
        if failure:partial.append(failure.get('receipt',{}).get('operation_counts',{}))
        for failure in failures.values():
            for frame in failure.get('partial_counters',[]):
                for name in ('guard','receipt'):
                    if isinstance(frame.get(name),dict):partial.append(frame[name].get('operation_counts',{}))
        total.update(primary_scientific_ridge_solves=max([x.get('solve_attempts',0) for x in partial]+([train['receipt']['operation_counts']['solve_attempts']] if train else [0])),
            independent_augmented_lstsq_solves=max([x.get('lstsq_attempts',0) for x in partial]+([audit['receipt']['operation_counts']['lstsq_attempts']] if audit else [0])),
            independent_eigendecompositions=audit['independent_numerical_counts']['symmetric_eigendecompositions'] if audit else None if (controls/'training_audit_intent.json').exists() else 0,
            training_main_and_literal_bank_query_checks=audit['training_bank_checks'] if audit else None if (controls/'training_audit_intent.json').exists() else 0,
            main_training_bank_forecast_rows=audit['main_training_bank_forecast_rows'] if audit else None if (controls/'training_audit_intent.json').exists() else 0,
            literal_training_bank_forecast_rows=audit['literal_training_bank_forecast_rows'] if audit else None if (controls/'training_audit_intent.json').exists() else 0,
            actual_online_local_forecast_counts=dict(counts),online_LLM_API_calls=0,neural_updates=0,C4_C8_fits=0,model_used_for_control=False,
            prefreeze_test_executions=91,unique_new_tests=32,old_source_bound_checks_reused=2286,prefreeze_measured_synthetic_solves=50,prefreeze_measured_synthetic_lstsq=42,prefreeze_measured_synthetic_eigendecompositions=6,
            earlier_two_synthetic_suite_counts_from_asserted_ledger=dict(solves=100,lstsq=84,eigendecompositions=12,not_outer_guard_measured=True),old_simulation_tests_repeated=False)
        old=ROOT/'outputs/paired_packet_response/development_v1/paired_packet_20261027T101154Z_bb74926c3c07/presentation/costs.json'
        historical=dict(old_training_samples_reused=0,old_learned_weights_loaded=0,prior_paired_trial=dict(path=old.relative_to(ROOT).as_posix(),sha256=io.sha(old),total=io.read(old)['total']),
            source_engineering_history='PRIOR_PAIRED_TRIAL_LEDGER_RETAINS_NATIVE_PI_PID_SOURCES_NOT_DOUBLE_ADDED')
        qual=optional(root/'qual_evaluation/result.json');cal=optional(root/'cal_evaluation/result.json')
        status='PIPELINE_FAILED_RETAINED' if failures else qual['status']
        timings={p.name:io.read(p)['wall_ns']/1e9 for p in controls.glob('*_receipt.json')}
        timings['freeze_validation_s']=io.read(a.VALIDATION/'complete.json')['wall_ns']/1e9
        supplement=optional(controls/'nested_seed_scope_supplement.json')
        if supplement is not None:timings['nested_seed_scope_supplement_s']=supplement['wall_ns']/1e9
        io.write(out/'costs.json',dict(by_phase=costs,total=total,historical_sources_separate=historical,stage_process_wall_seconds=timings,
            parallel_or_nested_durations_not_additive_elapsed_time=True,full_task_tail_evaluated=False,analysis_guard=guard))
        decision=dict(status=status,qualification=qual,failure_records=failures,no_retry_or_extension=True,old_failed_versions_remain_closed=True,
            next='仅作为标准已知命令组件；新获取/采用机制仍须具体区别、完整自身历史任务比较与消融' if qual and qual['status']=='QUALIFIED_RESPONSE_CONTRAST_COMPONENT_ONLY' else '封存该历史核版本；不能按QUAL换窗口/带宽/特征、扩样或改参考；不概括为公开历史必然无信息',
            algorithm_novelty_established=False,complete_task_utility_evaluated=False,publication_goal_complete=False)
        io.write(out/'research_decision.json',decision)
        models=contrasts=details='尚无独立QUAL分数。\n'
        if qual:
            panels=io.read(root/'qual_evaluation/panels.json')
            models=table(['模型','全分配平均端点损失mm↓','可用端点描述均值mm↓','可用/全部端点'],[[r['method'],f"{r['mean_endpoint_loss_m']*1000:.9f}",'缺失' if r['available_only_mean_endpoint_loss_m'] is None else f"{r['available_only_mean_endpoint_loss_m']*1000:.9f}",f"{r['available_endpoints']}/{r['allocated_endpoints']}"] for r in panels if r['level']==[]])
            contrasts=table(['HISTORY_KERNEL−参考','均差mm','独立组bootstrap95%mm'],[[k,f"{v['mean_difference_m']*1000:+.9f}",f"[{v['bootstrap95_m'][0]*1000:+.9f}, {v['bootstrap95_m'][1]*1000:+.9f}]"] for k,v in qual['co_primary'].items()])
            details=table(['完整边际层',*METHODS],[[str({field:value})]+[f"{next(p['mean_endpoint_loss_m'] for p in panels if p['level']==[field] and p['strata']=={field:value} and p['method']==kind)*1000:.6f}" for kind in METHODS] for field,values in (('task',io.TASKS),('context',('UNCHANGED','CHANGED')),('acquisition_action',('IN_TASK','MOVE')),('boundary',(16,32,64)),('horizon',(8,16))) for value in values])
            with (out/'all_qualification_panels.csv').open('x',encoding='utf8',newline='') as f:
                writer=csv.DictWriter(f,fieldnames=list(panels[0]),lineterminator='\n');writer.writeheader()
                for row in panels:writer.writerow({k:str(v) if isinstance(v,(dict,list)) else v for k,v in row.items()})
        phase_table=table(['阶段','实际/分配','状态','控制步','真实入口','完整包'],[[r[0],f'{r[1]}/{r[2]}',*r[3:]] for r in phase_rows])
        cost_table=table(['阶段','控制步','全部重置','物理帧','固定策略在线/审计查询','采集秒'],[[s,c['control_steps'],c['all_resets'],c['physical_frames'],f"{c['fixed_policy_queries']}/{c['independent_policy_queries']}",f"{c['collection_wall_s']:.3f}"] for s,c in costs.items()])
        gates='无独立资格结果。' if not qual else '\n'.join('- `'+k+'`：`'+str(v)+'`。' for k,v in qual['gates'].items())
        failure_text='无阶段执行异常。' if not failures else '\n'.join('- `'+n+'`：`'+v['exception'].splitlines()[-1]+'`；原文与部分记录保留。' for n,v in failures.items())
        training_text='训练未完成。' if not train else f"登记{train['families']}个TRAIN家族，其中{train['complete_families']}个三角色H16完整家族；实际主求解{total['primary_scientific_ridge_solves']}次。"
        interpretation='尚未形成独立资格结论。'
        if qual:
            failed_ci=[k for k,v in qual['co_primary'].items() if v['bootstrap95_m'][1]>=0]
            failed_points=[k for k,v in qual['points'].items() if not v['below_all_references']]
            interpretation=f"固定候选的区间门未过参考：{failed_ci}；点比较未过层：{failed_points}。" if qual['status']=='CLOSED_NEGATIVE' else '固定候选通过本协议限定的全部响应组件资格门，仍非逆控制、闭环任务或算法创新资格。'
        figure='' if qual is None else f'![六参考完整资格比较](../outputs/history_response/development_v1/{root.name}/presentation/qualification.png)'
        for name in ('training/models.json','training/audit.json','training/training_receipt.json','model_lock.json',
            'cal_evaluation/result.json','cal_evaluation/audit.json','qual_evaluation/result.json','qual_evaluation/audit.json','pipeline_control/nested_seed_scope_supplement.json'):
            if (root/name).exists():source_hashes[name]=io.sha(root/name)
        text=f'''# A线：公开历史条件响应 v1 中文报告

结果：**`{status}`**。这是标准预测组件的新训练与独立资格；完整截止任务损失、错误更新率和论文创新仍未建立。CCF A目标保持未完成。

## 冻结与全部人口

冻结`{m['source_git_commit']}`；运行`{m['experiment_run_id']}`；manifest ID `{m['manifest_id']}`；清单文件SHA256 `{io.sha(path)}`。
收集器、32项新数组/合成记录检查、独立记录/数值/统计审计、种子和预算先提交。2,286项旧检查按源码哈希复用；编译、依赖、全跟踪文件秘密扫描、真实索引补充扫描、差异及提交字节核验通过。91次冻结前测试执行含重复，不算91项新测试。前两次终端摘要保留，未捕获完整源绑定/外层计数的限制明示。

{phase_table}

全部864分配逐例登记，包括未执行、提前成功、短包、未就绪和异常；不重试或扩样。模型始终只观察，没有选择实际控制。
六个预测器共用同一物理人口，不是6×864次独立执行。补充只读种子审计发现原检查器没有完整遍历嵌套范围数组；对冻结的297个JSON源再检查333次范围出现（含重复）后无冲突。该补充核验晚于采集开始，不能声称其在冻结前完成；分配、种子、模型和记录均未改，检查器缺陷与时间戳保存在pipeline_control/nested_seed_scope_supplement.json。

## 名称和信息权限

- ZERO：预测不同命令没有响应差异。零发送命令仍有真实扰动和噪声。
- INSTANT：一个任务级XY增益乘累计命令。
- FIR：16个延迟响应核，按已知输入的时间顺序预测。
- STATE_KERNEL：依据当前公开观测及携带积分，给训练响应核加权。
- HISTORY_NN：取最近的历史中心，使用其已由最近8个训练家族预拟合的FIR。这是简单局部重加权参考。
- HISTORY_KERNEL：用16段真实已完成的动作/位移历史给响应核加权，是采集前唯一指定候选。

STATE共41维，HISTORY共153维。STATE含MetaWorld自带前一帧观测及携带积分，不能称为完全无历史。额外历史包含16段发送命令与手部XYZ实际位移；不使用获取类别、时刻、种子、真扰动、噪声或私有目标。私有值仅独立执行审计使用，标签来自实际公共手部位置。
响应差异目标不识别唯一的绝对执行偏置；保存的核系数也不等于执行器物理参数。数值合法、当前预测能力与包含获取成本的任务收益分别评价，三者不能互相替代。没有逐步接触力/接触对输入，不能据误差分层认定接触是唯一原因。

固定原任务策略RAW PI0.5前缀，IN_TASK或原LOCAL_PID移动，真实共同8步测量，随后已声明的ZERO/PLUS/MINUS16步包。每个角色实际从初始开始，不能恢复获取位移。共享入口预测早于任何角色包第一步，另两角色核对物理/公开/RNG/时钟入口后只引用缓存。

## 训练与独立资格

{training_text}
各任务先等权组、再家族、再16H。三角色完整筛选存在输入依赖的终止偏差。反对称标签减少重复线性行；偶分量是参数无关常数，仍完整进入测试三配对评分。正则固定0.001，描述符按TRAIN标准化，核带宽固定1；最近邻数量固定8。
独立读取器和增广最小二乘/特征分解重建训练，不调用生产特征、拟合、预测器。预测时只有矩阵乘法和核权重，无新拟合。CAL不选模型/阈值，固定HISTORY_KERNEL在QUAL前锁定。

{models}

{figure}

评分为H8/H16×三配对的XY端点RMSE，缺失/无效罚1m、封顶1m，80位十进制HALF_EVEN至纳米。主指标是完整分配损失，包含缺失罚分；可用子集仅描述。不能把含罚分均值称为纯物理误差。9独立组按干预时点分层bootstrap10,000次，相关步/配对不当作独立样本。

{contrasts}

{interpretation}
全局FIR在本次新人口中为强参考，不能把这轮分数与旧QUAL直接比较并称为旧版改善：种子、实际可用窗口和缺失罚分比例均不同，旧资格仍关闭。HISTORY与STATE两核也改变了距离几何（分别除以153和41）；其比较不是仅增加历史信息而其他因素完全相同的因果消融。不能由两者差值证明信息价值或唯一失败原因。

资格门：

{gates}

有独立QUAL时，全部边际如下，单位mm；任务×条件×获取×时点×H全部交叉层保留在all_qualification_panels.csv，没有挑选子集。未进入QUAL时不生成该表。

{details}

## 失败、限制与后续判断

{failure_text}

完整逐例与缺失原因见all_case_outcomes.csv、full_population_missingness.json，逐步记录原样保留。包末成功标志不是完整任务成功率；未执行任务尾部，完整截止损失及错误更新率均为未评价，不能填零。
FIR原资格、旧ARX/GRU/SS/F20和A1负结果不改变。本版不因结果换历史长度、带宽、特征、最佳任务或强参考。负结果只否定固定候选的本次资格，不能推导所有公开历史都无信息或唯一物理失配原因。通过也不能自动进入逆控制或声称适应收益。

下一步判断：{decision['next']}。最终仍要新获取/采用机制在自身独立时序中以包含获取/失败的完整截止损失超过强控制，并完成消融。DIRECT_C8、积分、RAW PI/廉价固定率、始终获取/不更新及标准检测/历史辨识/任务相关获取不能被削弱。

## 成本与来源

{cost_table}

本版实际{total['executions']}次、{total['control_steps']}控制步、{total['all_resets']}全部重置、{total['physical_frames']}帧；上限864/80,640/44,064/22,435,200。包括工厂50次内部重置和每尝试一次受控初始重置。主求解{total['primary_scientific_ridge_solves']}，独立增广LS {total['independent_augmented_lstsq_solves']}，独立特征分解{total['independent_eigendecompositions']}。模型使用与计算延迟单列于costs.json和canonical_forecast_latencies.json；审计CPU查询另收费。
冻结前构造测试的数值费用与科学拟合分开，前两次由确定性断言/控制流复算、最后一次由外层guard实测，不能混称全为测量。旧来源原账本和哈希单列，不复用旧样本或权重、不重复计作新交互。在线LLM API=0，神经更新=0，C4/C8拟合=0，物理恢复=0。
独立执行审计复算float32仿射/死区→XYZ噪声→最终裁剪及每个原生目标更新；补充策略重放只读保存观测，共享原策略类/调度解析器的限制已披露，不是独立物理重仿真。

历史条件、核LPV、模型适用域、收益预测及策略相关建模都有先例。查新及阅读范围见[决定文档](../docs/research/history_response_decision_v1_zh.md)，包括[LPV核辨识](https://arxiv.org/abs/2303.07932)、[MDE](https://arxiv.org/html/2401.04007v2)、[OCCAM](https://arxiv.org/html/2406.17620v1)、[CAPTURE](https://arxiv.org/html/2410.20357v2)及[策略驱动世界模型](https://proceedings.mlr.press/v306/chen26fl.html)。尚未建立超出这些路线的新颖性。

协议docs/protocols/history_response_v1_zh.md；入口scripts/run_history_response_v1.py。科学人口不重跑。原始gzip保留，结果提交包含不超过4MiB分片及索引，逐个实际恢复和核对哈希，恢复副本保留；远端紧凑归档明确省略原始gzip和.bin分片，不声称远端包含全部大记录。
'''
        report=ROOT/'reports/history_response_v1_zh.md';write(report,text)
    io.write(out/'report_receipt.json',dict(integrity='RENDERED_TEXT',report_sha256=io.sha(report),source_manifest_sha256=io.sha(path),source_artifacts_sha256=source_hashes,
        guard=guard,wall_ns=perf_counter_ns()-start,status=status,new_environment_steps=0,new_model_fits=0,online_LLM_API_calls=0))
    costs_file=io.read(out/'costs.json');costs_file['analysis_guard']=guard;io.write(out/'costs.json',costs_file,exclusive=False)
    archives=a.BASE/'archives_v1';archives.mkdir(parents=True,exist_ok=True)
    attribute=archives/'.gitattributes'
    if not attribute.exists():write(attribute,'**/*.bin binary\n*.json text eol=lf\n')
    dest=archives/root.name;dest.mkdir(exist_ok=False);restoration=a.BASE/'restoration_v1'/root.name;restoration.mkdir(parents=True,exist_ok=False);catalog=[]
    for split in a.SPLITS:
        folder=root/split.lower();done=optional(folder/'completion.json')
        if done is None:continue
        for name,sha in done['artifact_sha256'].items():
            original=folder/name;io.require(io.sha(original)==sha,'unchanged collection bytes')
            if original.suffix!='.gz':continue
            parts=dest/split.lower()/(name+'.parts');packed=split_file(original,parts,sha,part_bytes=4*1024**2)
            proof=restore(parts/'parts.json',restoration/split.lower()/name)
            io.require(proof['sha256']==sha and proof['size']==original.stat().st_size,'actual raw byte restoration')
            catalog.append(dict(split=split,source=original.relative_to(ROOT).as_posix(),size=original.stat().st_size,sha256=sha,
                index=(parts/'parts.json').relative_to(ROOT).as_posix(),index_sha256=io.sha(parts/'parts.json'),parts=len(packed['parts']),actual_restore=proof,remote_raw_or_binary_published=False))
    io.write(dest/'catalog.json',dict(integrity='PASSED',files=catalog,originals_preserved=True,restoration_copies_retained=True,new_environment_steps=0,online_LLM_API_calls=0))
    print(dict(report=str(report),status=status,costs=total,archives=len(catalog)),flush=True)

if __name__=='__main__':build(Path(sys.argv[1]).resolve())

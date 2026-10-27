"""Post-run presentation and full raw-byte transport; no scientific fits/physics."""
from pathlib import Path
from collections import Counter,defaultdict
from time import perf_counter_ns
import csv,sys,shutil
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import paired_packet_io_v1 as a
from src.analysis.release_learning_guard_v1 import read_only
from scripts.archive_action_response import split_file,restore
io=a.io


def table(head,rows):return '| '+' | '.join(head)+' |\n| '+' | '.join('---' for _ in head)+' |\n'+''.join('| '+' | '.join(str(x) for x in row)+' |\n' for row in rows)
def write_text(path,text):
    with path.open('x',encoding='utf8',newline='\n') as f:f.write(text)


def build(path):
    m=a.checked(path);root=path.parent;out=root/'presentation';out.mkdir(exist_ok=False);start=perf_counter_ns();guard={};phase_rows=[];case_rows=[];reasons=[];cost={};forecast_counts=Counter();latency=[]
    io.require((root/'pipeline_control/completion.json').exists() or list((root/'pipeline_control').glob('*failure.json')),'stopped complete/failed pipeline only')
    with read_only(guard):
        failures={p.name:io.read(p) for p in (root/'pipeline_control').glob('*failure.json')}
        for split in a.SPLITS:
            folder=root/split.lower()
            if not (folder/'summary.json').exists():phase_rows.append([split,0,a.limits(split)['executions'],'未执行','—','—','—']);continue
            s=io.read(folder/'summary.json');counts=s['lifecycle']['counts'];audit=io.read(folder/'audit.json') if (folder/'audit.json').exists() else None
            cs=list(io.rows(folder/'cases.jsonl.gz'));full=sum(c['complete_packet'] for c in cs);entries=sum(c['entry_at_calls'] is not None for c in cs)
            failed=io.read(folder/'failed_case.json') if (folder/'failed_case.json').exists() else None
            cost[split]=dict(executions=len(cs)+int(failed is not None),completed_executions=len(cs),control_steps=s['control_steps'],all_resets=counts.get('reset_attempts',0),physical_frames=counts.get('simulation_frames_completed',0),
                fixed_policy_queries=sum(c['policy_queries'] for c in cs)+(failed or {}).get('policy_queries',0),independent_policy_queries=0 if audit is None else audit['extra_independent_policy_queries'],
                collection_wall_s=s['wall_ns']/1e9,record_audit_wall_s=None if audit is None else audit['wall_ns']/1e9,model_fits=s['new_model_fits'],online_LLM_API_calls=s['online_LLM_API_calls'])
            phase_rows.append([split,len(cs),a.limits(split)['executions'],s['status'],s['control_steps'],entries,full])
            for c in cs:
                case_rows.append({k:c[k] for k in (*a.KEYS,'total_steps','reposition_steps','common_measure_steps','entry_at_calls','packet_steps','complete_packet','reason','success_at_response_horizon','terminated','truncated')})
                fr=c['forecast_record']
                if fr is not None and fr['canonical']:
                    forecast_counts.update(fr['model_compute_counts']);latency.append(dict(split=split,group=c['group'],task=c['task'],context=c['context'],acquisition_action=c['acquisition_action'],compute_wall_ns=fr['compute_wall_ns'],error=fr['forecast_error']))
            if failed is not None:
                row={k:failed.get(k) for k in (*a.KEYS,'total_steps','reposition_steps','common_measure_steps','entry_at_calls','packet_steps','complete_packet','reason','success_at_response_horizon','terminated','truncated')};row['reason']='EXECUTION_EXCEPTION';case_rows.append(row)
            for task in io.TASKS:
                for ctx in ('UNCHANGED','CHANGED'):
                    for anchor in ('IN_TASK','MOVE'):
                        for boundary in (16,32,64):
                            rr=[c for c in cs if c['task']==task and c['context']==ctx and c['acquisition_action']==anchor and c['boundary']==boundary]
                            reasons.append(dict(split=split,task=task,context=ctx,acquisition_action=anchor,boundary=boundary,allocated=len(rr),entries=sum(c['entry_at_calls'] is not None for c in rr),
                                full_packets=sum(c['complete_packet'] for c in rr),reasons=dict(Counter(c['reason'] for c in rr))))
        io.write(out/'all_case_outcomes.json',case_rows);io.write(out/'full_population_missingness.json',reasons);io.write(out/'canonical_forecast_latencies.json',latency)
        names=('split','group','task','seed','context','boundary','acquisition_action','packet_kind','total_steps','reposition_steps','common_measure_steps','entry_at_calls','packet_steps','complete_packet','reason','success_at_response_horizon','terminated','truncated')
        with (out/'all_case_outcomes.csv').open('x',encoding='utf8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=names,lineterminator='\n');w.writeheader();w.writerows(case_rows)
        total={k:sum(v[k] for v in cost.values()) for k in ('executions','control_steps','all_resets','physical_frames','fixed_policy_queries','independent_policy_queries')}
        train=io.read(root/'training/training_receipt.json') if (root/'training/training_receipt.json').exists() else None
        ta=io.read(root/'training/audit.json') if (root/'training/audit.json').exists() else None
        partial=[]
        if (root/'training/failure.json').exists():partial.append(io.read(root/'training/failure.json').get('receipt',{}).get('operation_counts',{}))
        for failure in failures.values():
            for frame in failure.get('partial_counters',[]):
                for key in ('receipt','guard'):
                    if isinstance(frame.get(key),dict):partial.append(frame[key].get('operation_counts',{}))
        total.update(primary_scientific_ridge_solves=max([v.get('solve_attempts',0) for v in partial]+([train['receipt']['operation_counts']['solve_attempts']] if train else [0])),
            independent_augmented_lstsq_solves=max([v.get('lstsq_attempts',0) for v in partial]+([ta['receipt']['operation_counts']['lstsq_attempts']] if ta else [0])),
            training_main_and_literal_bank_query_checks=0 if ta is None else ta['training_bank_checks'],actual_online_forecast_counts=dict(forecast_counts),
            online_LLM_API_calls=0,neural_updates=0,C4_C8_fits=0,new_model_used_for_control=False,
            prefreeze_test_executions=30+34+35+35+37,prefreeze_synthetic_ridge_solves=15,prefreeze_synthetic_lstsq_solves=5,prefreeze_synthetic_inverse_checks=5,
            unique_new_tests=37,old_source_bound_tests_reused=2228,old_simulation_tests_repeated=False)
        native_source=ROOT/'outputs/native_command_witness/qualification_v1/native_command_witness_20261022T172319Z_9c64ab52ca23/native/summary.json';prior=io.read(native_source)
        historical=dict(old_training_samples_reused=0,old_learned_model_weights_loaded=0,source_native_interface_qualification=dict(path=native_source.relative_to(ROOT).as_posix(),sha256=io.sha(native_source),
            executions=prior['executions'],control_steps=prior['control_steps'],all_resets=prior['lifecycle']['counts']['reset_attempts'],physical_frames=prior['lifecycle']['counts']['simulation_frames_completed']),
            shared_PI_PID_engineering_history=dict(report='reports/acquisition_reference_qualification_v1_zh.md',report_sha256=io.sha(ROOT/'reports/acquisition_reference_qualification_v1_zh.md'),
                not_new_training_data=True,all_original_ledgers_retained=True,not_added_again_to_current_costs=True))
        total.update(primary_bootstrap_replicates=10000 if (root/'qual_evaluation/result.json').exists() else 0,independent_bootstrap_reconstruction_replicates=10000 if (root/'qual_evaluation/audit.json').exists() else 0)
        io.write(out/'costs.json',dict(by_phase=cost,total=total,historical_sources_separate=historical,analysis_guard=guard,full_task_tail_evaluated=False))
        qual=io.read(root/'qual_evaluation/result.json') if (root/'qual_evaluation/result.json').exists() else None
        status='PIPELINE_FAILED_RETAINED' if failures else qual['status'];io.write(out/'research_decision.json',dict(status=status,qualification=qual,
            failure_records=failures,no_retry_or_extension=True,old_failed_versions_remain_closed=True,not_absolute_plant_or_inverse_qualification=True,task_utility_unevaluated=True,
            next='独立设计纠正后适用性/完整成本决策及强参考；本组件不直接进入逆控制' if qual and qual['status']=='QUALIFIED_RESPONSE_CONTRAST_COMPONENT_ONLY' else '封存本版本，不追加样本或修参数；先定位数据/观测/实现资格限制',
            algorithm_novelty_established=False,publication_goal_complete=False))
        model_table=detail_table=primary_table='尚无独立 QUAL 分数。\n'
        if qual:
            panels=io.read(root/'qual_evaluation/panels.json');all_rows=[p for p in panels if p['level']==[]]
            model_table=table(['模型','全人口平均端点损失 mm↓','可用窗口描述性均值 mm↓','可用/全部端点'],[[p['method'],f"{p['mean_endpoint_loss_m']*1000:.6f}",f"{p['available_only_mean_endpoint_loss_m']*1000:.6f}" if p['available_only_mean_endpoint_loss_m'] is not None else '缺失',f"{p['available_endpoints']}/{p['allocated_endpoints']}"] for p in all_rows])
            primary_table=table(['选定模型−参考','均差 mm','组 bootstrap95% mm'],[[b,f"{v['mean_difference_m']*1000:+.6f}",f"[{v['bootstrap95_m'][0]*1000:+.6f}, {v['bootstrap95_m'][1]*1000:+.6f}]"] for b,v in qual['co_primary'].items()])
            detail_table=table(['层','ZERO mm','INSTANT mm','FIR mm','CENTERED_FIR mm','FREE_CAUSAL mm'],[[str(v)]+[f"{next(p['mean_endpoint_loss_m'] for p in panels if p['level']==[field] and p['strata']=={field:v} and p['method']==kind)*1000:.6f}" for kind in ('ZERO','INSTANT','FIR','CENTERED_FIR','FREE_CAUSAL')] for field,values in (('task',io.TASKS),('context',('UNCHANGED','CHANGED')),('acquisition_action',('IN_TASK','MOVE')),('boundary',(16,32,64)),('horizon',(8,16))) for v in values])
        phases=table(['阶段','已执行','冻结分配','状态','控制步','实际入口','完整16步包'],phase_rows)
        ct=table(['阶段','控制步','全部重置','物理帧','在线/审计固定策略查询','采集秒'],[[s,v['control_steps'],v['all_resets'],v['physical_frames'],f"{v['fixed_policy_queries']}/{v['independent_policy_queries']}",f"{v['collection_wall_s']:.3f}"] for s,v in cost.items()])
        fail_text='无阶段执行异常。' if not failures else '\n'.join(f"- `{n}`：`{v['exception'].splitlines()[-1]}`。部分计数、记录和异常原文均保留。" for n,v in failures.items())
        gates='尚未进行独立资格评价。' if not qual else '\n'.join(f"- `{k}`：`{v}`。" for k,v in qual['gates'].items())
        interpretation='尚无完整资格结论。'
        if qual:
            v=qual['co_primary']['INSTANT'];interpretation=f"选定 FIR 相对 INSTANT 的全人口平均差为 {v['mean_difference_m']*1000:+.6f} mm，95% 区间 [{v['bootstrap95_m'][0]*1000:+.6f}, {v['bootstrap95_m'][1]*1000:+.6f}] mm。"
            if qual['status']=='CLOSED_NEGATIVE':interpretation+='区间跨零，未建立相对强参考的稳定优势；这也不证明两者等价。reach 和 H16 的预设点规则未通过。数值/记录门通过与性能门失败分别保留，不能把资格失败解释成纯软件问题。'
        training_text=f"尚未完成训练；已尝试主求解 {total['primary_scientific_ridge_solves']}、独立求解 {total['independent_augmented_lstsq_solves']}，失败费用保留。" if not train else f"TRAIN 共 {train['families']} 个登记家族，完整三角色 H16 家族 {train['complete_families']}；主求解 {total['primary_scientific_ridge_solves']}，独立增广最小二乘 {total['independent_augmented_lstsq_solves']}。"
        figure='' if qual is None else f'![完整五参考对照图](../outputs/paired_packet_response/development_v1/{root.name}/presentation/qualification.png)\n'
        text=f'''# A线：已知命令包响应差异模型 v1 中文报告

结果状态：**`{status}`**。本轮是标准前向响应组件的训练与独立资格试验，完整任务收益尚未评价，算法新颖性尚未成立，CCF A 目标仍未完成。

## 冻结与执行

科学冻结 `{m['source_git_commit']}`，运行 `{m['experiment_run_id']}`，清单 `{m['manifest_id']}`。
先实现收集器、测试、独立审计与固定预算，再提交冻结，随后一次性执行。在线 LLM API 调用为零。
37 项新测试通过，2,228 项旧检查按源码哈希复用，未重跑旧仿真。171 次冻结前测试执行中重复项目不重复算新测试；合成求解费用与科学训练分列。

冻结前发现包装器的墙钟计时会造成跨新尝试哈希误报。原35项候选回执保留，补充2项约束测试；仅投影掉唯一已知 `episode_start_time`，原始完整 Python 哈希另存，不改实际包装器或 RNG/物理状态。
`freeze_validation_v2` 的编译、依赖、全仓秘密扫描、实际暂存对象补充扫描、普通/暂存差异和提交后60对象字节核对通过。

{phases}

## 方法名称与可用信息

每个家族含 ZERO/PLUS/MINUS 三个独立实际尝试，共同前缀、获取程序及入口一致。可选 MOVE 是原 LOCAL_PID，随后真实 common8，再执行预先公开16步包。不能重置撤销移动。ZERO 入口先保存全部三配对预测，另两尝试核对真实入口后复用，不能看 ZERO 结果重算。

- ZERO：假定两组命令不会产生响应差异。
- INSTANT：用一个固定 XY 增益矩阵乘累计命令差。
- FIR（有限脉冲响应）：用16个延迟响应核表达输入对后续运动的影响。
- CENTERED_FIR：同数据三角色减均值的回归，登记为 FIR 的等价性检查，不计新算法。
- FREE_CAUSAL：每个预测时长单独拟合线性映射，禁止读该时长之后的命令。

模型只用任务名与已知命令。入口公共历史用于因果性/配对审计，不作为状态条件特征。真实扰动、实际噪声、私有状态只用于执行核对，不进入拟合输入或标签。所有标签都是实际公共 XY 观测。
ZERO 角色发送零命令，实际仍受扰动和噪声影响，不能把它称为物理静止。
未来输入已知依赖本轮的固定开放环包；不能外推为闭环未知动作预测。模型从未求逆或进入任务控制。

## 训练、校准与独立资格

{training_text}
固定 ridge=0.001、16阶、TRAIN 加权 RMS、不设截距。缺失家族不进入拟合，但保留全部分母；输入依赖的生存选择并未被随机命令消除。CAL 只选一个全局 FIR/FREE_CAUSAL，权重不重训；模型锁先于 QUAL。

{model_table}

{figure}

主评分是 H8/H16 的三配对端点 XY RMSE，缺失/无效端点罚1m，数值上限1m，十进制80位后舍入至1nm。可用子集均值仅作描述，不能替代全分配评价。组等权，9个独立组按边界分层 bootstrap10,000次。

{primary_table}

{interpretation}

QUAL 每模型 648 个登记端点中，484 个可用、164 个缺失，所有方法使用同一缺失惩罚。数百毫米的全人口分数主要包含这一预设惩罚，不能称为实际可用窗口的纯物理预测误差。可用子集仍有生存选择和不同组内分母。

资格门：

{gates}

完整边际分层如下。任务×条件×获取×时点×H 的全部交叉层保存在 `qual_evaluation/panels.json`，没有按结果挑子集。

{detail_table}

## 缺失、失败与识别边界

{fail_text}

全部实际案例、提前结束、未达锚点、部分包及原因见 `presentation/all_case_outcomes.csv` 和 `full_population_missingness.json`，也保留每步原始记录。包末成功标志只描述该有限响应窗口，不能当作完整任务成功率；本轮没有任务尾部或截止损失比较。
没有执行采用新模型纠正的完整任务，错误更新率与完整截止损失均为未评价，不填零。
独立记录审计复算 float32 仿射/死区→XYZ噪声→最终裁剪及原生目标更新，核对真实前后值、噪声游标、命令引用和生命周期。补充重放共享调度程序/原策略类，只使用保存观测，不物理重仿真。全状态哈希是固定运行时的来源见证，不能当作普遍隐藏状态或安全证明。

## 完整费用

{ct}

实际总计 {total['executions']} 次、{total['control_steps']} 控制步、{total['all_resets']} 全部重置、{total['physical_frames']} 物理帧；冻结上限864次/80,640步/44,064次重置/22,435,200帧。包含工厂每次50次内部重置及受控初始重置，未把这部分隐藏为免费准备。
科学主线性求解 {total['primary_scientific_ridge_solves']}、独立复算 {total['independent_augmented_lstsq_solves']}；在线实际预测计数 `{dict(forecast_counts)}`。原生见证与日志耗时包括在采集时间内，模型计算逐次延迟另存。在线 LLM API=0，神经更新=0，C4/C8拟合=0，恢复=0。
旧数据/试验费用不计为本轮新增，但旧历史保留；不利用旧资格调整本轮模型或阈值。详见 `presentation/costs.json`。
历史来源费用单列：已声明原生接口的既有资格为18次、2,835控制步、918次全部重置、473,175帧，来源哈希写入成本清单。固定 PI/PID 原语的原开发账本见 `reports/acquisition_reference_qualification_v1_zh.md`；不将重叠历史重复加总。旧训练样本复用=0、旧学习模型权重加载=0。本轮独立训练成本另列，不能把已有工程原语说成从零免费开发。

## 后续判断与已有工作

标准动态模型通过时，只支持它在本分配的已知命令响应差异上作为参考；仍需检验纠正后的实际状态/输入适用性和包含获取成本的任务收益。失败则封存版本，不扩样、修权重、换最佳任务或叠加选择规则。
本次模型按任务固定，入口状态历史未作为特征；状态、参数变化、接触和噪声均可能影响表现。本试验不能区分唯一失败原因，不根据 QUAL 增添特征补救当前版本。
配对未来输入诊断已有研究，见[2026年时间序列模型研究](https://arxiv.org/html/2610.08118v1)；闭环辨识与反事实适应也已有 [AdaptOn](https://arxiv.org/abs/2003.11227)。本轮未复现这些论文，也不主张配对/FIR/中心化为创新。
MDE、Residual RL、OCCAM、GAUGE、Poke and Strike、TOM 等仍是必要邻近路线，阅读范围和限制见 `docs/research/paired_packet_response_decision_v1_zh.md`。
下一项研究仍要建立“获取改变实际状态与模型适用性”时的具体机制，保留 DIRECT_C8、积分补偿、RAW PI/廉价固定率、始终获取/不更新及标准辨识/检测/任务相关获取强参考，在新方法自身独立时序中证明完整截止损失优势并做消融。测试、组件资格和归档均不代替论文贡献。

## 来源与复算

冻结协议 `docs/protocols/paired_packet_response_v1_zh.md`；入口 `scripts/run_paired_packet_response_v1.py`；原科学分配不允许重跑。可对原记录运行另行版本化的只读审计，不改已存在输出。
原始 gzip 均留本地，结果提交包含≤4MiB原始字节分片及索引，逐个实际恢复并核对字节；恢复副本保留。来源、大小、哈希、索引和恢复证明见 `outputs/paired_packet_response/archives_v1`。紧凑远端归档沿既有规则省略原始gzip和二进制分片，目录明确列出省略项目，不能声称远端已具备全部大记录。
'''
        report=ROOT/'reports/paired_packet_response_v1_zh.md';write_text(report,text)
        io.write(out/'report_receipt.json',dict(report_sha256=io.sha(report),source_manifest_sha256=io.sha(path),guard=guard,wall_ns=perf_counter_ns()-start,
            new_environment_steps=0,new_model_fits=0,online_LLM_API_calls=0,status=status))
    # Guard receipt is finalized after leaving the scope.
    r=io.read(out/'report_receipt.json');r['guard']=guard;io.write(out/'report_receipt.json',r,exclusive=False)
    c=io.read(out/'costs.json');c['analysis_guard']=guard;io.write(out/'costs.json',c,exclusive=False)
    archives=a.BASE/'archives_v1'/root.name;archives.mkdir(parents=True,exist_ok=False);restoration=a.BASE/'restoration_v1'/root.name;restoration.mkdir(parents=True,exist_ok=False);catalog=[]
    for split in a.SPLITS:
        folder=root/split.lower()
        if not (folder/'completion.json').exists():continue
        done=io.read(folder/'completion.json')
        for name,h in done['artifact_sha256'].items():
            source=folder/name;io.require(io.sha(source)==h,'unchanged collection bytes')
            if source.suffix!='.gz':continue
            dest=archives/split.lower()/(name+'.parts');packed=split_file(source,dest,h,part_bytes=4*1024**2);proof=restore(dest/'parts.json',restoration/split.lower()/name)
            io.require(proof['sha256']==h and proof['size']==source.stat().st_size,'actual restored bytes')
            catalog.append(dict(split=split,source=source.relative_to(ROOT).as_posix(),size=source.stat().st_size,sha256=h,index=(dest/'parts.json').relative_to(ROOT).as_posix(),index_sha256=io.sha(dest/'parts.json'),
                parts=len(packed['parts']),actual_restore=proof,remote_raw_or_binary_published=False))
    io.write(archives/'catalog.json',dict(integrity='PASSED',files=catalog,originals_preserved=True,restoration_copies_retained=True,new_environment_steps=0,online_LLM_API_calls=0))
    print(dict(report=str(report),status=status,costs=total,archives=len(catalog)),flush=True)


if __name__=='__main__':build(Path(sys.argv[1]).resolve())

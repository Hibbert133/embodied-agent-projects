"""Full-population descriptive exports; no fitting or counterfactual rollouts."""
from pathlib import Path
from collections import Counter,defaultdict
from itertools import product
from time import perf_counter_ns
import csv,json,sys
import numpy as np
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from scripts import run_correction_effect_learning_v1 as command
from src.analysis.release_learning_guard_v1 import read_only
main=command.main;io=main.io;path=Path(sys.argv[1]).resolve();main.checked(path);run=path.parent
out=run/'presentation';out.mkdir(exist_ok=False);start=perf_counter_ns();guard={}

def export(name,rows,fields):
    with (out/name).open('x',encoding='utf8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(rows)

with read_only(guard):
    rows=io.read(run/'pairs/public_pairs.json');register=io.read(run/'pairs/pair_register.json');private=io.read(run/'pairs/oracle_diagnostics.json')
    pred=io.read(run/'models/predictions.json');lookup={(p['pair_id'],p['kind']):p for p in pred};decision=io.read(run/'evaluation/decision.json');panels=io.read(run/'evaluation/panels.json')
    assert len(register)==972 and len({r['pair_id'] for r in register})==972
    for name in ('pairs','models','evaluation'):assert io.read(run/name/'audit.json')['integrity']=='PASSED'
    methods=main.model.COMPARATORS;pair_lookup={r['pair_id']:r for r in rows};private_lookup={r['pair_id']:r for r in private}
    tasks=sorted(set(r['task'] for r in register));contexts=sorted(set(r['context'] for r in register));boundaries=sorted(set(r['boundary'] for r in register))
    actions=sorted(set(r['acquisition_action'] for r in register));rates=[list(x) for x in main.PAIRS]
    rate_values=[(main.RATES[a],main.RATES[b]) for a,b in main.PAIRS]
    statuses=('ACTUAL_DIVERGENCE','BEFORE_DECISION_TERMINAL','ACQUISITION_TERMINAL','NO_SENT_DIFFERENCE')
    def metrics(subset):
        if not subset:return {kind:None for kind in methods}
        weights=main.weights(subset)
        return {kind:float(sum(float(w)*lookup[(r['pair_id'],kind)]['mse'] for w,r in zip(weights,subset))) for kind in methods}
    # Full Cartesian source cells, including cells without a defined first fork.
    cells=[]
    for task,context,boundary,action,rate in product(tasks,contexts,boundaries,actions,rate_values):
        selected=[r for r in register if (r['task'],r['context'],r['boundary'],r['acquisition_action'],tuple(r['rates']))==(task,context,boundary,action,rate)]
        assert len(selected)==3
        available=[pair_lookup[r['pair_id']] for r in selected if r['status']=='ACTUAL_DIVERGENCE'];counts=Counter(r['status'] for r in selected)
        cells.append(dict(task=task,context=context,boundary=boundary,acquisition_action=action,rate_a=rate[0],rate_b=rate[1],registered=3,available=len(available),
            independent_groups=len({r['group'] for r in available}),**{s:counts[s] for s in statuses},**metrics(available)))
    assert len(cells)==324 and sum(r['registered'] for r in cells)==972 and sum(r['available'] for r in cells)==len(rows)
    export('full_strata_324.csv',cells,list(cells[0]));io.write(out/'full_strata_324.json',cells)
    flat=[]
    for r in register:
        record={k:r[k] for k in ('pair_id','group','task','context','boundary','acquisition_action','first_difference','status','loss_difference','success_a','success_b')}
        record.update(rate_a=r['rates'][0],rate_b=r['rates'][1]);record.update({kind:lookup[(r['pair_id'],kind)]['mse'] if r['pair_id'] in pair_lookup else None for kind in methods});flat.append(record)
    export('all972_pair_register.csv',flat,list(flat[0]))
    extras=[]
    for keys in (('group',),('rates',),('task','context','boundary','acquisition_action')):
        grouped=defaultdict(list)
        for r in register:grouped[tuple(tuple(r[k]) if k=='rates' else r[k] for k in keys)].append(r)
        for values,subset in sorted(grouped.items(),key=lambda v:str(v[0])):
            actual=[pair_lookup[r['pair_id']] for r in subset if r['status']=='ACTUAL_DIVERGENCE']
            extras.append(dict(axes=list(keys),values=list(values),registered=len(subset),available=len(actual),statuses=dict(Counter(r['status'] for r in subset)),mse=metrics(actual)))
    io.write(out/'additional_panels.json',extras)
    w=main.weights(rows);diagnostic={name:float(sum(float(q)*private_lookup[r['pair_id']][name] for q,r in zip(w,rows))) for name in ('nominal_sent_error','applied_semantics_error_oracle','zero_effect_error')}
    ratios={}
    for name in ('observed_to_sent_norm_ratio','observed_to_applied_norm_ratio_oracle'):
        values=[r[name] for r in private if r[name] is not None];ratios[name]=dict(available=len(values),missing=len(private)-len(values),pair_median=None if not values else float(np.median(values)),pair_p90=None if not values else float(np.quantile(values,.9)))
    diagnostic.update(ratios=ratios,ratios_are_correlated_pair_descriptions_not_independent_estimates=True,applied_action_is_private_diagnostic_only=True,not_a_noise_free_physics_error=True)
    quantiles=[0.,.1,.5,.9,1.]
    diagnostic['first_fork_magnitude_quantiles']={name:dict(zip(('min','p10','p50','p90','max'),np.quantile(values,quantiles).tolist())) for name,values in (
        ('sent_XY_L2',[float(np.linalg.norm(np.asarray(r['input']['command_b'][:2])-np.asarray(r['input']['command_a'][:2]))) for r in rows]),
        ('actual_effect_XY_L2_mm',[10*float(np.linalg.norm(r['target']['effect'])) for r in rows]))}
    global_models=[]
    for fold in range(9):
        scalar=io.read(run/f'models/group{fold}_GLOBAL_SCALAR.json');matrix=io.read(run/f'models/group{fold}_GLOBAL_MATRIX.json')
        global_models.append(dict(held_group=fold,scalar=float(scalar['coef'][0][0]/scalar['scale'][0]),
            matrix_input_rows_output_columns=(np.asarray(matrix['coef'])/np.asarray(matrix['scale'])[:,None]).tolist()))
    diagnostic['fitted_global_references']=global_models
    io.write(out/'diagnostic_summary.json',diagnostic)
    total=next(p for p in panels if not p['axes']);bytask=[p for p in panels if p['axes']==['task']]
    group_rows=[p for p in extras if p['axes']==['group']]
    outcomes=Counter((r['success_a'],r['success_b']) for r in register)
    verdict='通过预先固定的开发点比较' if decision['status']=='DEV_PREDICTIVE_ADVANTAGE' else '未通过预先固定的开发点比较，封存本版本负结果'
    next_step=('仅支持另行设计独立响应资格协议；先明确适用域、训练/校准/资格分配和强简单参考，不能直接接入逆控制或扩大任务评价。' if decision['status']=='DEV_PREDICTIVE_ADVANTAGE' else
        '停止该版成对上下文回归；不调整ridge、特征、子任务或样本量挽救。当前证据不足以支持将此构件用于纠正或解锁新采集。后续研究须提出独立机制，并先对简单全局作用模型与状态历史参考作同权限比较。')
    io.write(out/'research_decision.json',dict(status=decision['status'],development_only=True,next_step=next_step,new_collection_unlocked=False,task_benefit_qualified=False,
        old_native_qualification='FAILED_RETAINED',CCF_A_goal_complete=False,all972_pairs_retained=True,all324_cells_exported=True))
    def table(header,data):return '| '+' | '.join(header)+' |\n| '+' | '.join(['---']*len(header))+' |\n'+'\n'.join('| '+' | '.join(map(str,row))+' |' for row in data)
    overall_table=table(['方法','整体效应 MSE↓']+tasks,[[kind,f"{total['mse'][kind]:.9g}"]+[f"{next(p for p in bytask if p['values']==[task])['mse'][kind]:.9g}" for task in tasks] for kind in methods])
    groups_table=table(['整组','有分歧／登记']+list(methods),[[p['values'][0],f"{p['available']}/{p['registered']}"]+[('缺失' if p['mse'][kind] is None else f"{p['mse'][kind]:.6g}") for kind in methods] for p in group_rows])
    phase_times={name:io.read(run/name/'receipt.json')['wall_ns']/1e9 for name in ('pairs','models','evaluation')}
    audit_times={name:io.read(run/name/'audit.json')['wall_ns']/1e9 for name in ('pairs','models','evaluation')}
    cost=dict(source_actual_executions=648,source_groups=9,source_control_steps=77563,source_all_resets=33048,source_physical_frames=16911815,
        new_environment_creations=0,new_resets=0,new_control_steps=0,new_physical_frames=0,new_robot_seeds=0,online_LLM_API_calls=0,
        scientific_ridge_fits=36,independent_augmented_lstsq_refits=36,neural_updates=0,
        main_held_pair_model_evaluations=len(pred),independent_held_pair_model_evaluations=len(pred),
        main_saved_weight_file_reads_in_held_prediction=4*len(rows),independent_saved_weight_file_reads_for_audit=36,
        descriptive_global_weight_reads_in_report=18,pre_report_inspection_global_weight_reads=18,
        evaluation_read_counts_derived_from_frozen_loops_not_network_requests=True,stage_wall_seconds=phase_times,audit_wall_seconds=audit_times)
    attempts=[]
    for f in sorted((main.BASE/'development_checks').glob('attempt_*/tests.json')):
        test=io.read(f);attempts.append(dict(name=f.parent.name,integrity=test['integrity'],unique_tests=test['tests_run'],synthetic_solve=test['guard']['operation_counts']['solve_attempts'],synthetic_lstsq=test['guard']['operation_counts']['lstsq_attempts']))
    cost['synthetic_test_attempts_separately_charged']=attempts;cost['unique_new_tests']=14;cost['unique_source_bound_test_total']=2216
    io.write(out/'costs.json',cost)
    statuses_table=table(['972 对完整分母中的状态','对数'],[[s,Counter(r['status'] for r in register)[s]] for s in statuses])
    matrix_gap=100*(total['mse']['PAIRED_CONTEXT']/total['mse']['GLOBAL_MATRIX']-1)
    mag=diagnostic['first_fork_magnitude_quantiles'];gain=[p['scalar'] for p in global_models]
    text=f'''# A线：真实命令分歧响应差与标准回归开发 v1

本报告全部新增分析属于**旧 TRAIN 上的事后描述性分析和标准构件开发**。结论：**{verdict}**。这不改变旧响应资格、ARX/F20负结果或原六项统计比较，也没有建立独立部署收益、算法新颖性或 CCF A 论文贡献。

## 来源、目标及完整分母

仅使用 A1 TRAIN 的648次已执行轨迹、9独立组、54任务/条件单元、162获取节点；CAL、TEST、旧QUAL和最新54次原生数据均未用于本次拟合。冻结提交 `{io.read(path)['source_git_commit']}`，运行 `{run.relative_to(ROOT).as_posix()}`。每节点四个已执行积分率0.125/0.5/2/8构成六对，完整登记972对。

{statuses_table}

只有首次实际float32发送命令不同且共同历史完整的 **{len(rows)}对** 有一步效应目标。其余对没有定义该目标，不补零，也不解释为预测失败或成功。表中MSE仅针对这部分条件人口。完整972行及全部324个任务×条件×时点×获取×率对单元分别见 `presentation/all972_pair_register.csv`、`full_strata_324.csv`；零可用单元误差留空，所有组与缺失原因保留。

核对四率的初始native/Python/RNG见证、同外生扰动与噪声承诺、共同获取返回点、相同发送命令和真实响应前缀、首分歧时物理时钟、同原始策略动作和Z/夹爪命令。只比较两个确实发生的下一观测，不生成未执行后缀。历史只取时点前两次已完成的真实转移。

目标是 Δd=(nextB−current)/0.01−(nextA−current)/0.01。它是保存的共同随机量实现下的有限命令响应差，不是无噪声物理误差、总体平均处理效果或任务收益。数值单位为归一化位移平方；换算XY平均mm²需乘100。此目标与旧绝对响应资格、F20名义跟踪评分的目标和条件人口不同，不能横向比较误差数值宣称旧问题解决。

## 六个标准参考及固定比较

ZERO_EFFECT预测零变化；NOMINAL_SENT直接用发送命令差Δu，代表未资格名义映射的动作差。GLOBAL_SCALAR和GLOBAL_MATRIX分别是全局一个增益及2×2矩阵；ABSOLUTE_CONTEXT在同一公开数据上回归两端绝对位移再相减；PAIRED_CONTEXT以公开上下文和Δu交互直接回归响应差。后两者分别48/32列，成对回归本身是标准构件，不称新算法。

固定16维公开上下文、ridge=0.01；只用训练折列RMS，不调参。9折逐整组留出，每折用其余8组训练，覆盖三个任务。每折四种拟合共36次；独立实现用增强lstsq重拟合36次。拆分和统计用组号，模型数值输入不含组、种子、任务名、条件、真实扰动、实际噪声、私有状态或任务结局。响应差标签来自公开观察，真实参数/噪声/实际施加动作隔离在诊断文件。

权重为组→可用任务/条件→获取节点→率对逐层等权。六对相关比较不当独立样本，重叠训练的9个LOO折也不当独立最终资格。不提供由这些重叠折伪造的最终置信保证。

{overall_table}

固定主规则要求PAIRED_CONTEXT整体及每个任务均严格低于ZERO_EFFECT、GLOBAL_MATRIX和ABSOLUTE_CONTEXT。判定为 `{decision['status']}`；没有按其他指标、子任务或最佳折替代门槛。

成对上下文整体MSE相对全局矩阵为 **{matrix_gap:+.3f}%**。这是固定点比较的失败，不据此宣称总体统计显著劣势。明显优于名义映射或同数据绝对回归，不能替代超过指定简单强参考的要求。

{groups_table}

![完整组和任务的效应预测误差](../{run.relative_to(ROOT).as_posix()}/presentation/figures/effect_prediction.png)

完整任务/条件/时点、获取动作和率对统计保存在机器可复算表中，包括无数据的全部单元。所有36个权重文件、逐对六方法预测、独立参数核验和全人口登记均保留。

## 名义动作语义与噪声诊断

按同一层级权重，名义发送差误差 **{diagnostic['nominal_sent_error']:.9g}**，实际施加动作差代入误差 **{diagnostic['applied_semantics_error_oracle']:.9g}**，零效应误差 **{diagnostic['zero_effect_error']:.9g}**。独立核对原float32仿射/死区→实际XYZ噪声→最终裁剪链及游标。实际施加动作只用于评估，未用于拟合或模型输入。

实际动作代入改变了输入语义；共同噪声在非线性动力学和裁剪后不必被完全消去。剩余误差不能称物理无噪声误差，误差变化也不唯一识别模型失配、接触、移动瞬态或噪声的贡献。比值分布及零分母缺失见 `diagnostic_summary.json`；比值按相关率对描述，不当独立证据。

另作事后尺度检查：首次分歧发送差L2的中位数/90分位/最大值为 {mag['sent_XY_L2']['p50']:.6g}/{mag['sent_XY_L2']['p90']:.6g}/{mag['sent_XY_L2']['max']:.6g}；对应真实响应差L2为 {mag['actual_effect_XY_L2_mm']['p50']:.6g}/{mag['actual_effect_XY_L2_mm']['p90']:.6g}/{mag['actual_effect_XY_L2_mm']['max']:.6g} mm。留组全局标量参考为 {min(gain):.6g}–{max(gain):.6g}。这只提示当前条件下名义单位增益并不合适，不能把小幅首分歧上的回归斜率称为全局植物参数、全动作域资格或可反演增益。完整九折标量/矩阵与五个尺度分位数均保存。

该实验能检查名义控制差与真实有限响应差是否一致，以及一个简单公开预测器在留组条件人口上是否有预测能力。反证包括全局矩阵、零效应或同数据直接位移参考可能同样好；不能从低误差推出绝对偏置已识别、纠正可安全反演或包含获取成本的任务收益。没有逐步接触力/接触对，不能唯一归因接触过程。

## 审计、费用与旧失败保留

主提取/主特征/主训练/主预测在独立相应审计中被禁用，分别重建首分歧、历史、特征、组权重、增强lstsq权重、留组预测与统计。独立数学和数组复算通过；共享旧执行器公式、NumPy与来源解析明确披露，不称不同机构审计或新的物理重模拟。

新增环境创建、重置、控制步、物理帧、机器人种子、在线LLM API均 **0**。新增36次科学ridge、36次独立重拟合、0神经更新。主与独立各 **{len(pred)}** 次留出成对模型预测；主保存权重读取 **{4*len(rows)}** 次，独立参数核验读取36次，按冻结循环单列。提取/拟合/统计分别耗时 {phase_times['pairs']:.3f}/{phase_times['models']:.3f}/{phase_times['evaluation']:.3f}秒；对应独立审计 {audit_times['pairs']:.3f}/{audit_times['models']:.3f}/{audit_times['evaluation']:.3f}秒。完整费用与来源哈希见 `costs.json`、manifest及各阶段receipt。

纯数组测试14项唯一；{len(attempts)}次开发测试各自1次合成solve和1次合成lstsq单列，重复运行不增加唯一测试数。源码绑定复用旧2202项，合计2216；旧六张量组另列，不重复仿真。来源648次/77,563控制步/33,048全部重置/16,911,815物理帧为已付历史费用，不隐去也不重复计为本轮。

原生资格仍为 `FAILED_RETAINED`，原审计软件失败及其只读修复记录保留，完整MOVE→测量→保存模型选择→连续执行链仍为0。原ARX/F20/旧响应版本不重开，原始文件、分片、恢复副本、全部缺失和负结果保留。提交前另核对编译、依赖、秘密与补充实际索引扫描、普通及暂存差异、Git/磁盘字节，并记录本地提交及紧凑归档回执。

## 后续判断与查新边界

{next_step}

当前仍分别缺少绝对响应资格、把纠正后模型适用性用于获取决策的明确机制、与强对照相同预算的独立自身时序历史、全任务成本优势和消融。保持DIRECT_C8、积分、固定廉价率、始终获取/不更新、标准检测与历史辨识、任务相关获取及完整成本Q/DR等参考。标准回归预测进步不能代替这些要求。

已有[MDE模型适用范围学习](https://arxiv.org/html/2401.04007v2)、[Residual RL](https://arxiv.org/abs/1812.03201)、[OCCAM](https://arxiv.org/html/2406.17620v1)、[GAUGE](https://arxiv.org/html/2609.32154v1)、[Poke and Strike](https://proceedings.mlr.press/v305/aoyama25a.html)及[策略相关模型TOM](https://proceedings.mlr.press/v211/ma23a.html)限制可主张范围：门控、残差混合、控制器表现预测、任务相关校准与探测、策略分布匹配均不能仅改名。共享随机量、成对回归、约束线性作用或重加权也不作为本轮新颖性。这里只作官方来源的部分阅读对照，没有声称完整复现或移植保证。

完整CCF A研究目标继续活跃，本次交付不是目标完成。
'''
    report=ROOT/'reports/correction_effect_learning_v1_zh.md';report.write_text(text,encoding='utf8',newline='\n')
io.write(out/'report_receipt.json',dict(integrity='FOR_DELIVERY_AUDIT',report_sha256=io.sha(report),all972_registered=True,all324_cells_exported=True,guard=guard,
    wall_ns=perf_counter_ns()-start,new_physics=0,new_fits=0,online_LLM_API_calls=0))
print(dict(status=decision['status'],available_pairs=len(rows),report=str(report)),flush=True)

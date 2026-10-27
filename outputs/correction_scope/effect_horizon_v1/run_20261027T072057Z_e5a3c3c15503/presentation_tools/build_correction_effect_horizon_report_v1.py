"""Complete descriptive horizon exports, no new statistical promotion rule."""
from pathlib import Path
from collections import Counter
from time import perf_counter_ns
import csv,json,sys
import numpy as np
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from scripts import run_correction_effect_horizon_v1 as command
from src.analysis.release_learning_guard_v1 import read_only
main=command.main;io=main.io;path=Path(sys.argv[1]).resolve();m=main.checked(path);run=path.parent;out=run/'presentation';out.mkdir(exist_ok=False);guard={};start=perf_counter_ns()

def export(name,rows):
    with (out/name).open('x',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def table(header,rows):return '| '+' | '.join(header)+' |\n| '+' | '.join(['---']*len(header))+' |\n'+'\n'.join('| '+' | '.join(map(str,r))+' |' for r in rows)

with read_only(guard):
    windows=io.read(run/'analysis/windows.json');panels=io.read(run/'analysis/panels.json');receipt=io.read(run/'analysis/receipt.json');audit=io.read(run/'analysis/audit.json');assert audit['integrity']=='PASSED'
    totals=sorted([p for p in panels if not p['axes']],key=lambda p:p['horizon']);assert len(totals)==6
    first,two,last=totals[0],totals[1],totals[-1]
    flat=[]
    for r in windows:
        x={k:r[k] for k in ('pair_id','group','task','context','boundary','acquisition_action','horizon','first_difference','status','loss_difference','success_a','success_b')}
        x.update(rate_a=r['rates'][0],rate_b=r['rates'][1],raw_policy_difference_steps=r.get('raw_policy_difference_steps'),z_gripper_difference_steps=r.get('z_gripper_difference_steps'))
        x.update({k:None if r['mse'] is None else r['mse'][k] for k in main.METHODS});flat.append(x)
    export('all5832_windows.csv',flat)
    flat=[]
    for p in panels:
        flat.append(dict(horizon=p['horizon'],axes=json.dumps(p['axes'],ensure_ascii=False),values=json.dumps(p['values'],ensure_ascii=False),
            registered=p['registered'],available=p['available'],independent_groups=p['independent_groups'],statuses=json.dumps(p['statuses'],sort_keys=True),
            **p['mse'],any_z_gripper_difference_weighted_fraction=p['any_z_gripper_difference_weighted_fraction'],mean_actual_endpoint_L2_mm=p['mean_actual_endpoint_L2_mm']))
    export('all2214_panels.csv',flat)
    full=[p for p in panels if len(p['axes'])==5];assert len(full)==1944 and sum(p['registered'] for p in full)==5832
    io.write(out/'full1944_strata.json',full)
    costs=dict(source_actual_executions=648,source_control_steps=77563,source_all_resets=33048,source_physical_frames=16911815,
        prior_effect_scientific_fits=36,prior_effect_independent_refits=36,
        main_frozen_matrix_file_reads=receipt['frozen_matrix_file_reads'],independent_frozen_matrix_file_reads=audit['independent_frozen_matrix_file_reads'],
        main_frozen_matrix_evaluations=receipt['frozen_matrix_evaluations'],independent_frozen_matrix_evaluations=audit['independent_frozen_matrix_evaluations'],
        main_deterministic_reference_evaluations=receipt['deterministic_reference_evaluations'],independent_deterministic_reference_evaluations=audit['independent_deterministic_reference_evaluations'],
        new_environment_creations=0,new_resets=0,new_control_steps=0,new_physical_frames=0,new_robot_seeds=0,new_fits=0,fixed_policy_queries=0,online_LLM_API_calls=0,
        main_wall_seconds=receipt['wall_ns']/1e9,independent_wall_seconds=audit['wall_ns']/1e9,unique_new_array_tests=12,unique_source_bound_test_total=2228,
        development_attempts=[dict(name=f.parent.name,guard=io.read(f)['guard']) for f in sorted((main.BASE/'development_checks').glob('attempt_*/tests.json'))])
    io.write(out/'costs.json',costs)
    io.write(out/'research_decision.json',dict(status='DESCRIPTIVE_ONLY_NO_PROMOTION_GATE',earlier_paired_context_version='CLOSED_NEGATIVE',
        old_native_qualification='FAILED_RETAINED',input_conditioned_check_not_entry_forecast=True,new_collection_unlocked=False,novelty_qualified=False,task_benefit_qualified=False,publication_goal_complete=False))
    overview=table(['窗口H','完整窗口／972','可用组','零效应RMSE mm','名义发送和RMSE mm','冻结矩阵RMSE mm','Z/夹爪发生差异权重'],
        [[p['horizon'],f"{p['available']}/972",p['independent_groups'],*[('缺失' if p['mse'][k] is None else f"{10*np.sqrt(p['mse'][k]):.6g}") for k in main.METHODS],
          '缺失' if p['any_z_gripper_difference_weighted_fraction'] is None else f"{100*p['any_z_gripper_difference_weighted_fraction']:.3f}%"] for p in totals])
    statuses=sorted({s for p in totals for s in p['statuses']})
    missing=table(['H']+statuses,[[p['horizon']]+[p['statuses'].get(s,0) for s in statuses] for p in totals])
    task=table(['任务','H','完整窗口／登记','可用组']+list(main.METHODS),[[p['values'][0],p['horizon'],f"{p['available']}/{p['registered']}",p['independent_groups'],
        *['缺失' if p['mse'][k] is None else f"{p['mse'][k]:.8g}" for k in main.METHODS]] for p in sorted((p for p in panels if p['axes']==['task']),key=lambda p:(p['values'][0],p['horizon']))])
    report=ROOT/'reports/correction_effect_horizon_v1_zh.md'
    text=f'''# A线：真实纠正后果的时间尺度诊断 v1

本报告**全部新增分析为事后描述性**。来源是已运行的MetaWorld仿真，不是实机测量。检查的是两条实际执行程序的后续命令与净位移一致性；**使用了实际未来命令，不是入口时的多步预测，不提供模型、任务收益或新颖性资格**。原成对上下文版本负结果保持关闭，原生资格仍FAILED_RETAINED。

## 完整结果与读表边界

冻结提交 `{m['source_git_commit']}`；运行 `{run.relative_to(ROOT).as_posix()}`。来源仅A1 TRAIN648执行、9独立组、54任务条件单元、162获取节点。四个已执行率构成972对，固定六窗共5832行；全部保留，其中每个H都有相同972登记分母。没有重新拟合或查询旧成对上下文模型，冻结全局矩阵只作标准一致性参考。

{overview}

最直接的证据是：首步矩阵RMSE约 **{10*np.sqrt(first['mse']['FROZEN_GLOBAL_MATRIX']):.6g} mm**；第2步窗口为 **{10*np.sqrt(two['mse']['FROZEN_GLOBAL_MATRIX']):.6g} mm**，两行均有803对，尚不存在这两行之间的短轨迹分母变化。但第2步已有 **{100*two['any_z_gripper_difference_weighted_fraction']:.3f}%** 的层级加权案例发生Z/夹爪差异，因此不能把误差增加唯一归因延迟或同一XY增益。32步窗口只有{last['available']}/972对，冻结矩阵RMSE **{10*np.sqrt(last['mse']['FROZEN_GLOBAL_MATRIX']):.6g} mm**；名义和参考为 **{10*np.sqrt(last['mse']['NOMINAL_SENT']):.6g} mm**。这些数值都来自实际未来输入条件下的检查，未证明入口预测能力。

RMSE是先按组→可用任务条件→获取节点→率对等权的XY平均MSE再开根，归一化位移乘10换算mm。每H完整窗口的人口不同，不能把这些行当作相同对象的时间趋势或唯一延迟证据。全部1944任务×条件×时点×获取×率对×H单元及2214面板已导出；无完整窗口的误差保留null/CSV空白。

![时间尺度与完整窗口分母](../{run.relative_to(ROOT).as_posix()}/presentation/figures/effect_horizon.png)

{missing}

决策前结束、获取结束、始终没有命令分歧，以及A/B/两来源不足H步均分开；没有用短轨迹冒充长窗口，也没有将成功后的状态虚拟延长。H=1与原803对零效应/名义/全局矩阵保存结果核对通过。未来输入目的为ENTRY_FORECAST时接口拒绝。

## 计算的物理意义

从共同首分歧前状态起，以两个实际末端位置差除0.01为D_H，以两条实际XY发送命令差逐步累加为U_H，比较0、U_H和U_H J_g。J_g是旧训练时未使用当前组g的冻结全局矩阵。两个位置均真实发生，无未执行后缀、环境恢复或新动作。

H>1时，U_H里的后续动作在入口处尚不可知；这是**事后给定实际输入的一致性检查**。即使误差很小，也不能宣称事前已预测未来政策动作、后继状态或纠正效果；误差很大，也不能唯一归因物理增益、瞬态、接触、噪声或其他隐藏状态。分歧后原政策、状态、Z与夹爪均可能不同，完整差异步数已保存。Z/夹爪与原策略差异按保存的float32字节比较；该比例只表示至少一处字节不同，没有度量变化幅度或其因果效应。更长窗是两个真实闭环程序的实现后果，不能当作每步相同状态下的局部命令效果。

当前没有接触力/接触对，未做无噪声物理对照，不能将剩余误差称无噪声物理误差。私有实际施加动作/真实扰动不进入模型；没有改变原命令的加噪/裁剪顺序。三个参考输出不作反演、稳定性或安全保证。

## 三任务完整展示

下表误差是归一化XY位移平方MSE；全部组、条件、时点、获取及六率对见 `presentation/all2214_panels.csv` 和 `full1944_strata.json`，全部5832行见 `all5832_windows.csv`。不按窗口、任务或是否成功筛掉负结果。

{task}

相关率对不当独立样本，不用时间步增加独立组数，也不根据这些事后指标作显著性或新的通过门槛。原六项比较只检查来源字节未变，CAL/TEST/旧QUAL内容未用于本轮分析、选择或拟合。

## 审计、费用与复算

主窗口、面板、来源组装与首分歧函数在独立实现中禁用；独立流读取、struct字节首差、标量累计、矩阵方向、全5832行、2214面板、组权重和缺失核对通过。共享旧JSON解析、NumPy来源权重参考/容差及模拟源记录，属于第二实现审计，不是独立实验机构或物理重模拟。

主/独立各读取冻结矩阵9次，各评价 **{receipt['frozen_matrix_evaluations']}** 个完整窗口及 **{receipt['deterministic_reference_evaluations']}** 次零/名义确定性参考。主分析 {costs['main_wall_seconds']:.3f}秒，独立 {costs['independent_wall_seconds']:.3f}秒。新增环境创建、重置、控制步、物理帧、机器人种子、固定政策查询、模型拟合和在线LLM API均 **0**，守卫计数和完整来源SHA随receipt保存。

历史来源648次/77,563步/33,048全部重置/16,911,815物理帧，以及旧36科学拟合和36独立重拟合另列已付费用。12新增纯数组测试、{len(costs['development_attempts'])}次开发运行均0拟合/物理/API，重复不增唯一项；按源码哈希复用旧2216项，合计2228唯一，旧六张量组另列。原始记录、分片、失败和恢复副本保留。

复算入口 `scripts/run_correction_effect_horizon_v1.py`，主/独立源码、配置和冻结协议均提交。每阶段意图先保存，失败保留、不自动重跑。结果提交前核对编译/依赖、全仓秘密和新增实际索引补充扫描、普通/暂存差异以及Git/磁盘字节；归档仅是保存习惯，不计研究成果。

## 后续决定与查新

本轮没有设置方法通过门槛，也不产生晋升资格。**不能从首分歧一步预测进步直接解锁纠正控制；也不能从事后输入条件检查通过，跳过真正入口预测与独立自身历史任务评价。** 若长窗出现失配，尚需区分状态/反馈/Z与夹爪/接触/时间效应，不能据此调旧ridge或宣称某个唯一新响应模型必要。保持成对上下文、ARX、F20、旧响应/原生失败关闭。

付费获取空间此前已有完整TRAIN事后包络：P优于免费家族F仅4/54，且415/433步正向差集中在组4。本轮不重复估算或把未来最优当可部署策略。后续必须同时超过完整免费反馈、廉价固定率、DIRECT_C8、积分、始终获取/不更新、标准检测/历史辨识、任务相关获取及完整成本Q/DR参考；不能缩小强对照来通过。

新增查新：联合物理状态与未知参数的信息获取规划已有[MIAC rho-POMDP](https://arxiv.org/html/2505.09119v1)；任务相关实验设计已有[NeurIPS2023 Optimal Exploration](https://papers.neurips.cc/paper_files/paper/2023/hash/31e018f43ab9c7065c058cc2c5848128-Abstract-Conference.html)。只读官方摘要和指定方法段，未完整复现或移植保证。原MDE/Residual RL/OCCAM/GAUGE/Poke/TOM与stateful performativity/VoSI/SPO等对照继续有效，不能把“获取改变状态”或改变预测尺度本身当新贡献。

新训练/采集仍须先形成具体可证伪机制、与同权限强组合参考的区别，以及独立TRAIN/CAL/自身时序资格、全部失败处理和费用协议。本轮既不解锁新采集，也不把完整研究目标缩成诊断。算法新颖性、独立完整成本任务优势、消融与CCF A目标均未完成。
'''
    report.write_text(text,encoding='utf8',newline='\n')
io.write(out/'report_receipt.json',dict(integrity='FOR_DELIVERY_AUDIT',report_sha256=io.sha(report),guard=guard,wall_ns=perf_counter_ns()-start,new_physics=0,new_fits=0,online_LLM_API_calls=0))
print(dict(registered_windows=len(windows),available_windows=receipt['available_windows'],report=str(report)),flush=True)

"""Chinese interpretation of all saved linear references; no promotion gate."""
from collections import defaultdict
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from src.analysis import linear_command_preflight_io_v1 as allocation
from src.analysis import observable_history_io_v1 as io


def number(x): return '缺失' if x is None else f'{x:.6g}'


def report():
    folder=allocation.OUTPUT; manifest=allocation.load_manifest(); audit=io.read(folder/'audit.json')
    io.require(audit['integrity']=='PASSED','independent audit required')
    details=io.read(folder/'model_geometry.json'); rows=io.read(folder/'trajectory_summaries.json')
    completion=io.read(folder/'completion.json'); parent=io.read(allocation.SOURCE/'delivery_v1/costs_and_provenance.json')
    text=['# 强线性模型的命令比较前置核对 v1','',
        '**事后描述性分析；不是新物理资格、逆控制器、任务收益或论文贡献。**',
        '本轮只使用旧FIT的144条轨迹、12个完整组及全部18个保存线性参考；没有修改或重新拟合任何模型。旧DEV、CAL、TEST及真实扰动、实际噪声、私有物理状态均未进入计算。',
        f"运行 `{manifest['experiment_run_id']}`；冻结实现 `{manifest['source_git_commit']}`；manifest `{manifest['manifest_id']}`。",'',
        '## 核对结论与限制','',
        '三个线性特征族H10／F20／F43都是加性的：给定同一当前历史、改变发送命令时，预测差等于固定命令矩阵乘命令差。F20加入状态不等于已经学习了状态依赖的命令响应；矩阵在一个模型内不会随接触、位置或移动阶段改变。',
        '该结构不能自动判定模型错误，某些局部响应确实可能近似不变；它明确了需要由独立真实命令干预检验的限制。低事实预测误差、矩阵非奇异、数值行空间和独立激励均不能替代此检验。',
        '冻结前曾只读检查六个F20命令矩阵以确认接口语义；本轮从始至终是事后分析，不冒称盲分析或独立确认。没有据此改变旧参数、阈值、人口或原六项比较。','',
        '## 全部模型与条件XY激励','',
        '每条来源轨迹赋总权重1。对未添加岭惩罚的归一化设计做SVD；将XY命令相对其余全部列（含Z和抓取命令）投影后，报告剩余激励。数值秩容差固定为设计最大维数×float64机器精度×最大奇异值，没有拟合输出或调整阈值。XY响应奇异值单位为mm／单位发送动作，条件激励奇异值为归一化加权设计单位，二者不可混用。','',
        '|训练来源|任务|特征|设计秩/列数|条件XY秩/2|条件XY最小奇异值|响应XY最小奇异值(mm/动作)|响应XY条件数|',
        '|---|---|---|---:|---:|---:|---:|---:|']
    for d in details:
        text.append(f"|{d['source']}|{d['task']}|{d['feature']}|{d['rank']}/{d['columns']}|{d['conditional_xy_rank']}/2|{number(d['conditional_xy_singular_values'][-1])}|{number(d['xy_singular_values_m'][-1]*1000)}|{number(d['xy_condition'])}|")
    text+=['','## 全任务、来源、特征与上下文的假设查询','',
        '在每个已记录决策点，从当时真实发送命令生成±0.25的X／Y四个偏移，只在发送层裁剪XY并保持Z／抓取不变。饱和导致与基准相同的查询保留，不补零为新数据。这里只保存模型查询，没有执行这些分支，也没有它们的真实响应、噪声、接触或任务结果。',
        '边界框指各命令轴的FIT范围，位于框内不等于处于联合状态动作支持域。行空间残差和加权杠杆值也只是线性设计几何，不能据此给出因果支持、置信度或安全保证。表中几何均值先在每条轨迹内，再在每个真实组内，最后按组等权；计数只描述这组有限假设查询。','',
        '|来源|任务|特征|上下文|完整轨迹/组|候选查询|零命令变化|越轴范围|非零查询行空间残差均值|非零查询杠杆均值|',
        '|---|---|---|---|---:|---:|---:|---:|---:|---:|']
    for d in details:
        for context in ('NOMINAL','RANDOM'):
            selected=[r for r in rows if r['model_key']==d['model_key'] and r['context']==context]
            grouped=defaultdict(list)
            for r in selected: grouped[r['group']].append(r)
            def grouped_mean(field):
                values=[np.mean([r[field] for r in rs if r[field] is not None]) for rs in grouped.values() if any(r[field] is not None for r in rs)]
                return None if not values else float(np.mean(values))
            text.append(f"|{d['source']}|{d['task']}|{d['feature']}|{context}|{len(selected)}/{len(grouped)}|{sum(r['candidates'] for r in selected)}|{sum(r['zero_candidates'] for r in selected)}|{sum(r['outside_command_axis_box'] for r in selected)}|{number(grouped_mean('mean_row_span_relative_residual'))}|{number(grouped_mean('mean_weighted_design_leverage'))}|")
    text+=['','## 后续进入条件','',
        '本核对没有物理资格晋级门，也不生成控制器或选择器。下一份独立资格协议应对固定候选实际执行共同前缀，再分别真实发送已保存命令，记录当前状态、一步响应和全部获取费用；每条分支一次受控初始重置，不能复制快照撤销位移。模型的预测与候选映射必须在该分支结果产生前保存。',
        '主要检验应针对真实命令响应差，并保留零差预测参考、所有任务／上下文／阶段与饱和候选。先证明它能比较命令，再单独验证逆纠正和包含获取成本的完整任务损失。不得以旧记录的未来观测填补反事实轨迹，也不得把本轮矩阵求逆后直接部署。',
        '若独立命令比较不具竞争力，应保留负结果，停止为这些模型叠加获取／采用门控；若通过，仍需合格被动适应、DIRECT_C8、积分、始终获取、获取不更新等强对照及方法自身形成的新时序评价。当前GRU的负结果不变。','',
        '## 费用、失败与来源','',
        f"完整核对{completion['counts']['query_positions']}个真实历史位置、{completion['counts']['model_query_pairs']}个模型查询和{completion['counts']['candidate_model_pairs']}个模型候选对，432个模型轨迹单元；独立审计全部复算。主分析54次设计SVD＋18次XY矩阵SVD，审计另作同样72次；这些是数据几何分解，未拟合任何响应参数。主分析耗时{completion['wall_ns']/1e9:.3f}秒，独立审计{audit['wall_ns']/1e9:.3f}秒。",
        '新增环境创建、控制步、全部重置、物理帧、在线LLM API、模型拟合和优化更新均为0。软件阶段保留一次短路径别名导致临时来源写保护测试失败的记录；修复在冻结之前完成，真实历史来源未改。',
        '实际读取FIT的144条轨迹含13690个已发生的来源控制步。它是旧TRAIN216／20195步的子集，也属于完整756条父研究，不能重复加算。完整父研究38556次全部重置、19636865物理帧，以及更早名义C8等来源费全部继承上轮成本账；上轮162个训练模型／720000更新、18次回归审计和软件验证另列为来源计算，不改写为本轮免费获取。',
        '新输入及代码哈希见manifest；每条请求、全部模型候选映射及设计诊断见queries.jsonl.gz；逐轨迹表、全部模型矩阵、独立审计和费用见同一运行目录。原六项比较、历史大文件与恢复副本保持原样。','',
        '## 新近邻及不能借用的保证','',
        '[Løvland等，CCTA2025](https://arxiv.org/html/2509.01188v1)研究稳态LTI闭环数据学习的敏感度及其对无约束反馈优化的影响，说明条件预测与真实输入输出作用不能直接等同。这里只读其引言及§II–III；其线性、稳态、可逆、凸性与时间尺度假设不自动适用于有裁剪和接触的本项目，不能借用其收敛结论。',
        '[Gilson与Van den Hof，Automatica2005](https://doi.org/10.1016/j.automatica.2004.09.016)的闭环工具变量方法也是必要近邻。这里仅使用出版方摘要／引言来核对闭环相关性问题，没有复现其完整方法。工具变量的外生性和相关性须另证，历史命令本身不能自动称为有效工具变量；也不能仅凭相关性认定本项目估计有偏的唯一原因。',
        '动作敏感评价、模型适用域、任务相关探索和控制器表现预测已有直接研究；本接口、SVD核对和标准线性参考都不是论文创新。CCF A目标仍需明确的新决策机制、强对照、独立部署与消融证据。','']
    target=ROOT/'reports/linear_command_preflight_v1_zh.md'
    with target.open('x',encoding='utf-8',newline='\n') as h: h.write('\n'.join(text))
    io.write(folder/'costs_and_provenance.json',{'scope':'POSTHOC_TRAIN_ONLY_NO_PHYSICAL_QUALIFICATION','new_environment_steps':0,
        'new_all_resets':0,'new_physical_frames':0,'new_online_llm_api_calls':0,'new_model_fits':0,'optimizer_updates':0,
        'analysis_svd_computations':72,'independent_audit_svd_computations':72,'actual_reused_FIT':{'trajectories':144,'source_control_steps':13690},
        'complete_parent_costs_separate':parent,'source_cost_sha256':io.sha(allocation.SOURCE/'delivery_v1/costs_and_provenance.json'),
        'report_sha256':io.sha(target),'analysis_wall_ns':completion['wall_ns'],'audit_wall_ns':audit['wall_ns'],
        'timing_scope':'Analysis starts before manifest creation. Software verification, reporting and Git operations are outside these clocks; no unmeasured time is asserted to be zero.'})
    io.write(folder/'report_receipt.json',{'report':target.relative_to(ROOT).as_posix(),'sha256':io.sha(target),'source_sha256':io.sha(__file__),
        'physical_qualification':False,'task_benefit':False})
    print(target)


if __name__=='__main__': report()

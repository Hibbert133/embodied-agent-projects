"""Chinese complete-denominator report, including partial and negative studies."""
from pathlib import Path
import argparse,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis import latent_response_io_v1 as a
from src.probe.latent_response_query_v1 import METHODS
io=a.io


def report(path):
    m=a.checked(path);root=path.parent;lines=['# 已声明命令的多步响应模型资格 v1','',
        '这是公开历史初始化、多步响应预测及摘要消融的组件研究。没有训练获取决策或执行新的任务纠正；预测误差不等于任务收益，CCF A目标未完成。', '',
        f"执行冻结 `{m['source_git_commit']}`；运行 `{m['experiment_run_id']}`；清单 `{m['manifest_id']}`。", '',
        '## 方法与可用信息','',
        'SS表示由公开历史初始化的8维隐状态，并在入口已声明的命令上逐步展开。SENT加入公开名义目标与手部的差；NO_SENT将相同结构的三个摘要输入通道置零；CURRENT_SENT只保留当前真实帧及摘要。DIRECT_MLP直接输出八步位移，参数数略多；DIRECT_RIDGE是同信息直接岭回归；PERSIST_ZERO是零位移参考。H10/F20保留为新同数据训练的强单步形式，不复活其旧控制选择器。', '',
        '所有模型只接收真实过去观测/发送命令及入口已知的未来八步命令。mocap、真扰动、实际噪声及施加动作仅评估；不作特权训练标签。名义摘要不是实际状态或概率均值。网络/历史编码均为既有辨识路线，本轮不声称算法新颖性。', '',
        '## 全部物理人口与费用','',
        '|阶段|冻结分配|实际完整执行|实际控制步|全部重置|物理帧|完整首8步|状态|',
        '|---|---:|---:|---:|---:|---:|---:|---|']
    totals={'executions':0,'steps':0,'resets':0,'frames':0};phase_sources={}
    for split in a.SPLITS:
        folder=root/split.lower();summary_path=folder/'summary.json'
        if not summary_path.exists():lines.append(f"|{split}|{len(a.population(split))}|未开始|缺失|缺失|缺失|缺失|前置门或阶段未执行|");continue
        s=io.read(summary_path);counts=s['lifecycle']['counts'];complete=sum(r['complete_first_eight'] for r in s['rows'])
        lines.append(f"|{split}|{len(a.population(split))}|{s['executions']}|{s['control_steps']}|{counts.get('reset_attempts',0)}|{counts.get('simulation_frames_completed',0)}|{complete}|{s['status']}|")
        totals['executions']+=s['executions'];totals['steps']+=s['control_steps'];totals['resets']+=counts.get('reset_attempts',0);totals['frames']+=counts.get('simulation_frames_completed',0)
        phase_sources[split]={'summary_sha256':io.sha(summary_path),'wall_ns':s['wall_ns'],'source_audit':io.read(folder/'audit.json')['integrity'] if (folder/'audit.json').exists() else 'NOT_COMPLETED'}
    lines+=['',f"新物理费用合计：{totals['executions']}次完整执行、{totals['steps']}控制步、{totals['resets']}全部重置、{totals['frames']}物理帧。失败/部分尝试的费用也在各阶段账本中，不补采。训练/资格在响应包结束时停止，success_at_response_horizon=False不能当成完整500步任务失败。", '',
        '每阶段原始cases/events/private_targets/public_trajectories/public_packet_metadata保留全部案例、未到边界、未到锚点、短包和早成功原因。原生数值每步记录，完整原生签名只在初末/变化边界记录，避免把未记录的逐步RNG状态称为已逐步测得。世界地址、时钟、噪声游标、实际动作与目标累计及全部重置/帧仍独立核对。', '',
        '## 训练与模型审计','']
    if (root/'training/support.json').exists():
        lines+=['|任务|有实际响应轨迹|完整首包|无响应轨迹|','|---|---:|---:|---:|']
        for t,v in io.read(root/'training/support.json').items():lines.append(f"|{t}|{v['available']}|{v['complete_entry_packets']}|{v['unavailable']}|")
    if (root/'training/completion.json').exists():
        tr=io.read(root/'training/completion.json');lines+=['',f"模型状态：{tr['status']}。21个拟合模型（12神经网络训练、30个闭式岭回归线性系统）加3个确定性零参考，共24个保存对象。每个神经模型5000更新，共60000更新，单个固定初值；同结构消融同初值、同采样。没有CAL/QUAL选模型、早停或改门槛。", '']
    else:lines+=['模型训练尚未完整完成，不能把计划拟合次数写作实际完成。部分日志、快照、支持门及失败回执保留。','']
    if (root/'training/audit.json').exists():
        aud=io.read(root/'training/audit.json');lines+=[f"独立模型审计：{aud['integrity']}，重算{aud['actual_audit_ridge_fits']}个岭回归系统，神经优化器重训0；另写特征、前向公式和采样日程，并在隔离Torch double核对{aud['torch_window_forwards_checked']}个窗口。它不等于独立重演优化器。",'']
    lines+=['## 独立资格结果','']
    stats_path=root/'qual_evaluation/statistics.json'
    if stats_path.exists():
        v=io.read(stats_path);lines+=[f"预定主候选SS_SENT资格：**{v['qualification']}**。不把较好的次要模型替换为主候选，不追加样本。",'',
            '|方法|完整分配|完整实际包|无效预测|完整分配H8损失m↓|完整分配H1损失m↓|','|---|---:|---:|---:|---:|---:|']
        for method in METHODS:
            s=v['summaries'][method];h8='不适用' if s['mean_h8_loss_m'] is None else f"{s['mean_h8_loss_m']:.9f}"
            lines.append(f"|{method}|{s['allocated']}|{s['complete_actual_packets']}|{s['invalid_saved_forecasts']}|{h8}|{s['mean_h1_loss_m']:.9f}|")
        lines+=['','|方法|有效H8分母|有效H8原始均值m|H8截断次数|有效H1分母|有效H1原始均值m|','|---|---:|---:|---:|---:|---:|']
        for method in METHODS:
            s=v['summaries'][method];raw8='不适用/缺失' if s['mean_valid_h8_raw_rmse_m'] is None else f"{s['mean_valid_h8_raw_rmse_m']:.9f}"
            raw1='缺失' if s['mean_valid_h1_raw_error_m'] is None else f"{s['mean_valid_h1_raw_error_m']:.9f}"
            lines.append(f"|{method}|{s['valid_h8_count']}|{raw8}|{s['h8_capped_count']}|{s['valid_h1_count']}|{raw1}|")
        lines+=['','未测量/短包/预测失败使用预登记1m损失，实际RMSE截断于1m，统计以Decimal80半偶舍入的整数纳米计算；原始未截断误差和缺失原因另存case_losses。这不是用户最终任务的截止步损失，也不是物理误差上界或安全保证。','',
            '|SS_SENT减对照|完整分配均差m|整组95%区间m|上界严格<0|','|---|---:|---|---|']
        for method,c in v['co_primary_comparisons'].items():lines.append(f"|{method}|{c['mean']['metres']:.9f}|[{c['ci95_low']['metres']:.9f}, {c['ci95_high']['metres']:.9f}]|{c['upper_strictly_below_zero']}|")
        lines+=['','18个独立组、三个时点分层整组重采样10000次，保留组内24单元相关性。区间条件于本次TRAIN源和单个固定网络初值，没有把相关时间步、重叠训练窗口或模型数当作独立样本，也不承诺充分统计功效。','',
            '|预登记门|结果|','|---|---|',*['|'+k+'|'+str(x)+'|' for k,x in v['gates'].items()], '',
            '|任务/初始/变化/命令包|完整包/18|','|---|---:|',*['|'+k+'|'+str(x)+'/18|' for k,x in v['coverage'].items()]]
    else:lines+=['独立QUAL未完整交付，或前置门未通过。没有资格结论，不能用训练、CAL或测试通过替代；具体失败回执及全部已消耗费用保留。','']
    lines+=['','## 限制与后续判断','',
        '数值合法、当前预测能力和包含获取费用的任务收益分别判断。本轮固定RAW PI/附近PID/外生命令源策略，预测不选动作，不能当作新方法自身历史的任务部署。即使所有预测门通过，也须另行冻结有效纠正与完整任务比较，保留RAW PI、DIRECT_C8、积分、始终获取/不更新、标准检测/历史辨识和任务相关获取强对照及消融。', '',
        '若未通过，保留这个版本负结果，不围绕其添加逆控制/选择规则，不交换主次模型或修补资格人口。下一步必须针对证据重新提出可证伪解释和独立协议。新颖性仍需围绕获取动作改变状态、模型适用性及采用/拒绝后继行为的具体机制；旧来源上的离线建议不能代替独立自身时序评价。', '',
        '参考边界：[SUBNET 2021](https://proceedings.mlr.press/v144/beintema21a.html)及[在线ANN-SS 2026](https://arxiv.org/html/2607.17614v2)提供已有历史初始化/多步展开思路；输出误差噪声假设不能直接转为本环境执行输入噪声保证。原模型适用范围、Residual RL、OCCAM、GAUGE、Poke and Strike及双重控制比较继续保留。CCF A目标未完成。','']
    dest=a.ROOT/'reports/latent_response_qualification_v1_zh.md';io.require(not dest.exists(),'exclusive response report');dest.write_text('\n'.join(lines),encoding='utf-8')
    io.write(root/'report_receipt.json',{'integrity':'RENDERED_SOURCE_BOUND','manifest_id':m['manifest_id'],'report':dest.relative_to(a.ROOT).as_posix(),
        'report_sha256':io.sha(dest),'phases':phase_sources,'actual_physical_totals':totals,'online_LLM_API_calls':0,'publication_goal_complete':False})
    return dest


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);v=p.parse_args();print(report(v.manifest.resolve()),flush=True)

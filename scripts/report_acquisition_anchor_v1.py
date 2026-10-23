"""Complete Chinese descriptive readiness diagnosis, no tuned recommendation."""
from pathlib import Path
import argparse,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis import acquisition_anchor_diagnosis_io_v1 as s
io=s.io


def main(path):
    path=path.resolve();s.checked(path);out=path.parent;r=io.read(out/'results.json');a=io.read(out/'audit.json');done=io.read(out/'completion.json');traj=io.read(out/'trajectory_diagnostics.json');stage=io.read(out/'stage_diagnostics.json')
    io.require(a['integrity']=='PASSED' and a['completion_sha256']==io.sha(out/'completion.json'),'independent export audit')
    for n,h in a['artifact_sha256'].items():io.require(io.sha(out/n)==h,'audited export changed')
    moves=[v for v in traj if v['action']=='MOVE_MEASURE8'];L=lambda p,t:'['+t+']('+p.resolve().as_posix()+')'
    text=['# 获取位置失败诊断：完整54例的事后描述性分析','',
        '**全部新增分析均为事后描述性分析。没有新增环境交互、重置、物理帧、模型拟合、在线LLM API或未执行轨迹；不修改移动参数、进入阈值、旧结论或失败分母。**','',
        f'完整核对54次执行、8,836个保存步和全部8个任务失败。18例分配MOVE，14例实际移动，3例完整窗口、11例达到移动上限、4例介入前成功。分析耗时{done["wall_ns"]/1e9:.3f}秒；独立审计{a["wall_ns"]/1e9:.3f}秒，核对{a["fields_checked"]:,}个字段。','',
        '新增13项数组检查在环境/拟合/网络守卫下通过；旧1,759项按源码哈希和回执复用。开发首次有2项数值类型错误：代数参考返回NumPy标量，不符合普通JSON数字接口；冻结前转成Python float，原日志保留，未改数值、容差或采集记录。','',
        '## 卡在哪些进入条件','',
        '沿用原程序的四个条件：至少4个真实移动观测；手位置距固定目标(0,0.6,0.25)的最大轴误差≤15mm；手与物体距离≥100mm；最近三段真实移动的最大轴位移≤3mm。首段历史不足时运动量缺失，不能填零。四个条件均通过才开始8步新测量。','',
        f'实际移动结束时的完整条件组合计数：`{r["final_gate_mask_counts_among_actual_moves"]}`。下面保留全部18例；没有移动的4例标缺失原因，不画成零误差。','',
        '|任务|条件|介入|实际移动|抬升/横移|位置误差mm|近期运动mm|手物间距mm|未过条件|窗口|','|---|---|---:|---:|---:|---:|---:|---:|---|---|']
    for v in moves:
        g=v['final_relocation_gates'];fmt=lambda k:'缺失' if g is None or g[k] is None else f'{g[k]*1000:.3f}'
        failure=v['phase_missing_reason'] if g is None else '+'.join(g['failed_conditions']) or '均通过'
        text.append(f'|{v["task"]}|{v["context"]}|{v["planned_boundary"]}|{v["movement_steps"]}|{v["lift_steps"]}/{v["lateral_steps"]}|{fmt("position_error_inf_m")}|{fmt("recent_motion_inf_m")}|{fmt("clearance_m")}|{failure}|{v["complete_warm_window"]}|')
    text+=['','## 全部阶段与步段','',
        '先在每条真实轨迹内计算，再按组组织。全部54例×抬升/横移两阶段×1–8、9–16、17–32、33–64四段，共432个登记行；非移动、短段和未到阶段保留缺失原因。分段在本次分析冻结前声明，是对已完成采集的事后规定，不冒称采集前预注册，也不选择最后“表现较好”的片段。','',
        '|任务|条件|阶段|有观测的轨迹/分配MOVE|逐轨迹平均位置误差mm|','|---|---|---|---:|---:|']
    for task in io.TASKS:
        for context in ('UNCHANGED','CHANGED'):
            for phase in ('LIFT','LATERAL'):
                trajectories=[]
                # Each trajectory contributes one phase mean, reconstructed from
                # disjoint fixed bins by actual within-trajectory step count.
                for v in moves:
                    if (v['task'],v['context'])!=(task,context):continue
                    parts=[p for p in stage if p['task']==task and p['context']==context and p['group']==v['group'] and p['action']=='MOVE_MEASURE8' and p['stage']==phase and p['actual_n']]
                    n=sum(p['actual_n'] for p in parts)
                    if n:trajectories.append(sum(p['actual_n']*p['position_error_mean_m'] for p in parts)/n)
                value='缺失' if not trajectories else f'{sum(trajectories)/len(trajectories)*1000:.3f}'
                text.append(f'|{task}|{context}|{phase}|{len(trajectories)}/3|{value}|')
    text+=['','这些均值不把长轨迹或时间步充作额外独立样本；每格只有三个介入组，缺失阶段不填零。完整432行、组标签及实际步数在stage_diagnostics.json。','',
        '抬升阶段控制目标保留起始XY；进入条件始终比较最终固定目标。上表位置误差对应最终进入目标，不能把它称为抬升控制器的主动目标跟踪误差。后表另列主动目标误差，二者语义分开。','',
        '## 发送指令、噪声与代数参考','',
        '每个已执行步独立复核float32仿射/死区变换→XYZ实际噪声→最终裁剪，并与原executed_action_oracle一致。分别保留策略动作裁剪、任务纠正发送裁剪、移动PD的±0.5限幅及执行器最终裁剪。控制器第一移动步按注册程序将导数项置0；诊断把该位移标为未测得，不能据此伪造历史。','',
        '|任务|条件|介入|末8个实际移动步数|平均主动目标误差XY mm|真参数零输入参考XY mm|末段实际噪声均值XYZ|任务纠正发送限幅步|执行器最终裁剪步|','|---|---|---:|---:|---|---|---|---:|---:|']
    for v in moves:
        fmt=lambda x:'缺失' if x is None else ', '.join(f'{n*1000:.3f}' for n in x)
        ref=v['balance_reference_oracle'];ref=None if ref is None else ref['error_xy_m']
        noise=v['late_noise_xyz_mean_oracle'];noise='缺失' if noise is None else ', '.join(f'{n:.6f}' for n in noise)
        text.append(f'|{v["task"]}|{v["context"]}|{v["planned_boundary"]}|{v["late_relocation_actual_n"]}|{fmt(v["late_active_error_xy_mean_m"])}|{fmt(ref)}|{noise}|{v["task_correction_send_limit_steps"]}|{v["actuator_final_clip_steps"]}|')
    text+=['',
        '代数参考e=−M⁻¹b/8只对应：原发送纠正是恒等、死区为0、测得运动为0且PD输入未限幅时，使无噪声施加XY命令为0的目标误差。它使用评估端真实扰动，不是拟合、部署估计或物理稳态证明；低噪声输入参考也不是物理无噪声响应。接触、内部mocap/机器人动力学、尚在移动、限幅及有限64步都可能破坏解释。不能仅因末段接近参考就断言唯一原因。','',
        '任务积分在移动中保留于任务记忆，原固定PD移动器仅使用恒等纠正，不使用任务积分，也没有独立的移动积分。保持记忆不能自动补偿移动器的常值输入误差。是否需要已有标准PID、局部目标或其他获取控制，必须由新的独立资格验证；本轮不生成那些未执行轨迹，也不调旧增益。','',
        '## 完整任务损失及可解释范围','',
        '|组|实际配对单元|平均移动减继续损失|平均真实移动/测量步|','|---|---:|---:|---:|']
    for g in r['whole_groups']:text.append(f'|{g["group"]}|{g["paired_units"]}|{g["mean_L_move_minus_continue"]:+.6f}|{g["mean_actual_acquisition_steps"]:.6f}|')
    p=r['paired_costs'];delta=sum(v['L_move_minus_continue'] for v in p);cost=sum(v['actual_movement_and_probe_steps'] for v in p);tail=sum(v['remaining_loss_difference_after_paid_acquisition'] for v in p)
    text+=['',f'全部18个配对：截止损失差总和{delta:+d}步=实际移动/测量{cost}步+其后剩余损失差{tail:+d}步；这是已观察完整程序损失的恒等分解，不把任何阶段收益解释成独立因果效应。成功转失败{sum(v["success_to_failure"] for v in p)}例，失败转成功{sum(v["failure_to_success"] for v in p)}例。原程序均值、8个失败和全部对照保持原样。','',
        '手/物体位置、物体位移和抓取开合观测仅是代理；没有逐步接触力/接触对，不能唯一分离接触、状态改变、指令失配与噪声。相关轨迹步也不能充作独立样本来给显著性。','',
        '## 判断与后续','',
        '本轮给出可见进入条件、真实控制阶段、裁剪、噪声、指令跳变及完整费用的证据；反证和无法区分的因素也保留。若位置条件失败，不能归结为“测量需要更久”而擅自延长64步；若运动或间距条件失败，也不能放宽阈值。所有控制参数和54例保持冻结。','',
        '推荐先独立资格获取控制与中途辨识/新纠正接口，而不是对这3个完整窗口直接训练收益选择器。已有FIXED_PID、LOCAL_PD、LOCAL_PID等标准参考及RAW PI、C8、积分补偿、始终探测/探测不更新应保留，不能把本固定PD弱覆盖当作新方法优势。新训练、校准和自身历史评价需要单独种子与完整预算。','',
        '[MathWorks官方PID设计说明](https://www.mathworks.com/help/slcontrol/ug/baseline-pid-and-available-tuning-tools.html)将PID作为工作条件下的标准控制基线，并要求建模/调节后验证性能。这里只读该说明的控制项和设计流程；不继承其机器人保证，不以积分控制或静态平衡公式主张创新。原五项查新继续保留；获取改变状态及适用性时的具体新机制、强对照、独立部署和消融仍未完成。','',
        '## 复算与来源','',
        '- '+L(path,'冻结manifest与全部来源哈希'),'- '+L(out/'step_diagnostics.jsonl.gz','全部8,836个保存步的诊断'),
        '- '+L(out/'trajectory_diagnostics.json','全部54条轨迹及缺失原因'),'- '+L(out/'stage_diagnostics.json','全部432条阶段/步段登记'),
        '- '+L(out/'move_cases.csv','全部18个分配移动案例'),'- '+L(out/'audit.json','禁用主诊断函数的独立审计'),
        '- '+L(s.SOURCE/'native/historical_costs.json','原采集及历史来源费用，未重复计费'),
        '', '![全部18个分配移动案例]('+(out/'figures/all_18_assigned_moves.png').as_posix()+')',
        '', '全部新增分析为事后描述性分析。仅本地提交，不推送合并；CCF A目标仍未完成。','']
    report=io.ROOT/'reports/acquisition_anchor_diagnosis_v1_zh.md'
    with report.open('x',encoding='utf-8',newline='\n') as f:f.write('\n'.join(text))
    io.write(out/'report_receipt.json',{'report':report.relative_to(io.ROOT).as_posix(),'report_sha256':io.sha(report),'generator_sha256':io.sha(__file__),'audit_sha256':io.sha(out/'audit.json'),'classification':'POST_HOC_DESCRIPTIVE_ONLY'})
    print({'Chinese_report':str(report),'new_interactions':0},flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);v=p.parse_args();main(v.manifest)

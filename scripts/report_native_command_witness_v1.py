"""Native conformance Chinese report; no prediction or task-effect promotion."""
from pathlib import Path
import argparse,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis import native_command_witness_io_v1 as a
io=a.io


def report(path):
    m=a.checked(path);out=path.parent/'native';audit=io.read(out/'audit.json');io.require(audit['integrity']=='PASSED','record audit required')
    for n,h in audit['artifact_sha256'].items():io.require(io.sha(out/n)==h,'unchanged native report source')
    io.require(io.sha(out/'trajectory_audit.json')==audit['trajectory_audit_sha256'],'audited case tables')
    rows=io.read(out/'trajectory_audit.json');summary=io.read(out/'summary.json')
    lines=['# 原生命令目标见证与公开输入资格 v1','',f"软件合同资格：**{audit['native_contract']}**。这是新收集器的执行/测量资格，不是新响应模型、任务收益或安全资格。",'',
        f"冻结 `{m['source_git_commit']}`；运行 `{m['experiment_run_id']}`；清单 `{m['manifest_id']}`。",'',
        f"完整18次执行，实际{audit['control_steps']:,}控制步、{audit['all_resets']:,}全部重置、{audit['physical_frames']:,}物理帧；{audit['task_failures_preserved']}个任务失败全部保留。新模型训练/拟合、在线LLM API均为0。独立审计另查询固定策略{audit['independent_extra_policy_queries']:,}次，只用保存观测，新增物理交互/拟合为0。",'',
        f"全部原生命令目标累计是否逐位一致：{audit['all_native_target_updates_bit_exact']}；最大逐轴误差m：{audit['max_native_target_error_m']}。{audit['paired_prefixes']}对实际共同前缀和{audit['private_target_records']:,}条私有数值见证已核对。",'',
        '## 完整案例','',
        '|组/时点|任务|条件|控制步|任务成功|完整8步窗口|最大原生重建误差m|入口SENT−原生目标mm|入口原生目标−手部坐标差mm|',
        '|---|---|---|---:|---|---|---:|---:|---:|']
    fmt=lambda x:'缺失' if x is None else f'{x:.6f}'
    for r in rows:lines.append(f"|{r['group']}/{r['planned_boundary']}|{r['task']}|{r['context']}|{r['total_steps']}|{r['success']}|{r['complete_warm_window']}|{r['max_native_target_error_m']}|{fmt(r['entry_sent_native_gap_mm'])}|{fmt(r['entry_native_hand_coordinate_gap_mm'])}|")
    lines+=['','完整窗口数量（每格分配3次）：','',*['- '+k+'：'+str(v)+'/3' for k,v in audit['complete_windows_by_task_context'].items()],
        '', '## 三种资格与限制','',
        '数值/因果合同：记录了每次实际施加前后的mocap数值、真实时钟、世界地址、动作/噪声游标和有界命令的保存消费。独立计算float32仿射/死区→XYZ加噪→最终裁剪，以及float32缩放→float64目标累计→逐步工作空间裁剪。公开摘要只从过去发送命令递推，独立审计禁用主观测/摘要代码并复算。', '',
        '物理预测能力：本轮没有训练模型，没有证明由公开历史能够准确估计私有目标或预测新命令响应。原生mocap仅评估使用，不能作为在线模型或训练的特权输入/标签。公开SENT假设恒等变换、零执行噪声，不是实际目标或概率均值；它与实测目标的差只作描述。手部/目标坐标差也可能包含固定站点偏移，不能认定唯一动力学原因。', '',
        '任务收益：本轮只执行固定LOCAL_PID_KEEP，没有新方法与强对照的任务比较。成功/失败只是全部软件资格案例的描述，不能用于推广算法；9个配对环境、3组不宣称充分统计功效。完整任务、重置和物理帧费用按真实账本计一次。', '',
        '私有文件与公开导出分离。public_trajectories仅含任务、初始观测、已实际发送命令、公开观测和名义摘要；public_prefix(at)只读取已完成前缀，不读取当前/未来响应。种子、条件、真参数、实际噪声、施加动作及原生mocap不能进入预测输入。数据记录的后继观测将来只能作为训练目标，不能回填成同一步预测特征。', '',
        '审计共享了已测试的只读分组器和标准控制程序回放，但原生命令目标累计及公开摘要数值另写；固定策略/PI/移动还由既有独立公式审计。该界限不等于独立重演物理，也不构成安全保证。', '',
        '## 费用与后续','',
        f"采集核心{summary['wall_ns']/1e9:.6f}秒；审计核心{audit['wall_ns']/1e9:.6f}秒。完整进程（含启动）另见collect/audit_process_receipt.json；所有失败/短/无窗口保留，没有补采。历史获取研究与前轮零交互诊断费用不计作本轮新交互。",'',
        '若软件合同未通过，停止，不启动训练。若通过，只允许据此继续独立响应训练/资格协议；仍需先冻结具体模型、同容量去摘要消融、强历史/前向基线、未知输入变换与噪声语义，以及独立TRAIN/CAL/QUAL和完整预算。旧QUAL不可调参，失败的ARX/F20/位置历史模型不复活。', '',
        '后续可检验由公开历史初始化隐状态、再多步展开的标准响应模型；这是已有状态空间辨识路线，换网络不构成论文贡献。当前与旧单步GRU/位置回归的差别需要在新设计中明确、独立验证，不能把未执行想法写成效果。获取改变状态/模型适用性时的决策机制、强任务基线、消融和方法自身独立时序部署仍未完成，CCF A目标未完成。', '',
        '原文范围：[SUBNET 2021](https://proceedings.mlr.press/v144/beintema21a.html)摘要；[初始化改进2023](https://arxiv.org/html/2304.02119)摘要、引言及模型/编码节；[在线ANN-SS 2026](https://arxiv.org/html/2607.17614)摘要、引言及II–III节。2026文的输出误差噪声假设与本环境执行输入噪声不同，其结论不能直接转成此处保证。既有模型适用范围、Residual RL、OCCAM、GAUGE、Poke and Strike查新继续保留。','']
    dest=a.ROOT/'reports/native_command_witness_v1_zh.md';io.require(not dest.exists(),'exclusive native report');dest.write_text('\n'.join(lines),encoding='utf-8')
    io.write(path.parent/'report_receipt.json',{'integrity':'PASSED','report':dest.relative_to(a.ROOT).as_posix(),'sha256':io.sha(dest),
        'audit_sha256':io.sha(out/'audit.json'),'native_contract':audit['native_contract'],'new_environment_steps':0,'new_model_fits':0,'online_LLM_API_calls':0})
    return dest


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--manifest',required=True,type=Path);v=p.parse_args();print(report(v.manifest.resolve()),flush=True)

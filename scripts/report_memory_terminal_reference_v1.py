"""Chinese finite-model/component report, never a robot performance report."""
from pathlib import Path
import argparse,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis.response_qualification_io_v1 import read,write,sha,require,ROOT


def main(path):
    path=path.resolve();out=path.parent;m=read(path);r=read(out/'results.json');a=read(out/'audit.json');done=read(out/'completion.json')
    require(a['integrity']=='PASSED' and a['completion_sha256']==sha(out/'completion.json'),'independent rational audit binding')
    for n,h in a['artifact_sha256'].items():require(sha(out/n)==h,'audited output changed')
    for name in ('interaction_guard.json','audit_interaction_guard.json'):require(read(out/name)['integrity']=='PASSED','zero interaction guard')
    link=lambda p,label:'['+label+']('+Path(p).resolve().as_posix()+')'
    rows=['# 带任务记忆的获取后缀与完整价值：标准参考资格','',
        '**本轮完成20项数组测试和已知有限模型的40项标准恒等式核验；没有机器人任务执行、训练或收益资格。DR、PI记忆交接及这些数值反例均不是本项目的新算法或CCF A贡献。**','',
        '## 完成了什么','',
        '任务记忆组件在普通任务步复用原PI精确算术；移动中断冻结任务积分，返回时更新实际回执中的步数和观测。若验证执行正常任务PI，则每步照实际回执提交积分。CARRY和EXPLICIT_RESET是两个明确模式，不能悄悄清零；保持积分本身不保证无突跳或安全。原PI源码没有修改。','',
        '两阶段参考估计的是固定目标获取／采用策略的完整截止损失，而不是随机采用行为的边际均值。用实际第一选项成本C、剩余终局损失Y和已付前缀t，递推D2=V2+ρ2(Y−Q2)，D1=V1+ρ1(C+D2−Q1)，完整估计t+D1。选项内提前结束没有第二动作，按真实终止罚值处理；不编造KEEP，也不把同一成本收费两次。','',
        'CONTINUE直接完成整个继续任务，因此其第一选项成本可以包含全部实际任务步，不能把所有C都叫额外获取成本。失败即使提前停止，截止损失仍为500，实际消耗另列。DR估计可能超出[0,500]，本轮不裁剪；那是估计器取值，不是执行了负步数或超过控制预算。','',
        '## 资格人口与费用','',
        f'固定全枚举{r["finite_atoms"]}个正概率模型原子，4个第一目标策略×2个后继策略×6种误设，共{r["estimate_rows"]:,}条估计、48个完整汇总。它们是已知离散模型的概率原子，**不是44次独立采样或机器人轨迹**，不计算机器人成功率、样本置信区间或统计功效。','',
        f'冻结提交`{m["source_git_commit"]}`。主枚举耗时{done["wall_ns"]/1e9:.6f}秒；独立有理数审计耗时{a["wall_ns"]/1e9:.6f}秒，检查{a["fields_checked"]:,}个字段。新环境创建、重置、控制步、物理帧、随机流、模型拟合、策略训练和在线LLM API均为0。模型里的步数是符号成本，不记作实际机器人交互。','',
        '冻结前已进行同一已知模型的完整均值算术开发核对（2,112次估计器调用）和20项单元测试；正式冻结测试另有守卫及调用计数。开发核对缺少原始专用耗时回执，标为缺失，不伪造计时。正式输出不是未见数据上的独立确认；独立审计指另外实现的有理数枚举与展开公式，而非独立数据。','',
        '正确Q由已知有限模型的条件均值构造，是评价端oracle测试夹具，不是新训练出的机器人价值模型；零／常数Q是固定误设夹具。报告概率数值合法不意味着等于真实行为概率，二者均错的偏差完整保留。','',
        '## 机会与代价的数值反例','',
        '固定目标后继规则在NEAR／FAR使用不同采用概率，行为规则随机采用。下表只比较这些预先定义规则的已知期望；不挑单次未来噪声结果，也不说明真实机器人会有同样收益。','',
        '| 可见前缀code | 第一选项 | 固定后继规则完整损失 | 行为边际完整损失 |','|---|---|---:|---:|']
    for c in r['conditional_action_comparisons']:rows.append(f'| {c["visible_code"]} | {c["first_action"]} | {c["fixed_poststate_policy_whole_loss"]:.6f} | {c["behavior_marginal_whole_loss"]:.6f} |')
    rows += ['',
        'code=1是刻意构造的机会例：随机采用行为下的MOVE均值可能劣于CONTINUE，但固定后继规则的MOVE价值更好；code=0保留移动代价较高的反例。不能把随机采用均值直接作为另一个后继策略的监督，也不能把这个人工构造当成真实任务收益。','',
        '## 全部误设组合','',
        '五种按阶段正确的组合共40项，其加权均值恒等式通过；两者均错的8项全部保留，不按无偏性晋级。DR并不在每个误设下都比IS有更小方差或MSE；完整数值见下表和CSV。','',
        '| 第一／后继策略 | 误设条件 | 真值 | DR均值 | DR偏差 | IS偏差 | DR MSE | 超范围原子 |','|---|---|---:|---:|---:|---:|---:|---:|']
    for s in r['setting_summaries']:
        v=s['estimators'];rows.append(f'| {s["first_target_policy"]}/{s["tail_target_policy"]} | {s["mode"]} | {s["known_target_whole_loss"]:.6f} | {v["whole_DR"]["mean"]:.6f} | {v["whole_DR"]["bias"]:+.6f} | {v["whole_IS"]["bias"]:+.6f} | {v["whole_DR"]["MSE"]:.6f} | {s["DR_atoms_outside_0_500"]} |')
    rows += ['',
        'P_TRUE_Q_ZERO／P_TRUE_Q_WRONG：两阶段报告概率正确，Q为0或常数；P_WRONG_Q_TRUE：报告概率错而两阶段Q正确；P1_TRUE_Q2_TRUE／Q1_TRUE_P2_TRUE：逐阶段混合正确；BOTH_WRONG：均错。正确模型要求针对同一个固定目标后继规则的条件价值，不能拿另一个策略的均值冒充。','',
        '## 查新与后续机制','',
        '[Jiang与Li原文](https://proceedings.mlr.press/v48/jiang16.pdf)已有序贯DR；[OCCAM](https://arxiv.org/html/2406.17620v1)已有控制器表现预测与在线参数优化；[官方PID切换示例](https://www.mathworks.com/help/simulink/slref/bumpless-control-transfer-between-manual-and-pid-control.html)已有积分跟踪。阅读范围和机制边界见'+link(ROOT/'docs/research/memory_terminal_reference_prior_art_v1_zh.md','一手来源说明')+'。本轮没有复现这些完整系统或继承其机器人保证。','',
        '具体后继假说仍是：同时建模真实获取后状态、控制器记忆、模型适用性证据与保留／采用的完整尾部损失，再估计该后继规则的获取前价值。当前只把其中状态交接和标准估计底座做成可运行参考；纠正／重辨识动作族、学习模型、原生连续执行契约、同预算强对照、独立自身历史部署和消融仍未完成。','',
        '后续原生执行器必须验证环境、噪声、时钟和先保存后执行；本模块的公开回执不能自行证明物理连续。新的随机获取／采用数据必须记录真实选择概率，训练／校准／评价分离，拒绝后从实际状态继续。标准DR恒等式不保证有限数据学习出的策略更优、减少错误更新或保留所有适应机会。','',
        '旧PI资格与F20开发失败保持原样，全部旧记录、原分片、恢复及预留种子保留。不调旧权重或把本次合成结果用于替旧方法翻案。下一步需要把上述假说落实到已资格的真实动作族和独立研究协议，不能以20项测试或40条恒等式作为论文完成。','',
        '## 复算文件','',
        '- '+link(path,'冻结manifest与来源SHA256'),
        '- '+link(out/'finite_atoms.jsonl','全部44个合成模型原子和终止分支'),
        '- '+link(out/'estimates.jsonl','全部2,112条输入、预测夹具及估计'),
        '- '+link(out/'setting_summaries.csv','完整48组合、偏差、方差与MSE'),
        '- '+link(out/'audit.json','禁用主函数的独立有理数／展开公式审计'),
        '- '+link(ROOT/'outputs/memory_terminal_reference/validation_v1','开发核对披露、20项测试与检查回执'),
        '', '仅本地提交，不推送或合并。CCF A目标仍未完成。','']
    report=ROOT/'reports/memory_terminal_reference_v1_zh.md'
    with report.open('x',encoding='utf-8',newline='\n') as f:f.write('\n'.join(rows))
    write(out/'report_receipt.json',{'report':report.relative_to(ROOT).as_posix(),'report_sha256':sha(report),'generator_sha256':sha(__file__),
        'audit_sha256':sha(out/'audit.json'),'classification':'STANDARD_SYNTHETIC_REFERENCE_ONLY','publication_goal_complete':False})
    print({'Chinese_report':str(report),'robot_task_evaluation':False},flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);a=p.parse_args();main(a.manifest)

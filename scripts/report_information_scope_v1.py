"""Chinese exact-counterexample report; no claim of new robot performance."""
from pathlib import Path
from time import perf_counter_ns
import subprocess,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis import information_scope_io_v1 as a
io=a.io


def report(path):
    start=perf_counter_ns();m=a.checked(path);root=path.parent;audit=io.read(root/'audit.json')
    io.require(audit['integrity']=='PASSED','independent Fraction/Decimal audit before report')
    for folder in ('planning','evaluation'):
        done=io.read(root/folder/'completion.json')
        for name,h in done['artifact_sha256'].items():io.require(io.sha(root/folder/name)==h,'audited finite data bytes unchanged')
    command=['C:/Users/Administrator/Documents/ChatGPT/robotic agent/.venv-latent-report/Scripts/python.exe','-I',
        str(a.ROOT/'scripts/plot_information_scope_v1.py'),'--root',str(root),'--output',str(root/'figures')]
    with (root/'plot_process.log').open('x',encoding='utf-8',newline='\n') as handle:process=subprocess.run(command,cwd=a.ROOT,stdout=handle,stderr=subprocess.STDOUT)
    io.write(root/'plot_process_receipt.json',dict(command=command,returncode=process.returncode));io.require(process.returncode==0,'finite report plotting')
    rows=io.read(root/'planning/probability_results.json');w=io.read(root/'planning/witness.json');non=io.read(root/'planning/noninformative_witness.json')
    summary=io.read(root/'evaluation/summary.json');problems=io.read(root/'planning/decision_problems.json');values=io.read(root/'evaluation/results.json')
    violations=sum(not v['unconditional_posterior_contraction_holds'] for v in rows)
    true_all=all(v['corrected_slack_bound_holds'] and v['joint_KL_contraction_holds'] and v['true_information_contraction_holds'] for v in rows)
    lines=['# 信息误差与实际采用规则：有限模型参考 v1','',
        '**本轮是构造性数学复核和标准决策参考，不是机器人实验、新算法资格或CCF A成果。** '
        '所有构造与网格在完整枚举前冻结；显式反例是事先推导的数学见证，不伪装成独立抽样发现。'
        '新环境/重置/控制步/帧、拟合、优化器、在线LLM API、任务种子均为0。','',
        f"冻结`{m['source_git_commit']}`；清单`{m['manifest_id']}`；独立审计核对{audit['independently_checked_fields']}字段，"
        '采用精确有理概率和80位Decimal对数，禁用主计算/规划函数。','',
        '## 要解决的具体问题','',
        '上一轮机器人主候选仍未通过资格；本轮不改模型或旧QUAL。当前研究需要区分：'
        '后验在数值上合法、对当前观测/状态有预测能力、实际采用后降低完整任务损失。'
        '若把一般信息准则的收缩直接当成更新风险缩小，就可能跳过其中两层。','',
        '[Callahan与Catanach，AISTATS2026](https://proceedings.mlr.press/v300/callahan26a.html)'
        '研究失配推断下的信息价值。已读正文§2–4及附录C.2–C.3，并实际查看PDF第3、4、17页。'
        '以下只复核附录C.2按共同核合并观测时使用的后验条件KL收缩步骤；正文R4的充分关系措辞有方向歧义，'
        '本报告不推断作者意图，也不声称作者已接受任何修订。','',
        '## 一个全支撑、共同先验的明确见证','',
        '隐变量Θ有两值，观测Y有三值。P和Q都是合法联合分布，所有六个单元严格为正。'
        '两者的Θ先验均为(1/2,1/2)，细观测下Θ=1的后验均为(1/10,1/2,9/10)。'
        '差异仅在观测频率：P_Y=(1/4,1/2,1/4)，Q_Y=(2/5,1/5,2/5)。共同确定性核把前两类观测合并，保留第三类。','',
        '|Θ|P(Y=0)|P(Y=1)|P(Y=2)|Q(Y=0)|Q(Y=1)|Q(Y=2)|',
        '|---|---|---|---|---|---|---|']
    for z in range(2):lines.append('|'+str(z)+'|'+'|'.join(w['input']['p'][z]+w['input']['q'][z])+'|')
    lines+=['','令C为按P观测频率平均的后验KL，J为联合KL，M为观测边际KL。所有对数为自然对数。','',
        '|量，单位nats|细观测|合并观测|','|---|---:|---:|']
    for name in ('conditional_posterior_KL','joint_KL','predictive_marginal_KL','true_mutual_information','EGIG'):
        lines.append(f"|{name}|{w['result']['fine'][name]:.15f}|{w['result']['coarse'][name]:.15f}|")
    lines+=['','合并后的第一类观测，P的Θ=1后验为11/30，Q为7/30。'
        '细观测后验误差为0，合并后为正；与此同时，联合KL仍然减小。因此共同核下的联合KL数据处理不等式，'
        '不能直接改写成这里的条件后验KL收缩。该见证不需要零概率、先验差异、近似推断或数值奇异。','',
        '由标准KL链式法则与联合数据处理不等式，可直接得到修正边界：','',
        r'\[C_2-C_1\leq M_1-M_2,\qquad J_i=M_i+C_i.\]','',
        '右端是观测频率失配被合并掉的量，不一定为零。若两模型细观测边际相同，则右端为0，'
        '此时恢复条件后验收缩。这里只使用标准恒等式，不将这两行推导声称为新的理论贡献或机器人安全保证。','',
        '## 完整构造网格与正对照','',
        f'完整保留324条构造记录、270个唯一联合分布/通道问题，54条重复是两个检验族的明确重叠，'
        f'不是独立样本。条件后验无条件收缩在{violations}/324条中不成立；'
        f'所有联合KL收缩、真实信息收缩和带边际松弛项边界均通过：{true_all}。'
        '同观测边际的162条正对照全部保留，不只展示反例。没有p值、置信区间或样本量功效主张。','',
        f"![全部构造及修正界](../{(root/'figures/conditional_and_joint_scope.png').relative_to(a.ROOT).as_posix()})",'',
        '另外，在两模型后验都保持先验不动、但观测频率不同的无信息例中，'
        f"EGIG为{non['metrics']['EGIG']:.12f}，联合惩罚版RFIM_KL为{non['metrics']['RFIM_KL']:.12f}。"
        '因此，“后验不更新的归一化”与“同时惩罚预测频率失配”是不同要求，不能把它们当作同一条件。','',
        '## 成本、后状态与实际采用：全部有限决策参考','',
        '216个构造问题覆盖正向/反向频率失配、全部预定获取成本和后状态变化。每题12个参考程序，'
        '共2592份策略先保存再评估。CONTINUE、FINE、COARSE是有限数学决策，'
        '并非真实机器人指令；025/050/100仅是合成尾策略标签，不是重新启动旧ARX限幅实验。','',
        '成功时损失为获取成本加真实后状态下的完成时长；失败按500截止。'
        '实际期望损失为(1−f)(k+d_s)+500f，失败时不能再加k。'
        'KEEP在获取后的状态继续，不能撤销状态变化；STOP保留已花代价，截止损失仍为500。','',
        'WORKING_BAYES使用工作模型Q的标准有限贝叶斯选择；两个ORACLE显式读取合成真分布P，'
        '属于有特权的参考，不是可部署算法。ORACLE_JOINT_IMPLEMENTED评价实际Q后继规则；'
        'ORACLE_IDEAL_EXECUTED同时用P作后继决策。OPTIMISTIC_POST_MISMATCH先假想理想后继，'
        '实际却执行Q规则，专门暴露前后规则不一致造成的乐观性。另保留忽略状态、忽略成本、'
        '四种直接固定尾策略和两种始终获取参考。','',
        '下表是完整构造网格等权描述，不是独立机器人成功率。成功概率来自声明的有限概率表，'
        '不是新增物理执行；有特权参考的优势不能当作本方法任务收益。','',
        '|参考|完整截止损失均值|平均成功概率|平均获取等价成本|不利采用概率|保留但错过收益概率|',
        '|---|---:|---:|---:|---:|---:|']
    for v in summary:
        x=v['means'];lines.append(f"|{v['method']}|{x['cutoff_loss']:.9f}|{x['success_probability']:.9f}|{x['acquisition_equivalent']:.9f}|{x['harmful_adoption_probability']:.9f}|{x['keep_missing_benefit_probability']:.9f}|")
    lines+=['','“不利采用”用同一已获取后状态及该观测下，所选采用尾策略的真条件期望损失高于KEEP定义；'
        '“错过收益”是保留时存在更低损失尾策略。这里只在声明真分布的有限问题中可精确计算，'
        '实际机器人中一次配对实现值不等于这些条件期望。','',
        f"![实际后继和完整成本的诊断切片](../{(root/'figures/implemented_continuation_costs.png').relative_to(a.ROOT).as_posix()})",'',
        '图仅展示事先声明的正向失配、FINE状态变化0、COARSE成本1切片；全部216题、两个失配方向、'
        '12程序及其动作、成功概率与采用错误均保留在evaluation/results.json，不据切片选择新任务或阈值。','',
        '## 后续研究判断','',
        '新证据改变了资格要求：后验更集中或更稳定不足以推出模型更可信，'
        '还必须检查获取所产生的公开后状态/证据频率及实际后继行为。'
        '但真联合分布在机器人在线决策时不可用，本轮没有得到一个可直接部署的风险评分器。','',
        '下一独立设计应先给出可用公开数据估计的联合后状态—证据分布和完整尾收益参考，'
        '区分工作模型、实际采用规则与获取后的真实状态。与OCCAM类直接表现预测、'
        '标准双重控制/决策相关探测作同权限强比较；不将本轮标准链式推导或两阶段结构当作新颖性。'
        '旧两阶段RBF和尾价值参考的负结果继续保留，不能换名重试旧人口。','',
        '新采集前仍需独立冻结训练/校准/最终自身时序评价、种子检查、完整物理及拟合费用、'
        '主比较和停止条件。最终任务标准保持截止损失优于DIRECT_C8和积分，并保留更强RAW PI、'
        '始终获取、获取不更新、标准检测/历史辨识及任务相关参考。'
        '当前不采集、不调旧QUAL、不接入失败SS/ARX，不宣称安全或完成CCF A目标。','',
        '[本轮一手文献与具体差异核对](../docs/research/information_scope_prior_art_v1_zh.md)','']
    dest=a.ROOT/'reports/information_scope_reference_v1_zh.md'
    with dest.open('x',encoding='utf-8',newline='\n') as handle:handle.write('\n'.join(lines))
    io.write(root/'report_receipt.json',dict(manifest_id=m['manifest_id'],report=dest.relative_to(a.ROOT).as_posix(),report_sha256=io.sha(dest),
        audit_sha256=io.sha(root/'audit.json'),conditional_contraction_counterexamples=violations,
        all_corrected_and_joint_bounds_hold=true_all,wall_ns=perf_counter_ns()-start,
        new_environment_steps=0,new_model_fits=0,online_LLM_API_calls=0,publication_goal_complete=False))
    return dest

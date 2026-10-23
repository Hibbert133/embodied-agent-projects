"""Chinese complete-population descriptive report; no selection or new model."""
from pathlib import Path
from time import perf_counter_ns
import subprocess,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis import latent_response_diagnosis_io_v1 as a
io=a.io
PLOT_PYTHON=Path('C:/Users/Administrator/Documents/ChatGPT/robotic agent/.venv-latent-report/Scripts/python.exe')


def write_text(path,text):
    with path.open('x',encoding='utf-8',newline='\n') as f:f.write(text)


def report(path):
    start=perf_counter_ns();m=a.checked(path);root=path.parent;folder=root/'analysis';audit=io.read(folder/'audit.json');io.require(audit['integrity']=='PASSED','independent whole diagnosis audit first')
    for name,h in audit['artifact_sha256'].items():io.require(io.sha(folder/name)==h,'audited diagnostic bytes')
    curves=io.read(folder/'TRAIN_objectives.json');broad=io.read(folder/'broad_grouped_metrics.json');menu=io.read(folder/'reference_menu_summary.json');units=io.read(folder/'reference_menu_units.json')
    done=io.read(folder/'completion.json');original=io.read(a.LATENT/'qual_evaluation/statistics.json');register=io.read(folder/'case_register.json')
    worker=a.ROOT/'scripts/plot_latent_response_diagnosis_v1.py';command=[str(PLOT_PYTHON),'-I',str(worker),'--analysis',str(folder),'--output',str(root/'figures')]
    before=perf_counter_ns()
    with (root/'plot_process.log').open('x',encoding='utf-8',newline='\n') as handle:plotted=subprocess.run(command,cwd=a.ROOT,stdout=handle,stderr=subprocess.STDOUT)
    io.write(root/'plot_process_receipt.json',{'command':command,'returncode':plotted.returncode,'wall_ns':perf_counter_ns()-before,'new_environment_steps':0,'new_model_fits':0,'online_LLM_API_calls':0});io.require(plotted.returncode==0,'isolated plot worker')
    find=lambda task,method,regime='ALL_WINDOWS',checkpoint=None:next(r for r in curves if (r['task'],r['method'],r['regime'],r['checkpoint'])==(task,method,regime,5000 if checkpoint is None and method in a.NEURAL else checkpoint))
    lines=['# 响应失败与完整任务机会诊断 v1','',
        '**全部新增分析为事后描述性分析。** 本轮未采集、拟合、更新、选择或部署模型，也不改变旧资格/统计。数值合法、当前预测与完整任务收益继续分开。CCF A目标未完成。','',
        f"分析冻结`{m['analysis_git_commit']}`；运行`{m['experiment_run_id']}`；清单`{m['manifest_id']}`。",'',
        f"独立审计PASSED，核对{audit['independently_checked_fields']}字段。每遍复算100464个既有权重/查询，另读取3424个既有CAL/QUAL预测；训练、优化器更新、环境/重置/步/帧、在线LLM API新增均0。主分析{done['wall_ns']/1e9:.3f}秒，独立审计{audit['wall_ns']/1e9:.3f}秒；不可把同一轨迹的窗口或前向次数当作独立样本。",'',
        '## 原始结论及全部分母','',
        f"原SS_SENT资格仍为**{original['qualification']}**。原完整分配H8损失{original['summaries']['SS_SENT']['mean_h8_loss_m']:.9f}m；有效窗口原均值{original['summaries']['SS_SENT']['mean_valid_h8_raw_rmse_m']*1000:.6f}mm，直接岭回归{original['summaries']['DIRECT_RIDGE_H8']['mean_valid_h8_raw_rmse_m']*1000:.6f}mm。以上直接引用冻结统计，不被下文不同权重的描述替代。",'',
        '|来源阶段|全部执行|有诊断查询的轨迹|查询窗口|完整首8步物理包|','|---|---:|---:|---:|---:|']
    for split in a.latent.SPLITS:
        rs=[r for r in register if r['split']==split];lines.append(f"|{split}|{len(rs)}|{sum(r['diagnostic_queries']>0 for r in rs)}|{sum(r['diagnostic_queries'] for r in rs)}|{sum(r['complete_first_eight'] for r in rs)}|")
    lines+=['','SOFTWARE按原协议未运行预测，不能将其空预测当成失败误差。TRAIN4186窗口包含一个提前结束的32步包，所有掩码/空箱保留；CAL/QUAL只读原先真实执行前保存的入口预测，没有重算其他检查点。完整792例登记及每个空箱原因见case_register和trajectory_metrics。', '',
        '## 训练目标是否已落后于简单参考','',
        '此表按冻结神经采样：每任务可用轨迹等权、轨迹内实际窗口等权、窗口内实际有效XY元素等权，使用物理mm²单位。它是完整经验训练目标，不是一个随机小批次的loss；部分标签掩码使其不必等于岭回归各时域分别拟合的目标。', '',
        '|任务|方法|可用轨迹|全部窗口目标mm²↓|入口目标mm²↓|','|---|---|---:|---:|---:|']
    counter=[]
    for task in io.TASKS:
        for method in a.METHODS:
            allr=find(task,method);entry=find(task,method,'ENTRY_ONLY');value=allr['metrics']['masked_H8_objective_m2'];ev=entry['metrics']['masked_H8_objective_m2']
            lines.append(f"|{task}|{method}|{allr['available_trajectories']}|{'H1模型不适用' if value is None else format(value*1e6,'.9f')}|{'不适用' if ev is None else format(ev*1e6,'.9f')}|")
        ss=find(task,'SS_SENT')['metrics']['masked_H8_objective_m2'];ridge=find(task,'DIRECT_RIDGE_H8')['metrics']['masked_H8_objective_m2'];counter.append({'task':task,'SS_TRAIN_objective_m2':ss,'ridge_TRAIN_objective_m2':ridge,'network_already_worse_on_TRAIN':ss>ridge})
    lines+=['','|任务|SS_SENT在TRAIN目标上已劣于直接岭|','|---|---|',*['|'+r['task']+'|'+str(r['network_already_worse_on_TRAIN'])+'|' for r in counter], '',
        '若上表为True，纯粹由独立人口分布变化解释该任务上的全部差距不充分。它仍不能区分表示容量、优化过程、目标权重和噪声；没有追加训练、换初值或修改容量验证任何唯一原因。反之也不能仅凭TRAIN较好断定独立差距只由某种漂移造成。', '',
        '### 所有既有神经检查点，仅TRAIN','',
        '|任务|方法|更新步|全部窗口目标mm²|入口目标mm²|','|---|---|---:|---:|---:|']
    for task in io.TASKS:
        for method in a.NEURAL:
            for k in a.CHECKPOINTS:
                v=find(task,method,checkpoint=k);e=find(task,method,'ENTRY_ONLY',k)
                lines.append(f"|{task}|{method}|{k}|{v['metrics']['masked_H8_objective_m2']*1e6:.9f}|{e['metrics']['masked_H8_objective_m2']*1e6:.9f}|")
    lines+=['','没有选取“最好检查点”。最终权重仍是5000步；曲线改善、停滞或非单调都不是新优化方案的资格证据。','',
        f"![完整TRAIN目标](../{(root/'figures/TRAIN_fixed_checkpoints.png').relative_to(a.ROOT).as_posix()})", '',
        '## 入口和后续窗口：按轨迹及独立组组织','',
        '下表先在每条真实轨迹内平均，再在独立组内和组间等权。可用性不同时，这与原“有效案例等权均值”可能不同，因此不能替换原3.482987mm或原完整分配比较。每项原始误差只平均有实际相应时域的窗口，缺失分母另列；不填零、不产生新的区间或显著性。','',
        '|阶段|任务|方法|窗口|分配/可用轨迹|独立/可用组|H1均值mm|H8均值mm|','|---|---|---|---|---|---|---:|---:|']
    for r in broad:
        if r['checkpoint'] not in (None,5000) or r['regime'] not in ('ENTRY_ONLY','ALL_WINDOWS'):continue
        v=r['metrics'];fmt=lambda x:'缺失/不适用' if x is None else f'{x*1000:.6f}'
        lines.append(f"|{r['split']}|{r['task']}|{r['method']}|{r['regime']}|{r['allocated_trajectories']}/{r['available_trajectories']}|{r['independent_groups']}/{r['available_groups']}|{fmt(v['H1_rmse_m']) if v else '缺失'}|{fmt(v['H8_rmse_m']) if v else '缺失'}|")
    lines+=['','完整task×初始条件×变化×包×时点×窗口分段表位于grouped_metrics.json；空段的reason保留在trajectory_metrics。', '',
        f"![真实时域](../{(root/'figures/QUAL_actual_horizons.png').relative_to(a.ROOT).as_posix()})", '',
        '## 累积、原生目标与手部响应','',
        '以下为QUAL完整H8窗口、轨迹/组等权的有符号能量。终点误差=增量误差能量+所有交叉项；交叉项负值表示抵消，正值表示相干累积，不能由此独断噪声或物理失配的唯一来源。模型/名义/实测原生/手部的三项分解也保留全部交叉项。', '',
        '|任务|方法|H8末端mm²|增量对角mm²|有符号交叉mm²|','|---|---|---:|---:|---:|']
    for r in broad:
        if r['split']!='QUAL' or r['regime']!='ENTRY_ONLY' or r['checkpoint'] not in (None,5000) or r['method'] not in a.METHODS[:6]:continue
        v=r['metrics'];lines.append(f"|{r['task']}|{r['method']}|{v['H8_terminal_error_m2']*1e6:.9f}|{v['H8_increment_diagonal_energy_m2']*1e6:.9f}|{v['H8_increment_cross_energy_m2']*1e6:.9f}|")
    lines+=['','原生目标与名义累计不等，原生目标也不等于手部位置。两个差都包括真实执行过程的影响，不能把剩余项叫“无噪声物理误差”。本轮没有重做真实参数拟合或使用私有状态监督。入口连续特征只是代理描述，冻结标准化幅度不是适用域证明；缺少接触力/接触对，手物距离不能确定接触机制。', '',
        '## 完整任务：现有动作菜单有多少记录内机会','',
        '这一部分来自另一个旧QUAL，54任务单元、9独立组、540次完整程序执行，不能与响应误差人口混合。八个RAW共同前缀程序实际匹配378对；C8和积分另有前缀，只作为完整程序外部强对照。以下全部旧均值/成功数与原统计核对不变。','',
        '|程序|成功/54|完整截止损失均值↓|','|---|---:|---:|']
    for r in menu['program_summaries']:lines.append(f"|{r['program']}|{r['successes']}/54|{r['mean_deadline_loss']:.6f}|")
    lines += ['',f"八程序未来结果可见的记录内最优菜单均值{menu['oracle_mean_loss']:.6f}步；RAW均值{menu['raw_mean_loss']:.6f}步；乐观平均余地{menu['optimistic_mean_raw_saving']:.6f}步，{menu['positive_realized_opportunity_units']}/54单元有严格正的实现差值。四程序同获取/采用分支子菜单均值{menu['same_acquisition_submenu_mean_loss']:.6f}步、乐观余地{menu['same_acquisition_submenu_mean_raw_saving']:.6f}步。所有并列最小值保留。",'',
        '这是看过所有已发生未来结果的乐观记录菜单；它必然不差于菜单内RAW，不能当成真实策略、一般最优界、可学习性证明或新的任务收益。新方法仍须在独立自身时序历史中实际部署并支付全部费用。', '',
        '|任务|条件|时点|全部单元|RAW均值|记录菜单均值|正实现余地单元|','|---|---|---:|---:|---:|---:|---:|']
    for r in menu['cells']:lines.append(f"|{r['task']}|{r['context']}|{r['boundary']}|{r['allocated']}|{r['raw_mean_loss']:.6f}|{r['oracle_mean_loss']:.6f}|{r['positive_realized_opportunity_units']}|")
    lines+=['','### 全部54单元及获取/采用分解','',
        '完整损失已经包含移动与测量。KEEP减RAW包含获取成本和实际状态改变；RESET/CARRY减KEEP在相同获取路径后描述分支差，保留所有分配，不按采用/拒绝筛选因果样本。下面三列是代数恒等式，不把拟合误差或纯移动步数当收益。', '',
        '|组|任务|条件|程序|整体减RAW|KEEP减RAW|分支减KEEP|','|---:|---|---|---|---:|---:|---:|']
    for u in units:
        for name,d in u['decompositions'].items():lines.append(f"|{u['group']}|{u['task']}|{u['context']}|{name}|{d['whole_minus_raw']}|{d['acquisition_keep_minus_raw']}|{d['reference_minus_keep']}|")
    lines+=['',f"![完整任务记录机会](../{(root/'figures/reference_full_cost_opportunity.png').relative_to(a.ROOT).as_posix()})",'',
        '## 费用、来源与后续判断','',
        '原响应来源费用为792执行/59268控制步/40392全部重置/20492340帧，包含21个拟合模型的12神经训练/60000更新、30岭系统及30审计重算；旧参考QUAL费用为540执行/65854步/27540全部重置/14099270帧，初始C4/C8尝试216、过去审计重算216。它们是历史费用，不能称为本轮新增；也不与本轮零交互重复相加。','',
        '本轮新前向计算和独立前向复核分别记账；没有新拟合、优化器步、环境或LLM。分析完整来源哈希及未改变的原比较在manifest，全部预测/掩码/误差/轨迹/组/菜单表在analysis目录。','',
        '后续不围绕失败SS版本增加逆控制、混合权重或门控，也不按旧QUAL改优化器/容量/阈值。训练目标上的反证只能促成可检验的新解释；菜单乐观余地只能说明值得或不值得进一步研究的范围，不能替代可观察证据与独立部署。新的研究设计应明确联合处理获取后的实际状态、所获数据、模型适用性及采用/拒绝后继行为，并以完整任务损失对强基线验证。','',
        '任务相关模型本身有先例：[Value Equivalence，NeurIPS 2020](https://proceedings.neurips.cc/paper_files/paper/2020/hash/3bb585ea00014b0e3ebe4c6dd165a358-Abstract.html)讨论模型对价值规划的作用；[Task-based Model Learning，NIPS 2017](https://proceedings.neurips.cc/paper/2017/hash/3fc2c60b5782f641f76bcefc39fb2392-Abstract.html)直接以最终任务目标学习模型。本轮只读官方摘要，未复现算法/证明；不能将“改用任务损失”或“用价值模型”本身称作创新。原五项路线、双重控制和任务相关探索继续必须比较。','']
    dest=a.ROOT/'reports/latent_response_diagnosis_v1_zh.md';write_text(dest,'\n'.join(lines))
    decision=['# 响应与任务机会诊断 v1：后续判断','',
        '这是事后描述性诊断，所有旧资格与负结果不变。新增环境/重置/控制步/拟合/优化器更新/在线LLM API均为0。','',
        '|任务|网络在TRAIN完整目标上已弱于直接岭|','|---|---|',*['|'+r['task']+'|'+str(r['network_already_worse_on_TRAIN'])+'|' for r in counter], '',
        f"完整旧任务记录的八程序乐观菜单余地为{menu['optimistic_mean_raw_saving']:.6f}步，发生于{menu['positive_realized_opportunity_units']}/54单元。这看到了未来，既不证明可学习，也不证明状态改变或模型更新的唯一原因。",'',
        '两项结果不能支持在旧QUAL上调大网络/延长训练，也不能把直接岭回归事后换为原主候选。先针对训练/表示与任务价值分离形成独立可证伪解释；仅当另行冻结训练、资格、完整成本、强对照和新方法自身时序部署协议后，才能考虑新采集。', '',
        '潜在贡献必须具体区别于双重控制、任务相关探索、价值等价/任务导向学习，处理获取动作改变状态和适用性后采用/拒绝的后继行为；目前没有完成新机制、强任务收益、消融或CCF A目标。', '',
        '[完整中文诊断报告](../../reports/latent_response_diagnosis_v1_zh.md)','']
    decisionpath=a.ROOT/'docs/research/latent_response_diagnosis_decision_v1_zh.md';write_text(decisionpath,'\n'.join(decision))
    io.write(root/'report_receipt.json',{'integrity':'SOURCE_BOUND_DESCRIPTIVE_REPORT','manifest_id':m['manifest_id'],'report':dest.relative_to(a.ROOT).as_posix(),'report_sha256':io.sha(dest),
        'decision':decisionpath.relative_to(a.ROOT).as_posix(),'decision_sha256':io.sha(decisionpath),'diagnostic_audit_sha256':io.sha(folder/'audit.json'),
        'TRAIN_counterevidence':counter,'wall_ns':perf_counter_ns()-start,'new_environment_steps':0,'new_model_fits':0,'online_LLM_API_calls':0,'publication_goal_complete':False})
    return dest

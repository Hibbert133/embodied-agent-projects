from pathlib import Path
from time import perf_counter_ns
import csv,json,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import correction_transfer_learning_v1 as m
io=m.io;path=Path(sys.argv[1]).resolve();manifest=m.checked(path);base=path.parent;start=perf_counter_ns()
assert io.read(base/'pipeline_control/completion.json')['status']=='COMPLETED'
r=io.read(base/'results.json');rows=io.read(base/'selected_rows.json');fit=io.read(base/'fit_receipt.json');audit=io.read(base/'model_audit.json');replay=io.read(base/'replay_audit.json')
out=base/'presentation';out.mkdir(exist_ok=True)
def table(headers,records):return '\n'.join(['|'+'|'.join(headers)+'|','|'+'|'.join(['---']*len(headers))+'|',*['|'+'|'.join(str(v) for v in row)+'|' for row in records]])
def export(name,headers,records):
    with (out/name).open('x',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(headers);w.writerows(records)
failures=[v for v in rows if not v['leaf']['success']];harm=[v for v in rows if v['leaf']['loss']>v['baseline']['loss']]
cols=['selector','group','task','condition','boundary','action','rate','loss','success','steps','acquisition_steps','baseline_loss','same_acquisition_loss','source_case_sha256']
def values(v):return [v['selector'],v['unit'][1],v['unit'][2],v['unit'][3],v['boundary'],v['action'],v['rate'],v['leaf']['loss'],v['leaf']['success'],v['leaf']['steps'],v['leaf']['movement_steps']+v['leaf']['measurement_steps'],v['baseline']['loss'],v['same_acquisition']['loss'],v['leaf']['source_case_sha256']]
export('all_selections.csv',cols,[values(v) for v in rows]);export('all_selected_failures.csv',cols,[values(v) for v in failures]);export('all_harmful_choices.csv',cols,[values(v) for v in harm])
export('all_task_condition_boundary_panels.csv',['selector','task','condition','boundary','n','success','mean_loss'],
    [[selector,*key.split('/'),v['n'],v['success'],v['mean_loss']] for selector,s in r['selectors'].items() for key,v in s['panels'].items()])
cand='JOINT_SPO/TWO_STAGE';candidate=r['selectors'][cand];comparators=[v+'/TWO_STAGE' for v in m.VARIANTS if v!='JOINT_SPO']+[s for s in m.SELECTORS if s.startswith('FIXED/')]
total=lambda name:sum(v['leaf']['loss'] for v in rows if v['selector']==name)
gate=all(total(cand)<total(v) for v in comparators)
decision=dict(status='DEVELOPMENT_NECESSARY_CONDITION_ONLY' if gate else 'CLOSED_THIS_JOINT_SPO_VERSION',
    candidate=cand,candidate_total_loss=total(cand),all_comparator_total_losses={v:total(v) for v in comparators},
    complete_population_mean_loss_criterion=gate,independent_task_benefit_qualified=False,algorithm_novelty_established=False,
    permission_for_new_physical_collection=False,online_LLM_API_calls=0,publication_goal_complete=False)
io.write(base/'development_decision.json',decision)
learn=[s for s in m.SELECTORS if not s.startswith('FIXED/')];fixed=[s for s in m.SELECTORS if s.startswith('FIXED/')]
def result_table(selectors):return table(['程序','成功/54','平均完整损失↓','相对CONTINUE0.5有害/有利/相同','成功→失败/失败→成功','已有获取步数'],
    [[s,f"{r['selectors'][s]['success']}/54",f"{r['selectors'][s]['mean_loss']:.6f}",f"{r['selectors'][s]['harm']}/{r['selectors'][s]['help']}/{r['selectors'][s]['tie']}",
      f"{r['selectors'][s]['success_to_failure']}/{r['selectors'][s]['failure_to_success']}",r['selectors'][s]['acquisition_steps']] for s in selectors])
main_comparisons=table(['候选JOINT两阶段 − 对照','平均损失差（步）'],[[v,f"{candidate['mean_loss']-r['selectors'][v]['mean_loss']:+.6f}"] for v in comparators])
group_table=table(['组','时点','DIRECT_MSE','DIRECT_SPO','经验重加权','条件误差','JOINT'],
    [[g,(16,32,64)[g%3],*[f"{r['selectors'][v+'/TWO_STAGE']['groups'][str(g)]:.3f}" for v in m.VARIANTS]] for g in range(9)])
best_fixed=min(fixed,key=lambda key:total(key));group_gap={str(g):candidate['groups'][str(g)]-r['selectors'][best_fixed]['groups'][str(g)] for g in range(9)}
concentration=table(['来源组','JOINT两阶段 − 最低全人口均值固定程序（步）'],[[g,f'{v:+.6f}'] for g,v in group_gap.items()])
forecast_table=table(['版本','有效/全部RETURN','成本分数MSE','访问分布平方L2','joint平方L2','均值误差MSE','历史未覆盖质量'],
    [[v,f"{s['available_nodes']}/162",*[f"{s['equal_group_mean'][k]:.6f}" for k in ('full_cost_score_mse','occupancy_squared_l2','joint_squared_l2','mean_error_mse','unknown_historical_mass')]] for v,s in r['forecast_diagnostics'].items()])
synthetic={}
for p in (m.BASE/'development_checks').glob('attempt_*/tests.json'):
    for k,v in io.read(p)['synthetic_neural_ledger'].items():synthetic[k]=synthetic.get(k,0)+v
test=io.read(m.BASE/'freeze_validation/complete.json')
headline='仅满足本轮开发必要条件，不能宣称独立收益' if gate else '未通过预定开发标准，关闭这一版JOINT_SPO'
lines=[f'# 纠正后适用性辅助学习：中文开发报告 v1',f'**{headline}。** 本报告新增分析全部为**事后描述性分析**。候选两阶段成功{candidate["success"]}/54，平均完整截止损失{candidate["mean_loss"]:.6f}步。旧TRAIN来源用于开发留出重放；没有新的真实在线部署或独立资格人口。',
    f'运行 `{base.name}`；科学冻结 `{manifest["source_git_commit"]}`。完整32程序×54单元=1728次离线选择；9组、3任务×2条件×3时点全部保留。所有科学拟合、参数独立复算和日志/统计审计已完成。',
    '## 方法名字与问题',
    'DIRECT 表示直接用完整任务损失训练，MSE为均方误差；SPO+表示训练时关心选错程序的代价。EMPIRICAL_REWEIGHT把候选纠正之后预测会访问的查询，用已有历史条件误差重新加权。CONDITIONAL学习各查询条件下误差；JOINT直接学习“在哪里访问、在那里误差多大”的加权分布。TWO_STAGE先选是否继续/验证/移动，再在真实返回节点选PI时间常数；时间常数越小积分适应越快，0.125/0.5/2/8并不是采用新ARX的百分比。',
    '候选只检验辅助监督是否帮助完整任务决策。p和条件误差可代数分解成j，没有自动的信息优势；有限参数和损失函数的不同至多说明学习偏置。所有版本保留相同完整公开历史及直接风险旁路，经验重加权未覆盖箱保留缺失质量。没有把更低模型残差当成任务收益，也没有反演工作模型。',
    '## 预定主标准及结果',main_comparisons,
    '严格按全部54个单元整数总损失比较，不用四舍五入后差值筛选；候选必须低于其余四个两阶段学习参考和全部12个固定程序。成功率不作隐藏筛选，完整披露。三折训练集重叠且旧来源已经用于研究开发，因此本表不提供名义显著性、置信区间或独立泛化主张。',
    f'必要条件虽满足，证据很弱：相对12固定程序中最低全人口均值的 `{best_fixed}`，候选总损失仅少{total(best_fixed)-total(cand)}步，即平均少{r["selectors"][best_fixed]["mean_loss"]-candidate["mean_loss"]:.6f}步。该固定程序是事后描述中的最小者，原主标准仍逐一比较全部12个；不将它替换为新的调参目标。九组中仅组4改善，四组变差、四组相同，正负抵消后只剩微小均值差。54/54不能作为独立成功率证据。',
    '## 全部学习程序',result_table(learn),'## 全部固定程序',result_table(fixed),
    '表内获取步数、执行步数是所选择**已有真实事实路径**的累计，不能算作本轮新增环境开销；原完整截止损失已经包含获取一次，不再重复加费。失败时损失500，实际交互步数仍按原记录；提前成功/获取结束保留在54分母。终止单元中的固定程序名称是分配标记，不表示结束后又执行动作。',
    '## 按来源组检查',group_table,concentration,
    '每组含三个任务×不变/变化共6单元。完整576个任务/条件/时点分格见 `all_task_condition_boundary_panels.csv`，每格3组，不按步当独立样本。没有筛除困难任务或只报告有利时点。',
    '## 预测能力与任务收益分别报告',forecast_table,
    '预测指标先在真实RETURN轨迹内对四个候选求均值，再组内汇总、九组均权。全部810个节点×版本位置逐项登记；有效RETURN134个/版本，其余28个按提前任务结束或获取结束保留缺失，绝不补零。预测的长度误差、各组指标及逐节点p/j/g/长度/未覆盖质量保存在 `forecast_diagnostics.json`。',
    '工作模型dXY=.01sentXY仍未资格化；残差包含噪声、控制瞬态、接触和尺度失配，不能视为物理无噪声误差。p=0的条件误差没有标签；经验未观测箱的0是带显式缺失质量的数值编码。风险输出是未裁剪排名分数，MSE不能当校准证据。有效数值、当前预测和完整任务收益是三个分别检验的判断。',
    '反证和未区分解释：JOINT的访问分布预测误差没有全面超过CONDITIONAL，成本MSE也高于DIRECT_MSE；其平均预测未覆盖历史质量约0.765，不能称模型在这些查询上已验证。候选的任务差异可能来自有限样本辅助正则、优化路径或来源组4的特殊结局；本轮没有匹配伪辅助目标/普通未来特征控制来区分这些解释，不能归因为“解决纠正后适用性”。',
    '## 所有失败与不利更新',
    f'1728次支持重放选择中，{len(failures)}行选择了原有失败事实叶子；{len(harm)}行完整损失高于同单元CONTINUE0.5。一个源失败可能被多个离线程序选择，这些行不是新的独立物理失败。全部选择、全部失败、全部不利选择分别见 `all_selections.csv`、`all_selected_failures.csv`、`all_harmful_choices.csv`；逐行包含来源案例哈希及同获取0.5对照。不能把接受/拒绝或有害分项当作机制因果效果。',
    '旧TRAIN物理来源648次执行共39个任务失败，全部原记录保留。此次科学管线没有自动重训、额外样本、挑选检查点或替换结果；依赖探测发现Torch未安装，冻结前选择NumPy实现，未安装/改变项目依赖。三轮数组开发检查均通过，重复检查不增加唯一测试数。',
    '## 独立复算与完整成本',
    f'科学拟合：15个风险/辅助网络×1000次全批SGD＝15000次更新，15个固定receiver绑定的前置RBF风险拟合；另15次独立数组反向微分重训＝15000次更新、15次lstsq独立复算。主训练耗时{fit["wall_ns"]/1e9:.3f}秒，独立模型审计{audit["wall_ns"]/1e9:.3f}秒，重放审计{replay["wall_ns"]/1e9:.3f}秒；全管线{io.read(base/"pipeline_control/completion.json")["wall_ns"]/1e9:.3f}秒，报告/作图时间另记。',
    f'独立模型审计核对{audit["scalar_fields"]}个数值字段、从原TRAIN事件重建{audit["literal_factual_target_fields"]}个标签字段，最大参数绝对差{audit["maximum_parameter_absolute_gap"]:.12g}≤预定5e−8，实际纠正选择完全一致。主网络/初始化/梯度/训练、特征和基底入口禁用后进行独立复算；两实现共享NumPy数值库，不能称独立机构/框架审计。',
    f'本轮新增24个数组检查通过，与哈希未变的2115个历史检查回执合计{test["unique_test_total"]}项唯一检查，另保留旧6组张量检查；未重跑旧物理测试。三次开发检查合计的合成训练开销为 `{json.dumps(synthetic,ensure_ascii=False)}`，与科学拟合分别登记。编译、依赖、全仓秘密扫描、索引字节补充扫描和普通/暂存差异检查见交付验证目录。',
    '本轮新环境创建/重置/控制步/物理帧、策略查询、机器人种子、响应或逆模型训练、底层策略训练、在线LLM API均为0。旧TRAIN来源成本另列：648次执行、77563控制步、33048次全部重置、16911815物理帧；不能用离线重放把来源物理采集称作免费。旧CAL/TEST没有用于本轮学习或评价；旧统计字节哈希保持不变。',
    '## 查新、限制与后续判断',
    '[SPO](https://arxiv.org/abs/1710.08005)已经研究决策导向的成本预测；[Successor Features](https://arxiv.org/abs/1606.05312)提供策略相关未来特征表示；[VaGraM](https://arxiv.org/abs/2204.01464)讨论预测误差与下游价值目标失配。因此“未来特征＋任务成本”本身不构成新颖性。本轮新增核对主要是官方摘要，未完成这些工作的全文复现；不把其理论保证转移到本系统。',
    '完整查新表见冻结决策文档，继续覆盖MDE、Residual RL、OCCAM、GAUGE、Poke and Strike、TOM及任务相关获取/停止路线。状态相关响应也可属于固定MDP，不能因此宣称超出既有未来特征方法。',
    ('本轮仅满足开发必要条件。建议先单独冻结区分真实纠正相关辅助信息与普通辅助正则的同权限消融；不在本结果上调整权重、步数或任务。当前组间集中和微小优势不足以支持大规模采集。机制区别成立后，仍须另行冻结真实状态耦合训练、校准及独立自身历史部署；不可直接宣布收益资格或追加采集。' if gate else '本轮关闭这一版JOINT_SPO辅助表示，不在该人口上调辅助权重、训练步数、阈值、任务或获取候选来挽救。保留所有负结果。下一研究协议需要一个更具体、可检验且优于标准决策学习的获取/采用机制；当前数据与结果不支持启动该候选的大规模新物理采集。'),
    '原DIRECT_C8和MOVE_INTEGRAL完整强对照不在此来源树的同入口叶子中；没有跨历史拼接它们的结局。本轮不能声称超过这两个原强基线。未来独立完整实验必须补齐它们、始终探测/不更新、标准变化检测、历史辨识、任务相关获取及同预算无LLM对照。',
    '还需训练/校准/最终评价分离、候选自身形成的真实时序历史、完整成本优势和消融。此次交付没有完成CCF A目标，也不提供安全或物理稳定保证。',
    '## 可追溯文件',
    f'- `manifest.json`：冻结源、输入哈希、零新增物理范围。\n- `bank.json` 与 `models/`：全部末步模型与训练摘要；`fixed_receiver_labels.json`保存前置目标绑定。\n- `fit_attempts.jsonl`、`model_audit.json`、`replay.jsonl`、`replay_audit.json`：全部尝试、独立复算和决策先于事实叶子读取的日志。\n- `results.json`、`forecast_diagnostics.json`、`selected_rows.json`：全量结果、缺失和预测；`development_decision.json`：固定标准结论。\n- `presentation/`：四个完整CSV和PNG/SVG图。所有原始大文件、失败及旧实际恢复副本继续保留。',
    '![开发结果与完整来源组](../'+(out/'figures_v2/learning_comparison.png').relative_to(ROOT).as_posix()+')']
report=ROOT/'reports/correction_transfer_learning_v1_zh.md';report.write_text('\n\n'.join(lines)+'\n',encoding='utf8',newline='\n')
io.write(out/'report_receipt.json',dict(integrity='PASSED',report=report.relative_to(ROOT).as_posix(),report_sha256=io.sha(report),
    result_sha256=io.sha(base/'results.json'),source_freeze_commit=manifest['source_git_commit'],decision_sha256=io.sha(base/'development_decision.json'),
    export_sha256={p.name:io.sha(p) for p in out.glob('*.csv')},all_selected_failure_rows=len(failures),all_harmful_rows=len(harm),
    wall_ns=perf_counter_ns()-start,new_physics=0,new_fits=0,online_LLM_API_calls=0))
print(dict(report=str(report),decision=decision['status'],candidate_mean_loss=candidate['mean_loss'],success=candidate['success']))

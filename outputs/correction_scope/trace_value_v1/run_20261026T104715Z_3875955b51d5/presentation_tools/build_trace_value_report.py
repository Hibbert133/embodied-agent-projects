from pathlib import Path
from time import perf_counter_ns
import csv,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import correction_trace_value_v1 as m
io=m.io

def table(headers,rows):return '\n'.join(['|'+'|'.join(headers)+'|','|'+'|'.join(['---']*len(headers))+'|']+['|'+'|'.join(map(str,r))+'|' for r in rows])+'\n'
def n(v):return f'{v:.6g}'

def build(path):
    path=Path(path).resolve();manifest=m.checked(path);base=path.parent;start=perf_counter_ns()
    result=io.read(base/'results.json');audit=io.read(base/'replay_audit.json');models=io.read(base/'model_audit.json');fit=io.read(base/'fit_receipt.json')
    choice=io.read(base/'posthoc_choice_diagnosis_v2/audit.json');assert choice['integrity']=='PASSED'
    assert audit['integrity']==models['integrity']=='PASSED' and audit['results_sha256']==io.sha(base/'results.json')
    assert io.read(base/'pipeline_control/completion.json')['status']=='COMPLETED'
    out=base/'presentation';out.mkdir(exist_ok=False)
    rows=result['results'];fields=list(rows[0])
    for name,data in (('all_offline_replays.csv',rows),('all_offline_failure_rows.csv',[r for r in rows if not r['success']])):
        with (out/name).open('x',encoding='utf-8-sig',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(data)
    source=ROOT/manifest['config']['source_A1_run'];cases=list(io.rows(source/'train/cases.jsonl.gz'));summary=io.read(source/'train/summary.json')
    case_fields=(*m.old.a.KEYS,'success','deadline_loss','total_steps','stop_reason','event_start_sequence','event_end_sequence_exclusive')
    with (out/'all_source_TRAIN_cases.csv').open('x',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=case_fields,extrasaction='ignore');writer.writeheader();writer.writerows(cases)
    selected={s['selector']:s for s in result['summaries']};relative=base.relative_to(ROOT).as_posix()
    fixture=[io.read(p) for p in (m.BASE/'development_checks').glob('attempt_*/tests.json')]
    synthetic_solves=sum(r['guard']['operation_counts']['solve_attempts'] for r in fixture);synthetic_lstsq=sum(r['guard']['operation_counts']['lstsq_attempts'] for r in fixture)
    text=['# 获取后额外轨迹：同接收者TRAIN交叉开发对照 v1',
        '\n**本轮全部结果是事后描述性开发分析。** 在已执行的同一获取返回处，固定同一个接收模型，只改变额外获取轨迹是否提供。'
        '新增环境交互/重置/控制步/物理帧/旧政策查询/机器人种子/在线LLM API与tokens均为0。不是新的机器人部署、信息论最优价值或CCF A成果。',
        '\n源码/协议/配置在 `'+manifest['source_git_commit']+'` 先提交冻结，再用既有TRAIN拟合6个标准风险模型并作6次独立复算。只解析TRAIN；'
        'CAL/TEST没有用于新训练、评价、阈值或模型选择。原A1的NOT_QUALIFIED及13项比较不变，旧M/D等价草案及5940次未执行预算保持关闭。',
        '\n## 重点对照：额外轨迹是否改变采用，以及是否改善完整任务\n',
        'FULL提供付费移动/测量期间的全部真实额外轨迹；MASK只屏蔽这一段。两者拥有完全相同的原任务前缀、真实返回观测、积分、已执行获取和已花费步数，'
        '使用同一个折内冻结接收模型。差值为FULL完整截止损失减MASK，负值表示该接收者利用额外轨迹后损失更低。\n',
        table(['核','FULL成功/54','MASK成功/54','FULL平均损失','MASK平均损失','FULL−MASK','速率选择变化/54','FULL不利/改善/相同'],[
            [c['kind'],str(c['FULL_success'])+'/54',str(c['MASK_success'])+'/54',n(selected['MOVE_FULL_'+c['kind']]['mean_loss']),n(selected['MOVE_MASK_'+c['kind']]['mean_loss']),n(c['mean_FULL_minus_MASK']),str(c['choice_changes'])+'/54',f"{c['FULL_harm_cases']}/{c['FULL_help_cases']}/{c['ties']}"] for c in result['FULL_MASK_contrasts']]),
        '\n必须把预测变化、采用选择变化和任务成本变化分别检查；预测MSE降低不能替代任务收益。正负差都保留，不据结果选核、删组、换阈值或追加样本。',
        '\n**本轮为负结果。** FULL额外轨迹使线性/核岭接收者的完整损失分别增加12.851852/25.537037步，成功数分别减少1/3。'
        '核岭FULL的平均归一化MSE为0.075593，低于MASK的0.082280，但完整任务表现更差。该固定接收者没有证明能够把这些信息转成更好的决策；'
        '这也不能排除有限样本、共享容量、表示或排序误差等解释，更不能证明所有接收者都无法利用额外轨迹。',
        '\n### 保存选择的补充核对（事后描述性）\n',
        '以下只读取已保存的预测和选择，不新查询、拟合或设置门限。对FULL与MASK选择不同速率的单元，在FULL预测中比较两个速率，'
        '再核对其两个真实来源叶的完整成本差。负预测差却得到正实际差，表示这次保存排序过于乐观；不是唯一物理原因或校准后的错误概率。'
        '每核54单元全部登记，11个提前终止单元没有预测，明确记为缺失。\n',
        table(['核','全部/可查询/终止缺失','选择变化','FULL乐观而实际不利','不利且预测数值平局'],[
            [c['kind'],f"{c['all_units']}/{c['live_pairs']}/{c['missing_terminal_pairs']}",c['changed'],c['FULL_optimistic_but_actually_harmful'],c['FULL_harm_predicted_tie_cases']] for c in choice['summaries']]),
        '\n[全部108组核配对，包括未变选择、改善、不利及缺失](../'+relative+'/posthoc_choice_diagnosis_v2/all_108_pairs.csv)。'
        '补充检查与原冻结主要对照分开，未据它挑选新模型、风险阈值或实验样本。第一次补充读表误把明文日志当gzip读取，'
        '在读表处失败；失败回执及修改前源码保留，修复后使用新输出目录，不涉及科学拟合、查询、交互或原始记录改写。',
        '\n## 全部9组，避免总体均值掩盖分歧\n',
        '组0/3/6为16步，1/4/7为32步，2/5/8为64步；每组含三任务×两条件。每次留出3组、训练另6组，三个折的训练集相互重叠。'
        '以下是组差的完整描述，不给未经重训/推导的独立置信区间或显著性宣称，也不把复制视图当新增独立样本。\n',
        table(['核',*[str(g) for g in range(9)]],[[c['kind'],*[n(c['group_differences'][str(g)]) for g in range(9)]] for c in result['FULL_MASK_contrasts']]),
        '\n![全部组对照](../'+relative+'/presentation/figures/FULL_MASK_groups.png)',
        '\n## 包含完整免费反馈的全部10参考\n',
        'CONTINUE_FULL保留原免费历史，VALIDATE8_FULL保留正常任务继续8步的全部反馈，不为消融削弱它们。两个固定0.5参考不拟合。'
        '成功时损失为来源执行的全部实际控制步，失败为500；移动、测量及失败费用已经计入一次。提前结束保留在54分母里，不创建假查询。\n',
        table(['选择器','成功/全部','平均完整损失'],[[s['selector'],str(s['success'])+'/'+str(s['units']),n(s['mean_loss'])] for s in result['summaries']]),
        '\n![全部完整程序参考](../'+relative+'/presentation/figures/all_selectors.png)',
        '\n## 所有任务、条件与干预时点\n',
        table(['核','任务','条件','时点','单元','FULL−MASK平均完整损失'],[
            [c['kind'],p['task'],p['context'],p['boundary'],p['units'],n(p['mean_difference'])] for c in result['FULL_MASK_contrasts'] for p in c['panels']]),
        '\n![全部任务条件时点](../'+relative+'/presentation/figures/all_panels.png)',
        '\n## 同获取下相对保留0.5的不利与改善\n',
        '这是保存的配对事实叶成本差，不是新的在线错误更新概率；不由单次差值推断长期期望或唯一原因。全部54单元包括未改变速率及提前结束。\n',
        table(['选择器','不利/改善/相同','平均差','不利步数和','最坏不利差','成功→失败','失败→成功'],[
            [s['selector'],f"{s['harm']}/{s['help']}/{s['ties']}",n(s['mean_same_acquisition_difference']),s['harm_steps'],s['worst_harm'],s['success_to_failure'],s['failure_to_success']] for s in result['summaries']]),
        '\n## 当前风险预测能力\n',
        '标签是完整损失/500，每节点对四速率的平方误差平均。各组/逐节点值全保留；终止节点按缺失登记，不填零。模型共享容量、有限数据和核归纳偏置均可能影响结果，'
        '本轮度量的是该固定接收者利用信息的效果，不能把零收益解释为额外轨迹完全不含信息或任何更好接收者也无法利用。\n',
        table(['选择器','活节点','终止缺失','节点平均归一化MSE'],[[v['selector'],v['live_nodes'],v['missing_terminal_nodes'],n(v['trajectory_mean_MSE'])] for v in result['prediction_metrics']]),
        '\n## 信息、物理状态和支持边界\n',
        'MASK仍有返回位置/物体状态代理、积分、花费时钟与完整原任务前缀；它不是“无信息”。本轮不是全部物理效应/信息效应的自然中介分解。'
        '受控变化发生在获取完成、采用速率之前；原获取控制器在两条件中始终使用完整观测执行同一原语，没有通过关闭传感器改变获取路径。',
        '\n每折、每核的FULL/MASK共用同一模型文件。MOVE视图复制各分原节点权重一半，组平衡后总权重等于原节点数，保留原正则强度。'
        '空额外轨迹输入必须相同；没有额外release标志让同一证据产生不同输出。缺失轨迹为None和显式可用性mask，不伪造零观测；时钟不退款。',
        '\n选择器只读合法公开查询与冻结模型，不能读组/折、种子、条件、真扰动、实际噪声、私有状态或未来结果。折号只用于实验分配模型，不是在线政策特征。'
        '查询/预测/选择持久化先于结果公开。每个已选速率都对应一个原本真实执行的来源叶；没有在旧记录上捏造混合控制或未执行轨迹。',
        '\n独立审计禁用主特征、查询、拟合、预测和汇总实现，重新从原TRAIN记录构建事实树、特征、权重、核矩阵、参数与全部选择/结果。'
        '共同物理状态/RNG/控制记忆另绑定原始完整审计，不能只靠公开观测相等推断全部隐藏状态充分。第二实现不是独立机构或新的物理复现。',
        '\n## 来源成本、拟合与检查\n',
        table(['来源执行','已有控制步','已有全部重置','已有物理帧'],[[summary['executions'],summary['control_steps'],summary['lifecycle']['counts']['reset_attempts'],summary['lifecycle']['counts']['simulation_frames_completed']]]),
        '\n以上648次TRAIN执行是复用数据，未再次发生。本轮540次是分支重放，不能标成540次新机器人执行；重复引用的来源步数不计为新交互。'
        '整个A1及其他历史费用/失败继续见[原报告](correction_scope_development_v1_zh.md)和[风险参考报告](correction_scope_risk_reference_v1_zh.md)。',
        '\n实际科学拟合6、独立lstsq复算6，均无新响应/逆模型或低层政策训练。训练含I/O墙钟'+n(fit['wall_ns']/1e9)+'秒，独立模型审计'+n(models['wall_ns']/1e9)+'秒；'
        '重放'+n(result['wall_ns']/1e9)+'秒，独立重放审计'+n(audit['wall_ns']/1e9)+'秒。代码/记录检查不是物理安全或任务资格保证。',
        '\n20项新数组/构造记录检查加2073项源码绑定复用检查，共2093项独特检查，旧六组张量检查另列；没有重复老仿真。合成检查的'+str(synthetic_solves)+'次solve和'+str(synthetic_lstsq)+'次lstsq单列，'
        '不冒作真实训练或新增样本。独立参数核对'+str(models['scalar_fields'])+'字段、重放核对'+str(audit['checked_fields'])+'字段，也不是新增测试数。',
        '\n## 全部失败和后续判断\n',
        '原TRAIN来源'+str(sum(not c['success'] for c in cases))+'个任务失败保留；本轮重放'+str(sum(not r['success'] for r in rows))+'个失败行可能重复引用同一实际叶，不能当新增独立失败。'
        '全部核、组、任务/条件/时点、模型/视图/选择与失败均保存。\n',
        '- [全部540重放](../'+relative+'/presentation/all_offline_replays.csv)\n'
        '- [全部失败行](../'+relative+'/presentation/all_offline_failure_rows.csv)\n'
        '- [全部648来源案例索引](../'+relative+'/presentation/all_source_TRAIN_cases.csv)\n'
        '- [完整结果/逐节点指标](../'+relative+'/results.json)\n'
        '- [独立模型审计](../'+relative+'/model_audit.json)\n'
        '- [独立重放审计](../'+relative+'/replay_audit.json)\n'
        '- [冻结协议](../docs/protocols/correction_trace_value_v1_zh.md)\n'
        '- [查新与决定边界](../docs/research/correction_trace_value_decision_v1_zh.md)',
        '\n明确后续判断：封存这一版共享线性/核岭接收者的负结果，不据旧人口叠加采用门控，也不以预测MSE改善作为新采集资格。'
        '下一步须先定义区别于标准任务风险/决策导向学习的可证伪机制，并说明它为何应改善采用后的完整任务；独立冻结后才能采集。'
        '任何新方案仍须超过完整免费反馈和其他强参考，并在新方法自身形成的独立时序历史验证；不能用CAL/TEST调参、选核、删任务、换接收者或扩样本使本轮通过。',
        '\n“信息剥离”“保留后续选择”“任务后悔风险”均已有近邻，本轮不作新算法主张。潜在方法仍需可证伪的具体区别、同权限标准VOI/两阶段风险/适用性组合、'
        'DIRECT_C8、积分、完整被动历史、始终获取/不更新、变化检测/历史辨识和任务相关获取等对照及消融。'
        '**新采集的机制与独立冻结协议尚缺，CCF A目标保持未完成。**\n']
    report=ROOT/'reports/correction_trace_value_v1_zh.md';assert not report.exists();report.write_text('\n'.join(text),encoding='utf8',newline='\n')
    io.write(out/'report_receipt.json',dict(integrity='PASSED',report_sha256=io.sha(report),script_sha256=io.sha(__file__),
        results_sha256=io.sha(base/'results.json'),model_audit_sha256=io.sha(base/'model_audit.json'),replay_audit_sha256=io.sha(base/'replay_audit.json'),
        source_failures=sum(not c['success'] for c in cases),offline_failure_rows=sum(not r['success'] for r in rows),new_physics=0,new_fits=0,online_LLM_API_calls=0,wall_ns=perf_counter_ns()-start))
    print(dict(report=str(report),FULL_MASK_contrasts=[{k:v for k,v in c.items() if k in ('kind','mean_FULL_minus_MASK','choice_changes')} for c in result['FULL_MASK_contrasts']]))

if __name__=='__main__':build(sys.argv[1])

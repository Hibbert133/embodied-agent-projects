from pathlib import Path
from time import perf_counter_ns
import csv,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import correction_program_support_v1 as m
io=m.io

def table(headers,rows):return '\n'.join(['|'+'|'.join(headers)+'|','|'+'|'.join(['---']*len(headers))+'|']+['|'+'|'.join(map(str,r))+'|' for r in rows])+'\n'
def num(x):return f'{x:.6g}'

def build(path):
    start=perf_counter_ns();path=Path(path).resolve();manifest=m.checked(path);base=path.parent
    result=io.read(base/'results.json');audit=io.read(base/'audit.json')
    assert audit['integrity']=='PASSED' and audit['results_sha256']==io.sha(base/'results.json')
    assert io.read(base/'pipeline_control/completion.json')['status']=='COMPLETED'
    out=base/'presentation';out.mkdir(exist_ok=False);units=result['units'];s=result['summary'];relative=base.relative_to(ROOT).as_posix()
    flat=[];case_rows=[]
    for row in units:
        flat.append(dict(cohort=row['unit'][0],group=row['unit'][1],task=row['unit'][2],context=row['unit'][3],boundary=row['boundary'],
            prefix_available=row['prefix_available'],return_availability=';'.join(row['return_availability']),
            **{name:row[name] for name in ('baseline_loss','B_minus_F','B_minus_P','F_minus_P','F_minus_H')},
            **{name+'_loss':v['loss'] for name,v in row['families'].items()},
            **{name+'_all_optimal_indices':';'.join(map(str,v['optimal_leaf_indices'])) for name,v in row['families'].items()}))
        for i,leaf in enumerate(row['leaves']):
            case_rows.append(dict(cohort=row['unit'][0],group=row['unit'][1],task=row['unit'][2],context=row['unit'][3],boundary=row['boundary'],
                source_leaf=i,source_case_key=io.json.dumps(leaf['source_case_key']),**{k:v for k,v in leaf.items() if k!='source_case_key'}))
    for name,rows in (('all_54_units.csv',flat),('all_648_source_cases.csv',case_rows),('all_source_failure_cases.csv',[r for r in case_rows if not r['success']]),
        ('all_144_program_pairs.csv',result['pairwise_programs']),('all_540_existing_selector_rows.csv',result['existing_selector_rows'])):
        with (out/name).open('x',encoding='utf-8-sig',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    prior_source=ROOT/manifest['config']['source_A1_run'];cost=io.read(prior_source/'train/summary.json')
    envrows=[[name,num(v['mean_loss']),str(v['minimum_successes'])+'–'+str(v['maximum_successes'])+'/54'] for name,v in s['families'].items()]
    positive=s['paid_better'];negative=s['paid_worse'];ties=s['paid_tie']
    beneficial=[r for r in units if r['F_minus_P']>0]
    decision=('全部54单元都没有付费叶降低免费家族事后最小的例子；关闭这一有限事实表的支持主张。' if positive==0 else
        '确有'+str(positive)+'个单元存在付费叶降低免费家族事后最小的例子，故不能把前轮接收者失败解释为所有付费候选都不可能有作用。'
        '这些例子由未来结果选出，尚未证明能在行动前识别；也不能据此挑有利任务或对旧人口增加门控。')
    text=['# A线完整事实程序支持审计 v1',
        '\n**全部新增分析为事后描述性。** 本轮不训练、选择或部署新方法；新增环境创建/重置/控制步/物理帧、原政策查询、机器人种子、模型拟合和在线LLM API均为0。',
        '\n实现、配置、预算与审计协议先在 `'+manifest['source_git_commit']+'` 冻结提交，之后才读取TRAIN计算这些统计。来源为全部9组54单元648个真实已执行程序，'
        '没有解析CAL/TEST数值，旧统计和原资格结论保持不变。原始大记录及恢复副本保留。',
        '\n## 这次回答的问题与主要数字\n',
        '对每个单元，B是固定CONTINUE/0.5；F0是四个CONTINUE叶的事后最小，F8是四个VALIDATE8叶的事后最小；'
        'F取这八个免费家族叶的最小，P取四个移动测量叶的最小，H取全部12叶的最小。所有并列最小索引均保存。'
        'VALIDATE8正常任务步骤实际收费，“免费”指没有额外移动测量；成功损失为全部实际步数，失败为500，获取费用已计一次。\n',
        table(['事后包络（不是部署策略）','平均完整损失','等损失最小叶成功数范围'],envrows),
        '\n固定B平均完整损失'+num(s['means']['baseline_loss'])+'步。P优于F／差于F／相同为 **'+str(positive)+'／'+str(negative)+'／'+str(ties)+'（全部54）**；'
        'F−P平均'+num(s['means']['F_minus_P'])+'步（正值表示付费事后最小较好）。加入付费候选后F−H平均'+num(s['means']['F_minus_H'])+'步。',
        '\n'+decision,
        '\n### 全部付费事后较好的案例（仍以54为总分母）\n',
        table(['组','任务','条件','时点','免费最小F','付费最小P','实现差F−P'],[
            [r['unit'][1],r['unit'][2],r['unit'][3],r['boundary'],r['families']['FREE']['loss'],r['families']['MOVE']['loss'],r['F_minus_P']] for r in beneficial]),
        '\n正向差集中在组0/4/6：16/415/2步，组4占全部433步正向差的415步。'
        '其中一个免费家族全部失败的案例贡献352步。该集中现象是事后描述，不能把同组两条件当独立复现；'
        '全部42个负向、8个平局和所有18格仍完整保留。',
        '\n## 全部12个固定程序\n',
        table(['程序','速率τ','成功/54','平均完整损失','实际来源步数','移动步数','测量/普通验证步数'],[
            [p['action'],p['rate'],str(p['success'])+'/54',num(p['mean_loss']),p['actual_source_steps'],p['movement_steps'],p['measurement_steps']] for p in result['programs']]),
        '\n![全部固定程序与全部任务条件时点](../'+relative+'/presentation/figures/factual_support.png)',
        '\n## 全部9组，组内单位等权\n',
        table(['组','单元','F均值','P均值','H均值','F−P','F−H','P优/差/同'],[
            [r['group'],r['summary']['units'],num(r['summary']['families']['FREE']['mean_loss']),num(r['summary']['families']['MOVE']['mean_loss']),
             num(r['summary']['families']['ALL']['mean_loss']),num(r['summary']['means']['F_minus_P']),num(r['summary']['means']['F_minus_H']),
             f"{r['summary']['paid_better']}/{r['summary']['paid_worse']}/{r['summary']['paid_tie']}"] for r in result['group_summaries']]),
        '\n## 全部三任务×两条件×三时点\n',
        table(['任务','条件','时点','单元','F−P','F−H','P优/差/同'],[
            [p['task'],p['context'],p['boundary'],p['summary']['units'],num(p['summary']['means']['F_minus_P']),num(p['summary']['means']['F_minus_H']),
             f"{p['summary']['paid_better']}/{p['summary']['paid_worse']}/{p['summary']['paid_tie']}"] for p in result['panels']]),
        '\n## 既有接收者的实现差距\n',
        '下表只读取前轮已审计保存的540行实际选择，不新查询或重放模型。同家族差为所选叶减同一获取家族的事后最小；'
        '全部家族差为所选叶减H。与F之差可以为负。均为单次实现描述，不是新模型的期望后悔值或可部署信息价值。\n',
        table(['既有选择器','成功/54','平均完整损失','同家族事后差','全部家族事后差','减免费包络F'],[
            [r['selector'],str(r['success'])+'/54',num(r['loss']),num(r['same_family_realized_gap']),num(r['all_family_realized_gap']),num(r['difference_to_free_envelope'])]
            for r in result['existing_selector_summaries']]),
        '\n## 提前结束、并列成功与全部失败\n',
        '有'+str(s['prefix_unavailable'])+'个入口提前结束；CONTINUE/VALIDATE8/MOVE不可用返回数分别为'+
        '/'.join(str(s['unavailable_returns'][a]) for a in m.A)+'。全部保留，没有用零损失或假输入补齐。'
        '一个成本最小集合若同时含成功500步与失败500罚损，不任意挑较好的成功标签；包络成功数以所有并列最小的下/上范围披露。'
        '原648个来源执行中'+str(sum(not r['success'] for r in case_rows))+'个任务失败全部登记。144个程序对（7776个单元配对）的正反差、平局及成功变化均保留。',
        '\n首次10项构造检查中5项因测试期待RuntimeError而实际使用的校验器抛ValueError记为错误；仅修正异常类型断言后10项全部通过。'
        '第一次失败、日志和8个源码快照保留，未采集真实新数据或调整科学公式。',
        '\n## 独立复算、成本与严格边界\n',
        '主实现从冻结事实图读表，第二实现从原始TRAIN cases/examples重建，禁用主读图、校验、包络、分组和汇总等函数，'
        '以整数/Fraction核对'+str(audit['checked_fields'])+'个字段。这些字段和7776个配对都不是新测试或新样本。'
        '10项新数组检查加2093项源码绑定复用检查，共2103项独特检查；旧六组张量另列，不重跑旧仿真。',
        '\n本轮分析含I/O墙钟'+num(result['wall_ns']/1e9)+'秒、独立审计'+num(audit['wall_ns']/1e9)+'秒；新科学拟合0、独立模型复拟合0。'
        '复用来源费用为'+str(cost['executions'])+'次执行、'+str(cost['control_steps'])+'控制步、'+str(cost['lifecycle']['counts']['reset_attempts'])+'全部重置、'+
        str(cost['lifecycle']['counts']['simulation_frames_completed'])+'物理帧；费用未再次发生。原完整A1及其他历史成本见旧报告。',
        '\n有限保存表内只选这些叶的选择器不可能低于H，这是代数事实。它不证明总体期望界，不证明信息可辨识，不证明观测历史充分，'
        '也不证明低H可被新方法实现。F也不是实际执行的自适应控制器。共同物理状态/RNG/积分依靠绑定的来源审计，不能仅靠公开观测相等。'
        'P与F的差同时包含真实获取位移、花费、控制状态与候选差，不能归因为纯信息作用。',
        '\n本表未包含同入口新DIRECT_C8/MOVE_INTEGRAL及更多验证动作的事实尾部，不能从其他政策历史借尾部填补。'
        '未来独立部署仍必须包括DIRECT_C8、积分补偿、完整免费历史、始终获取/不更新、标准变化检测/历史辨识、任务相关获取及SPO/CPC/MDE等适用的同权限强参考。',
        '\n## 后续判断\n',
        decision+' 下一阶段需先建立可以区别于普通SPO/两阶段Q、MDE/表现预测和风险控制的具体机制。'
        '真实短时采用候选再验证是尚未被此事实表执行的新动作，其结果不能由当前叶推造；若研究它，必须先冻结真正连续执行的采集、完整成本、'
        '强组合参考、训练/校准/最终独立自身历史和消融。不得用本次正差案例筛样或调整旧资格。',
        '\n本轮包络不自动触发新采集，也不救回FULL_RBF、旧ARX/SS、固定接收者或已关闭草案。'
        '论文贡献、独立任务收益及完整CCF A目标均仍未完成。\n',
        '- [全部54单元](../'+relative+'/presentation/all_54_units.csv)\n'
        '- [全部648来源与失败索引](../'+relative+'/presentation/all_648_source_cases.csv)\n'
        '- [全部来源失败](../'+relative+'/presentation/all_source_failure_cases.csv)\n'
        '- [全部144程序对](../'+relative+'/presentation/all_144_program_pairs.csv)\n'
        '- [既有540行的实现差距](../'+relative+'/presentation/all_540_existing_selector_rows.csv)\n'
        '- [完整结果](../'+relative+'/results.json)\n'
        '- [独立审计](../'+relative+'/audit.json)\n'
        '- [冻结协议](../docs/protocols/correction_program_support_v1_zh.md)\n'
        '- [技能筛选、查新与决定](../docs/research/correction_program_support_decision_v1_zh.md)\n']
    report=ROOT/'reports/correction_program_support_v1_zh.md';assert not report.exists();report.write_text('\n'.join(text),encoding='utf8',newline='\n')
    io.write(out/'report_receipt.json',dict(integrity='PASSED',script_sha256=io.sha(__file__),report_sha256=io.sha(report),
        results_sha256=io.sha(base/'results.json'),audit_sha256=io.sha(base/'audit.json'),new_physics=0,new_model_fits=0,
        online_LLM_API_calls=0,wall_ns=perf_counter_ns()-start))
    print(dict(report=str(report),paid_better=positive,paid_worse=negative,paid_tie=ties))

if __name__=='__main__':build(sys.argv[1])

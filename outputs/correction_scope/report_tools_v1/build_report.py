"""Chinese factual report from audited outputs; no model/parameter selection."""
from pathlib import Path
from time import perf_counter_ns
import csv,json,sys
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from src.analysis import correction_scope_io_v1 as a
io=a.io


def table(headers,rows):return '\n'.join(['|'+'|'.join(headers)+'|','|'+'|'.join(['---']*len(headers))+'|']+['|'+'|'.join(map(str,r))+'|' for r in rows])+'\n'
def number(v):return f'{v:.6g}'


def build(manifest):
    manifest=Path(manifest).resolve();m=a.checked(manifest);base=manifest.parent;start=perf_counter_ns()
    s=io.read(base/'results/statistics.json');audit=io.read(base/'results/statistics_audit.json');extra=io.read(base/'results/reported_summaries_audit.json')
    io.require(audit['integrity']==extra['integrity']=='PASSED','all statistics audits required')
    checks={}
    for c in a.COHORTS:
        checks[c]=dict(record=io.read(base/c.lower()/'audit.json'),
            state=io.read(a.BASE/'common_state_audit_v1'/f'{c.lower()}.json'),
            semantics=io.read(base/'supplemental_audit_v1'/f'{c.lower()}_semantic_controls.json'))
        io.require(all(v['integrity']=='PASSED' for v in checks[c].values()),'complete supplemental checks '+c)
    model_audit=io.read(base/'learning/model_audit.json');fit=io.read(base/'learning/fit_receipt.json')
    io.require(model_audit['integrity']=='PASSED','independent models required')
    out=base/'presentation';out.mkdir(exist_ok=False)
    all_cases=[]
    for c in a.COHORTS:all_cases.extend(io.rows(base/c.lower()/'cases.jsonl.gz'))
    fields=[*a.KEYS,'success','total_steps','deadline_loss','policy_queries','movement_steps','measurement_steps','stop_reason','event_start_sequence','event_end_sequence_exclusive']
    for name,rows in (('all_cases.csv',all_cases),('all_task_failures.csv',[r for r in all_cases if not r['success']])):
        with (out/name).open('x',encoding='utf-8-sig',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(rows)
    with (out/'all_prediction_metrics.csv').open('x',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(s['metrics'][0]));writer.writeheader();writer.writerows(s['metrics'])
    gate=s['component_gate'];passed=gate=='PASSED';total=audit['total_actual_costs'];relative=base.relative_to(ROOT).as_posix()
    better=sum(r['upper_strictly_below_zero'] for r in s['comparisons'])
    worse=sum(r['CI95'][0]>0 for r in s['comparisons'])
    unresolved=len(s['comparisons'])-better-worse
    text=['# 纠正后适用性变化：A1预测基础独立开发报告',
        '\n本轮结论：**'+('FULL_RBF通过冻结的A1组件门。' if passed else 'FULL_RBF未通过冻结的A1组件门。')+'** '
        '这是标准预测工具的检验；本轮没有让学习器选择实际控制，不能据此宣称完整获取算法、任务收益、新颖性或CCF A目标完成。',
        '\n用户已选择A。实现先在本地提交 `'+m['source_git_commit']+'` 冻结，再采集新TRAIN/CAL/TEST；'
        '旧ARX、SS、记忆清零与闭合DR草案保持原样，未重采旧人口或调旧资格参数。实验在线LLM API调用为**0**。',
        '\n## 三个不可替换的判断\n',
        table(['层次','本轮证据','边界'],[
            ['数值/时序合法','记录、字面PI、执行链、全部费用和共同状态核对通过','不是物理安全保证或唯一失配原因识别'],
            ['当前预测能力',gate+'；主要对象是移动前32步24箱频率及误差矩','不是完整状态分布、合格物理响应模型或可逆控制器'],
            ['完整任务收益','未检验新学习机制的部署收益','下表为预定事实程序，未执行最终获取/采用算法与完整强对照']]),
        '\n## 方法名字及执行含义\n',
        table(['名字','含义'],[
            ['CONTINUE','立即从当前状态继续；随后使用指定PI速率'],
            ['VALIDATE8','先正常继续原任务8步，再采用指定速率；不是一种新的物理探测'],
            ['MOVE_MEASURE','同一LOCAL_PID移动及实际测量，然后从真实后状态继续'],
            ['时间常数τ','只改变积分更新速度；较小通常更新更快，积分保留，底层政策固定'],
            ['PERSISTENCE','沿用最近8步的查询/误差统计'],
            ['COMMAND_RBF','用命令/响应历史摘要的核岭预测参考'],
            ['RATE_BLIND_RBF','另看当前公开观测、积分和预算，但不看候选速率'],
            ['FULL_LINEAR / FULL_RBF','相同完整入口特征的线性/核岭预测器；标准工具，不是新算法']]),
        '\n完整入口特征使用当前39维观测、控制积分/预算和最近8步固定摘要；接口虽保留完整真实历史，'
        '本版没有穷尽利用长历史。工作模型是明示的 `XY位移=.01×发送XY命令`，未获得物理预测资格、未用于求逆。'
        '误差包含噪声、瞬态、接触及模型条件错误，不能解释为物理无噪声误差。24箱只包含命令象限/幅值和公开手物距离代理。',
        '\n## 冻结主要比较：PRE、32步\n',
        '差值为FULL_RBF预测MSE减参考；负值表示本组件预测误差更低。95%区间按独立组、时点内整组重抽10,000次，'
        '不把相关时间步或程序当作独立样本。9个TEST组，每时点3组；这是探索规模，不宣称充分统计功效。\n',
        table(['误差族','参考','平均差','95%区间','上界<0'],[
            [r['family'],r['comparator'],number(r['mean']),'['+number(r['CI95'][0])+', '+number(r['CI95'][1])+']','是' if r['upper_strictly_below_zero'] else '否'] for r in s['comparisons']]),
        '\n全部13项及所有PRE分层有事实目标的要求均在采集前冻结。没有用POST、8步、次优模型或有利任务替代。'
        '访问频率MSE是频率单位；误差/加权矩MSE是按0.01m归一化后的统计预测误差，不能标作物理位移RMSE。'
        '边际乘积只是明确的矩分解参考，不是完整的纠正后重加权、MDE或OCCAM复现。',
        '\n本轮'+str(better)+'/'+str(len(s['comparisons']))+'项的组区间支持FULL_RBF误差更低，'+str(worse)+'项支持其误差更高，'
        +str(unresolved)+'项区间跨零。较好的结果仅出现在访问频率预测；工作模型误差大小及其在访问箱中的加权矩没有通过主要比较。'
        '这说明本版较丰富的公开输入和非线性工具没有形成稳定的预测优势，不能把“看见了候选速率”直接解释为模型适用性或获取收益。'
        '这些是各项冻结95%区间的描述，不另作多重比较后显著性或充分统计功效宣称。'
        '当前证据不能区分有限开发数据、特征/目标设计、估计误差和动力学条件各自造成多少损失；不据此确定唯一失败原因。',
        '\n![冻结主要比较](../'+relative+'/presentation/figures/primary_comparisons.png)',
        '\n## 独立TEST的全部事实程序\n',
        '每程序54个任务/条件单元。截止损失为成功时整段实际控制步数，失败为500；移动/验证/测量已在实际步数中计一次。'
        '这些程序使用各自实际到访的状态；没有推算未执行轨迹、按TEST挑选速率或跨旧人口比较优劣。\n',
        table(['获取','τ（秒）','成功/全部','平均截止损失'],[
            [r['action'],r['rate'],str(r['success'])+'/'+str(r['executions']),number(r['mean_deadline_loss'])] for r in s['complete_factual_program_results']]),
        '\n新方法对DIRECT_C8、MOVE_INTEGRAL、完整被动适应、始终获取/不更新、检测/历史辨识及任务相关获取等的独立优势仍未检验。'
        '本版没有完成这些方法的同人口对照，不能把组件参考称为完整强基线胜出。',
        '\n![全部事实程序](../'+relative+'/presentation/figures/all_factual_programs.png)',
        '\n## 固定速率改变的实际不利/改善案例\n',
        '同一单元、同一获取下，相对τ=0.5比较完整实际损失。全部单元保留；这是预定程序的配对描述，'
        '不是学习器的错误更新率，也不能据单次差值认定稳定期望或唯一原因。\n',
        table(['获取','τ','分母','损失增/减/同','平均损失差','成功→失败','失败→成功'],[
            [r['action'],r['rate'],r['denominator'],f"{r['harm']}/{r['help']}/{r['ties']}",number(r['mean_difference']),r['success_to_failure'],r['failure_to_success']] for r in s['fixed_rate_paired_harm_descriptive']]),
        '\n## 全部分层和未完成窗口\n',
        '以下分母是分配的逻辑预测位置；实际提前结束不补观测/标签、不填零。短尾部按真实长度归一化并保存长度比例。'
        'MSE仅对有事实目标的预测计算，不是全部执行的任务收益率。\n']
    panels={}
    for p in s['panels']:panels[(p['task'],p['context'],p['boundary'],p['stage'])]=p
    text.append(table(['任务','条件','时点','PRE有目标/全部','POST有目标/全部'],[
        [t,c,b,f"{panels[(t,c,b,'PRE')]['targets']}/{panels[(t,c,b,'PRE')]['allocated']}",f"{panels[(t,c,b,'POST')]['targets']}/{panels[(t,c,b,'POST')]['allocated']}"]
        for t in a.io.TASKS for c in ('UNCHANGED','CHANGED') for b in (16,32,64)]))
    text.append('\n![全部目标可用性](../'+relative+'/presentation/figures/all_availability.png)')
    empty=[p for p in s['panels'] if p['stage']=='PRE' and p['targets']==0]
    if empty:
        text.append('\n**覆盖门未通过**：'+ '；'.join(p['task']+'/'+p['context']+'/'+str(p['boundary'])+'步' for p in empty)+
            '没有事实预测对象。这是本版资格覆盖不足，不是把已成功任务算成失败，也不是预测误差的证据。'
            '冻结规则要求各层有目标，本次仍按该规则报告NOT_QUALIFIED，不删除空层使其通过。'
            '未来协议须在新数据前明确“当前仍有决策”与“任务已结束”的目标域；不能回改本轮门或用次优结果替代。')
    text+=['\n缺失原因总表：\n',table(['阶段/原因','数量'],list(s['availability'].items())),
        '\nCAL只形成各误差族90%经验误差半径，没有选模型或超参数；它不参与实际控制。全部覆盖率/半径/MSE保存在逐项指标CSV，'
        '不宣称时序交换性、概率安全保证或新自适应策略下的覆盖。',
        '\n## 实际成本和独立复算\n',
        table(['阶段','执行','控制步','全部仿真重置','物理仿真帧','实际政策查询','审计政策重放查询'],[
            [c,*[s['costs'][c][k] for k in ('executions','control_steps','all_resets','physical_frames','policy_queries','independent_policy_replay_queries')]] for c in a.COHORTS]),
        '\n总计 **'+str(total['executions'])+'次执行、'+str(total['control_steps'])+'控制步、'+str(total['all_resets'])+'全部重置、'+str(total['physical_frames'])+'物理仿真帧**。'
        '每执行1次受控初始重置与50次工厂重置；所有获取/停止均保留真实状态、RNG游标与时钟，没有中途重置/回退位移。',
        '\n墙钟耗时另列，包含各自I/O与审计实现开销；并行操作的墙钟时间不能相加冒充CPU核时。500步截止损失是仿真控制步目标，不是硬件实时延迟保证。\n',
        table(['阶段','采集墙钟秒','记录审计墙钟秒'],[[c,number(s['costs'][c]['collection_wall_ns']/1e9),number(s['costs'][c]['audit_wall_ns']/1e9)] for c in a.COHORTS]),
        '\n预测拟合墙钟'+number(fit['wall_ns']/1e9)+'秒，独立模型复算'+number(model_audit['wall_ns']/1e9)+'秒；'
        '组统计独立复算'+number(audit['wall_ns']/1e9)+'秒，补充报表核对'+number(extra['wall_ns']/1e9)+'秒。完整细分保存在各回执。',
        '\n实际拟合为'+str(fit['actual_forecast_fits'])+'个142输出预测模型；另有'+str(model_audit['independent_refits'])+'次独立增广最小二乘复算。'
        '新响应/逆模型训练、低层政策训练、实验在线LLM调用及API tokens均为0。合成测试解另计，不冒作真实训练或新样本。'
        '本版没有使用旧机器人记录训练；历史研究来源费用另保留在原报告。',
        '\n代码/记录审计通过不代表算法贡献。冻结验证23项新数组/保存记录检查加2022项源码绑定复用检查，共2045项独特检查；'
        '重复开发运行不再累计，旧六组张量检查另列。最初开发运行的接口归一化/语法失败日志保留。'
        '组统计主审计核对'+str(audit['scalar_fields'])+'个标量，补充报表审计核对'+str(extra['reported_fields'])+'个字段；这些不是新单元测试或独立样本。',
        '\n独立复算指第二实现，不是独立机构评审或独立物理重现。主记录重放共享不可变获取原语，字面PI/执行链另算。'
        '私有见证只能核对记录字节/相等，不能证明所有隐藏状态充分。补充核对覆盖所有组的共同状态与控制记忆，'
        '以及未知变化前公开入口相等；零步继续不会提前看到真实变化。',
        '\n## 失败、文件与来源\n',
        '全部'+str(sum(not r['success'] for r in all_cases))+'个实际任务失败及完整分母保留。原始事件/见证/案例gz、预测输入输出、速率计划与执行轨迹位于 `'+relative+'`。'
        '数据分片及实际恢复字节检查见本地结果交付索引；大原始文件与恢复副本保留，不按成败筛选。',
        '\n- [全部案例]('+('../'+relative+'/presentation/all_cases.csv')+')\n'
        '- [全部任务失败]('+('../'+relative+'/presentation/all_task_failures.csv')+')\n'
        '- [完整预测指标]('+('../'+relative+'/presentation/all_prediction_metrics.csv')+')\n'
        '- [冻结manifest]('+('../'+relative+'/manifest.json')+')\n'
        '- [主要统计]('+('../'+relative+'/results/statistics.json')+')\n'
        '- [独立统计审计]('+('../'+relative+'/results/statistics_audit.json')+')\n'
        '- [冻结协议](../docs/protocols/correction_scope_development_v1_zh.md)\n'
        '- [查新补充](../docs/research/correction_scope_prior_art_addendum_v1_zh.md)',
        '\n## 后续判断\n',
        ('本版仅获得这一有限预测组件的资格。下一步须先把具体获取/采用机制、完整费用、同权限强参考、消融与独立自身时序历史评价单独冻结；不能直接把本版核岭/联合矩当成新贡献。' if passed else
         '封存此版FULL_RBF预测器和负结果，不据TEST叠加门控、换次优模型为主方法、挑任务/速率或补样本。本版没有支持进入据此选择控制的新采集；这也不证明A方向或所有预测工具不可行。先形成新的可证伪机制与独立资格设计。'),
        '\nTOM、模型适用范围学习、GAUGE、Residual RL、OCCAM、Poke and Strike、DISaM/VoSI等近邻继续约束贡献主张。'
        '门控/混合/重加权/普通收益预测已存在；同权限组合参考若解释全部收益，应关闭该区别。'
        '**本次交付没有完成CCF A目标。**\n']
    report=ROOT/'reports/correction_scope_development_v1_zh.md';report.write_text('\n'.join(text),encoding='utf8',newline='\n')
    inputs={str(p.relative_to(ROOT)).replace('\\','/'):io.sha(p) for p in (manifest,base/'results/statistics.json',base/'results/statistics_audit.json',base/'results/reported_summaries_audit.json',base/'learning/model_audit.json',base/'learning/fit_receipt.json')}
    io.write(out/'report_build_receipt.json',dict(integrity='PASSED',report_sha256=io.sha(report),script_sha256=io.sha(__file__),input_sha256=inputs,
        wall_ns=perf_counter_ns()-start,all_cases=len(all_cases),all_task_failures=sum(not r['success'] for r in all_cases),new_physics=0,new_fits=0,online_LLM_API_calls=0))
    print(dict(report=str(report),component_gate=gate,actual_costs=total))


if __name__=='__main__':build(sys.argv[1])

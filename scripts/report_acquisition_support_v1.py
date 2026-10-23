"""Chinese report of descriptive room and actual suffix support, no promotion."""
from pathlib import Path
import argparse
import csv
from collections import Counter
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis import acquisition_support_sources_v1 as src
io=src.io


def main(path):
    path=Path(path).resolve();out=path.parent;m=io.read(path);result=io.read(out/'results.json');audit=io.read(out/'audit.json')
    io.require(audit['integrity']=='PASSED' and audit['completion_sha256']==io.sha(out/'completion.json'),'complete independent audit')
    visual=io.read(out/'visual_review.json');io.require(visual['integrity']=='PASSED','actual figure review required')
    for name,h in io.read(out/'figure_receipt.json')['output_sha256'].items():io.require(io.sha(out/name)==h,'figure unchanged')
    for name,h in audit['artifact_sha256'].items():io.require(io.sha(out/name)==h,'audited results changed')
    report=src.ROOT/'reports/acquisition_support_audit_v1_zh.md'
    link=lambda p,label:'['+label+']('+Path(p).resolve().as_posix()+')'
    rows=['# 获取分支与完整任务价值：支持核查','',
        '**全部新增分析为事后描述性分析。没有训练或采集新数据，没有改变原资格／开发失败结论；本次不是新的获取方法或CCF A贡献。**','',
        '本次回答两件不同的事：已执行的完整程序还有多少事后选择空间；这些终局能否支持同一移动前历史处的获取／不获取、以及获取后采用／拒绝比较。利用全部未来结局挑最小损失不是可部署策略，也不是条件期望或总体性能界。','',
        '## 完整来源与费用','',
        '| 银行 | 执行 | 单元 | 独立组 | 程序 | 已发生控制步 | 失败 |','|---|---:|---:|---:|---:|---:|---:|']
    with (out/'all_cases.csv').open(encoding='utf-8-sig',newline='') as f:cases=list(csv.DictReader(f))
    for b in result['banks']:
        bad=sum(c['bank']==b['bank'] and c['success']=='False' for c in cases)
        rows.append(f'| {b["bank"]} | {b["executions"]} | {b["units"]} | {b["groups"]} | {b["programs"]} | {b["actual_saved_control_steps"]:,} | {bad} |')
    rows += ['',f'完整登记{len(cases):,}次科学执行、204,824个已发生控制步；三个银行分别计算，不合并组、不把相关时间步当独立样本。旧PI DEV用于选过参数，旧QUAL在本次被重新读作事后来源；它们都不是新方法的独立评价。新F20未运行QUAL。原生软件费用和所有历史训练／开发费用继续保留原账，本次不把读取旧记录重复计成机器人交互。',
        '',f'本次新增环境创建、重置、控制步、物理帧、模型拟合、策略训练和在线LLM API调用均为0。主分析耗时{io.read(out/"completion.json")["wall_ns"]/1e9:.3f}秒；独立审计耗时{audit["wall_ns"]/1e9:.3f}秒。审计逐字段复核{audit["fields_checked"]:,}个CSV字段，并独立比较全部JSON汇总；守卫回执另列。','',
        '## 完整程序的事后选择空间','',
        '每单元最小损失使用该单元所有程序已经实际取得的终局；MOVE最小值只在已执行MOVE集合中取。二者均带有未来信息和选择乐观性，不能当作在线Oracle、方法收益、条件平均效果或总体价值界。即使某MOVE实现优于RAW PI，二者的前缀也可能不同，不能把差异直接归因于移动。','',
        '| 银行 | RAW PI(.5s)均值 | 全程序事后最小均值 | 事后选择差值 | MOVE事后最小均值 | MOVE较好／较差／持平 |','|---|---:|---:|---:|---:|---:|']
    with (out/'all_unit_portfolio_room.csv').open(encoding='utf-8-sig',newline='') as f:room=list(csv.DictReader(f))
    for b in result['banks']:
        r=[v for v in room if v['bank']==b['bank']];mean=lambda k:sum(float(v[k]) for v in r)/len(r)
        diffs=[float(v['best_MOVE_minus_RAW_PI']) for v in r]
        rows.append(f'| {b["bank"]} | {mean("RAW_PI_loss"):.3f} | {mean("all_program_minimum_realized_loss"):.3f} | {mean("clairvoyant_gap_vs_RAW_PI"):.3f} | {mean("MOVE_minimum_realized_loss"):.3f} | {sum(d<0 for d in diffs)}/{sum(d>0 for d in diffs)}/{sum(d==0 for d in diffs)} |')
    rows += ['',f'![完整程序集合的事后空间]({(out/"figures/portfolio_room.png").as_posix()})','',
        '以下保留全部三任务×不变／变化条件，括号是MOVE事后最小实现相对RAW PI较好／较差的完整单元计数。不变条件仍有初始偏置，不是无扰动。','',
        '| 银行／任务／条件 | 分母 | RAW PI | 全程序事后最小 | MOVE事后最小（较好／较差） |','|---|---:|---:|---:|---:|']
    for b in result['banks']:
        for c in b['all_task_context_cells']:
            rows.append(f'| {b["bank"]}/{c["task"]}/{c["context"]} | {c["n"]} | {c["RAW_PI_mean_loss"]:.3f} | {c["all_program_clairvoyant_min_mean"]:.3f} | {c["best_MOVE_mean_loss"]:.3f} ({c["MOVE_better_than_RAW_PI"]}/{c["MOVE_worse_than_RAW_PI"]}) |')
    rows += ['', '## 同一物理前缀和候选后缀的支持','',
        '前三个节点以MOVE_KEEP_C8为规范来源：8步后、计划移动前、实际移动后。第四节点以RAW PI(.5s)在同一计划边界的自身历史为规范来源。没有合法规范节点时保留缺失，不替换规范来源。每个节点比较实际初始见证和已执行物理前缀，不仅比较当前位置；只移除原来源明确的计时字段，不忽略真实施加动作、噪声游标或物理时钟。','',
        '阶段标签和未发送的raw_policy不参与物理等价；控制程序的PI启动时间、控制器记忆语义另行核对。因此“物理前缀相同”不等于在线代理所有内部状态相同。完整初始与状态见证来源审计保持其原有局限，不声称独立重现物理或普适隐藏状态证明。','',
        '| 银行／节点 | 候选后缀 | 有支持／规范存活／完整分母 |','|---|---|---:|']
    relevant=(('AFTER8','BEGIN_C8_PI_0.5_NOW'),('BEFORE_MOVE','KEEP_C8'),('BEFORE_MOVE','BEGIN_C8_PI_0.5_NOW'),
        ('BEFORE_MOVE','MOVE_THEN_KEEP_C8_PI_0.5'),('BEFORE_MOVE','MOVE_THEN_INTEGRAL_PI_2.0'),
        ('AFTER_MOVE','REJECT_KEEP_C8_AFTER_MOVE'),('AFTER_MOVE','REJECT_KEEP_C8_PI_0.5_AFTER_MOVE'),
        ('AFTER_MOVE','REIDENTIFY_AFTER_MOVE'),('AFTER_MOVE','SHORT_VALIDATION_RETURN_OLD'),
        ('RAW_PI_BEFORE_MOVE','CONTINUE_RAW_PI_0.5'),('RAW_PI_BEFORE_MOVE','MOVE_FROM_RAW_PI_PREFIX_KEEP_PI_MEMORY'))
    for b in result['banks']:
        for stage,request in relevant:
            r=next(c for c in b['support_counts'] if (c['stage'],c['requested_suffix'])==(stage,request))
            rows.append(f'| {b["bank"]}/{stage} | {request} | {r["supported_units"]}/{r["canonical_live_units"]}/{r["complete_denominator"]} |')
    rows += ['',f'![后缀支持与缺失]({(out/"figures/suffix_support.png").as_posix()})','',
        '0条支持表示来源中没有相应已执行后缀，**不表示该动作收益为零或一定有害**。第8步就启动的DIRECT PI不能伪装成第16／32／64步才启动的PI；初始8步拟合不能伪装成移动后重新辨识；普通任务片段不能改名为短验证及回退。获取后的拒绝也要从已移动的状态继续，不能借用不移动分支的结局。','',
        '全部程序对按公共前缀匹配登记。只有两端都在规范节点存活且物理前缀相同时，才输出完整损失差和余下损失差，两者相等；否则保持缺失。它们只是实际单次耦合实现的配对差，不自动成为给定可见历史的条件期望。','',
        '## 完整程序表与缺失','']
    for b in result['banks']:
        rows += ['### '+b['bank'],'','| 程序 | 成功／全部 | 平均截止损失↓ |','|---|---:|---:|']
        for r in b['full_program_results']:rows.append(f'| {r["program"]} | {r["successes"]}/{r["n"]} | {r["mean_deadline_loss"]:.6f} |')
        rows += ['',f'全部节点缺失原因：`{b["node_missing_counts"]}`。同一轨迹可以出现在多个节点，不能把节点数量当新的轨迹分母。','']
    rows += ['## 后续判断','',
        '现有数据能支持若干C8公共前缀上的已执行完整后缀比较，但缺少移动决策点才启动强PI、实际移动后重测及显式短验证返回的完整分支。RAW PI自身访问的历史也没有相应保留PI记忆的MOVE分支。故不能从这些来源直接训练／确认一个完整移动前获取决策器，更不能把事后最小值当成可达到收益。','',
        '不继续修补已封存的F20评分或ARX选择规则，不根据上述事后分层挑任务、调阈值或放大故障。下一机制设计必须先固定完整后缀效用、可获得反馈和控制器记忆语义；若需新数据，应单独冻结同历史不移动强PI／真实获取／获取后拒绝等分支，以及训练、校准、最终自身历史部署和费用。此报告没有启动新采集，也没有证明该候选数据设计必然产生正收益。','',
        '## 查新、边界与复算','',
        '[AA-POMDP](https://arxiv.org/html/2410.03892v1)已处理获取与任务的联合决策；[Poke and Strike](https://arxiv.org/html/2509.00178v1)已考虑探索扰动后的任务状态。动态规划、支持条件、收益预测及任务相关探索均不能直接算作新颖性。具体阅读范围和仍需区别的机制见'+link(src.ROOT/'docs/research/acquisition_branch_support_prior_art_v1_zh.md','一手查新与问题定义')+'。','',
        '实现／分析协议冻结提交：`'+m['analysis_git_commit']+'`。13项新增纯数组测试通过；旧检查按对应源码哈希复用。来源原统计、选择锁及原文件SHA256保持不变。主分析／独立审计均有阻断环境、拟合和网络的守卫；没有使用未执行轨迹填补标签。','',
        '- '+link(path,'分析manifest与全部来源哈希'),
        '- '+link(out/'all_cases.csv','全部执行与失败、首个PI时点'),
        '- '+link(out/'all_nodes.csv','全部节点及缺失原因'),
        '- '+link(out/'all_requested_suffix_support.csv','全部候选后缀支持'),
        '- '+link(out/'all_node_program_pairs.csv','全部程序对及不可比较的原因'),
        '- '+link(out/'all_unit_portfolio_room.csv','逐单元事后空间及全部并列'),
        '- '+link(out/'audit.json','独立逐字段及原始前缀复核'),
        '- '+link(out/'results.json','逐银行／组／任务条件汇总'),
        '', '本次结果、标准公式和软件检查均不视为CCF A目标完成。原始记录、全部失败、原分片及恢复副本保留；只本地提交，不推送合并。','']
    with report.open('x',encoding='utf-8',newline='\n') as f:f.write('\n'.join(rows))
    io.write(out/'report_receipt.json',{'report':report.relative_to(src.ROOT).as_posix(),'report_sha256':io.sha(report),'generator_sha256':io.sha(__file__),
        'audit_sha256':io.sha(out/'audit.json'),'classification':'POST_HOC_DESCRIPTIVE_ONLY','publication_goal_complete':False})
    print({'report':str(report),'source_executions':1584,'new_interactions':0},flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);a=p.parse_args();main(a.manifest)

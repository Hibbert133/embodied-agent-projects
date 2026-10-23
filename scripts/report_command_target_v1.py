"""Chinese descriptive report: retain all denominators and separate source priors."""
from collections import defaultdict
from math import fsum
from pathlib import Path
from time import perf_counter_ns
import argparse,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis import command_target_sources_v1 as source
io=source.io


def number(x):return '缺失' if x is None else f'{x:.6f}'


def mean_group(rows,key):
    groups=defaultdict(list)
    for r in rows:
        if r[key] is not None:groups[r['group']].append(r[key])
    return fsum(fsum(v)/len(v) for v in groups.values())/len(groups) if groups else None


def report(path):
    start=perf_counter_ns();m=source.checked(path);out=Path(path).parent;audit=io.read(out/'independent_audit.json')
    io.require(audit['integrity']=='PASSED','independent diagnostic audit required')
    for n,h in audit['artifact_sha256'].items():io.require(io.sha(out/n)==h,'report source artifact')
    traces=io.read(out/'trajectory_summaries.json');entries=io.read(out/'measurement_entries.json');tables=io.read(out/'grouped_tables.json')
    lines=['# 命令累计状态的零新增交互诊断（读取修复 v2）','',
        '**全部新增分析为事后描述性分析。** 完整遍历1,752次保存执行/152,128步，独立复算通过；新增环境、重置、控制步、物理帧、拟合及在线LLM API均为0。',
        '', '安装源码表明输入先累计到命令目标，再由物理系统产生手部响应。因而只有当前手部位置及短位移历史不能自动视为完整控制状态。公开发送命令可形成合法的名义累计摘要，但未知执行变换、噪声与裁剪使它不能直接等于实际控制目标；本轮没有训练或验证新的物理预测器。',
        '', '这支持把输入累计状态列为下一独立模型设计中需要检验的因素，不能认定它是既往模型失败的唯一原因，不能声称补上摘要会改善预测或任务。旧附近点联合响应/ARX/F20负结果与原资格门不变。',
        '', '## 来源与口径','',f"分析冻结 `{m['analysis_git_commit']}`；运行 `{m['experiment_run_id']}`；清单 `{m['manifest_id']}`。",'',
        '|来源|完整执行|保存步数|完整8步窗口|原任务结局口径|','|---|---:|---:|---:|---|']
    for label,_,_,n,steps in source.cohorts():
        part=[r for r in traces if r['cohort']==label];complete=sum(r['complete_measurement'] for r in part)
        outcome='仅名义测量采集，success=False不等于任务失败' if label=='OLD_NOMINAL_TRAIN' else f"成功{sum(r['source_success'] for r in part)}/{n}；失败{sum(not r['source_success'] for r in part)}"
        lines.append(f'|{label}|{n}|{steps}|{complete}|{outcome}|')
    lines+=['','旧selected_response只读全部TRAIN，没有读它的QUAL；最新研究的原生与QUAL均完整纳入。没有筛出成功窗口重训。逐轨迹CSV保留每项成功、停止原因、短/无窗口与完整分母。',
        '', '## 三个参考及解释限制','',
        'SENT使用公开环境先验(重置目标、边界、输入尺度)及过去发送命令，恒等变换、零执行噪声。APPLIED使用保存的实际动作；TRUE_ZERO_NOISE使用当前真参数和同一保存命令流去噪变换。后两者仅评估端。三者均逐步工作空间裁剪，严格保留float32输入尺度与float64目标加法。',
        '', '旧见证保存私有状态哈希，没有实际mocap值。因此APPLIED目标仍是条件于安装代码和重置先验的重建，不能称为旧运行私有状态的独立测量。安装方法只在数组替身上做过精确算术比对，没有新建环境。',
        '', '命令目标与手部观测可能有体/站点固定坐标差。下表同时列绝对坐标差及相对初始差的变化；二者都不是物理预测残差或唯一动态滞后。噪声/变换项只分解输入累计向量，不分解物理无噪声误差；范数不能相加。固定旧反馈命令的去噪重建不是新闭环轨迹。',
        '', '## 规范测量入口（先于探测数据）','',
        '最新获取仅用预定LOCAL_PID_KEEP作为规范入口，其他程序不合并增加样本。旧名义TRAIN每项只有一个登记入口。先轨迹后组求均值；缺失不填零。',
        '', '|来源|任务|条件|完整分配|有入口|完整窗口|APPLIED−手部坐标差mm|相对初始差变化mm|SENT−APPLIED mm|入口末步手部位移mm|',
        '|---|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for label,_,_,_,_ in source.cohorts():
        canonical=[r for r in traces if r['cohort']==label and (label=='OLD_NOMINAL_TRAIN' or r['program']=='LOCAL_PID_KEEP')]
        for task in ('push-v3','reach-v3','door-open-v3'):
            for context in sorted({r['context'] for r in canonical}):
                allocated=[r for r in canonical if r['task']==task and r['context']==context];ids={r['case_id'] for r in allocated}
                es=[r for r in entries if r['case_id'] in ids]
                vals=[mean_group(es,k) for k in ('applied_hand_gap_mm','applied_initial_gap_change_mm','sent_applied_difference_mm','last_hand_displacement_mm')]
                lines.append(f"|{label}|{task}|{context}|{len(allocated)}|{len(es)}|{sum(r['complete_measurement'] for r in allocated)}|"+'|'.join(number(x) for x in vals)+'|')
    lines+=['','以上入口是可用性条件下的描述，不能外推到缺失入口；完整分配分母并列保留。入口差值不能证明模型失效，也不能比较接受/拒绝分支为因果效果。',
        '', '## 全部程序的移动阶段','',
        '下表完整展示三任务×条件×原程序的移动汇总。无移动明确缺失；新旧来源不混合。完整抬升/抬升后四段、其它全部阶段和尾部在grouped_tables.csv及压缩逐轨迹阶段表中逐项给出，先轨迹后独立组汇总。相同MOVE前缀保留在各程序各自表内，没有合并成额外独立组。',
        '', '|来源|任务|条件|程序|有阶段/完整分配|有数据组/分配组|APPLIED−手部差mm|初始差变化mm|累计参考差mm|工作空间裁剪率|',
        '|---|---|---|---|---:|---:|---:|---:|---:|---:|']
    for r in tables:
        if (r['phase'],r['stage'],r['bin_lo'],r['bin_hi'])!=('REPOSITION','ALL',1,500):continue
        lines.append(f"|{r['cohort']}|{r['task']}|{r['context']}|{r['program']}|{r['available_trajectories']}/{r['allocated_trajectories']}|{r['available_groups']}/{r['allocated_groups']}|"+
            '|'.join(number(r[k]) for k in ('applied_hand_gap_mm','applied_initial_gap_change_mm','sent_applied_difference_mm','applied_workspace_clipped'))+'|')
    lines+=['','## 支持证据、反证与下一步','',
        '支持：累计输入变量在源码中真实存在；发送命令摘要可在严格公开接口内构造；源数组方法的精度和逐步裁剪测试通过。完整轨迹表给出何处存在非零坐标差、变换/噪声参考差及裁剪，不只展示有利任务。',
        '', '反证/无法区分：手部观测和短历史可能已经足够隐式估计部分累计状态，尚无新模型消融证明新增摘要有价值；非零差还可能涉及固定坐标、物理约束、接触和初始条件。旧记录缺少mocap数值、接触力/接触对，无法识别唯一原因；输入目标重建也没有提供物理响应误差、逆控制效果或含获取成本的任务收益。',
        '', '明确建议：先制定并冻结独立的输入状态模型训练与资格协议，先验证收集器的原生目标见证和在线/评估隔离，再采集新TRAIN/CAL/独立资格。不能复用旧QUAL调模型、把标准位置/历史回归再命名重跑，或立即进行限幅/获取选择。需对比不带累计摘要的同容量模型与强历史/物理基线，单列输入变换/噪声不确定性及所有获取失败；预测门通过后仍须独立验证纠正与完整任务费用。',
        '', '初始条件处理、输入状态摘要及物理先验本身不构成新颖性。后续潜在贡献仍是获取改变状态/适用性时的决策机制，须有强对照、消融及新方法自身形成的独立时序部署。CCF A目标未完成。',
        '', '## 审计、复算及费用','',
        '首次冻结9013187在完成全部旧TRAIN及一条原生轨迹后，遇到历史TASK/APPROACH阶段标签停止；75,744行部分派生记录、原清单及失败回执保留。v2只增加这两个原始阶段标签，不合并或更改它们；原算术、数据、分母、控制程序、资格门均不变。重新冻结后从同一完整来源重新分析，属于只读计算重跑，没有新增交互或替换原结果。', '',
        f"独立审计核对{audit['independently_checked_fields']:,}个字段，{audit['executions']:,}次执行/{audit['saved_steps']:,}步、{audit['phase_rows']:,}个阶段行和{audit['measurement_entries']:,}个入口。主诊断算术/归约在审计期间禁用；另写float32变换、逐轴累计及组统计。共用来源分组适配器这一限制明确披露。",'',
        f"分析{io.read(out/'completion.json')['wall_ns']/1e9:.6f}秒；独立审计{audit['wall_ns']/1e9:.6f}秒。新环境/重置/控制步/物理帧/拟合/在线LLM API全为0；历史费用不再次计作本轮交互。旧统计、模型、原始文件字节保持不变。",'',
        '复算：`scripts/analyze_command_target_v1.py --manifest <本轮manifest>`，随后`scripts/audit_command_target_v1.py --manifest <本轮manifest>`。写入采用排他模式；已完成目录不能覆盖，独立复现需核对冻结源码并写新协议目录。', '',
        f"结果目录：`{out.relative_to(source.ROOT).as_posix()}`。`manifest.json`含来源和安装代码SHA256；`trajectory_summaries.json`/`trajectories.csv`保留全部个案；`step_diagnostics.jsonl.gz`及`phase_summaries.jsonl.gz`可逐步复算；`measurement_entries.json`/CSV与`grouped_tables.json`/CSV保留全部分层和缺失。",'',
        '阅读边界：初始条件辨识论文摘要/引言、脉冲响应实验设计2.2–2.3及部分3节、机器人辨识综述摘要；见冻结协议中的原文链接。未复现其算法，不把LTI条件或摘要读取得到的启发称为本环境的保证。模型适用范围、Residual RL、OCCAM、GAUGE、Poke and Strike等既有比较保持。','']
    dest=source.ROOT/'reports/command_target_diagnostic_v2_zh.md';io.require(not dest.exists(),'new report path')
    dest.write_text('\n'.join(lines),encoding='utf-8')
    io.write(out/'report_receipt.json',{'integrity':'PASSED','report':dest.relative_to(source.ROOT).as_posix(),'report_sha256':io.sha(dest),
        'manifest_id':m['manifest_id'],'audit_sha256':io.sha(out/'independent_audit.json'),'wall_ns':perf_counter_ns()-start,
        'classification':'POST_HOC_DESCRIPTIVE_ONLY','new_environment_steps':0,'new_fits':0,'new_online_LLM_API_calls':0})
    return dest


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);v=p.parse_args();print(report(v.manifest),flush=True)

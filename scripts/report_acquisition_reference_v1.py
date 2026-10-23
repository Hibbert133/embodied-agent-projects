"""Chinese complete-phase report: standard action, correction and task costs separate."""
from pathlib import Path
from collections import Counter
import argparse,csv,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis import acquisition_reference_io_v1 as a
from src.probe.acquisition_reference_program_v1 import PROGRAMS
io=a.io
LABELS={'RAW_CONTINUE':'原始任务PI直接继续','DIRECT_C8':'初始C8直接执行','MOVE_INTEGRAL':'原C8移动积分补偿',
    'FIXED_PD_KEEP':'固定点PD，保留任务纠正','FIXED_PID_KEEP':'固定点PID，保留任务纠正','LOCAL_PD_KEEP':'附近点PD，保留任务纠正',
    'LOCAL_PID_KEEP':'附近点PID，保留任务纠正','LOCAL_PID_REFERENCE_RESET':'附近点PID参考纠正，清零任务积分',
    'LOCAL_PID_REFERENCE_CARRY':'附近点PID参考纠正，保留任务积分','LOCAL_PID_REFERENCE_RESET_NO_PROBE':'附近点PID参考纠正，清零积分且不探测'}


def main(path):
    path=path.resolve();m=a.checked(path);phases=[];stats=None
    for cohort in ('SOFTWARE_NATIVE','QUAL'):
        folder=path.parent/cohort.lower()
        if not (folder/'summary.json').exists():continue
        summary=io.read(folder/'summary.json');io.require(summary['status']=='COLLECTED_FOR_INDEPENDENT_AUDIT','partial phase requires explicit failure report, never smaller-population statistics')
        audit=io.read(folder/'audit.json');io.require(audit['integrity']=='PASSED' and audit['collection_completion_sha256']==io.sha(folder/'completion.json'),'independent phase audit')
        for n,h in audit['artifact_sha256'].items():io.require(io.sha(folder/n)==h,'audited phase changed '+n)
        phases.append((cohort,folder,summary,audit))
    io.require(bool(phases),'at least one audited phase')
    if (path.parent/'qual/statistics.json').exists():
        stats=io.read(path.parent/'qual/statistics.json');audit=io.read(path.parent/'qual/statistics_audit.json')
        io.require(audit['integrity']=='PASSED' and audit['source_statistics_sha256']==io.sha(path.parent/'qual/statistics.json'),'independent full-group statistics')
    lines=['# 标准获取控制与参考纠正：独立资格报告','',
        '**本轮验证标准动作与参考分支，不是新学习算法、物理参数辨识资格或CCF A贡献。数值合法、窗口取得、采用后的任务效果及完整获取收益分别评价。**','',
        f'冻结提交`{m["source_git_commit"]}`。两阶段分别分配60项原生软件案例、540项独立资格案例；只有原生契约通过才执行后者，不能用未执行或缺失数据补全门槛。','',
        '## 方法含义','']
    for p in PROGRAMS:lines.append('- `'+p+'`：'+LABELS[p]+'。')
    lines+=['',
        '四个移动控制使用已存在且参数不变的固定/附近目标与PD/PID实现。主参考分支RESET采用移动期间形成的有界偏移，任务积分显式清零；CARRY采用同一偏移并保留任务积分，属于固定次要比较，不得在RESET失败后替换。二者均不保证无扰切换或安全。','',
        '移动积分是移动已提供的信息，形成时间早于额外8步探测。NO_PROBE强对照在相同实际移动状态后直接采用参考，不再执行8步；其窗口记为未测量，不能计为测量失败。其他程序没有合格完整窗口时从当前状态保留原控制继续，不回滚或换基线。','',
        'DIRECT_C8/MOVE_INTEGRAL逐字调用原程序和旧初始重置模型；只有这些初始程序执行C4/C8推断。新参考不是M/b物理参数估计，SelectedAnchorWindow不进入ColdPrefix，新响应训练和在线LLM API均为0。','',
        '## 已完成阶段与完整费用','',
        '|阶段|实际/分配|控制步|全部重置|物理帧|初始C4/C8尝试|审计C4/C8复算|采集秒|审计秒|','|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    allcases=[];actual={k:0 for k in ('executions','control_steps','all_resets','physical_frames','C4_C8_attempts','audit_C4_C8_refits')}
    for cohort,folder,s,au in phases:
        c=s['lifecycle']['counts'];refits=au['costs'].get('independent_c4_c8_refits',0)
        lines.append(f'|{cohort}|{s["executions"]}/{s["allocated_executions"]}|{s["control_steps"]}|{c["reset_attempts"]}|{c["simulation_frames_attempted"]}|{s["c4_c8_fit_attempts"]}|{refits}|{s["wall_ns"]/1e9:.3f}|{au["wall_ns"]/1e9:.3f}|')
        actual['executions']+=s['executions'];actual['control_steps']+=s['control_steps'];actual['all_resets']+=c['reset_attempts'];actual['physical_frames']+=c['simulation_frames_attempted'];actual['C4_C8_attempts']+=s['c4_c8_fit_attempts'];actual['audit_C4_C8_refits']+=refits
        allcases.extend(s['rows'])
    lines+=['',f'实际总费用：`{actual}`。上限600次执行、300,000控制步、30,600全部重置、16,800,000物理帧；采集初始C4/C8最多240次，审计最多另复算240次。一次受控初始重置/执行，全部工厂目标生成计费。新响应模型/底层策略训练及在线LLM API均0；不能把初始推断和审计复算隐去或称全部拟合为0。','',
        '完整历史来源另外披露：C8名义来源480执行/3,840控制步/24,480全部重置/12,259,200帧；RAW PI参数选择DEV720执行/90,626步/36,720全部重置/18,813,130帧；旧局部获取资格72执行/5,939步/3,672全部重置/1,865,695帧。旧研究有共享/重叠名义来源，不按程序重复加为新交互；完整来源哈希与费用由交付回执绑定。','']
    for cohort,folder,s,au in phases:
        n=6 if cohort=='SOFTWARE_NATIVE' else 54
        lines += [f'## {cohort} 全部程序','',
            '|程序|成功/分配|平均截止损失|实际步|完整测量窗口|实际采用|','|---|---:|---:|---:|---:|---:|']
        for p in PROGRAMS:
            part=[r for r in s['rows'] if r['program']==p];window='未测量' if p in ('RAW_CONTINUE','DIRECT_C8','MOVE_INTEGRAL','LOCAL_PID_REFERENCE_RESET_NO_PROBE') else str(sum(r['complete_warm_window'] for r in part))
            lines.append(f'|{p}|{sum(r["success"] for r in part)}/{n}|{sum(r["deadline_loss"] for r in part)/n:.6f}|{sum(r["total_steps"] for r in part)}|{window}|{sum(r["reference_update_applied"] for r in part)}|')
        lines += ['',f'记录审计`{au["integrity"]}`；原生软件契约`{au["native_software_contract"]}`。原生人口不用于选择增益、方法或替代独立资格。','']
    if stats is not None:
        lines+=['## 预登记资格判据与整组比较','',
            f'获取可用性：**{stats["acquisition_status"]}**，检查`{stats["acquisition_checks"]}`。','',
            f'主参考采用分支：**{stats["reference_update_status"]}**，检查`{stats["reference_update_checks"]}`。','',
            '以上两个门分开，不把窗口取得当作模型预测正确，也不把同获取状态下的参考采用效果当成获取前整体净收益。完整540项的9个独立组、每介入层3组，按整组分层bootstrap10,000次；不把相关步或同组任务当独立样本。区间是固定来源模型和固定参数条件下的描述，非物理保证；所有区间未作多重比较校正。','',
            '|左减右|指标|平均差|组bootstrap95%区间|','|---|---|---:|---|']
        for c in stats['registered_contrasts']:lines.append(f'|{c["left"]} − {c["right"]}|{c["metric"]}|{c["mean_difference"]:+.6f}|[{c["group_bootstrap95"][0]:+.6f}, {c["group_bootstrap95"][1]:+.6f}]|')
        lines+=['','RESET减LOCAL_PID_KEEP是唯一预定主采用损失比较；CARRY和NO_PROBE为固定次要对照，没有结果后换主角。失败门槛不通过则保留负结果、不追加或微调本版本。即使分支门通过，最终新方法仍须在包含全部获取费用的独立自身历史上超过RAW PI、C8、积分、NO_PROBE等强参考。','',
            '## 资格人口全部任务×条件','',
            '|任务|条件|程序|成功/9|平均截止损失|完整窗口|实际采用|','|---|---|---|---:|---:|---:|']
        rows=next(s['rows'] for co,_,s,_ in phases if co=='QUAL')
        for t in io.TASKS:
            for c in ('UNCHANGED','CHANGED'):
                for p in PROGRAMS:
                    part=[r for r in rows if (r['task'],r['context'],r['program'])==(t,c,p)]
                    window='未测量' if p in ('RAW_CONTINUE','DIRECT_C8','MOVE_INTEGRAL','LOCAL_PID_REFERENCE_RESET_NO_PROBE') else str(sum(r['complete_warm_window'] for r in part))
                    lines.append(f'|{t}|{c}|{p}|{sum(r["success"] for r in part)}/9|{sum(r["deadline_loss"] for r in part)/9:.6f}|{window}|{sum(r["reference_update_applied"] for r in part)}|')
    else:lines+=['## 独立资格未完成','', '没有完整且通过两级审计的QUAL统计，不能作参考分支或获取能力资格结论；软件结果不替代。','']
    lines+=['## 全部分母和失败','',
        'all_cases.csv保留所有完成案例；失败任务、不完整测量、提前结束及采用/保留分别计数。接受与拒绝子集只作描述，不能比较为因果效果。软件错误/部分人口不进入统计，须单独保留失败记录，不能按小人口通过。','']
    for co,_,s,_ in phases:
        lines.append(f'- {co}：任务失败{sum(not r["success"] for r in s["rows"])}；获取结果计数`{dict(Counter(str(r["option_reason"]) for r in s["rows"]))}`；采用理由计数`{dict(Counter(r["reference_admission_reason"] for r in s["rows"]))}`。')
    lines+=['','## 后续与研究边界','',
        '所有程序都是既有控制器/固定脚本的标准参考，没有新价值模型、学出的获取策略、物理重辨识或安全证明。当前完整窗口仍需独立姿态/历史条件化响应资格，不能由类型名或几何通过认证。新算法还须建立获取改变实际状态、模型适用性和后继采用/拒绝时的具体机制，补齐标准变化检测/历史辨识/任务相关获取、独立自身历史和消融。','',
        '保留模型适用范围、Residual RL、OCCAM、GAUGE、Poke and Strike及后续查新。控制混合、积分记忆、局部目标、收益预测或标准DR本身均非新颖性；本轮标准基线或软件门不完成CCF A目标。全部失败、负结果、原始记录/分片和恢复副本保留，仅本地提交，不推送合并。','',
        f'冻结manifest与源码/模型来源哈希：`{path.as_posix()}`；各阶段原始事件、私有见证、账本及审计均在同运行目录。','']
    with (path.parent/'all_cases.csv').open('x',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(allcases[0]));w.writeheader();w.writerows(allcases)
    report=io.ROOT/'reports/acquisition_reference_qualification_v1_zh.md'
    with report.open('x',encoding='utf-8',newline='\n') as f:f.write('\n'.join(lines))
    io.write(path.parent/'report_receipt.json',{'report':report.relative_to(io.ROOT).as_posix(),'report_sha256':io.sha(report),'all_cases_csv_sha256':io.sha(path.parent/'all_cases.csv'),
        'completed_phases':[co for co,_,_,_ in phases],'actual_costs':actual,'generator_sha256':io.sha(__file__),'classification':'STANDARD_COMPONENT_ONLY','publication_goal_complete':False})
    print({'Chinese_report':str(report),'phases':[c for c,_,_,_ in phases]},flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);v=p.parse_args();main(v.manifest)

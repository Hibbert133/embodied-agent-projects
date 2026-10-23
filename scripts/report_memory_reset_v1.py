"""Chinese full-population standard-reference report; no simulation or fitting."""
from pathlib import Path
from time import perf_counter_ns
import argparse,csv,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis import memory_reset_io_v1 as a
io=a.io


def table(headers,rows):
    return '\n'.join(['|'+'|'.join(headers)+'|','|'+'|'.join(['---']*len(headers))+'|']+
                     ['|'+'|'.join(str(x) for x in row)+'|' for row in rows])+'\n'


def csv_file(path,rows):
    with path.open('x',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def report(path):
    start=perf_counter_ns();path=Path(path).resolve();m=a.checked(path);root=path.parent
    dest=root/'report_tables';dest.mkdir(exist_ok=False);native=io.read(root/'software_native/summary.json')
    native_audit=io.read(root/'software_native/audit.json') if (root/'software_native/audit.json').exists() else None
    text=['# 任务积分清零与获取收益：独立标准反机制资格 v1\n',
        '本轮检验是否存在比移动和新测量更廉价的任务积分操作。它是标准强对照资格，不是新学习算法或 CCF A 成果。旧 SS/ARX 负结果、旧人口与原比较不变；本轮零在线 LLM API 调用、零新响应/策略训练。\n',
        f"冻结提交：`{m['source_git_commit']}`；运行：`{m['experiment_run_id']}`；manifest：`{m['manifest_id']}`。\n",
        '## 方法含义与可识别范围\n',
        'RAW 是原固定策略外的任务 PI 纠正，积分会保存过去误差。RESET_I 只将该积分清零；NOOP 保存并消费一个恒等操作。LOCAL_PID 是真实移动到附近测量位置，KEEP 保留旧纠正/任务积分；REFERENCE 更新移动期间形成的参考偏置，RESET/CARRY 分别清零/保持任务积分。C8 与 MOVE_INTEGRAL 是原初始辨识、积分移动两个完整强参考。\n',
        '积分重置/保持是标准控制功能，[ROS 官方文档](https://control.ros.org/rolling/doc/api/classcontrol__toolbox_1_1Pid.html)已提供接口；不能声称新颖、无扰切换、稳定或安全。当前预测能力本轮没有新模型资格。任务表现只来自真实完整任务；记录回放不是额外仿真证据。\n',
        '## 原生软件契约\n',
        f"原生分配90，实际完成{native['executions']}；状态 `{native['status']}`；契约 `{None if native_audit is None else native_audit['native_software_contract']}`。所有早停、缺窗口、零积分操作和失败保留。\n"]
    if native_audit:text += ['独立审计成本/核对数：\n','```json\n'+json.dumps(native_audit['costs'],ensure_ascii=False,indent=2)+'\n```\n']
    data=[]
    for phase in ('software_native','qual'):
        if (root/phase/'summary.json').exists():
            for r in io.read(root/phase/'summary.json')['rows']:data.append(dict(**{k:m[k] for k in a.IDENTITY},phase=phase,**r))
    if data:csv_file(dest/'all_cases.csv',data)
    if not (root/'qual/statistics_audit.json').exists():
        text+=['## 尚未完成或停止\n','独立 QUAL 统计审计尚未完成，不能给出通过结论或由原生软件表现推断任务收益。所有已发生费用/部分记录保留。\n']
    else:
        stats=io.read(root/'qual/statistics.json');sa=io.read(root/'qual/statistics_audit.json')
        io.require(sa['integrity']=='PASSED' and sa['source_statistics_sha256']==io.sha(root/'qual/statistics.json'),'audited statistics')
        rows=io.read(root/'qual/summary.json')['rows'];programs=stats['program_summaries'];contrasts=stats['registered_contrasts']
        primary=contrasts[0];qualified=stats['primary_status']!='NOT_QUALIFIED'
        text+=['## 主要结果：完整54单元、9独立组\n',
            f"主要判断：`{stats['primary_status']}`。RAW_RESET_I−RAW_CONTINUE 平均截止损失差 **{primary['mean_difference']:+.6f}步**，95%整组区间 **[{primary['group_bootstrap95'][0]:+.6f}, {primary['group_bootstrap95'][1]:+.6f}]**。预定标准为区间上界严格小于零。成功率同时完整报告，未暗加成功率门槛。\n",
            table(['程序','成功/54','平均截止损失↓','实际控制步','移动步','测量步','实际记忆操作','非零积分改变'],
                [[v['program'],f"{v['successes']}/54",f"{v['mean_deadline_loss']:.6f}",v['actual_control_steps'],v['movement_steps'],v['probe_steps'],v['memory_transitions'],v['nonzero_integral_changes']] for v in programs]),
            '![全部程序表现](../'+(root/'figures/full_programs.png').relative_to(a.ROOT).as_posix()+')\n',
            '主要比较之外均是预定次要未校正区间，不用它们替换失败主角：\n',
            table(['左−右','平均损失差','整组95%区间'],[[v['left']+' − '+v['right'],f"{v['mean_difference']:+.6f}",f"[{v['group_bootstrap95'][0]:+.6f}, {v['group_bootstrap95'][1]:+.6f}]"] for v in contrasts]),
            '## 全部分层与完整失败\n',
            '以下180格保留全部程序×三任务×两条件×三个时点，每格3独立组。不按长度给轨迹或时间步加额外独立权重。\n',
            table(['程序','任务','条件','时点','成功/3','平均损失','记忆操作','完整窗口'],
                [[v['program'],v['task'],v['context'],v['planned_boundary'],f"{v['successes']}/3",f"{v['mean_deadline_loss']:.3f}",v['memory_transitions'],v['complete_windows']] for v in stats['full_assignment_panels']])]
        csv_file(dest/'all_180_panels.csv',[dict(**{k:m[k] for k in a.IDENTITY},**v) for v in stats['full_assignment_panels']])
        paired=[]
        for contrast in contrasts:
            left=[r for r in rows if r['program']==contrast['left']];right=[r for r in rows if r['program']==contrast['right']]
            for x,y in zip(left,right):
                io.require(all(x[k]==y[k] for k in ('group','task','context','seed','planned_boundary')),'actual paired units')
                paired.append(dict(**{k:m[k] for k in a.IDENTITY},left=x['program'],right=y['program'],**{k:x[k] for k in ('group','task','context','seed','planned_boundary')},
                    loss_difference=x['deadline_loss']-y['deadline_loss'],left_success=x['success'],right_success=y['success'],
                    success_to_failure=y['success'] and not x['success'],failure_to_success=x['success'] and not y['success']))
        csv_file(dest/'all_paired_cases.csv',paired)
        text+=['配对不利/改善是完整已执行程序的描述。按实际采用/拒绝或非零改变分项不能识别这些分支的因果效果。\n',
            table(['左−右','不利/相同/改善','成功→失败','失败→成功','不利总步数','改善总步数'],
                [[c['left']+' − '+c['right'],
                  '/'.join(str(sum((v['loss_difference']>0 if sign==1 else v['loss_difference']==0 if sign==0 else v['loss_difference']<0) for v in paired if (v['left'],v['right'])==(c['left'],c['right']))) for sign in (1,0,-1)),
                  sum(v['success_to_failure'] for v in paired if (v['left'],v['right'])==(c['left'],c['right'])),
                  sum(v['failure_to_success'] for v in paired if (v['left'],v['right'])==(c['left'],c['right'])),
                  sum(max(0,v['loss_difference']) for v in paired if (v['left'],v['right'])==(c['left'],c['right'])),
                  sum(max(0,-v['loss_difference']) for v in paired if (v['left'],v['right'])==(c['left'],c['right']))] for c in contrasts])]
        failures=[r for r in data if not r['success']]
        text += [f"原生与QUAL合计 **{len(failures)}个任务失败**，全部列出（失败损失均500）；早成功与未执行操作仍在原分母。\n",
            table(['阶段','组','任务','条件','时点','程序','实际步','窗口','记忆操作/原因','停止原因'],
                [[r['phase'],r['group'],r['task'],r['context'],r['planned_boundary'],r['program'],r['total_steps'],r['complete_warm_window'],str(r['memory_transition_applied'])+'/'+r['memory_transition_reason'],r['stop_reason']] for r in failures])]
        if failures:csv_file(dest/'all_task_failures.csv',failures)
        reasons=[]
        from collections import Counter
        for name in ('RAW_NOOP','RAW_RESET_I','LOCAL_PID_RESET_I'):
            for reason,count in sorted(Counter(r['memory_transition_reason'] for r in rows if r['program']==name).items()):reasons.append([name,reason,count])
        text += ['未操作与缺失原因按全部分配登记：\n',table(['程序','原因','例数'],reasons),
            '## 判断与后续边界\n',
            ('本次支持的仅是这个固定时点标准积分清零参考；它必须成为后续学习机制的廉价强比较。不能将其重命名为新学习/安全算法。\n' if qualified else
             '本次未证明这个固定时点标准积分清零能改善完整损失。封存此版本及负结果，不在该QUAL上调时点、阈值或叠加门控。次要分支即使更好也不替代主比较。\n'),
            '同移动后的清零/参考差仅针对这些已分配完整程序；零移动差与同移动差不能相加成未执行混合策略的收益。输入合法、实际预测能力与任务效果依然独立。此人口不是学习方法自身形成的最终时序历史，不能证明可学习的获取/停止决策。\n',
            '继续研究须单独定义可训练的完整程序表现与获取后实际采用机制，分开TRAIN/CAL/最终自身历史；完整费用下超过RAW PI、零移动标准参考、DIRECT_C8和积分，补齐变化检测/历史辨识/任务相关获取及状态改变/证据/后继/费用消融。仅换回归器、增加采集或数学恒等式不足以构成贡献；CCF A目标未完成。\n']
    text+=['## 全部实际费用、来源与限制\n']
    costs=[]
    for phase in ('software_native','qual'):
        if not (root/phase/'summary.json').exists():continue
        summary=io.read(root/phase/'summary.json');ledger=summary['lifecycle']['counts'];audit=io.read(root/phase/'audit.json') if (root/phase/'audit.json').exists() else {}
        costs.append([phase,summary['executions'],summary['control_steps'],ledger.get('reset_attempts',0),ledger.get('simulation_frames_completed',0),summary['c4_c8_fit_attempts'],audit.get('costs',{}).get('independent_c4_c8_refits',0),f"{summary['wall_ns']/1e9:.3f}",f"{audit.get('wall_ns',0)/1e9:.3f}"])
    text += [table(['阶段','执行','控制步','全部重置','物理帧','实际C4/C8拟合','审计额外复算','收集秒','审计秒'],costs),
        '上限为630执行/315,000控制步/32,130全部重置/17,640,000帧。每例50次工厂重置加一次受控初始重置；工厂与控制帧全部计费。移动、探测、失败罚已经进入一次完整截止损失。审计的额外固定策略查询和优化nfev见各阶段audit.json，均不产生新物理帧。来源费用另列，不把复算说成新响应训练，也不把它藏为零拟合。\n',
        '历史C8名义：480执行/3,840步/24,480全部重置/12,259,200帧；RAW PI选择DEV：720执行/90,626步/36,720全部重置/18,813,130帧；旧局部获取资格：72执行/5,939步/3,672全部重置/1,865,695帧。旧完整参考资格和诊断是已有研究背景，完整费用见各旧中文报告；不能再作为本轮新独立样本或重复按程序摊销。\n',
        '冻结模型哈希：`'+io.C8_SHA+'`。manifest记录全部源码、模型、配置、协议与运行时锁，seed_scope记录嵌套种子扫描来源。原始记录、全部失败/负结果保留；大文件若分片，索引与实际恢复另记。\n',
        '记录审计共享完整程序解释器进行保存观测重放，同时独立复算PI/PID/清零映射并核对世界见证；统计审计独立整数/Fraction公式且禁用主统计。重放不等于完全独立软件实现，也不把公共见证投影视为物理安全证明。9组样本有限、区间条件于固定来源模型，所有次要区间未多重校正。\n',
        '开发29项首轮有1个序列化形式断言失败，按journal规范表示修正后重新验证；保留首轮日志，不修改控制/统计方法或旧结果。源重用1921唯一检查与旧六组tensor分开，本轮新29项不能把参数组合/回放字段数算成额外测试或独立样本。\n']
    target=a.ROOT/'reports/memory_reset_qualification_v1_zh.md'
    with target.open('x',encoding='utf-8',newline='\n') as f:f.write('\n'.join(text))
    io.write(root/'report_receipt.json',dict(**{k:m[k] for k in a.IDENTITY},integrity='GENERATED',report_sha256=io.sha(target),
        artifacts_sha256={p.relative_to(a.ROOT).as_posix():io.sha(p) for p in dest.iterdir()},
        wall_ns=perf_counter_ns()-start,new_environment_steps=0,new_model_fits=0,new_online_LLM_API_calls=0))
    return target


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);v=p.parse_args()
    from scripts.analyze_acquisition_support_v1 import guarded
    result,guard=guarded(lambda:report(v.manifest));io.write(v.manifest.parent/'report_guard.json',guard);print(result)

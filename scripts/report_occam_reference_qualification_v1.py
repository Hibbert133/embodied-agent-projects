"""Complete Chinese qualification report; technical partials remain explicit nulls."""
from pathlib import Path
from time import perf_counter_ns
import argparse,csv,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis import occam_reference_qualification_io_v1 as a
io=a.io


def csv_file(path,rows,keys):
    with path.open('x',encoding='utf8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=keys);writer.writeheader();writer.writerows({k:r.get(k) for k in keys} for r in rows)


def report(manifest):
    started=perf_counter_ns();path=Path(manifest).resolve()
    io.require(path.name=='manifest.json' and path.parent.parent==a.OUTPUT.resolve(),'owned readable qualification manifest')
    m=io.read(path);copy=dict(m);mid=copy.pop('manifest_id');io.require(io.digest(copy)==mid and m['config']==a.config(),'immutable readable manifest')
    for name,h in {**m['source_sha256'],**m['input_sha256']}.items():io.require(io.sha(a.ROOT/name)==h,'frozen report sources '+name)
    out=path.parent/'report_v1';out.mkdir(exist_ok=False);rows=[];costs=[];sources={path.relative_to(a.ROOT).as_posix():io.sha(path)}
    for phase in a.PHASES:
        folder=path.parent/phase.lower();summary=io.read(folder/'summary.json') if (folder/'summary.json').is_file() else None
        by={r['case_index']:r for r in summary['outcomes']} if summary else {}
        for index,spec in enumerate(a.population(phase),1):
            outcome=by.get(index);metrics=outcome.get('task_metrics') if outcome else None
            rows.append({**spec,'case_index':index,'status':'PHASE_NOT_OPENED' if outcome is None else outcome['status'],
                'success':None if metrics is None else metrics['success'],'deadline_loss':None if metrics is None else metrics['deadline_loss'],
                'total_steps':None if metrics is None else metrics['total_steps']})
        if summary:
            costs.append(dict(phase=phase,allocated=summary['allocated_executions'],complete=summary['executions'],
                actual_control_steps_from_completed_cases=summary['control_steps'],complete_case_ledger=summary['lifecycle'],
                partial_and_unknown_cost_accounting=summary['cost_accounting'],collection_active_wall_ns=summary['wall_ns']))
            for name in ('summary.json','completion.json','process_audit.json','audit.json'):
                p=folder/name
                if p.is_file():sources[p.relative_to(a.ROOT).as_posix()]=io.sha(p)
    csv_file(out/'all_1740_allocated_cases.csv',rows,(*a.KEYS,'case_index','status','success','deadline_loss','total_steps'))
    failures=[r for r in rows if r['status']=='COMPLETE' and not r['success']]
    unresolved=[r for r in rows if r['status']!='COMPLETE']
    csv_file(out/'all_complete_task_failures.csv',failures,(*a.KEYS,'case_index','status','success','deadline_loss','total_steps'))
    csv_file(out/'all_unresolved_or_unstarted_cases.csv',unresolved,(*a.KEYS,'case_index','status','success','deadline_loss','total_steps'))
    io.write(out/'all_costs.json',dict(phases=costs,new_online_LLM_API_calls=0,
        prior_new_training_data=dict(executions=684,control_steps=85789,all_resets=34884,physical_frames=17870945,AdamW_updates=9000,training_solves=66712,mathematical_audit_solves=918),
        closed_v2_source=dict(control_steps=27982,all_resets=11475,physical_frames=5877410),
        older_C8_and_design_sources_separate_and_not_charged_once_per_program=True,unknown_costs_are_not_zero=True))
    stats_path=path.parent/'statistics_v1/statistics.json';audit_path=path.parent/'statistics_v1/independent_audit.json'
    complete=not unresolved and stats_path.is_file() and audit_path.is_file()
    statistics=None;table='尚无完整独立QUAL统计，不能从已完成前缀中比较或晋级。';comparisons='未计算。';prediction='未计算。'
    if complete:
        statistics=io.read(stats_path);independent=io.read(audit_path)
        io.require(statistics['integrity']==independent['integrity']=='PASSED' and independent['source_statistics_sha256']==io.sha(stats_path),'independent statistics before report claims')
        sources[stats_path.relative_to(a.ROOT).as_posix()]=io.sha(stats_path);sources[audit_path.relative_to(a.ROOT).as_posix()]=io.sha(audit_path)
        csv_file(out/'all_29_programs.csv',statistics['programs'],tuple(statistics['programs'][0]))
        csv_file(out/'all_1566_qualified_cases.csv',io.read(path.parent/'qual/audit.json')['panels'],tuple(io.read(path.parent/'qual/audit.json')['panels'][0]))
        panels=io.read(path.parent/'qual/audit.json')['panels'];cells=[]
        for program in a.PROGRAMS:
            for task in io.TASKS:
                for context in ('UNCHANGED','CHANGED'):
                    for boundary in (16,32,64):
                        group=[r for r in panels if (r['program'],r['task'],r['context'],r['planned_boundary'])==(program,task,context,boundary)]
                        observed=[r for r in group if r['mse'] is not None]
                        io.require(len(group)==3,'each task/condition/time cell retains all groups')
                        cells.append(dict(program=program,task=task,context=context,boundary=boundary,executions=3,
                            success=sum(r['success'] for r in group),mean_loss=sum(r['deadline_loss'] for r in group)/3,
                            prediction_available=len(observed),mean_MSE=None if not observed else sum(r['mse'] for r in observed)/len(observed)))
        csv_file(out/'all_522_task_condition_boundary_cells.csv',cells,tuple(cells[0]))
        table='|完整程序|成功／全部|平均截止损失↓|实际控制步|递归更新|有预测轨迹|\n|---|---:|---:|---:|---:|---:|\n'+'\n'.join(
            '|'+r['program']+'|'+str(r['success'])+'/54|'+format(r['mean_deadline_loss'],'.3f')+'|'+str(r['actual_steps'])+'|'+str(r['filter_updates'])+'|'+str(r['prediction_available'])+'|' for r in statistics['programs'])
        comparisons='|META_ADAPT__CONTINUE减参考|平均损失差|95%区间|\n|---|---:|---|\n'+'\n'.join('|'+r['right']+'|'+format(r['mean_loss_difference'],'.3f')+'|['+','.join(format(x,'.3f') for x in r['CI95'])+']|' for r in statistics['primary'])
        pred=statistics['prediction'];prediction='主程序有预测轨迹'+str(pred['available_trajectories'])+'/54；固定门判定'+str(pred['qualified'])+'。\n\n|任务|有预测／分配|同事实窗口MSE差|\n|---|---:|---:|\n'+'\n'.join(
            '|'+task+'|'+str(v['available'])+'/18|'+('缺失' if v['mean_MSE_difference'] is None else format(v['mean_MSE_difference'],'.6g'))+'|' for task,v in pred['task_points'].items())
        prediction+='\n\n整组条件区间：'+str(pred['CI95'])+'；无标签重采样数'+str(pred['unavailable_bootstrap_draws'])+'，没有替换重抽。'
        csv_file(out/'all_primary_comparisons.csv',statistics['primary'],tuple(statistics['primary'][0]))
        csv_file(out/'all_adaptation_and_meta_ablations.csv',statistics['secondary'],tuple(statistics['secondary'][0]))
    numerical=all((path.parent/p.lower()/'audit.json').is_file() and io.read(path.parent/p.lower()/'audit.json')['integrity']=='PASSED' for p in a.PHASES)
    note=f'''# 固定表现参考：独立预测与自身历史部署资格 v1

来源提交{m['source_git_commit']}，manifest {m['manifest_id']}。
完整性：{'完整NATIVE174及QUAL1566' if complete else '尚未完整；所有未执行／技术未决指标保留null'}。
数值／执行资格{numerical}，前瞻预测资格{False if statistics is None else statistics['prediction']['qualified']}，
完整截止损失资格{False if statistics is None else statistics['task_qualified']}；三者分别判断。
这是一项标准表现参考资格，不是A的新获取方法、完整OCCAM复现或CCF A贡献。

## 全部程序及失败

{table}

PI_0125／0500／2000／8000分别是0.125／0.5／2／8秒PI时间常数，四者全部
保留；META是已做适应元训练的bank，ERM是匹配普通回归训练的bank。
ADAPT只在真实完整窗口后更新线性权重，FROZEN保留参数并观察同样事实。
后缀CONTINUE直接继续、VALIDATE8继续原任务8步、MOVE_MEASURE实际移动后
测量8步。它们是预定完整程序，当前模型只选尾部PI增益，不选择是否获取。
DIRECT_C8和MOVE_INTEGRAL保留原初始C4/C8估计及原控制／积分移动行为。

全部1740项分配、{len(failures)}个完整任务失败、{len(unresolved)}个未决／未执行
分别在完整CSV中；NATIVE不并入QUAL的54单元分母。技术未决不填500或0；
原程序无效辨识后的完整停止按原规则记截止损失500，实际交互仍按已发生计。
三任务／两条件／三时点及全部获取／控制程序不筛选，不追加或挑冠军。

## 十个预定主比较与固定消融

{comparisons}

资格要求十个主差的整组95%区间上界全部严格小于0。9个独立组，时点
分层各3组，组内任务／条件／程序相关性保留；10000次整组bootstrap，
整数损失的Fraction分位数独立复算。不把1566程序执行或时间步当独立组。
成功变化完整披露，不以成功数替换主截止损失标准。固定元训练／适应
消融全部交付，次要区间未多重校正；九组不称充分功效。

## 真实前瞻预测、缺失及方差

{prediction}

每个标签只对应已保存预测后实际执行的窗口。先在轨迹内平均，再按组
组织，缺失保留原因及原分配。比较常数预测时使用同一事实窗口，不能
由当前误差推断未执行增益排序或获取收益。各程序访问状态不同，跨程序
MSE差本身不能作适应分支的因果效果。latent、加R观测及加Q创新方差各
自登记，不看覆盖率挑口径；beta固定0，没有概率校准或安全保证。

## 原始链路、独立性与完整费用

查询／选择／命令先保存再执行，反馈后才更新；任务内没有reset撤销移动，
环境、噪声、RNG和物理钟连续。双审计核对全部进程和原始字节、实际动作
及float32执行器顺序、完整原生／Python见证、共同前缀与获取后状态。
重放共享原actor／政策和严格特征提取，明确披露；另做标量费用／PI／
C8命令、独立dense前向、标量及最终批后验，禁用主模型计算与选择函数。
审计无物理重仿真，原始记录、部分失败、分片及恢复副本保留。

实际账本与未知成本见all_costs.json，最大预算1740执行、870000控制步、
88740全部reset、48720000帧。工厂与受控reset全部收费；获取已计入控制
步，失败惩罚不作为实际交互重复计费。递归／C4/C8估计、重放／分析计算
及CLI入口墙时分别保留；nfev不等于全部Jacobian或线性运算调用。
历史训练与旧v2、原C8名义模型和更早来源另列，不能隐藏历史费用或把
每个共享来源再乘程序数。在线LLM API为0，没有再训练神经网络或新响应模型。

## 后续判断与停止线

若数值／执行未完整通过，不作预测或任务晋级。若预测或任务门未通过，
保留负结果，不围绕该版表现接收者追加获取门控、调beta、换bank或补样；
不能从表现更好的某获取臂取代预定主程序。若两门通过，也只支持固定
标准参考的后续使用；移动前获取决策、完整Q／DR、简单重加权、CPC和
同历史被动适应等强对照、独立机制区别与消融仍需另冻新实验。
本次不完成CCF A研究目标，不把软件检查或基线改善当论文创新。
'''
    dest=a.ROOT/'reports/occam_reference_qualification_v1_zh.md'
    with dest.open('x',encoding='utf8',newline='\n') as f:f.write(note)
    io.write(out/'source_manifest.json',dict(manifest_id=m['manifest_id'],source_sha256=sources,report_sha256=io.sha(dest),new_physics=0,online_LLM_API_calls=0))
    result=dict(integrity='COMPLETE_REPORT' if complete else 'RETAINED_PARTIAL_REPORT',manifest_id=m['manifest_id'],allocated=1740,
        complete_task_failures=len(failures),unresolved=len(unresolved),scientific_population_complete=complete,
        numerical_qualification=numerical,predictive_qualification=False if statistics is None else statistics['prediction']['qualified'],
        task_qualification=False if statistics is None else statistics['task_qualified'],new_physics=0,online_LLM_API_calls=0,wall_ns=perf_counter_ns()-started)
    io.write(out/'complete.json',result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--manifest',required=True);v=p.parse_args();print(report(v.manifest),flush=True)

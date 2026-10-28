"""Describe the complete audited TRAIN population; never claims task superiority."""
from collections import defaultdict
from pathlib import Path
import csv,json,shutil,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import occam_native_case_io_v1 as c
RUN=c.OUTPUT/'occam_reference_train_v3_20261028T071949Z_c92356173d9e'
OUT=c.BASE/'data_report_v1';OUT.mkdir(exist_ok=False)
m=c.check_manifest(RUN/'manifest.json');s=c.read(RUN/'train/summary.json');p=c.read(RUN/'train/process_audit.json');a=c.read(RUN/'train/audit.json')
assert s['executions']==648 and p['integrity']=='PASSED_ISOLATED_PROCESS_AND_BYTE_CONTINUITY_ONLY' and a['integrity']=='PASSED'
assert a['counts']['executions']==648 and a['counts']['observed_window_labels']==3296 and p['ledger']==a['ledger']==s['lifecycle']
rows=s['rows'];failed=[r for r in rows if not r['success']];missing=[r for r in rows if not r['performance_windows']]
assert sum(r['total_steps'] for r in rows)==80390 and len(failed)==46
keys=('cohort','group','task','seed','context','planned_boundary','acquisition_action','behavior','success','deadline_loss','total_steps','policy_queries','performance_windows','full_feedback_windows','boundary_applied')
for name,values in (('all_648_cases.csv',rows),('all_46_task_failures.csv',failed),('all_without_performance_windows.csv',missing)):
    with (OUT/name).open('x',encoding='utf8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=keys);writer.writeheader();writer.writerows({k:r[k] for k in keys} for r in values)
cells=defaultdict(list)
for row in rows:cells[(row['task'],row['context'],row['planned_boundary'])].append(row)
table=[]
with (OUT/'all_18_task_condition_boundary_cells.csv').open('x',encoding='utf8',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=('task','context','boundary','cases','success','failure','steps','mean_deadline_loss'));writer.writeheader()
    for (task,condition,boundary),values in sorted(cells.items()):
        row=dict(task=task,context=condition,boundary=boundary,cases=len(values),success=sum(v['success'] for v in values),failure=sum(not v['success'] for v in values),steps=sum(v['total_steps'] for v in values),mean_deadline_loss=sum(v['deadline_loss'] for v in values)/len(values));writer.writerow(row)
        table.append('|'+task+'|'+condition+'|'+str(boundary)+'|'+str(row['cases'])+'|'+str(row['success'])+'|'+str(row['failure'])+'|')
text=f'''# 标准表现参考v3：完整TRAIN数据与两级审计

2026-10-28。一次新NATIVE36与TRAIN648完整结束，全部门通过。分配
{m['manifest_id']}，收集源码c923561，冻结fbcc0fe。TRAIN有18个独立组，
三个任务／两条件／三边界全部保留；不把648条相关程序执行或时间步当
独立组。602任务成功／46任务失败／0技术失败，未启动0，未补样或替换。
这只是训练人口描述，不是模型或新算法的独立任务结果。

## 完整人口

|任务|条件|干预步|案例|成功|失败|
|---|---|---:|---:|---:|---:|
{chr(10).join(table)}

逐条648例、全部46失败及全部无表现窗口案例分别见data_report_v1的三个
完整CSV。每个任务／条件／时点均显示，不筛掉失败、早终止或获取后立即
结束的案例。3296个实际窗口标签，{len(missing)}例没有表现窗口，84例未到
干预边界；这些不是虚构零标签。缺失指标由真实结束位置和原接口规则登记。
三获取×两行为是数据生成程序，不是已训练新方法；不据这些分项挑冠军。

## 两级审计

进程／字节／会计审计检查648个实际worker及其原始回执、PID、时间和
压缩成员，原始流未重写。完整动态／PI／执行器／噪声／成本和原生／Python
状态见证审计通过；271对共同获取后完整状态一致，53对提前结束配对保留。
审计共享原actor作控制重放，独立标量费用／PI／动作链另核，不冒称新的
物理重仿真或完全独立算法实现。审计守卫的环境、reset、仿真、拟合、求解
和网络操作均0，独立政策重放查询73028次另计。

## 完整费用

|阶段|案例|控制步|全部reset|物理帧|实际政策查询|审计政策查询|
|---|---:|---:|---:|---:|---:|---:|
|NATIVE|36|5399|1836|944995|5083|5083|
|TRAIN|648|80390|33048|16925950|73028|73028|
|合计|684|85789|34884|17870945|78111|78111|

TRAIN工厂16200000帧、受控初始reset324000帧、实际控制401950帧，全部计入。
获取／验证／移动已在控制步中支付，不重复收费。全部实际帧低于19152000
冻结总上限；每例500步、51全部reset、28000帧上限不变。
TRAIN采集9172.869秒，完整审计1252.287秒；进程审计、入口和打包／恢复／
归档分别有回执。原v2的27982步／11475全部reset／5877410帧及更早来源
另列；旧188项部分人口未使用。采集／审计本身科学拟合与在线LLM为0，
之后的训练并行运行并单独计Adam／求解／时间，不能把全项目当前更新记0。

## 学习入口与尚未完成的证据

完整公开投影SHA-256：
{a['public_trajectories_sha256']}。
只有该公开流进入新learner，种子、真实扰动／噪声、私有状态及旧人口均不
作为特征。TRAIN归一化与既定1000预训练／4000 META／4000匹配ERM保持，
三个checkpoint预先指定，不按任务成绩选择。实际训练状态和费用另报告。

本报告不提前声明训练完成、数学导出通过或独立资格。完整原始记录、失败
及公开投影保留；打包／实际Git恢复和归档以各自完成回执为准，未完成时
不能称已发布全部数据。压缩成员字节恢复和独立科学资格是不同证据。

后续仍需独立预测／自身时序历史的完整任务验证、直接C8／积分／被动适应／
始终获取与不更新／完整风险及DR等强对照、消融和A的具体机制区别。
OCCAM相关参考、训练MSE或数值合法不构成创新；无收益保留负结果，CCF A
研究目标尚未完成。
'''
(ROOT/'reports/occam_reference_train_data_v3_zh.md').write_text(text,encoding='utf8',newline='\n')
source_files=[RUN/'manifest.json',RUN/'train/summary.json',RUN/'train/completion.json',RUN/'train/audit.json',RUN/'train/process_audit.json']
c.write(OUT/'source_manifest.json',dict(integrity='PASSED_COMPLETE_POPULATION_DESCRIPTION',source_sha256={p.relative_to(ROOT).as_posix():c.sha(p) for p in source_files},
    executions=648,independent_groups=18,success=602,task_failures=46,missing_windows=len(missing),all_cases_retained=True,
    no_independent_task_benefit_claim=True,new_physics_during_report=0,new_fits=0,online_LLM_API_calls=0))
shutil.copyfile(Path(__file__),OUT/Path(__file__).name)
print(dict(integrity='PASSED_COMPLETE_POPULATION_DESCRIPTION',cases=648,failures=46,missing_windows=len(missing)),flush=True)

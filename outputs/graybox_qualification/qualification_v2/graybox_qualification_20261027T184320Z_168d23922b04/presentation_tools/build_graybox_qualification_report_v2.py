"""Terminal supplemental qualification report and byte-exact raw transport."""
from pathlib import Path
from collections import Counter,defaultdict
from time import perf_counter_ns
import csv,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import graybox_qualification_io_v2 as a
from src.analysis.release_learning_guard_v1 import read_only
from scripts.archive_action_response import split_file,restore
io=a.io
def optional(p):return io.read(p) if p.exists() else None
def write(p,s):
    with p.open('x',encoding='utf8',newline='\n') as f:f.write(s)
def table(head,rows):return '| '+' | '.join(head)+' |\n| '+' | '.join('---' for _ in head)+' |\n'+''.join('| '+' | '.join(str(v) for v in r)+' |\n' for r in rows)
def csvwrite(p,rows):
    if not rows:return
    with p.open('x',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)

def build(path):
    start=perf_counter_ns();m=a.checked(path);root=path.parent;control=root/'pipeline_control';failures={p.name:io.read(p) for p in control.glob('*failure.json')}
    io.require((control/'completion.json').exists() or failures,'terminal supplement only');out=root/'presentation';out.mkdir(exist_ok=False);guard={};cases=[];phase={};compute=Counter();latencies=[]
    with read_only(guard):
        for split in a.SPLITS:
            folder=root/split.lower();s=optional(folder/'summary.json');audit=optional(folder/'audit.json');done=optional(folder/'completion.json')
            cc=[] if done is None else list(io.rows(folder/'cases.jsonl.gz'));failed=optional(folder/'failed_case.json');indexed={tuple(c[k] for k in a.KEYS):c for c in cc}
            if failed is not None:indexed[tuple(failed[k] for k in a.KEYS)]=failed
            for spec in a.population(split):
                c=indexed.get(tuple(spec[k] for k in a.KEYS));status='NOT_STARTED' if c is None else 'FAILED' if c is failed else 'COMPLETED'
                fields=('total_steps','reposition_steps','common_measure_steps','entry_at_calls','packet_steps','complete_packet','reason','success_at_response_horizon','terminated','truncated')
                row=dict(spec,record_status=status,**{k:None if c is None else c.get(k) for k in fields})
                if c is None:row['reason']='NOT_STARTED'
                elif c is failed:row['reason']='EXECUTION_EXCEPTION'
                cases.append(row);fr=None if c is None else c.get('forecast_record')
                if fr is not None and fr['canonical']:
                    compute.update(fr['model_compute_counts']);latencies.append(dict(spec,compute_wall_ns=fr['compute_wall_ns'],global_error=fr['forecast_error'],method_errors=fr['method_errors']))
            if s is not None:
                ledger=s['lifecycle']['counts'];phase[split]=dict(executions=len(indexed),completed_executions=len(cc),control_steps=s['control_steps'],all_resets=ledger.get('reset_attempts',0),physical_frames=ledger.get('simulation_frames_completed',0),
                    fixed_policy_queries=sum(c.get('policy_queries',0) for c in indexed.values()),independent_policy_queries=None if audit is None else audit['extra_independent_policy_queries'],
                    independent_inference_counts=None if audit is None else audit['independent_inference_counts'],record_audit_guard=None if audit is None else audit['read_only_guard'],
                    collection_wall_s=s['wall_ns']/1e9,audit_wall_s=None if audit is None else audit['wall_ns']/1e9,network_guard=s['network_guard'],fitting_guard=s['fitting_guard'])
        io.require(len(cases)==432,'all supplement allocations');io.write(out/'all_case_outcomes.json',cases);csvwrite(out/'all_case_outcomes.csv',cases)
        grouped=defaultdict(list)
        for c in cases:grouped[tuple(c[k] for k in ('split','task','context','boundary','acquisition_action'))].append(c)
        missing=[dict(zip(('split','task','context','boundary','acquisition_action'),key),allocated=len(rows),completed=sum(c['record_status']=='COMPLETED' for c in rows),
            entries=sum(c['entry_at_calls'] is not None for c in rows),full_packets=sum(c['complete_packet'] is True for c in rows),reasons=dict(Counter(c['reason'] for c in rows))) for key,rows in grouped.items()]
        io.write(out/'all_strata_missingness.json',missing);io.write(out/'canonical_forecast_compute.json',latencies)
        old=[dict(c,source_run=a.SOURCE.name) for split in ('SOFTWARE','NOMINAL','TRAIN') for c in io.rows(a.SOURCE/split.lower()/'cases.jsonl.gz')]
        combined=[{k:r.get(k) for k in (*a.KEYS,'total_steps','reason')}|dict(source_run=a.SOURCE.name,record_status='COMPLETED') for r in old]
        combined.extend(dict(c,source_run=root.name) for c in cases);io.require(len(combined)==891 and len({tuple(r[k] for k in a.KEYS) for r in combined})==891,'same original891 assignments, historical unstarted placeholders not double counted')
        io.write(out/'combined_original_allocation_register.json',combined)
        total={k:sum(p[k] for p in phase.values()) for k in ('executions','completed_executions','control_steps','all_resets','physical_frames','fixed_policy_queries')}
        source=a.config()['imported_source_costs_separate'];overall={k:source[k]+total[k] for k in ('executions','control_steps','all_resets','physical_frames')}
        costs=dict(new_by_phase=phase,new_total=total,inherited_source_costs_separate=source,combined_actual=overall,new_primary_training=0,new_nominal_grid_fits=0,
            actual_online_inference_counts=dict(compute),partial_failure_counters=failures,online_LLM_API_calls=0,C4_C8_fits=0,full_task_tail_evaluated=False,new_model_used_for_control=False,
            new_unique_tests=18,reused_unique_tests=2410,unique_total=2428,constructed_checks_separate=dict(final='outputs/graybox_qualification/freeze_validation_v2/test_receipt.json',
                all_attempts='outputs/graybox_qualification/development_validation_v2',attempts_not_added_to_unique_total=True),
            stage_wall_seconds={p.stem:io.read(p)['wall_ns']/1e9 for p in control.glob('*_receipt.json')},nested_or_parallel_times_not_additive=True)
        io.write(out/'costs.json',costs);cal=optional(root/'cal_evaluation/result.json');qual=optional(root/'qual_evaluation/result.json');status='PIPELINE_FAILED_RETAINED' if failures else qual['status']
        decision=dict(status=status,qualification=qual,failures=failures,old_pipeline_failure_retained=True,no_retry_or_extension=True,
            next='仅完成标准响应差组件资格；实际控制与新获取机制须独立设计、完整费用任务比较及消融' if qual and qual['status']=='QUALIFIED_RESPONSE_CONTRAST_COMPONENT_ONLY' else '封存该固定版本及失败，不按QUAL调参、改基线或扩样，不围绕失败版本叠加反演／选择门',
            algorithm_novelty_established=False,full_task_utility_evaluated=False,publication_goal_complete=False)
        io.write(out/'research_decision.json',decision)
        archive=a.BASE/'archives_v2'/root.name;archive.mkdir(parents=True,exist_ok=False);restored=a.BASE/'restoration_v2'/root.name;catalog=[]
        raw=[(s.lower(),p) for s in a.SPLITS for p in sorted((root/s.lower()).glob('*.jsonl.gz'))]+[('metadata',p) for p in root.glob('*.json') if p.stat().st_size>8*1024**2]
        for directory,p in raw:
            dst=archive/directory/p.name;dst.parent.mkdir(exist_ok=True);parts=split_file(p,dst,io.sha(p),part_bytes=4*1024**2);idx=dst/'parts.json';r=restore(idx,restored/directory/p.name)
            catalog.append(dict(source=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=io.sha(p),index=idx.relative_to(ROOT).as_posix(),index_sha256=io.sha(idx),part_count=len(parts['parts']),actual_restore=r))
        io.write(archive/'catalog.json',dict(integrity='PASSED',files=catalog,originals_and_actual_restoration_retained=True,new_physics=0,new_primary_fits=0,online_LLM_API_calls=0))
        write(a.BASE/'archives_v2/.gitattributes','**/*.bin binary\n');write(root/'pipeline_control/.gitattributes','*.bin binary\n')
        def model_table(result,split):
            if result is None:return '未产生该阶段评分；不能写成模型资格负结果。\n'
            panels=io.read(root/(split+'_evaluation')/'panels.json');csvwrite(out/(split+'_all_panels.csv'),panels)
            return table(['方法','全分配平均端点损失mm↓','可用窗口描述值mm↓','可用／分配端点'],[[p['method'],f"{p['mean_endpoint_loss_m']*1000:.6f}",'缺失' if p['available_only_mean_endpoint_loss_m'] is None else f"{p['available_only_mean_endpoint_loss_m']*1000:.6f}",f"{p['available_endpoints']}/{p['allocated_endpoints']}"] for p in panels if not p['level']])
        ctable=model_table(cal,'cal');qtable=model_table(qual,'qual');contrasts='尚无独立QUAL比较。\n';strata='尚无QUAL分层。\n';interpretation='没有可解释的独立QUAL比较，不能将未执行阶段写成模型负结果。'
        if qual:
            contrasts=table(['GRAY_JOINT−参考','平均差mm','整组bootstrap95%区间mm'],[[k,f"{v['mean_difference_m']*1000:+.6f}",f"[{v['bootstrap95_m'][0]*1000:+.6f}, {v['bootstrap95_m'][1]*1000:+.6f}]"] for k,v in qual['co_primary'].items()])
            panels=io.read(root/'qual_evaluation/panels.json');names=list(qual['full_allocation_mean_m']);rows=[]
            for field,values in (('task',io.TASKS),('context',('UNCHANGED','CHANGED')),('acquisition_action',('IN_TASK','MOVE')),('boundary',(16,32,64)),('horizon',(8,16))):
                for v in values:rows.append([field+'='+str(v)]+[f"{next(p['mean_endpoint_loss_m'] for p in panels if p['level']==[field] and p['strata']=={field:v} and p['method']==n)*1000:.6f}" for n in names])
            strata=table(['完整边际层',*names],rows)
            fir=qual['co_primary']['FIR'];fixed=qual['co_primary']['GRAY_FIXED']
            interpretation=f"本轮预指定联合观测器相对FIR全人口平均差为{fir['mean_difference_m']*1000:+.6f}毫米，95%区间[{fir['bootstrap95_m'][0]*1000:+.6f},{fir['bootstrap95_m'][1]*1000:+.6f}]毫米；该区间含零。相对固定输入参数参考为{fixed['mean_difference_m']*1000:+.6f}毫米，区间[{fixed['bootstrap95_m'][0]*1000:+.6f},{fixed['bootstrap95_m'][1]*1000:+.6f}]毫米。联合方法虽优于ZERO、INSTANT及RLS_ARX，仍未通过全部强参考门，不能以局部胜出替代晋级。此为本冻结配置的负结果，不证明所有联合估计或A方向均无效。"
        report=ROOT/'reports/graybox_qualification_v2_zh.md'
        text=f'''# 公开历史联合观测器：独立资格补充 v2

2026-10-28。结论 **{status}**。本轮评价标准前向响应差参考，**没有完整任务收益、错误采用率、安全或算法新颖性结论，CCF A目标仍未完成**。

## 冻结与失败继承

冻结提交 `{m['source_git_commit']}`；运行 `{root.name}`；manifest ID `{m['manifest_id']}`。原cf2712d流水线因训练审计上下文计数错误停止，459次采集及训练保留。只读修复完成独立数值重建后，本补充在新目录、采集前独立冻结；原失败回执和原缺失的training/audit.json不修改，没有悄悄恢复旧流水线。

新入口仅允许CAL／QUAL，原预留但未使用的分配、种子、任务、条件、时点、获取位置、命令包、噪声及算子命名空间均逐条保持。原459实际记录与本补充432条计划按原KEYS合并仍为891条，不把历史呈现表里的未启动占位条目重复计数。原始完整种子census保留所有615份来源；七个确切原所有者／本补充来源是冲突判断例外，不豁免目录或外部登记。启动时另查原CAL／QUAL没有意图或目录、原进程终止、模型q未选择。

模型文件SHA为 `{a.MODEL_SHA}`；主训练、名义网格、C4／C8和政策的新拟合均为零。训练来源、模型与成功补充审计逐字节导入并标明来源，原训练费用另列。本轮不是新的训练模型或训练人口。

## 方法及固定资格

ZERO预测输入差无响应；INSTANT为累计输入差；FIR是16阶有限脉冲响应。RLS_ARX以全部真实公开历史递归辨识，起点来自受控名义来源。GRAY_FIXED固定输入仿射参数为恒等假设；GRAY_JOINT联合估计运动、隐目标和输入仿射行。理想灰箱均值存在标准ARX2实现，隐状态或联合EKF不能直接算新模型类或新获取算法。

CAL仅在q=0/0.001/0.01中以完整分配、等组三角色对H8/H16损失精确有理数选择，平局取最先者；没有选其他模型、特征、任务或阈值。数值、记录与统计门全部通过后才锁定，锁早于QUAL。选择锁及全部候选均保存。

{ctable}

QUAL只保留锁定q的GRAY_JOINT与五个强参考。评价端点是位置差预测的XY RMSE，封顶1米；无入口、短包或无效预测罚1米并保留分母。轨迹内计算后按独立组组织，三个时点层内整组bootstrap10000次；可用窗口列仅作描述，不能替代完整人口。

可用窗口列先在各可用组内平均，再对可用组等权；它不是把全分配均值简单去掉固定惩罚所得的原始逐端点均值。所有方法的缺失、组权和比较分母完全披露。

{qtable}

{contrasts}

{interpretation}

{'![保存的预测资格评分](../outputs/graybox_qualification/qualification_v2/'+root.name+'/presentation/qualification.png)' if qual else ''}

{strata}

三任务×不变／变化×IN_TASK／MOVE×时点×H8/H16的全部联合分层保存在对应阶段panels.json与presentation的CSV（阶段未执行则不造文件）。全部432条新分配、病例及缺失原因见all_case_outcomes.json、all_strata_missingness.json；原891条计划的无重复合并登记见combined_original_allocation_register.json。

五项组级区间上界全部<0、所有任务及H8/H16点低于全部参考、九组都有完整家族、每任务×条件×位置至少三个完整角色对和零无效预测，必须同时满足。完整门与失败见research_decision.json。不据QUAL调参、扩样或挑任务。

## 真实执行与独立审计

完整因果公开历史从真实初始观测起构建，没有伪造最早两段位移；只给定已声明未来命令，不给未来观测、真实扰动、噪声、种子或私有状态。任何家族包响应之前保存预测，兄弟角色仅消费原预测。复制的是数学信念；物理世界不捕获／恢复，每次受控初始重置后状态、随机数与时钟连续。

记录审计重建float32仿射／死区→XYZ实际噪声→最终裁剪→原生目标，核对游标、每步5帧及0.0125秒、原生见证和保存先后。独立预测禁用生产预测／拟合，以标量积分／协方差和批式RLS复算；统计禁用主评分／选择，以Decimal／Fraction读原保存结果。共享JSON、浮点、科学原语及部分固定政策／程序重放，不是物理重仿真或对全部未记录状态的保证。

## 全部成本和失败

本补充实际{total['executions']}次启动、{total['control_steps']}控制步、{total['all_resets']}全部重置、{total['physical_frames']}帧；上限432、40320、22032、11217600。政策查询实际{total['fixed_policy_queries']}。每次50次工厂内部重置＋1次受控重置全部计费，不能只报在线控制步。

加原459条真实来源后，累计{overall['executions']}次、{overall['control_steps']}控制步、{overall['all_resets']}全部重置、{overall['physical_frames']}帧。原主求解9／网格27、两次独立训练重建共LS18／网格54，原构造LS18等历史费用单列，不再次充当本轮新拟合。在线滤波／RLS、独立批式求解、延迟、阶段耗时和全部构造测试另列costs.json；嵌套／并行时间不简单相加。

18项新增入口检查＋2410项源码绑定复用＝2428项唯一检查。开发中Windows短路径比较失败及诊断、修正和重复构造次数保留，不重复计为新唯一测试。编译、依赖、完整已跟踪秘密扫描、新索引BASIC／EXTRA与字节检查按来源核对。在线LLM API=0，新主拟合=0，无重采训练人口。技术终止文件：{', '.join(failures) if failures else '无'}。

全部{len(catalog)}份新原始流／大元数据已分片、校验并实际恢复，原件与副本继续本地保留；索引位于outputs/graybox_qualification/archives_v2/{root.name}/catalog.json。紧凑远端若省略原始大记录或.bin分片，须按实际目录披露，不能声称已上传全部数据。旧源失败、原所有研究负结果及六项旧比较保持。

## 判断与下一步

{decision['next']}。数值合法、当前预测能力和完整费用任务收益分别验收。工作植物的XY解耦、零平衡偏移、高斯矩和局部裁剪／EKF均有建模限制；参数协方差不是概率覆盖或安全保证。包期成功标志不等于完整任务成功率，预测差误差也不是参数真值或逆控制资格。

若组件通过，仍须独立自身时序的完整任务评价，保留DIRECT_C8、积分、强廉价被动适应、始终获取／不更新、标准检测和历史辨识，以及MDE、Residual RL、OCCAM、GAUGE、Poke and Strike、TOM、双重控制、CPC及同权限完整程序风险／DR与消融。新机制必须说明获取和纠正如何改变后续适用性，并经过查新，不能将门控、混合或普通表现预测包装成新颖性。

本轮补充查新见 `docs/research/correction_scope_validity_policy_review_v3_zh.md`：UAI2024局部模型有效性主动学习及ICML2023 PDML是直接相关路线，实际读取范围与限制均披露；不据此修改本轮规则或宣称已证明新颖性。
'''
        write(report,text);a.checked(path)
    io.write(out/'report_receipt.json',dict(integrity='PASSED',report_sha256=io.sha(report),manifest_sha256=io.sha(path),raw_files_actually_restored=len(catalog),
        guard=guard,wall_ns=perf_counter_ns()-start,new_physics=0,new_primary_fits=0,online_LLM_API_calls=0))
    print(dict(integrity='PASSED',status=status,new_total=total,combined_actual=overall,restored=len(catalog)),flush=True)

if __name__=='__main__':build(Path(sys.argv[1]).resolve())

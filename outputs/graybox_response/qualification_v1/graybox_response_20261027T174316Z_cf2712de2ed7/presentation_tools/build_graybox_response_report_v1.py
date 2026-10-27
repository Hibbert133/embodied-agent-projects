"""Read-only post-run presentation, complete allocation, costs and exact transport."""
from pathlib import Path
from collections import Counter,defaultdict
from time import perf_counter_ns
import csv,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import graybox_response_io_v1 as a
from src.analysis.release_learning_guard_v1 import read_only
from scripts.archive_action_response import split_file,restore
io=a.io
CHUNK_BYTES=4*1024**2

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
    io.require((control/'completion.json').exists() or failures,'terminal pipeline, not a polling timeout')
    out=root/'presentation';out.mkdir(exist_ok=False);guard={};cases=[];phase={};actual_counts=Counter();latencies=[];phase_table=[];source={}
    with read_only(guard):
        for split in a.SPLITS:
            folder=root/split.lower();s=optional(folder/'summary.json');audit=optional(folder/'audit.json');done=optional(folder/'completion.json')
            cc=[] if done is None else list(io.rows(folder/'cases.jsonl.gz'));failed=optional(folder/'failed_case.json');indexed={tuple(c[k] for k in a.KEYS):c for c in cc}
            if failed is not None:indexed[tuple(failed[k] for k in a.KEYS)]=failed
            for spec in a.population(split):
                c=indexed.get(tuple(spec[k] for k in a.KEYS));status='NOT_STARTED' if c is None else 'FAILED' if c is failed else 'COMPLETED'
                fields=('total_steps','reposition_steps','common_measure_steps','nominal_steps','entry_at_calls','packet_steps','complete_packet','reason','success_at_response_horizon','terminated','truncated')
                row=dict(spec,record_status=status,**{k:None if c is None else c.get(k) for k in fields})
                if c is None:row['reason']='NOT_STARTED'
                elif c is failed:row['reason']='EXECUTION_EXCEPTION'
                cases.append(row);fr=None if c is None else c.get('forecast_record')
                if fr is not None and fr['canonical']:
                    actual_counts.update(fr['model_compute_counts']);latencies.append({k:c[k] for k in a.KEYS}|dict(compute_wall_ns=fr['compute_wall_ns'],global_error=fr['forecast_error'],method_errors=fr['method_errors']))
            phase_table.append([split,len(indexed),a.limits(split)['executions'],'未开始' if s is None else s['status'],None if s is None else s['control_steps'],sum(c.get('entry_at_calls') is not None for c in cc),sum(c.get('complete_packet',False) for c in cc)])
            if s is not None:
                ll=s['lifecycle']['counts'];phase[split]=dict(executions=len(indexed),completed_executions=len(cc),control_steps=s['control_steps'],all_resets=ll.get('reset_attempts',0),physical_frames=ll.get('simulation_frames_completed',0),
                    fixed_policy_queries=sum(c.get('policy_queries',0) for c in indexed.values()),independent_policy_queries=None if audit is None else audit['extra_independent_policy_queries'],
                    independent_forecast_rows=None if audit is None else audit['independent_forecast_rows'],independent_inference_counts=None if audit is None else audit['independent_inference_counts'],
                    independent_guard=None if audit is None else audit['read_only_guard'],collection_wall_s=s['wall_ns']/1e9,record_audit_wall_s=None if audit is None else audit['wall_ns']/1e9,
                    fit_guard=s['fitting_guard'],network_guard=s['network_guard'])
            for name in ('summary.json','completion.json','audit.json'):
                if (folder/name).exists():source[(folder/name).relative_to(root).as_posix()]=io.sha(folder/name)
        io.require(len(cases)==891,'all891 allocated executions including unstarted')
        io.write(out/'all_case_outcomes.json',cases);csvwrite(out/'all_case_outcomes.csv',cases);io.write(out/'canonical_forecast_latencies.json',latencies)
        groups=defaultdict(list)
        for c in cases:groups[tuple(c[k] for k in ('split','task','context','boundary','acquisition_action'))].append(c)
        missing=[dict(zip(('split','task','context','boundary','acquisition_action'),key),allocated=len(rows),completed=sum(c['record_status']=='COMPLETED' for c in rows),
            entries=sum(c['entry_at_calls'] is not None for c in rows),full_packets=sum(c['complete_packet'] is True for c in rows),reasons=dict(Counter(c['reason'] for c in rows))) for key,rows in groups.items()]
        io.write(out/'all_strata_missingness.json',missing)
        total={k:sum(v[k] for v in phase.values()) for k in ('executions','completed_executions','control_steps','all_resets','physical_frames','fixed_policy_queries')}
        train=optional(root/'training/completion.json');ta=optional(root/'training/audit.json');cal=optional(root/'cal_evaluation/result.json');qual=optional(root/'qual_evaluation/result.json')
        costs=dict(by_phase=phase,total=total,main_training_receipt=train,independent_training_audit=ta,actual_online_inference_counts=dict(actual_counts),
            partial_failure_counters=failures,online_LLM_API_calls=0,neural_updates=0,legacy_C4_C8_fits=0,old_training_samples_reused=0,old_learned_weights_loaded=0,
            model_used_for_control=False,full_task_tail_evaluated=False,new_unique_tests=32,source_reused_tests=2376,unique_total=2408,
            constructed_test_and_prior_array_costs_separate=dict(final_receipt='outputs/graybox_response/freeze_validation_v1/test_receipt.json',
                all_development_attempts='outputs/graybox_observer/collector_development_v1',previous_array='outputs/graybox_observer/array_implementation_v1',
                repeat_attempts_not_added_to_unique_total=True),
            historical_physics_separate=dict(path='outputs/history_response/development_v1/history_response_20261027T130543Z_b2f69d34b630/presentation/costs.json',
                training_records_or_weights_reused=False,previous_all_source_costs_retained=True),
            stage_wall_seconds={p.stem:io.read(p)['wall_ns']/1e9 for p in control.glob('*_receipt.json')},parallel_or_nested_times_not_additive=True)
        frames=[f for failure in failures.values() for f in failure.get('partial_counters',[]) if f.get('module')=='src.analysis.graybox_response_training_audit_v1']
        costs['actual_training_numerical_costs']=dict(primary_solves=0 if train is None else train['actual_counts']['ridge_solve_attempts'],
            primary_nominal_grid_passes=0 if train is None else train['actual_counts']['nominal_grid_candidate_evaluations'],
            independent_lstsq=ta['guard']['operation_counts']['lstsq_attempts'] if ta else sum((f.get('guard') or {}).get('operation_counts',{}).get('lstsq_attempts',0) for f in frames),
            independent_nominal_grid_passes=ta['independent_counts']['independent_nominal_grid_passes'] if ta else sum((f.get('counter') or {}).get('independent_nominal_grid_passes',0) for f in frames))
        io.write(out/'costs.json',costs)
        status='PIPELINE_FAILED_RETAINED' if failures else qual['status'];decision=dict(status=status,failures=failures,qualification=qual,
            no_retry_no_extension=True,algorithm_novelty_established=False,task_benefit_established=False,publication_goal_complete=False,
            next='封存本次失败流水线；先只读修复并完整测试独立审计，再另行冻结资格入口。不重采原训练人口、不改已保存参数；本次没有模型资格结论' if failures else '只作标准输入差响应参考，另行设计自身时序完整任务实验与具体获取机制' if qual and qual['status']=='QUALIFIED_RESPONSE_CONTRAST_COMPONENT_ONLY' else '封存此固定版本；不按QUAL调参、加反演或选择门，不声称A方向或所有历史辨识均无效')
        io.write(out/'research_decision.json',decision)
        parts=a.BASE/'archives_v1'/root.name;parts.mkdir(parents=True,exist_ok=False);restored=a.BASE/'restoration_v1'/root.name;catalog=[]
        raw_sources=[(split.lower(),src) for split in a.SPLITS for src in sorted((root/split.lower()).glob('*.jsonl.gz'))]
        raw_sources.extend(('metadata',src) for src in root.glob('*.json') if src.stat().st_size>8*1024**2)
        for directory,src in raw_sources:
                local=parts/directory/src.name;local.parent.mkdir(exist_ok=True);transport=split_file(src,local,io.sha(src),part_bytes=CHUNK_BYTES)
                idx=local/'parts.json';r=restore(idx,restored/directory/src.name)
                catalog.append(dict(source=src.relative_to(ROOT).as_posix(),sha256=io.sha(src),bytes=src.stat().st_size,index=idx.relative_to(ROOT).as_posix(),
                    index_sha256=io.sha(idx),part_count=len(transport['parts']),actual_restore=r))
        io.write(parts/'catalog.json',dict(integrity='PASSED',files=catalog,original_raw_retained=True,restoration_retained=True,new_physics=0,new_model_fits=0,online_LLM_API_calls=0))
        # A scoped attribute file protects binary transport without touching old tracked rules.
        write(a.BASE/'archives_v1/.gitattributes','**/*.bin binary\n')
        def modeltable(result,split):
            if result is None:return '此阶段未产生可用评分。\n'
            panels=io.read(root/(split+'_evaluation')/'panels.json');csvwrite(out/(split+'_all_panels.csv'),panels)
            return table(['方法','全分配端点损失 mm↓','可用窗口描述值 mm↓','可用／全部端点'],[[p['method'],f"{p['mean_endpoint_loss_m']*1000:.6f}",'缺失' if p['available_only_mean_endpoint_loss_m'] is None else f"{p['available_only_mean_endpoint_loss_m']*1000:.6f}",f"{p['available_endpoints']}/{p['allocated_endpoints']}"] for p in panels if not p['level']])
        caltable=modeltable(cal,'cal');qualtable=modeltable(qual,'qual');contrast='没有独立 QUAL 比较。\n';details='没有 QUAL 分层。\n'
        if qual:
            contrast=table(['GRAY_JOINT−参考','平均差 mm','独立组95%区间 mm'],[[k,f"{v['mean_difference_m']*1000:+.6f}",f"[{v['bootstrap95_m'][0]*1000:+.6f}, {v['bootstrap95_m'][1]*1000:+.6f}]"] for k,v in qual['co_primary'].items()])
            pp=io.read(root/'qual_evaluation/panels.json');names=list(qual['full_allocation_mean_m']);rows=[]
            for field,values in (('task',io.TASKS),('context',('UNCHANGED','CHANGED')),('acquisition_action',('IN_TASK','MOVE')),('boundary',(16,32,64)),('horizon',(8,16))):
                for v in values:rows.append([field+'='+str(v)]+[f"{next(p['mean_endpoint_loss_m'] for p in pp if p['level']==[field] and p['strata']=={field:v} and p['method']==n)*1000:.6f}" for n in names])
            details=table(['完整边际层',*names],rows)
        nominal_details='名义阶段未完成。'
        if (root/'nominal/summary.json').exists():
            nn=[c for c in cases if c['split']=='NOMINAL'];nominal_details=table(['任务','九条实际长度','至少40步条数'],[[t,','.join(str(c['total_steps']) for c in nn if c['task']==t),sum(c['total_steps'] is not None and c['total_steps']>=40 for c in nn if c['task']==t)] for t in io.TASKS])
        text=f'''# 公开历史联合观测器：标准响应参考独立资格 v1

2026-10-28。当前结论 **{status}**。本轮是标准预测组件验证，**不评估完整任务截止损失、成功率收益、错误采用率或论文创新**。A“纠正后的适用性变化”保持为已选主线，CCF A 目标仍未完成。

## 可复核来源与时序

冻结提交 `{m['source_git_commit']}`，运行 `{root.name}`，manifest ID `{m['manifest_id']}`。源码、配置、协议、种子与原始记录均按哈希约束。采样前32项新增、2376项源码绑定复用检查，共2408项唯一检查；编译、依赖、全部已跟踪文件秘密扫描、实际索引 BASIC／EXTRA 扫描和逐字节核对通过。重复构造测试不是新独立测试，更不是机器人训练数据。

共同入口先保存全部预测，再执行三个已声明包；兄弟角色消费原保存预测。每次从一个受控初始重置开始，获取、测量、随机数和时钟连续，无捕获／恢复撤销获取位移。真实目标、扰动、实际噪声及原生状态仅用于执行器与审计，不能进入模型特征或标签。

阶段进展（包后即结束，没有任务尾部）：

{table(['阶段','已启动','分配','状态','实际控制步','有入口执行','完整16步包执行'],phase_table)}

全部891条分配及未启动／失败病例见 `presentation/all_case_outcomes.json` 和 CSV，全部分层缺失原因见 `all_strata_missingness.json`。不能把未启动的 QUAL 当作负预测结果，也不能删除早结束来改善均值。

## 名字及同数据强参考

ZERO 预测输入差无位置差；INSTANT 为累计输入差；FIR 是16阶有限脉冲响应。RLS_ARX 从新名义岭回归起点出发，以全部真实公开历史递归辨识。GRAY_FIXED 是输入参数固定恒等的同植物状态观测器；GRAY_JOINT 联合估计隐目标、运动及输入仿射参数。理想均值可以写成 ARX2，隐状态不创造一个新的确定性模型类。

已声明的 NOMINAL 恒等输入通道用于名义植物与 RLS 起点；INSTANT／FIR 使用新 TRAIN 三角色实际响应差。所有方法可以访问同一新公开来源，但实际采用的设计矩阵不同。名义27条全部登记，灰箱使用所有非空，RLS使用所有至少三步来源；没有伪造最早两段位移或用未知评价真值拟合。

{nominal_details}

名义网格每任务9候选、每轴选创新似然最低者，共27遍历、6轴选择。主求解最多9，独立增广 LS 最多9，另27遍独立标量名义网格。在线滤波、RLS与独立批式复算次数完整记录于费用JSON，不能把“零离线银行拟合”写成零适应计算。

## CAL与独立 QUAL

CAL只在 q=0/0.001/0.01 中按全分配、等组H8/H16精确有理数损失选择，平局取最先者；全部模型数值有效且记录／统计审计通过才锁定并开始 QUAL。未按 CAL 换模型、特征、任务或门槛。

{caltable}

QUAL中的端点量为位置差预测的 XY RMSE，封顶1米；缺入口、短包或无效预测罚1米，全部保留分母。先轨迹内平均再等组，九独立组／三个时点层内bootstrap10000次，不把时间步当独立样本。可用窗口均值仅为描述性精度，不能替代完整人口资格。

{qualtable}

{contrast}

{'![独立预测资格](../outputs/graybox_response/qualification_v1/'+root.name+'/presentation/qualification.png)' if qual else ''}

完整边际分层（mm），三任务×条件×获取位置×时点×H8/H16的全部联合分层已保存在 `qual_evaluation/panels.json` 与 `presentation/qual_all_panels.csv`：

{details}

资格门同时要求五项区间上界<0、全部任务与H8/H16点估计低于所有参考、每组有完整家族、每任务×条件×位置至少三个完整对，以及零无效预测。保存结论与全部门见 `research_decision.json`。数值合法、当前预测与完整费用任务收益是三个不同判断。

## 全部费用、失败与局限

本轮实际 {total['executions']} 次启动、{total['control_steps']} 控制步、{total['all_resets']} 全部重置、{total['physical_frames']} 物理帧。冻结上限为891、82800、45441、23134500。全部重置包括每次50次工厂内部和1次受控重置。实际政策查询 {total['fixed_policy_queries']}；名义程序不查询任务政策。各阶段／原始帧、审计、滤波／RLS计数、延迟、训练、构造复查及历史来源费用分列在 `costs.json`。重复时间与嵌套耗时不相加当总时长。

在线 LLM API=0，神经更新=0，旧 C4／C8 重拟合=0，旧记录训练／旧学习权重加载=0。终止失败文件：{', '.join(failures) if failures else '无技术流水线失败'}。没有自动重试、扩样或换种子。全部早结束、缺失、数值失败和负结果保留，发生失败时不假装完成未开始的阶段。

独立实现禁用主预测、拟合及来源读取器；Gaussian矩用积分、协方差用标量循环、RLS用批式方程，评分用Decimal／Fraction。仍共享JSON、浮点、线性代数、分配及补充程序／政策重放；不是物理重仿真或对未记录状态的穷尽保证。裁剪后目标均值、局部EKF、XY解耦、零平衡偏移与高斯噪声均为工作近似，预测方差不是安全或覆盖保证。

全部新分析遵从冻结资格；任何新增失配原因解释只能作描述，不能从相关或一个模型失败推定唯一原因。原ARX、SS、FIR、HISTORY_KERNEL、A1等负结果及六项旧比较不改动。没有完整任务结果，不从包期成功标志推导方法成功率收益。

## 后续判断与查新

{decision['next']}。即使组件通过，也必须另行冻结自身时序的获取／采用完整任务比较、完整费用、DIRECT_C8／积分／廉价被动适应／始终获取不更新、检测与历史辨识、MDE／OCCAM／GAUGE／Poke and Strike／Residual RL／TOM／双重控制／CPC及同权限完整程序风险／DR参考和消融。

补充查新见 `docs/research/graybox_event_learning_review_v1_zh.md`：参数滤波式事件触发学习已包含失配触发、主动激励和精度达标后更新；用途相关辨识也已有理论。不能把这些组成部分或工程检查当作本项目新机制。

## 原始记录与复算

入口 `scripts/run_graybox_response_v1.py`，冻结协议 `docs/protocols/graybox_response_v1_zh.md`。实际执行、独立审计与失败全过程见本运行目录；原始gzip留在本地，全部{len(catalog)}份原始文件已分片、校验并实际恢复，索引 `outputs/graybox_response/archives_v1/{root.name}/catalog.json`。恢复副本继续保留。远端紧凑归档是否省略原始大文件必须按实际发布目录单独披露。
'''
        report=ROOT/'reports/graybox_response_v1_zh.md';write(report,text)
        io.write(out/'source_hashes.json',source);a.checked(path)
    io.write(out/'report_receipt.json',dict(integrity='PASSED',report_sha256=io.sha(report),source_manifest_sha256=io.sha(path),guard=guard,
        all891_allocations_registered=True,raw_files_actually_restored=len(catalog),wall_ns=perf_counter_ns()-start,new_physics=0,new_model_fits=0,online_LLM_API_calls=0))
    print(dict(integrity='PASSED',status=status,actual=total,restored=len(catalog)),flush=True)

if __name__=='__main__':build(Path(sys.argv[1]).resolve())

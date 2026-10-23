"""Loss-priority selection and independent whole-group task qualification."""
from collections import Counter
from itertools import combinations,product
from pathlib import Path
from time import perf_counter_ns
import numpy as np
from src.analysis import task_passive_io_v1 as allocation

io=allocation.io


def bootstrap(differences,cohort):
    groups=6 if cohort=='DEV' else 9; io.require(set(differences)==set(range(groups)),'complete independent groups')
    values=np.array([differences[g] for g in range(groups)],float); io.require(np.isfinite(values).all(),'missing group')
    seed=202610390 if cohort=='DEV' else 202610391; rng=np.random.default_rng(seed); chunks=[]
    for boundary in range(3):
        ids=np.arange(boundary,groups,3); chunks.append(values[ids[rng.integers(0,len(ids),(10000,len(ids)))]] )
    means=np.concatenate(chunks,axis=1).mean(axis=1)
    return {'mean':float(values.mean()),'lower95':float(np.quantile(means,.025)),
        'upper95':float(np.quantile(means,.975)),'groups':groups,'replicates':10000,'seed':seed,
        'unit':'WHOLE_GROUP_STRATIFIED_BY_BOUNDARY','multiplicity':'Unadjusted descriptive secondary intervals; both registered primary upper bounds must be negative'}


def validate_cases(cases,cohort,selected=None):
    specs=allocation.population(cohort,selected); io.require(len(cases)==len(specs),'full allocated population required')
    for c,s in zip(cases,specs):
        for k,v in s.items(): io.require(c[k]==v,'population order/spec differs')
        io.require(c['completed'] and c['error'] is None and c['close_error'] is None,'incomplete software case cannot disappear')
        io.require(type(c['success']) is bool and type(c['total_steps']) is int and 0<=c['total_steps']<=500,'observed result')
        io.require(c['deadline_loss']==(c['total_steps'] if c['success'] else 500),'deadline loss mischarged')
    return specs


def summary_rows(cases,cohort,selected=None):
    validate_cases(cases,cohort,selected); result=[]; groups=6 if cohort=='DEV' else 9
    for p in allocation.programs(cohort,selected):
        actual=[c for c in cases if c['style']==p.style and c['time_constant_s']==p.time_constant_s]
        means={g:float(np.mean([c['deadline_loss'] for c in actual if c['group']==g])) for g in range(groups)}
        result.append({'program':allocation.program_id(p.style,p.time_constant_s),'style':p.style,'time_constant_s':p.time_constant_s,
            'n':len(actual),'successes':sum(c['success'] for c in actual),'loss_sum':sum(c['deadline_loss'] for c in actual),
            'mean_deadline_loss':float(np.mean(list(means.values()))),'group_mean_deadline_loss':means,
            'actual_control_steps':sum(c['total_steps'] for c in actual),'movement_steps':sum(c['movement_steps'] for c in actual),
            'task_pi_steps':sum(c['pi_steps'] for c in actual),'boundary_missing_reasons':dict(Counter(c['boundary_missing_reason'] for c in actual if not c['boundary_applied'])),
            'failure_reasons':dict(Counter(c['stop_reason'] for c in actual if not c['success']))})
    return result


def choose(cases):
    rows=summary_rows(cases,'DEV'); choices={}; chosen=[]
    for style in allocation.PI_STYLES:
        candidates=[r for r in rows if r['style']==style]
        best=min(candidates,key=lambda r:(r['loss_sum'],-r['time_constant_s'])); chosen.append(best); choices[style]=best['time_constant_s']
    primary=min(chosen,key=lambda r:(r['loss_sum'],allocation.PI_STYLES.index(r['style'])))
    controls={r['style']:r for r in rows if r['style'] in allocation.CONTROLS}
    passed=all(primary['loss_sum']<controls[s]['loss_sum'] for s in ('DIRECT_C8','MOVE_INTEGRAL'))
    return {'selected_time_constants_s':choices,'primary_style':primary['style'],'primary_program':primary['program'],
        'development_gate':'PASSED_FOR_LOCKED_QUALIFICATION_ONLY' if passed else 'FAILED_STOP_NO_QUALIFICATION',
        'development_gate_passed':passed,'all_development_programs':rows,
        'selection_rule':'Complete DEV deadline-loss sum; time-constant tie largest, style tie registered order; no task/context tuning',
        'new_environment_steps':0,'new_api_calls':0,'new_response_predictor_training':0,'novel_algorithm':False}


def checked_cohort(path,cohort):
    folder=Path(path).parent/cohort.lower(); a=io.read(folder/'audit.json')
    io.require(a['integrity']=='PASSED' and a['completion_sha256']==io.sha(folder/'completion.json') and
        a['auditor_sha256']==io.sha(allocation.ROOT/'src/analysis/task_passive_audit_v1.py'),'source-bound complete record audit required')
    for n,h in io.read(folder/'completion.json')['artifact_sha256'].items(): io.require(io.sha(folder/n)==h,'audited bytes changed')
    return a,list(io.rows(folder/'cases.jsonl.gz'))


def select(path):
    path=Path(path).resolve(); m=allocation.load_manifest(path); io.require(not (path.parent/'qual').exists(),'no post-qualification selection')
    a,cases=checked_cohort(path,'DEV'); choice=choose(cases)
    value={**{k:m[k] for k in io.IDENTITY},**choice,'DEV_completion_sha256':io.sha(path.parent/'dev/completion.json'),
        'DEV_audit_sha256':io.sha(path.parent/'dev/audit.json'),'statistics_source_sha256':io.sha(__file__),
        'locked_ns':perf_counter_ns(),'DEV_costs':io.read(path.parent/'dev/summary.json')['lifecycle']}
    io.write(path.parent/'selection.json',value); return value


def verify_selection(path):
    path=Path(path).resolve(); v=io.read(path.parent/'selection.json'); m=allocation.load_manifest(path)
    io.require(v['development_gate_passed'],'negative development gate stops qualification; do not append samples')
    a,cases=checked_cohort(path,'DEV'); expected=choose(cases)
    for k,value in expected.items(): io.require(io.digest(v[k])==io.digest(value),'selection lock mismatch: '+k)
    for k in io.IDENTITY: io.require(v[k]==m[k],'selection identity mismatch')
    io.require(v['DEV_completion_sha256']==io.sha(path.parent/'dev/completion.json') and v['DEV_audit_sha256']==io.sha(path.parent/'dev/audit.json')
        and v['statistics_source_sha256']==io.sha(__file__),'selection source binding')
    return v


def summarize(cases,cohort,selected=None,primary=None):
    rows=summary_rows(cases,cohort,selected); byid={r['program']:r for r in rows}; pairs=[]
    for left,right in combinations(byid,2):
        a,b=byid[left],byid[right]
        pairs.append({'left':left,'right':right,'loss_difference':bootstrap({g:a['group_mean_deadline_loss'][g]-b['group_mean_deadline_loss'][g] for g in a['group_mean_deadline_loss']},cohort),
            'success_difference':a['successes']-b['successes'],'paired_denominator':a['n']})
    cells=[]
    for task,context,p in product(allocation.GAINS,('UNCHANGED','CHANGED'),allocation.programs(cohort,selected)):
        actual=[c for c in cases if c['task']==task and c['context']==context and c['style']==p.style and c['time_constant_s']==p.time_constant_s]
        cells.append({'task':task,'context':context,'program':allocation.program_id(p.style,p.time_constant_s),'n':len(actual),
            'successes':sum(c['success'] for c in actual),'mean_deadline_loss':float(np.mean([c['deadline_loss'] for c in actual])),
            'actual_control_steps':sum(c['total_steps'] for c in actual)})
    primary_results={}
    if primary is not None:
        a=byid[primary]
        for name in ('DIRECT_C8','MOVE_INTEGRAL'):
            b=byid[name]; primary_results[primary+'_MINUS_'+name]=bootstrap({g:a['group_mean_deadline_loss'][g]-b['group_mean_deadline_loss'][g] for g in a['group_mean_deadline_loss']},cohort)
    passed=bool(cohort=='QUAL' and len(primary_results)==2 and all(v['upper95']<0 for v in primary_results.values()))
    return {'cohort':cohort,'executions':len(cases),'programs':rows,'primary_program':primary,'primary_comparisons':primary_results,
        'all_paired_secondary_comparisons':pairs,'complete_task_context_cells':cells,
        'all_failure_case_ids':[c['case_id'] for c in cases if not c['success']],
        'qualification_gate':'PASSED_ENGINEERING_TASK_REFERENCE_ONLY' if passed else 'NOT_PASSED' if cohort=='QUAL' else 'DEVELOPMENT_SELECTION_ONLY',
        'no_safety_guarantee':True,'no_algorithmic_novelty_claim':True,'new_environment_steps':0,'new_api_calls':0,'new_model_fits':0}


def evaluate(path,cohort):
    path=Path(path).resolve(); m=allocation.load_manifest(path); io.require(cohort in ('DEV','QUAL'),'scientific evaluation cohort')
    a,cases=checked_cohort(path,cohort); selection=io.read(path.parent/'selection.json')
    if cohort=='QUAL': verify_selection(path)
    value={**{k:m[k] for k in io.IDENTITY},**summarize(cases,cohort,selection['selected_time_constants_s'] if cohort=='QUAL' else None,selection['primary_program']),
        'audit_sha256':io.sha(path.parent/cohort.lower()/'audit.json'),'selection_sha256':io.sha(path.parent/'selection.json'),
        'statistics_source_sha256':io.sha(__file__)}
    folder=path.parent/'evaluation'; folder.mkdir(exist_ok=True); io.write(folder/(cohort.lower()+'.json'),value); return value


def report(path):
    path=Path(path).resolve(); m=allocation.load_manifest(path); selection=io.read(path.parent/'selection.json')
    phases=[c for c in allocation.COHORTS if (path.parent/c.lower()/'summary.json').exists()]
    result=[]
    for c in ('DEV','QUAL'):
        p=path.parent/'evaluation'/(c.lower()+'.json')
        if p.exists(): result.append(io.read(p))
    lines=['# 任务期间被动积分适应：完整任务开发与独立资格验证','',
        f"运行 `{m['experiment_run_id']}`；冻结源码 `{m['source_git_commit']}`。",'',
        '本轮是强工程基线，区分参数数值合法、预测能力与完整任务收益。任务 PI 不使用 F20 逆模型，也不代表 ARX／GRU 已恢复有效；限幅和回退不构成安全保证。',
        '每步固定策略查询一次。位置误差是未裁剪 float32 策略动作除以任务固定 P 增益，仅表示当前策略目标，不是最终任务误差。积分以发送命令单位累积，并按实际有界发送命令投影抗饱和；收到真实物理回执后才提交积分状态。', '',
        'NO_PROBE 无初始探测；DIRECT_C8 使用八步初始标定；MOVE_KEEP_C8 执行原移动后保留标定；MOVE_INTEGRAL 只使用原移动阶段积分。RAW_TASK_PI 从零时刻持续积分；DIRECT_TASK_PI 在 C8 后积分；两个 MOVE_TASK_PI 在共同真实移动后持续积分，分别以 C8／原移动积分为基准。底层策略权重固定，XY 以外的发送命令保持该控制器原值。','',
        f"开发选择：`{selection['selected_time_constants_s']}`；锁定主方法 `{selection['primary_program']}`；开发门槛 `{selection['development_gate']}`。",'',
        '时间常数在完整六组开发人口的截止损失上选择，平局取较大时间常数；主程序平局遵循预注册顺序。没有按任务挑参数。独立资格使用九个新组；若开发不优于 DIRECT_C8 和 MOVE_INTEGRAL，则不采集资格人口。','']
    for v in result:
        lines += [f"## {v['cohort']}：{v['qualification_gate']}",'','| 程序 | 成功／全部 | 平均截止损失↓ | 实际控制步 |','|---|---:|---:|---:|']
        for r in v['programs']: lines.append(f"| {r['program']} | {r['successes']}/{r['n']} | {r['mean_deadline_loss']:.6f} | {r['actual_control_steps']} |")
        lines += ['','| 锁定主比较 | 平均损失差 | 95% 整组区间 |','|---|---:|---|']
        for name,d in v['primary_comparisons'].items(): lines.append(f"| {name} | {d['mean']:.6f} | [{d['lower95']:.6f}, {d['upper95']:.6f}] |")
        lines+=['','完整任务 × 不变／变化分层：','','| 任务 | 条件 | 程序 | 成功／全部 | 平均截止损失↓ |','|---|---|---|---:|---:|']
        for r in v['complete_task_context_cells']: lines.append(f"| {r['task']} | {r['context']} | {r['program']} | {r['successes']}/{r['n']} | {r['mean_deadline_loss']:.6f} |")
    lines+=['','## 完整成本与范围','','| 阶段 | 执行 | 控制步 | 全部重置 | 物理帧 | 在线 C4/C8 估计尝试 |','|---|---:|---:|---:|---:|---:|']
    costs=[]
    for c in phases:
        s=io.read(path.parent/c.lower()/'summary.json'); a=io.read(path.parent/c.lower()/'audit.json'); q=s['lifecycle']['counts']
        lines.append(f"| {c} | {s['executions']} | {s['control_steps']} | {q['reset_attempts']} | {q['simulation_frames_attempted']} | {s['online_c4_c8_fit_attempts']} |")
        costs.append({'cohort':c,'executions':s['executions'],'control_steps':s['control_steps'],'lifecycle':s['lifecycle'],
            'online_c4_c8_fit_attempts':s['online_c4_c8_fit_attempts'],'independent_audit_c4_c8_refits':a['costs'].get('independent_c4_c8_refits',0),
            'collection_wall_ns':s['wall_ns'],'audit_wall_ns':a['wall_ns'],'summary_sha256':io.sha(path.parent/c.lower()/'summary.json'),
            'completion_sha256':io.sha(path.parent/c.lower()/'completion.json'),'audit_sha256':io.sha(path.parent/c.lower()/'audit.json')})
    lines+=['',
        '截止损失是成功时的全部实际控制步，失败／无效初始估计为 500；初始探测和实际移动已经计入一次。受控初始重置后不重置、不恢复状态、不替换噪声；未到边界或移动阶段的提前成功保留完整分母。',
        '历史名义 C8 完整来源另有 480 次执行、3,840 控制步、24,480 全部重置和 12,259,200 物理帧。NO_PROBE 和 RAW_TASK_PI 不读取或收取该模型。每个选定 PI 程序还必须披露完整开发人口的调参费用，不能只报告获胜参数或成功分支；软件契约费用另列。',
        '组是独立统计单位，同一组中的任务、条件、程序及相关时间步不能增加独立样本量。bootstrap 在 16／32／64 步三个边界层内重采样完整组。全部二级配对比较及失败案例编号在统计 JSON 中；二级区间为未作多重比较校正的描述性结果。',
        '原生审计核对保存先于执行、真实回执后提交积分、一次策略查询、float32 仿射→实际噪声→最终裁剪、全部工厂／受控重置和物理帧，并检查共同移动后的状态。它使用原始状态见证与记录复算，不等同于独立物理引擎或实机验证。',
        '本轮新增响应模型训练、策略训练和在线 LLM API 调用均为 0。全部失败、负结果和原始日志保留；不补采、换种子或挑选有利任务。',
        '本轮仅建立任务期间被动适应的强对照。即使任务门槛通过，也不是算法创新或 CCF A 目标完成。移动前的获取决策还须与这一强对照实际部署比较，并在独立自身时序历史上验证完整获取成本、错误更新与消融；若无额外收益，应保留反证。','']
    delivery=path.parent/'result_delivery'; delivery.mkdir(exist_ok=True)
    (delivery/'report_zh.md').write_text('\n'.join(lines),encoding='utf-8',newline='\n')
    dev=next(c for c in costs if c['cohort']=='DEV'); denominator=54
    fees=[]
    for style in allocation.CONTROLS+allocation.PI_STYLES:
        bank=style not in ('NO_PROBE','RAW_TASK_PI'); tuned=style in allocation.PI_STYLES
        fees.append({'style':style,'qualification_units_per_program_if_run':denominator,
            'full_nominal_c8_source':{'executions':480,'control_steps':3840,'all_resets':24480,'physical_frames':12259200} if bank else None,
            'full_parameter_selection_DEV':dev if tuned else None,
            'amortized_source_control_steps_per_QUAL_unit_if_run':((3840 if bank else 0)+(dev['control_steps'] if tuned else 0))/denominator,
            'scope':'Source fees disclosed separately from already-charged online deadline loss; do not sum shared banks once per method as new interactions'})
    io.write(delivery/'costs_and_provenance.json',{'identity':{k:m[k] for k in io.IDENTITY},'actual_new_phases':costs,'source_fees':fees,
        'nominal_source_sha256':io.C8_SHA,'selection_sha256':io.sha(path.parent/'selection.json'),
        'software_contract_shared_cost_separately_listed':True,'new_api_calls':0,'new_response_predictor_training':0})
    return delivery/'report_zh.md'

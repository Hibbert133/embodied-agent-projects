"""Whole-group statistics of actual one-step contrasts, without response fitting."""
from collections import Counter
from itertools import product
from pathlib import Path
from time import perf_counter_ns
import numpy as np
from src.analysis import command_contrast_io_v1 as allocation

io=allocation.io
MODELS=('ZERO','H10','F20','F43')


def bootstrap_groups(group_differences,replicates=10000):
    io.require(set(group_differences)==set(range(9)),'all nine independent groups required')
    v=np.array([group_differences[g] for g in range(9)],float)
    io.require(np.isfinite(v).all(),'missing group differences remain null')
    rng=np.random.default_rng(202610380); samples=[]
    for start in (0,3,6): samples.append(v[start+rng.integers(0,3,(replicates,3))])
    draws=np.concatenate(samples,axis=1).mean(axis=1)
    return {'mean':float(v.mean()),'lower95':float(np.quantile(draws,.025)),
            'upper95':float(np.quantile(draws,.975)),'groups':9,'replicates':replicates,
            'bootstrap_seed':202610380,'strata':'THREE_QUERY_TARGET_STAGES',
            'scope':'Unadjusted development interval for realized eligible paired units'}


def summarize(cases,plans):
    allocated=allocation.population(); io.require(len(cases)==len(allocated),'retain entire registered population')
    byunit={}; rows=[]
    for spec,case in zip(allocated,cases):
        for key,value in spec.items(): io.require(case[key]==value,'allocation/order mismatch')
        byunit.setdefault(spec['unit_id'],[]).append(case)
    for unit,actual in byunit.items():
        base=actual[0]; row={k:base[k] for k in ('unit_id','group','task','context','measurement_program','target','planned_boundary')}
        row.update(allocated_branches=5,executed_branches=len(actual),eligible=all(c['query_available'] for c in actual),
            missing_reason=base['missing_reason'],steps=sum(c['total_steps'] for c in actual),
            branch_steps={c['action_id']:c['total_steps'] for c in actual},scores=None)
        io.require(len(actual)==5 and [c['action_id'] for c in actual]==list(allocation.core.BRANCHES),'five labeled real branches')
        if row['eligible']:
            io.require(unit in plans and all(c['plan_sha256']==base['plan_sha256'] for c in actual),'immutable saved plan required')
            plan=plans[unit]; observations=np.array([np.asarray(c['after_observation'])[:2]-np.asarray(c['before_observation'])[:2] for c in actual])
            truth=observations[1:]-observations[0]; scores={}
            for source in allocation.PROGRAMS:
                scores[source]={'ZERO':float(np.mean(truth**2))}
                for feature in ('H10','F20','F43'):
                    predicted=np.array(plan['models'][f"{source}/{base['task']}/LINEAR_{feature}"]['predictions_m'])
                    scores[source][feature]=float(np.mean((predicted[1:]-predicted[0]-truth)**2))
            row.update(scores=scores,actual_contrast_m=truth.tolist(),
                candidate_commands=plan['query']['candidates'],missing_reason=None,
                duplicate_command_labels=5-len({tuple(c['sent_command']) for c in plan['query']['candidates']}))
        else:
            io.require(unit not in plans and all(not c['query_available'] and c['missing_reason']==base['missing_reason'] for c in actual),'partial query unit cannot be imputed')
        rows.append(row)
    groups=[]
    for group in range(9):
        selected=[r for r in rows if r['group']==group]; eligible=[r for r in selected if r['eligible']]
        scores={m:float(np.mean([r['scores'][r['measurement_program']][m] for r in eligible])) if eligible else None for m in MODELS}
        groups.append({'group':group,'target':allocation.core.TARGETS[group//3],'allocated_units':len(selected),
                       'eligible_units':len(eligible),'matched_scores_m2':scores})
    complete=all(g['eligible_units']>0 for g in groups)
    comparisons={}
    for other in ('ZERO','H10','F43'):
        comparisons['F20_MINUS_'+other]=bootstrap_groups({g['group']:g['matched_scores_m2']['F20']-g['matched_scores_m2'][other] for g in groups}) if complete else None
    mean_scores={m:float(np.mean([g['matched_scores_m2'][m] for g in groups])) if complete else None for m in MODELS}
    tables=[]
    for target,task,context,program,source in product(allocation.core.TARGETS,allocation.POLICIES,allocation.CONTEXTS,allocation.PROGRAMS,allocation.PROGRAMS):
        selected=[r for r in rows if (r['target'],r['task'],r['context'],r['measurement_program'])==(target,task,context,program)]
        eligible=[r for r in selected if r['eligible']]
        tables.append({'target':target,'task':task,'context':context,'measurement_program':program,'model_source':source,
            'allocated_units':len(selected),'eligible_units':len(eligible),
            'mean_unit_mse_m2':{m:float(np.mean([r['scores'][source][m] for r in eligible])) if eligible else None for m in MODELS}})
    task_coverage=all(any(r['eligible'] and r['task']==task for r in rows) for task in allocation.POLICIES)
    passed=bool(complete and task_coverage and comparisons['F20_MINUS_ZERO']['upper95']<0 and
                all(mean_scores['F20']<mean_scores[m] for m in ('ZERO','H10','F43')))
    return {'registered_executions':540,'registered_units':108,'executions':len(cases),'units':rows,'whole_groups':groups,
        'eligible_units':sum(r['eligible'] for r in rows),'missing_reasons':dict(Counter(r['missing_reason'] for r in rows if not r['eligible'])),
        'matched_group_mean_mse_m2':mean_scores,'primary_and_secondary':comparisons,'complete_source_transfer_tables':tables,
        'fixed_F20_component_gate':'PASSED_REALIZED_ELIGIBLE_CONTRASTS_ONLY' if passed else 'NOT_QUALIFIED',
        'gate_reasons':{'all_nine_groups_have_pairs':complete,'all_three_tasks_have_pairs':task_coverage},
        'new_model_fits':0,'new_environment_steps':0,'new_api_calls':0,'task_benefit_established':False,
        'scope':'Actual matched-noise one-step contrast development; not inverse control, task utility, novel method or safety qualification'}


def evaluate(path):
    path=Path(path).resolve(); manifest=allocation.load_manifest(path); folder=path.parent/'collection'; started=perf_counter_ns()
    audited=io.read(folder/'audit.json'); io.require(audited['integrity']=='PASSED' and audited['executions']==540,'complete independent record audit required')
    io.require(audited['completion_sha256']==io.sha(folder/'completion.json'),'audited completion changed')
    completion=io.read(folder/'completion.json')
    for name,h in completion['artifact_sha256'].items(): io.require(io.sha(folder/name)==h,'audited collection changed')
    cases=list(io.rows(folder/'cases.jsonl.gz')); plans={}
    for event in io.rows(folder/'events.jsonl.gz'):
        if event['event']=='UNIT_PLAN_COMMITTED':
            io.require(event['unit_id'] not in plans,'repeated plan'); plans[event['unit_id']]=event['plan']
    result={**{k:manifest[k] for k in io.IDENTITY},**summarize(cases,plans),'audit_sha256':io.sha(folder/'audit.json'),
            'collection_summary_sha256':io.sha(folder/'summary.json'),'statistics_source_sha256':io.sha(__file__),'wall_ns':perf_counter_ns()-started}
    target=path.parent/'evaluation'; target.mkdir(exist_ok=False); io.write(target/'statistics.json',result); return result


def report(path):
    path=Path(path).resolve(); manifest=allocation.load_manifest(path); folder=path.parent/'evaluation'; value=io.read(folder/'statistics.json')
    io.require(value['audit_sha256']==io.sha(path.parent/'collection/audit.json'),'statistics audit changed')
    lines=['# 固定响应模型实际命令差分资格验证','',f"运行：`{manifest['experiment_run_id']}`；源码：`{manifest['source_git_commit']}`。",'',
        f"资格结果：**{value['fixed_F20_component_gate']}**。全部 540 次执行和 108 个单元保留，其中 {value['eligible_units']} 个单元实际到达查询点。",'',
        '本轮检验预测的命令差分是否能解释实际一步响应差分，不部署逆控制器，不评价完整任务收益。预测器为事先冻结的 FIT 模型；本轮没有响应预测器训练或在线 LLM API 调用。', '',
        '五个分支分别从一次受控初始重置开始；后续连续执行，不能通过中途重置撤销位移。相同前缀、噪声过去与私有状态见证均通过审计。五条实际命令及全部六个预测器的预测先于首个查询结果保存。', '',
        '| 比较（MSE 差，m²） | 九组平均 | 95% 组区间 |','|---|---:|---|']
    for key,c in value['primary_and_secondary'].items(): lines.append(f"| {key} | {c['mean']:.8g} | [{c['lower95']:.8g}, {c['upper95']:.8g}] |" if c else f'| {key} | 缺失 | 缺失组，不能补零 |')
    lines+=['','完整逐单元、九组、三个查询阶段 × 三任务 × 两条件 × 两程序 × 两模型来源对照在 `statistics.json` 中。缺失原因：`'+str(value['missing_reasons'])+'`。', '',
        '统计先平均四个非基准方向与 XY 坐标，再平均单元，最后等权平均九个独立组；bootstrap 在三个查询阶段内按完整组重采样。相关步骤和五个匹配分支不是独立样本。区间为开发性、未作多重比较调整的区间。', '',
        '相同完整噪声带只给出一个耦合噪声实现，不等于条件期望或物理无噪声响应。裁剪导致的重复候选保留原标签并实际执行，不去重挑样。提前结束及无效拟合不被替代，资格范围仅限本次实际可达且配对完整的查询点。', '',
        '若 F20 未超过 ZERO、H10、F43 或主区间不支持改善，则保留负结果，不在本人口切换候选、调整模型或追加样本。即使通过，仍需独立验证逆控制、包含获取成本的任务收益和获取导致状态/适用性变化的决策机制；此处不视为论文贡献或 CCF A 目标完成。','']
    software=io.read(path.parent/'software_native/summary.json'); collection=io.read(path.parent/'collection/summary.json')
    lines+=['实际成本（软件原生检查／独立科学人口分列）：','',
        '| 阶段 | 执行 | 控制步 | 全部重置 | 物理帧 | C4/C8 在线估计尝试 |','|---|---:|---:|---:|---:|---:|']
    for name,data in (('原生软件契约',software),('独立科学人口',collection)):
        counts=data['lifecycle']['counts']; lines.append(f"| {name} | {data['executions']} | {data['control_steps']} | {counts.get('reset_attempts',0)} | {counts.get('simulation_frames_attempted',0)} | {data['online_c4_c8_fit_attempts']} |")
    lines+=['','独立审计的 C4/C8 复算次数另列于各 `audit.json`；模型源数据和训练的完整历史费用另见来源交付 `costs_and_provenance.json`，不能按当前 540 次执行重新记为新采集费用。所有失败、不可用点与原始事件均保留。','']
    text='\n'.join(lines); (folder/'report_zh.md').write_text(text,encoding='utf-8'); return folder/'report_zh.md'

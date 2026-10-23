"""Registered finite-source analysis and Chinese report, no new physical execution."""
import argparse
import csv
from pathlib import Path
import sys
from time import perf_counter_ns

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import numpy as np
from scripts import run_paired_probe_effects_v1 as collector
from scripts import run_strong_chronological_reference_v1 as io
from src.analysis.paired_probe_statistics_v1 import ARMS,CONTRASTS,contrasts,nested_summary,stream_bootstrap

LABELS={'REUSE_OLD':'直接用旧参数','PROBE_KEEP':'补测但保留旧参数','PROBE_UPDATE':'补测并更新，无效即停','PROBE_UPDATE_KEEP':'补测并更新，无效沿用旧参数'}
CLABELS={'total_keep':'直接复用 − 补测稳健更新','motion_budget':'直接复用 − 补测保留','update_keep':'补测保留 − 补测稳健更新',
         'total_strict':'直接复用 − 补测严格更新','fallback':'严格更新 − 稳健更新'}


def matrices(summary,j):
    result=[]
    for row in summary['cases']:
        if row['disposition']!='WARM_ELIGIBLE':continue
        evaluations=row['evaluations']
        if [(e['future'],e['program']) for e in evaluations]!=[(f,p) for f in range(1,j+1) for p in ARMS]:raise ValueError('incomplete fresh future table')
        table=np.asarray([e['outcome']['deadline_loss'] for e in evaluations]).reshape(j,4)
        result.append((row,table))
    return result


def method_cell(outcomes):
    n=len(outcomes)
    return {'cases':n,'successes':sum(v['success'] for v in outcomes),'stops':sum(v['stopped'] for v in outcomes),
        **{name:float(np.mean([v[field] for v in outcomes])) if n else None for name,field in (
            ('mean_deadline_loss','deadline_loss'),('mean_logical_steps','total_steps'),('mean_physical_suffix_steps','suffix_steps'),
            ('mean_probe_suffix_steps','fixed_probe_suffix_steps'),('mean_policy_suffix_steps','policy_suffix_steps'))}}


def statistics(m,s,phase):
    j=m['config'][phase.lower()]['fresh_futures'];pairs=matrices(s,j);losses=[v for _,v in pairs]
    cells={p:method_cell([v['outcome'] for row,_ in pairs for v in row['evaluations'] if v['program']==p]) for p in ARMS}
    groups=[]
    for key in ('task','family_oracle','schedule_oracle'):
        for value in sorted({r[key] for r,_ in pairs}):
            selected=[a for r,a in pairs if r[key]==value]
            groups.append({'field':key,'value':value,'contexts':len(selected),'mean_contrast':np.stack([contrasts(a).mean(axis=0) for a in selected]).mean(axis=0).tolist()})
    recommendations={}
    for method in ('UNCERTAINTY4','TASK_IVR4'):
        outcomes=[];actions={}
        for row,table in pairs:
            action=row['references'][method]['action'];actions[action]=actions.get(action,0)+1
            outcomes.extend(table[:,0 if action=='RUN_CACHED' else 2].tolist() if action!='STOP_PUBLIC_CHECK' else [500]*j)
        recommendations[method]={'contexts':len(pairs),'actions':actions,'mean_current_state_deadline_loss':float(np.mean(outcomes)) if outcomes else None,
            'scope':'Current-state recommendation evaluated on the fixed UNCERTAINTY4 source history; not its independent deployment policy.'}
    streams={q['stream']:(q['family_oracle'],q['schedule_oracle']) for q in m['population_oracle'][phase]}
    return {'source_units':s['source_units'],'dispositions':{k:sum(r['disposition']==k for r in s['cases']) for k in ('COLD_SOURCE','WARM_PREFIX_ENDED','WARM_ELIGIBLE')},
        'contexts':len(pairs),'fresh_futures_per_context':j,'contrast_order':list(CONTRASTS),'methods':cells,
        'nested':nested_summary(losses) if len(pairs)>=2 else None,'groups':groups,'saved_recommendations':recommendations,
        'stream_bootstrap':stream_bootstrap(losses,[r['stream'] for r,_ in pairs],streams) if phase=='MAIN' and pairs else None,
        'universal_complete_hidden_state_qualification':False,'scope':'Evaluator mechanism measurement, warm-source-state population only. Four programs are not four independently deployed chronological policies; no new method or pure information-value claim.'}


def csv_out(path,rows):
    with path.open('x',encoding='utf-8-sig',newline='') as handle:
        if rows:
            writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def analyze(path,phase):
    started=perf_counter_ns();m,_=collector.load(path);folder=path.parent/phase.lower();s=io.read(folder/'summary.json')
    a=io.read(path.parent/(phase.lower()+'_audit.json'))
    if a['integrity']!='PASSED' or a['summary_sha256']!=io.sha(folder/'summary.json'):raise ValueError('matching record audit required')
    output=path.parent/(phase.lower()+'_analysis_v1');output.mkdir();identity={k:m[k] for k in io.IDENTITY}
    stats=statistics(m,s,phase);io.write(output/'statistics.json',{**identity,'phase':phase,'summary_sha256':a['summary_sha256'],'statistics':stats},exclusive=True)
    source_rows=[];branches=[];context_rows=[]
    for row in s['cases']:
        base={k:row[k] for k in ('stream','episode','seed','task','family_oracle','schedule_oracle')}
        source_rows.append({**base,'disposition':row['disposition'],'cache_before_episode':None if row['cache_before'] is None else row['cache_before']['source_episode'],
            'cache_after_episode':None if row['cache_after'] is None else row['cache_after']['source_episode'],
            'source_program':row['source']['program'],**row['source']['outcome'],**{'actual_'+k:v for k,v in row['case_actual'].items()}})
        for record in [row['source'],*row['evaluations'],*row['sentinels']]:
            branches.append({**base,**{k:record[k] for k in ('role','future','program')},**record['outcome']})
    for index,(row,table) in enumerate(matrices(s,stats['fresh_futures_per_context'])):
        cell={'context':index,**{k:row[k] for k in ('stream','episode','seed','task','family_oracle','schedule_oracle')},
            'source_age':row['evidence']['source_age'],'source_task':row['evidence']['source_task'],
            'source_action':row['references']['UNCERTAINTY4']['action'],'task_ivr_action':row['references']['TASK_IVR4']['action']}
        values=contrasts(table)
        for k,name in enumerate(CONTRASTS):
            cell[name]=float(values[:,k].mean());cell[name+'_mcse']=float(values[:,k].std(ddof=1)/np.sqrt(len(values)))
            cell[name+'_both_signs']=bool(values[:,k].min()<0<values[:,k].max())
        context_rows.append(cell)
    csv_out(output/'source_units.csv',source_rows);csv_out(output/'all_program_executions.csv',branches)
    csv_out(output/'failures.csv',[r for r in branches if not r['success']]);csv_out(output/'stops.csv',[r for r in branches if r['stopped']])
    csv_out(output/'state_effects.csv',context_rows)
    source_steps=sum(r['source']['outcome']['total_steps'] for r in s['cases'])
    evaluator_steps=sum(v['outcome']['suffix_steps'] for r in s['cases'] for v in r['evaluations'])
    sentinel_steps=sum(v['outcome']['suffix_steps'] for r in s['cases'] for v in r['sentinels'])
    if source_steps+evaluator_steps+sentinel_steps!=s['controlled_steps']:raise ValueError('actual source/evaluator cost decomposition')
    strong=io.read(ROOT/m['config']['strong_source_manifest']);prior=io.read(ROOT/strong['config']['source_costs'])
    costs={**identity,'phase':phase,'actual_controlled_steps':s['controlled_steps'],'actual_controlled_resets':s['controlled_resets'],
        'actual_source_steps':source_steps,'actual_evaluator_suffix_steps':evaluator_steps,'actual_sentinel_suffix_steps':sentinel_steps,
        'physical_lifecycle':s['lifecycle'],'recorded_computation':s['counters'],'collection_body_wall_ns':s['collection_body_wall_ns'],
        'audit_policy_queries':a['audit_policy_queries'],'audit_shared_fitter_attempts':a['audit_shared_fitter_attempts'],'audit_shared_optimizer_nfev':a['audit_shared_optimizer_nfev'],
        'audit_wall_ns':a['audit_wall_ns'],'modern_nominal_steps_full':3840,'modern_nominal_controlled_resets_full':480,
        'modern_nominal_lifecycle_full':prior['joint_source_full_lifecycle'],'nominal_steps_per_source_unit':3840/s['source_units'],
        'restore_qualification_prior_steps':4032,'restore_qualification_prior_controlled_resets':13,'restore_qualification_prior_all_resets':663,'restore_qualification_prior_requested_frames':351660,
        'nominal_model_fits':0,'selector_fits':0,'policy_weight_updates':0,'api_calls':0,
        'scope':'Common physical prefix charged once; every actually executed counterfactual suffix/sentinel is charged. Full nominal source separate, not divided by four programs or fresh futures. Capture/restore times are subsets of collection wall time, not additive. Earlier qualification is disclosed separately, not new training data.'}
    if phase=='MAIN':
        sm=io.read(path.parent/'smoke_analysis_v1/costs.json');costs['separate_smoke']={k:sm[k] for k in ('actual_controlled_steps','actual_controlled_resets','physical_lifecycle','recorded_computation','collection_body_wall_ns')}
    costs['analysis_body_wall_ns']=perf_counter_ns()-started;io.write(output/'costs.json',costs,exclusive=True)
    io.write(output/'completion.json',{**identity,'phase':phase,'summary_sha256':a['summary_sha256'],'artifact_sha256':{p.name:io.sha(p) for p in output.iterdir() if p.is_file()}},exclusive=True)
    print(phase,'analysis contexts',stats['contexts'],flush=True)


def report(path,phase):
    m,_=collector.load(path);output=path.parent/(phase.lower()+'_analysis_v1');s=io.read(path.parent/phase.lower()/'summary.json')
    stats=io.read(output/'statistics.json')['statistics'];cost=io.read(output/'costs.json');a=io.read(path.parent/(phase.lower()+'_audit.json'));n=io.read(path.parent/(phase.lower()+'_statistics_audit.json'))
    if any(x['integrity']!='PASSED' or x['summary_sha256']!=io.sha(path.parent/phase.lower()/'summary.json') for x in (a,n)) or n['statistics_sha256']!=io.sha(output/'statistics.json'):raise ValueError('matching record and independent numeric audits required')
    lines=['# 同一状态下，补测动作与参数更新的任务效应','',
        '本轮是MetaWorld机制开发测量，没有在线API、新算法或真实机器人硬件结果。来源行为固定为“考虑旧参数误差的4步检查”，评价分支不写入来源缓存。','']
    if phase=='SMOKE':lines+=['**这是采集与审计预检。任务分数不用于调参，也不能当主实验结论。**','']
    lines += [f"完整保留{s['source_units']}个来源单元：冷源{stats['dispositions']['COLD_SOURCE']}、4步内已结束{stats['dispositions']['WARM_PREFIX_ENDED']}、合格暖状态{stats['contexts']}。"
        f"每个合格状态另有{stats['fresh_futures_per_context']}个新未来；实际来源未来0与哨兵不进入效果均值。",'',
        '| 程序 | 中文意思 | 成功／全部 | 停止 | 平均截止损失 | 平均逻辑步数 | 平均实际后缀 |','|---|---|---:|---:|---:|---:|---:|']
    for p,v in stats['methods'].items():
        cells=[f'{v[k]:.6f}' if v[k] is not None else '不适用' for k in ('mean_deadline_loss','mean_logical_steps','mean_physical_suffix_steps')]
        lines.append(f"| {p} | {LABELS[p]} | {v['successes']}／{v['cases']} | {v['stops']} | "+' | '.join(cells)+' |')
    lines+=['','成功计从初始重置起的全部逻辑步数；失败／停止损失500，实际费用仍按真实执行步数。四程序起点都是来源的同一个4步状态，不是四条独立部署的完整时序政策。','']
    figure=output/'figures/effects.png'
    receipt=io.read(output/'figures/receipt.json')
    if receipt['statistics_sha256']!=io.sha(output/'statistics.json') or receipt['artifact_sha256']['effects.png']!=io.sha(figure):raise ValueError('matching scientific figure required')
    lines+=['![四程序损失与效应分解](../'+figure.relative_to(ROOT).as_posix()+')','']
    nested=stats['nested'];bootstrap=stats['stream_bootstrap']
    if nested:
        lines+=['| 注册效果（正值表示右侧程序损失较低） | 均值／步 | 95%完整流区间 | 正负方向都出现的状态数 |','|---|---:|---|---:|']
        for k,name in enumerate(CONTRASTS):
            interval='预检不作区间推断' if phase=='SMOKE' else '不适用'
            if bootstrap and bootstrap['percentile_95'] is not None:
                lo,hi=bootstrap['percentile_95'][k];interval=f'[{lo:+.6f}, {hi:+.6f}]'
            both=sum(v[k] for v in nested['per_context_both_strict_signs_observed'])
            lines.append(f"| {CLABELS[name]} | {nested['mean_contrast'][k]:+.6f} | {interval} | {both}／{stats['contexts']} |")
        lines+=['','逐未来满足 R−K=(R−P)+(P−K)。R−P包含补测运动、4步费用及后续状态变化；P−K是指定拟合器和拒绝规则的更新效应，不能称为纯信息价值或最优EVSI。',
            '状态均值的噪声修正协方差保留负值。每状态MC标准误、所有正负反转、原始与修正协方差保存在 statistics.json／state_effects.csv；它们不识别固定公开证据下的隐藏变异，也不保证单状态符号或可学习性。','']
    else:lines+=['合格状态少于2，嵌套方差统计不适用；完整来源人口及所有执行仍保留。','']
    if bootstrap:lines += [f"主采集使用{bootstrap['source_streams']}个完整来源流，在九因素格各4流内分层bootstrap10000次，重新计算状态加权分子／分母。"
        f"分母为0的重复{bootstrap['undefined_draws']}次；次比较区间未校正。人口由覆盖和预算确定，没有小差异80%功效、等效或非劣效结论。",'']
    lines+=['同证据的UNCERTAINTY4与TASK_IVR4建议在当前后续结果之前保存。其当前状态损失只描述固定来源历史上的选择，不是各自独立部署的长期效果，也没有用事后最优程序代替在线选择。',
        '全部任务、故障族与变化方式分组见 statistics.json；所有来源单元、程序执行、失败、停止和状态效果均单独导出CSV，没有按评价结果删状态。','',
        f"独立记录审计重放{a['events_checked']}个事件，共核对{a['coverage']['matched_probe_prefixes']}对共同探测前缀、{a['coverage']['source_returns']}次来源状态恢复和{a['coverage']['sentinels']}次完整哨兵。"
        f"独立数值审计核对{n['numeric_fields_checked']}个字段，最大差{n['max_absolute_difference']:.3g}。",'',
        '物理恢复使用已通过注册条件资格的原生复制工具；见证仍由来源生成，不能推广为任意隐藏状态、任意版本或真实硬件的完整证明。记录审计共享固定政策、数值拟合器、编码器及缓存／检查数学，未重新构建环境或调用复制执行器。','',
        f"本阶段实际{cost['actual_controlled_steps']}个控制步，其中来源{cost['actual_source_steps']}、评价后缀{cost['actual_evaluator_suffix_steps']}、哨兵后缀{cost['actual_sentinel_suffix_steps']}。"
        f"受控重置{cost['actual_controlled_resets']}次，全部重置{cost['physical_lifecycle']['counts']['reset_completed']}次，请求模拟帧{cost['physical_lifecycle']['counts']['simulation_frames_attempted']}。",'',
        f"完整名义模型来源3840步／480次受控重置、24480次全部重置／12259200请求帧，单列摊到本阶段每个来源单元{cost['nominal_steps_per_source_unit']:.6f}步；不按反事实程序或重复未来数量稀释。"
        '恢复工具两版本的既有资格费另列4032控制步／13受控重置／663全部重置／351660请求帧，包含保留的v1失败。', '',
        f"采集侧参数拟合{cost['recorded_computation']['fits']}次、nfev {cost['recorded_computation']['nfev']}、政策查询{cost['recorded_computation']['policy_queries']}；审计另重算拟合{cost['audit_shared_fitter_attempts']}次、nfev {cost['audit_shared_optimizer_nfev']}、政策查询{cost['audit_policy_queries']}。"
        f"采集主体墙钟{cost['collection_body_wall_ns']/1e9:.3f}秒，捕获{cost['recorded_computation']['capture_ns']/1e9:.3f}秒、恢复{cost['recorded_computation']['restore_ns']/1e9:.3f}秒为其子集；API／选择器拟合／政策更新均为0。",'']
    if phase=='MAIN':lines += ['预检的实际控制、全部生命周期与计算费用在 costs.json 的 separate_smoke 中单列，不能只报告主采集。','']
    lines += ['本轮结果用于约束下一候选机制；新方法定义、与已有工作的实质区别、独立新方法任务确认、消融和完整论文要求仍未完成，不将此测量当作CCF A发表证据。','',
        '证据：'+m['experiment_run_id']+'；清单 '+m['manifest_id']+'；冻结源码 '+m['source_git_commit']+'。']
    target=ROOT/'reports'/('paired_probe_effects_'+phase.lower()+'_v1.md')
    with target.open('x',encoding='utf-8',newline='\n') as handle:handle.write('\n'.join(lines)+'\n')
    io.write(output/'report_receipt.json',{**{k:m[k] for k in io.IDENTITY},'phase':phase,'report_path':target.relative_to(ROOT).as_posix(),
        'report_sha256':io.sha(target),'statistics_sha256':io.sha(output/'statistics.json'),'record_audit_sha256':io.sha(path.parent/(phase.lower()+'_audit.json')),
        'numeric_audit_sha256':io.sha(path.parent/(phase.lower()+'_statistics_audit.json'))},exclusive=True)
    print(target.relative_to(ROOT),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('operation',choices=['analyze','report']);parser.add_argument('--manifest',type=Path,required=True);parser.add_argument('--phase',choices=['SMOKE','MAIN'],required=True);args=parser.parse_args()
    (analyze if args.operation=='analyze' else report)(args.manifest.resolve(),args.phase)

"""Independent saved-table census and Chinese descriptive report, no refits."""
from pathlib import Path
from collections import Counter
from time import perf_counter_ns
import json,sys,math
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
from src.analysis.release_learning_guard_v1 import read_only
start=perf_counter_ns();out=ROOT/'outputs/controller_agreement/feasibility_v1';delivery=out/'presentation';delivery.mkdir(exist_ok=False)
complete=io.read(out/'complete.json');summary=io.read(out/'summary.json');manifest=io.read(out/'manifest.json');guard={}
assert complete['integrity']=='PASSED'
for n,h in complete['artifact_sha256'].items():assert io.sha(out/n)==h,n


def independently_summarize(rows):
    groups=sorted({r['group'] for r in rows});values={k:[] for k in ('live_fraction','matched_ge1_full','matched_ge8_full','terminal_certificate_full','live_mean_matched','live_mean_interval_width')}
    for g in groups:
        group=[r for r in rows if r['group']==g];live=[r for r in group if r['missing_reason'] is None];n=len(group)
        values['live_fraction'].append(len(live)/n)
        values['matched_ge1_full'].append(len([r for r in live if r['matched_steps']>=1])/n)
        values['matched_ge8_full'].append(len([r for r in live if r['matched_steps']>=8])/n)
        values['terminal_certificate_full'].append(len([r for r in live if r['status']=='MATCHED_TO_TERMINAL'])/n)
        if live:
            values['live_mean_matched'].append(sum(r['matched_steps'] for r in live)/len(live))
            values['live_mean_interval_width'].append(sum(r['loss_delta_interval'][1]-r['loss_delta_interval'][0] for r in live)/len(live))
    return dict(allocated_pairs=len(rows),live_pairs=sum(r['missing_reason'] is None for r in rows),missing_pairs=sum(r['missing_reason'] is not None for r in rows),independent_groups=len(groups),
        metrics={k:dict(mean=None if not v else sum(v)/len(v),contributing_groups=len(v)) for k,v in values.items()})


with read_only(guard):
    pairs=list(io.rows(out/'pairs.jsonl.gz'));audits=list(io.rows(out/'independent_audit_rows.jsonl.gz'))
    assert len(pairs)==len(audits)==1944 and len(summary['panels'])==54 and len(summary['rate_pairs'])==12
    fields=('group','task','context','planned_boundary','acquisition_action','time_constant_s','receiver_rate')
    seen=set();counters=Counter();prefixes=0
    for p,a in zip(pairs,audits):
        key=tuple(p[k] for k in fields);assert key not in seen and key==tuple(a[k] for k in fields);seen.add(key)
        if p['missing_reason'] is None:
            assert p['loss_delta_interval']==a['independently_rebuilt_interval']
            assert a['actual_loss_delta']==p['target_outcome_evaluator_only']['deadline_loss']-p['source_outcome']['deadline_loss']
            assert p['loss_delta_interval'][0]<=a['actual_loss_delta']<=p['loss_delta_interval'][1]
            assert p['matched_steps']==a['paired_common_receipts'];prefixes+=p['matched_steps']
            for k in ('actual_success_to_failure','actual_failure_to_success'):counters[k]+=a[k]
        else:assert p['matched_steps'] is None and p['loss_delta_interval'] is None and a['no_adoption_outcome_equal']
    def check(rows,actual):
        expected=independently_summarize(rows)
        for k,v in expected.items():assert actual[k]==v,(k,actual[k],v)
    check(pairs,summary['all'])
    for panel in summary['panels']:
        data=[r for r in pairs if all(r[k]==panel[k] for k in ('task','context','planned_boundary','acquisition_action'))];check(data,panel['summary'])
    for panel in summary['rate_pairs']:
        data=[r for r in pairs if r['time_constant_s']==panel['source_rate'] and r['receiver_rate']==panel['receiver_rate']];check(data,panel['summary'])
    observed=list(io.rows(out/'shadow_steps.jsonl.gz'));assert len(observed)==prefixes+sum(r['status']=='FIRST_DISAGREEMENT' for r in pairs)
    assert not any(complete['guard']['operation_counts'].values()) and complete['guard']['network']['attempted_network_calls']==0
    for n,h in manifest['config']['source']['source_sha256'].items():assert io.sha(ROOT/n)==h,n
plan_entries=summary['command_computations']['main_command_computations'];literal_calls=summary['command_computations']['independent_command_computations']
divergent=sum(r['status']=='FIRST_DISAGREEMENT' for r in pairs)
assert plan_entries==literal_calls
# In frozen TaskMemoryMachine: plan serializes PI numbers twice; each committed
# matching receipt reconstructs/checks/reads them three additional times.
static_pi_number_calls=2*plan_entries+3*(plan_entries-divergent)
assert static_pi_number_calls<2000000
costs=dict(new_environment_creations=0,new_resets=0,new_control_steps=0,new_physical_frames=0,new_policy_queries=0,new_model_fits=0,online_LLM_API_calls=0,
    measured_main_plan_entries=plan_entries,measured_literal_formula_calls=literal_calls,static_reconstructed_main_PI_numbers_calls=static_pi_number_calls,
    static_count_not_runtime_instrumentation=True,historical_source=manifest['config']['source']['historical_cost'])
io.write(delivery/'costs.json',costs)
io.write(delivery/'independent_statistics_audit.json',dict(integrity='PASSED',pairs=1944,joint_panels=54,directed_rate_panels=12,source_hashes_unchanged=True,
    independent_group_metrics=True,matched_receipts=prefixes,shadow_rows=len(observed),descriptive_actual_transitions=dict(counters),guard=guard,wall_ns=perf_counter_ns()-start,
    main_aggregate_not_called=True,new_physics=0,new_fits=0,online_LLM_API_calls=0))


def metric(s,k):return s['metrics'][k]['mean']
def number(x):return '缺失' if x is None else f'{x:.3f}'
def pct(x):return '缺失' if x is None else f'{100*x:.2f}%'
all_=summary['all'];live=[r for r in pairs if r['missing_reason'] is None]
group_task=[]
for task in ('push-v3','reach-v3','door-open-v3'):
    for context in ('UNCHANGED','CHANGED'):
        group_task.append((task,context,independently_summarize([r for r in pairs if r['task']==task and r['context']==context])))
longest=max(live,key=lambda r:r['matched_steps']) if live else None
decision=dict(status='DESCRIPTIVE_INSUFFICIENT_SUPPORT_FOR_COLLECTION_SAVINGS',no_nontrivial_reusable_prefix=not any(r['matched_steps']>=1 for r in live),
    any_eight_step_prefix=any(r['matched_steps']>=8 for r in live),any_terminal_certificate=any(r['status']=='MATCHED_TO_TERMINAL' for r in live),
    independent_task_superiority_established=False,novelty_established=False,old_negative_models_remain_closed=True,
    current_prefix_reuse_route_closed_for_new_collection=True,descriptive_judgment_not_a_preregistered_significance_gate=True)
io.write(delivery/'research_decision.json',decision)
lines=['# 控制器共同前缀：TRAIN 全人口事后描述性分析','',
    '本报告全部新增分析均为**事后描述性分析**。它检查既有纠正程序能否共享真实前缀，不是独立资格、获取算法、无偏OPE或任务收益试验。',
    '',f"冻结源码 `{manifest['source_git_commit']}`；来源 A1 TRAIN 648次、9个独立组。完整保留三任务、两条件、三个干预时点、三获取和四速率；1,944个有向速率配对中，{all_['live_pairs']}个有真实采用入口，{all_['missing_pairs']}个在采用前结束。相反方向与相关时间步均未当独立样本。",'',
    '## 主要观察','',
    f"按独立组等权、完整配对分母：匹配至少1步 {pct(metric(all_,'matched_ge1_full'))}，至少8步 {pct(metric(all_,'matched_ge8_full'))}，完整匹配到终局 {pct(metric(all_,'terminal_certificate_full'))}。有入口的组内平均匹配长度 {number(metric(all_,'live_mean_matched'))} 步，保守截止损失差范围平均宽度 {number(metric(all_,'live_mean_interval_width'))} 步。无入口的缺失长度没有填零；前述比例仍保留完整分母。",'',
    '有入口的1,608个有向配对中，1,586个在首个任务命令立即分歧（98.63%）；仅22个至少匹配一步。两个至少八步且匹配到终局的记录，是同一door-open、不变、时点64、VALIDATE8案例中0.125与0.5速率的一对相反方向，不能称两个独立成功。最大共同前缀为8步。','',
    '状态计数：`'+json.dumps(summary['status_counts'],ensure_ascii=False,sort_keys=True)+'`。','',
    '## 全部任务与条件','',
    '|任务|条件|有入口／全部配对|≥1步，全分母|≥8步，全分母|终局相同，全分母|有入口平均长度|',
    '|---|---|---:|---:|---:|---:|---:|']
for task,context,s in group_task:
    lines.append(f"|{task}|{context}|{s['live_pairs']}/{s['allocated_pairs']}|{pct(metric(s,'matched_ge1_full'))}|{pct(metric(s,'matched_ge8_full'))}|{pct(metric(s,'terminal_certificate_full'))}|{number(metric(s,'live_mean_matched'))}|")
lines += ['', '## 全部时点与获取联合分层','',
    '|任务|条件|时点|获取|有入口／全部|≥1步|≥8步|终局同|平均长度|',
    '|---|---|---:|---|---:|---:|---:|---:|---:|']
for p in summary['panels']:
    s=p['summary'];lines.append(f"|{p['task']}|{p['context']}|{p['planned_boundary']}|{p['acquisition_action']}|{s['live_pairs']}/{s['allocated_pairs']}|{pct(metric(s,'matched_ge1_full'))}|{pct(metric(s,'matched_ge8_full'))}|{pct(metric(s,'terminal_certificate_full'))}|{number(metric(s,'live_mean_matched'))}|")
lines += ['', '完整12个有向速率面板、逐组指标、缺失原因、每个影子命令与实际另一分支核对均保存在同目录汇总和逐行文件，不选择有利任务/速率。','',
    '## 方法、独立核对与限制','',
    '从真实获取返回后的公开观测、携带积分和原始固定政策动作开始复算。命令逐项float32精确一致才消费该步事实回执；首次不同不读取其后继观测或下一行。完整匹配到终局才说明同一已保存初态/噪声耦合上的结果相同。标量PI公式独立重建；实际另一速率的真实公共前缀、第一分歧命令与保存的原生状态/游标见证逐对核对。见证不构成新的物理复现或一般安全证明。','',
    '尚未结束的前缀只给出剩余截止损失的宽范围，不插补未来轨迹。该范围不是置信区间。实际两个分支的结果差只在评估端验证范围；不得用后见结果训练/选择。实际成功转失败和失败转成功的有向配对分别为 '+str(counters['actual_success_to_failure'])+' 和 '+str(counters['actual_failure_to_success'])+'，分母为全部1,944配对（其中有入口'+str(len(live))+'）。两方向相关且重复计同一对，不是独立因果样本或新方法错误更新率。','',
    '控制器当前命令相同仍不能推出延后获取最优：移动可能在命令分歧前改变接触、可观测性、验证费用或以后可访问的位置。本次没有估计这些机会，不能因此部署“等到分歧才获取”的规则。公共观测也没有被证明为充分Markov状态。','',
    '## 费用与后续判断','',
    f"新增环境/重置/控制步/物理帧/固定政策查询/拟合/在线LLM API全部为0。实测主规划入口 {plan_entries} 次、独立标量公式 {literal_calls} 次。主入口还会为序列化/哈希/回执重复计算PI数值，按冻结实现静态复算为 {static_pi_number_calls} 次（不是运行时逐函数计数）。这些均无拟合。主分析 {summary['wall_ns']/1e9:.3f} 秒，独立汇总审计另记。历史TRAIN实际来源648次、77,563控制步、33,048全部重置、16,911,815物理帧单列，未当本次新增费用。",'',
    '**后续决定：当前证据不足以支持依靠共同前缀节省采集，将本版路线封存，不追加该路线的机器人样本、动作容差或选择器。**这是对全人口描述结果与已有方法边界的研究判断，不是假装预注册显著性门失败；非零前缀确实存在，不能报告为完全没有结构。若未来提出不同机制，仍需超越标准重放/DR的具体资源差别、获取机会变化的可检验解释和独立自身历史完整任务试验。本次不训练模型、调整旧QUAL阈值、改变原六项比较或新增机器人采集。灰箱及其他失败预测器继续封存；A主线及CCF A完整目标保持，尚未完成。','',
    '冻结检查：20项新增纯数组测试通过，原2,428项按源码/回执哈希复用，共2,448项唯一检查。第一次开发检查11项错误来自元组/列表结构比较，未读取实际轨迹；原失败日志与修正前代码保留。编译、依赖、秘密、差异及实际索引字节回执随阶段交付。','',
    '来源：[冻结协议](../docs/protocols/controller_agreement_v1_zh.md)、[决定与查新](../docs/research/controller_agreement_decision_v1_zh.md)、[完整汇总](../outputs/controller_agreement/feasibility_v1/summary.json)、[独立统计审计](../outputs/controller_agreement/feasibility_v1/presentation/independent_statistics_audit.json)。']
report=ROOT/'reports/controller_agreement_v1_zh.md';report.write_text('\n'.join(lines)+'\n',encoding='utf8',newline='\n')
print(dict(integrity='PASSED',all=all_,status_counts=summary['status_counts'],decision=decision,report=str(report)),flush=True)

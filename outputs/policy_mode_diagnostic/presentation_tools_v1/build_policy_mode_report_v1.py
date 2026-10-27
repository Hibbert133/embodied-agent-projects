"""Descriptive tables and independent weighted census, no primary math changes."""
from pathlib import Path
from collections import Counter
from time import perf_counter_ns
import csv,json,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
from src.analysis import correction_effect_independent_v1 as independent
from src.analysis.release_learning_guard_v1 import read_only
start=perf_counter_ns();out=ROOT/'outputs/policy_mode_diagnostic/diagnostic_v1';presentation=out/'presentation';presentation.mkdir(exist_ok=False)
complete=io.read(out/'complete.json');manifest=io.read(out/'manifest.json');assert complete['integrity']=='PASSED'
for n,h in complete['artifact_sha256'].items():assert io.sha(out/n)==h,n
guard={}
with read_only(guard):
    windows=io.read(out/'windows.json');panels=io.read(out/'panels.json');trajectories=io.read(out/'trajectories.json')
    assert len(windows)==5832 and len(panels)==2214 and len(trajectories)==648
    census=Counter((r['pair_id'],r['horizon']) for r in windows);assert len(census)==5832 and set(census.values())=={1}
    for p in panels:
        selected=[r for r in windows if r['horizon']==p['horizon'] and all((tuple(r[k]) if k=='rates' else r[k])==(tuple(v) if k=='rates' else v) for k,v in zip(p['axes'],p['values']))]
        assert len(selected)==p['registered'] and dict(Counter(r['status'] for r in selected))==p['statuses']
        actual=[r for r in selected if r['metrics'] is not None];assert len(actual)==p['available'] and len({r['group'] for r in actual})==p['groups']
        if actual:
            w=independent.weights(actual)
            for k in p['metrics']:assert abs(sum(float(q)*r['metrics'][k] for q,r in zip(w,actual))-p['metrics'][k])<=1e-12,(p['axes'],k)
        else:assert p['metrics'] is None
    for r in windows:
        if r['metrics'] is not None:
            if r['task']=='reach-v3':assert r['metrics']['raw_mode_energy']==r['metrics']['sent_mode_energy']==0.
            if r['horizon']==1:assert r['metrics']['raw_total_energy']==r['metrics']['sent_total_energy']==0.
    with (presentation/'all2214_panels.csv').open('x',encoding='utf8',newline='') as f:
        names=['horizon','axes','values','registered','available','groups','metrics','statuses'];writer=csv.DictWriter(f,fieldnames=names);writer.writeheader()
        for r in panels:writer.writerow({k:json.dumps(r[k],ensure_ascii=False) if isinstance(r[k],(list,dict)) else r[k] for k in names})
io.write(presentation/'statistics_audit.json',dict(integrity='PASSED',windows=5832,panels=2214,independent_scalar_group_weights=True,
    reach_negative_control=True,first_step_zero=True,guard=guard,new_physics=0,new_fits=0,online_LLM_API_calls=0,wall_ns=perf_counter_ns()-start))


def n(x):return '缺失' if x is None else f'{x:.6g}'
def weighted_task(task,h):
    rows=[r for r in windows if r['task']==task and r['horizon']==h and r['metrics'] is not None]
    if not rows:return None
    w=independent.weights(rows)
    return dict(available=len(rows),groups=len({r['group'] for r in rows}),
        sent_any_mode_in_window=sum(float(q)*(r['metrics']['sent_mode_nonzero_fraction']>0) for q,r in zip(w,rows)),
        **{k:sum(float(q)*r['metrics'][k] for q,r in zip(w,rows)) for k in rows[0]['metrics']})
global_panels={p['horizon']:p for p in panels if not p['axes']}
decision=dict(classification='POST_HOC_FUNCTIONAL_NOT_PHYSICAL_CAUSAL',no_online_predictive_or_task_qualification=True,
    no_causal_plant_error_attribution=True,no_new_sampling_or_model_training_authorized_by_this_diagnostic=True,
    headlined_horizon=2,task_H2={t:weighted_task(t,2) for t in ('push-v3','reach-v3','door-open-v3')})
io.write(presentation/'decision.json',decision)
lines=['# 政策分支与连续反馈：完整TRAIN函数诊断','',
    '**全部新增分析为事后描述性分析。** 只分解固定政策函数对Z/夹爪命令差的来源，不解释真实植物响应的唯一原因，不构成入口预测、新模型、任务收益、安全或新颖性资格。','',
    f"冻结 `{manifest['source_git_commit']}`。648条既有TRAIN，9组、三任务×两条件×三个时点×三获取×四速率；972个无向实际速率对×六窗，共5,832行，2,214个完整面板。没有读取CAL/TEST/旧QUAL内容选择模型或阈值。",'',
    '## 方法与名字','',
    '“模式项”指同一观测下替换政策叶子造成的函数变化；“连续项”指固定叶子下观测改变造成的函数变化。push和door有接近/下降/推进等位置叶；push还有独立夹爪条件，reach没有这些分支。所有真实采用后政策动作均从当时公开观测精确重建。','',
    '这里的“模式不同”指同一时点两个真实程序选择了不同政策叶，并不统计某一条轨迹自身何时换叶。两个程序也可能同步换叶而没有配对模式差异。','',
    '对两个真实观测与各自真实叶，另计算两个交叉叶函数值，再作两种替换顺序的对称平均。交叉值可能不符合该叶条件，不是执行过的命令或可行物理轨迹。分解分别在原始float32政策输出与clip[-1,1]发送层完成；XY积分不改变Z/夹爪发送层。这是送出命令，未把执行器后续加噪、扰动和最终裁剪冒作相同层次。','',
    '## 预定H2全任务描述','',
    '|任务|完整窗口／324|可用组|窗口出现任一Z/夹爪差|窗口出现模式发送项|实际发送差L1|模式发送项L1|连续发送项L1|',
    '|---|---:|---:|---:|---:|---:|---:|---:|']
for task in ('push-v3','reach-v3','door-open-v3'):
    v=weighted_task(task,2)
    if v:lines.append(f"|{task}|{v['available']}/324|{v['groups']}|{100*v['sent_any_difference_in_window']:.3f}%|{100*v['sent_any_mode_in_window']:.3f}%|{n(v['sent_total_L1'])}|{n(v['sent_mode_L1'])}|{n(v['sent_state_L1'])}|")
    else:lines.append(f'|{task}|0/324|0|缺失|缺失|缺失|缺失|缺失|')
lines += ['', 'L1为Z/夹爪两个归一化命令分量及窗内步的均值，再按独立组→任务条件→获取节点→率对逐层等权。这里的分量可以抵消，模式L1和连续L1不能当作实际差的因果占比。任一差异的百分比只表示非零，不表示幅度大。','',
    '## 六窗完整总表','',
    '|H|完整／972|组|任一发送差窗口|原始总能量|原始模式能量|原始连续能量|原始交叉项|发送总L1|发送模式L1|发送连续L1|',
    '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
for h in (1,2,4,8,16,32):
    p=global_panels[h];v=p['metrics']
    if v:lines.append(f"|{h}|{p['available']}/972|{p['groups']}|{100*v['sent_any_difference_in_window']:.3f}%|{n(v['raw_total_energy'])}|{n(v['raw_mode_energy'])}|{n(v['raw_state_energy'])}|{n(v['raw_cross_energy'])}|{n(v['sent_total_L1'])}|{n(v['sent_mode_L1'])}|{n(v['sent_state_L1'])}|")
    else:lines.append(f"|{h}|0/972|0|缺失|缺失|缺失|缺失|缺失|缺失|缺失|缺失|")
lines += ['', '恒等式为总能量＝模式能量＋连续能量＋交叉项；交叉项可负。H越长可用人口越少，不能把表中变化唯一解释为时间延迟或模式失配。H1同一真实观测决定相同原始政策与Z/夹爪，全部分解恒零，独立核对通过。reach的模式项在所有实际窗口恒零。','',
    '## 三任务全部窗口','',
    '|任务|H|完整／324|两程序模式不同的步比例|发送差L1|模式项L1|连续项L1|',
    '|---|---:|---:|---:|---:|---:|---:|']
for task in ('push-v3','reach-v3','door-open-v3'):
    for h in (1,2,4,8,16,32):
        v=weighted_task(task,h)
        if v:lines.append(f"|{task}|{h}|{v['available']}/324|{100*v['mode_changed_fraction']:.3f}%|{n(v['sent_total_L1'])}|{n(v['sent_mode_L1'])}|{n(v['sent_state_L1'])}|")
        else:lines.append(f'|{task}|{h}|0/324|缺失|缺失|缺失|缺失|')
lines += ['', '完整的任务×条件×时点×获取×率对×H、逐组及全部边际表保存在all2214_panels.csv和panels.json；逐步代数分量、648条轨迹模式次数及缺失均保留。没有选有利任务/窗口或将相关时间步当独立样本。','',
    '## 审计、成本与限制','',
    '独立标量实现禁用主签名、叶和分解函数；另以已有独立层级权重复算全部面板。实际政策输出的float32字节、发送Z/夹爪、首分歧对齐及代数恒等式均核对。共享已审计来源解析器与独立权重参考明确披露；这是第二实现审计，不是独立机构或物理重模拟。','',
    f"新增环境创建、重置、控制步、物理帧、机器人政策查询、模型拟合和在线LLM API全部0。科学主叶展开{complete['leaf_counts']['main_leaf_evaluations']}次、独立标量展开{complete['leaf_counts']['independent_leaf_evaluations']}次，主＋数学核对耗时{complete['wall_ns']/1e9:.3f}秒；额外统计/展示另记。合成开发18次＋正式18次安装政策函数查询单列，不是机器人步骤。原开发1项夹具失败及配置exclusive写入失败保留，未读真实轨迹、未改变分解公式。历史来源648次、77,563步、33,048全部重置、16,911,815帧另列。",'',
    '旧记录没有逐步接触力/接触对；没有无噪声物理对照。模式项仅证明政策函数结构，不能证明它导致植物预测失败；真实状态变化、接触、动作反馈、噪声及执行器最终裁剪仍可能共同作用。交叉叶不是物理反事实。未来模式在入口尚不可知，本次并未预测它。','',
    '15项新增纯数组测试与原2,448项源码/回执绑定复用，共2,463项唯一检查。原六项比较、native和响应资格负结果不变；不因本诊断调模型、阈值、任务或追加人口。后续需要有区别的可计算机制、强廉价模式控制/完整成本Q或DR/任务相关获取参考以及独立自身历史完整任务验证；当前仍不能宣称CCF A目标完成。','',
    '来源：[冻结协议](../docs/protocols/policy_mode_diagnostic_v1_zh.md)、[决定与直接先例](../docs/research/policy_mode_diagnostic_decision_v1_zh.md)、[完整面板](../outputs/policy_mode_diagnostic/diagnostic_v1/panels.json)、[独立审计](../outputs/policy_mode_diagnostic/diagnostic_v1/independent_audit.json)。']
report=ROOT/'reports/policy_mode_diagnostic_v1_zh.md';report.write_text('\n'.join(lines)+'\n',encoding='utf8',newline='\n')
print(dict(integrity='PASSED',global_H2=global_panels[2],task_H2=decision['task_H2'],report=str(report)),flush=True)

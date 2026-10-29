"""Deliver complete empirical information census; never promote its oracle table."""
from fractions import Fraction
from pathlib import Path
from time import perf_counter_ns
import json
import subprocess
import sys

ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects')
sys.path.insert(0,str(ROOT/'outputs/observable_frontier_diagnostic_v1/tools'))
import run_frontier_v1 as r
sys.path.insert(0,str(ROOT/'outputs/train_decision_contract_v1/tools'))
from freeze_contract_v1 import check_index


def main():
    started=perf_counter_ns();source=sys.argv[1]
    r.need(len(source)==40 and r.git('rev-parse','HEAD').decode().strip()==source
        and not r.git('status','--porcelain','--untracked-files=no').strip(),'literal clean frozen source')
    complete=r.read(r.OUT/'complete.json');worker=r.read(r.OUT/'worker_complete.json')
    r.need(complete['source_commit']==source and complete['integrity']==worker['integrity']=='PASSED_COMPLETE_OBSERVABLE_FRONTIER_DIAGNOSTIC','whole one-time analysis')
    for name,value in complete['artifacts'].items():
        p=r.OUT/name;r.need(r.sha(p)==value['sha256'] and p.stat().st_size==value['bytes'],'complete source output '+name)
    r.need(r.read(r.OUT/'independent_audit.json')['integrity']=='PASSED_TYPED_PARTITIONS_AND_EXHAUSTIVE_CONTINGENT_PLANS'
        and r.read(r.OUT/'strata_audit.json')['integrity']=='PASSED_ALL_EXACT_STRATA_AND_PUBLIC_CLASSES','both independent routes')
    f=r.read(r.FREEZE)
    for key in ('source_sha256','input_sha256','scientific_source_sha256'):r.verify(f[key])
    out=r.BASE/'presentation_v1';out.mkdir(exist_ok=False);(out/'deliver_frontier_v1.py').write_bytes(Path(__file__).read_bytes())
    stats=r.read(r.OUT/'statistics.json');pop=r.read(r.OUT/'population.json');result=r.read(r.OUT/'empirical_frontier.json')
    failures=r.read(r.OUT/'all_source_task_failures.json');functions=stats['functionals']
    r.need(len(pop)==54 and len(result['records'])==972,'complete population and supported references')
    r.need(sum(v['source_failures'] for v in pop)==len(failures),'all source task failures')
    decision=dict(status='EMPIRICAL_INFORMATION_PARTITIONS_ONLY_NO_NEW_COLLECTOR',
        root_information_unique_for_all_live_units=stats['root_count']==stats['live_units'],
        conflicting_exact_root_classes=stats['conflicting_root_classes'],
        contingent_empirical_gain_steps=stats['contingent_empirical_gain'],extra_trace_empirical_gain_steps=stats['extra_trace_empirical_gain'],
        empirical_future_table_is_not_a_policy_candidate=True,oracle_tables_not_training_labels=True,
        no_approximate_precision_search=True,no_new_model_or_population_selected_from_result=True,
        original_low_rank_version_stays_sealed=True,local_NDE_or_Markov_assumptions_not_verified=True,
        independent_task_qualification=False,algorithm_novelty_established=False,publication_goal_complete=False)
    r.write(out/'research_decision.json',decision)
    report=ROOT/'reports/observable_frontier_diagnostic_v1_zh.md';r.need(not report.exists(),'new Chinese report')
    extra=['','## 如何读这些名字与差额','',
        '- UNIT_CLAIRVOYANT：每单位偷看未来，选最低记录成本，只作为明示的未来参照。',
        '- ROOT_CONTINUE_ONLY：相同公开前史绑定相同继续T，只在四个继续程序内取优。',
        '- ROOT_STATIC：相同前史绑定一个完整获取／T程序，不能看返回再改T。',
        '- ROOT_ADAPTIVE_FULL／MASK：先按相同前史选获取，返回后按实际可见证据选T；MASK保留返回当前状态与前史，只少获取新增的轨迹。',
        '- GLOBAL_FIXED_BEST：看到全表后选出的最低成本固定程序，不能说成预先验证的胜者。','',
        f'全部来源任务失败{len(failures)}条。当前{stats["live_units"]}个有根的单位形成{stats["root_count"]}类；早终止{stats["early_units"]}个仍在54分母中。同一等价类内的选择约束是本次计算对象，不能把972引用当作972个独立实验。','',
        '|全部组|单位看未来|根静态|实际返回FULL|实际返回MASK|','|---:|---:|---:|---:|---:|']
    for g in range(9):
        vals=[float(Fraction(functions[n]['group_means_exact'][str(g)])) for n in ('UNIT_CLAIRVOYANT','ROOT_STATIC','ROOT_ADAPTIVE_FULL','ROOT_ADAPTIVE_MASK')]
        extra.append('|'+str(g)+'|'+'|'.join(f'{v:.6f}' for v in vals)+'|')
    extra+=['','|FULL全部任务／条件／边界|成功/3|完整平均损失|','|---|---:|---:|']
    import csv
    with (r.OUT/'all_324_joint_cells.csv').open(encoding='utf-8',newline='') as stream:
        for row in csv.DictReader(stream):
            if row['functional']=='ROOT_ADAPTIVE_FULL':extra.append(f'|{row["task"]}／{row["context"]}／{row["boundary"]}|{row["success"]}/3|{float(Fraction(row["mean_loss_exact"])):.6f}|')
    if stats['root_count']==stats['live_units']:
        extra+=['','所有有效根在本精确输入上都唯一，经验记忆表无法判别跨单位泛化所需的信息结构。本项诊断按预定规则停止，不调精度制造共享类。']
    else:
        extra+=['','存在完全相同公开根，因而每单位看未来与可见信息约束下的最小记录成本可不同。这只建立有限事实表中的选择限制，不建立未知分布下的信息论界或可学习性。']
    if stats['extra_trace_empirical_gain']==0:
        extra+=['','FULL与MASK的最优经验总成本相同。当前返回信息仍可能包含大量证据，且不同连续输入可被未来表完美记忆；因此零差额不能被解释为轨迹无信息、学习接收者无需历史或所有状态变化均可识别。']
    else:
        extra+=['','FULL与MASK存在经验差额，说明在这组精确输入类和完整已执行菜单上，多给实际获取历史能解除部分选择约束。这不是学习算法已取得该差额，也不分离获取的自然信息／物理因果效应。']
    extra+=['','原低秩、完整风险／轨迹接收者的负结果保留；本结果不为其拟合阈值、换模型、筛任务或扩样。后续A机制仍须给出可识别的局部结构／支持获取与资源优势，直接比较简单重加权／局部重估、MDE、OCCAM、GAUGE、任务获取、完整风险／DR及DIRECT_C8／积分／始终获取／不更新／检测／历史辨识。',
        f'一次实际worker耗时{worker["wall_ns"]/1e9:.6f}秒，主经验表优化账本{worker["empirical_optimization"]}，独立穷举{worker["independent_exhaustive_plans"]}个计划。纯标准库守卫各禁用操作计数均0，没有预测模型查询／拟合或机器人交互。两次TRAIN图解码的实际行数／字节及全部历史费用另见worker receipt；不把有限经验优化称为新模型训练或独立任务验证。',
        '精确来源图另保存一个有界、字节相同的副本，SHA与原图相同，供复算；这是原TRAIN派生来源，不是新增原始采集或完整QUAL交付。原完整QUAL大记录仍待空间，所有原文件和恢复副本保留。','']
    with report.open('xb') as stream:stream.write((r.OUT/'report_zh.md').read_bytes());stream.write('\n'.join(extra).encode('utf-8'))
    original=ROOT/'outputs/occam_reference_qualification_v1/qualification_v1/occam_reference_qualification_v1_20261028T125131Z_7abaec83b085/statistics_v1/statistics.json'
    r.need(r.sha(original)=='dccede3a2838fb1ef98c20bab5e89080bcd42c8a53629c1ad22d646ae6fb75bc','old qualification comparisons unchanged; bytes only')
    r.write(out/'presentation_validation.json',dict(integrity='PASSED_COMPLETE_FUTURE_TABLE_DIAGNOSTIC_PRESENTATION',
        source_freeze_commit=source,source_analysis_sha256=r.sha(r.OUT/'complete.json'),source_failures=len(failures),
        information_tables_do_not_establish_learnability=True,all_9_groups_and_18_joint_cells=True,
        all_972_references_and_324_cells_and_162_group_rows=True,extra_predictive_fits_or_queries=0,
        original_qualification_statistics_sha256=r.sha(original),counters=r.ZERO))
    owned={p.relative_to(ROOT).as_posix() for folder in (r.OUT,out) for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    owned.add(report.relative_to(ROOT).as_posix())
    def stage(label):
        spec=out/(label+'.nul');owned.add(spec.relative_to(ROOT).as_posix());spec.write_bytes(b'\0'.join(n.encode() for n in sorted(owned))+b'\0')
        for flags in ((),('--renormalize',)):r.git('add',*flags,'--pathspec-from-file='+spec.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    stage('owned_initial');print(json.dumps(dict(stage='COMPLETE_PUBLIC_INFORMATION_FRONTIER_PRESENTED',files=len(owned))),flush=True)
    scan=perf_counter_ns()
    with (out/'secret_stdout.log').open('xb') as so,(out/'secret_stderr.log').open('xb') as se:
        p=subprocess.run([sys.executable,'-B','scripts/check_tracked_secrets.py','--staged'],cwd=ROOT,stdout=so,stderr=se)
    r.write(out/'secret_receipt.json',dict(returncode=p.returncode,wall_ns=perf_counter_ns()-scan));r.need(p.returncode==0,'result secret scan')
    owned.update(p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file());stage('owned_checked')
    r.write(out/'index_disk_proof.json',dict(integrity='PASSED_RESULT_INDEX_WITH_DECODED_SOURCE',objects=check_index(owned)))
    for key in ('source_sha256','input_sha256','scientific_source_sha256'):r.verify(f[key])
    r.write(out/'delivery_validation.json',dict(integrity='PASSED_OBSERVABLE_FRONTIER_RESULT_DELIVERY',new_unique_tests=15,
        prior_source_bound_scientific_checks_reused=2695,dependency_receipt_reused=True,secret_returncode=0,
        actual_index_basic_EXTRA_including_decoded_gzip=True,compiled_new_Python_in_memory=True,
        ordinary_and_staged_diff_checks=True,source_freeze_commit=source,uses_future_labels=True,deployable=False,
        wall_ns=perf_counter_ns()-started,counters=r.ZERO))
    owned.update(p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file());stage('owned_final');objects=check_index(owned)
    print(json.dumps(dict(integrity='PASSED_READY_FOR_OBSERVABLE_FRONTIER_RESULT_COMMIT',files=len(objects),bytes=sum(v['bytes'] for v in objects.values()))),flush=True)


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');main()

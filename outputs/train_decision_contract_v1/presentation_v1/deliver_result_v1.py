"""Present only completed frozen audit outputs; create-only delivery/byte proof."""
from pathlib import Path
from time import perf_counter_ns
from collections import defaultdict
import csv
import hashlib
import json
import subprocess
import sys

ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects')
BASE=ROOT/'outputs/train_decision_contract_v1'
sys.path.insert(0,str(BASE/'tools'))
import run_contract_v1 as r
from freeze_contract_v1 import check_index


def main():
    started=perf_counter_ns()
    source=r.git('rev-parse','HEAD').decode().strip()
    r.need(source=='28403b6a106e1c482f5547880489c0987ac5e5f5' and not r.git('status','--porcelain','--untracked-files=no').strip(),'clean frozen source')
    done=r.read(r.OUT/'complete.json');worker=r.read(r.OUT/'worker_complete.json');proof=r.read(r.OUT/'audit.json')
    r.need(done['source_commit']==source and done['integrity']==worker['integrity']=='PASSED_COMPLETE_TRAIN_DECISION_CONTRACT_AUDIT'
        and proof['integrity']=='PASSED_INDEPENDENT_TEMPORAL_CONTRACT_RECONSTRUCTION','complete independent data audit')
    for name,h in done['artifact_sha256'].items():r.need(r.sha(r.OUT/name)==h,'actual output receipt '+name)
    f=r.read(r.FREEZE);r.verify(f['source_sha256']);r.verify(f['input_sha256']);r.verify(f['scientific_source_sha256'])
    result=r.read(r.OUT/'statistics.json');rows=r.read(r.OUT/'case_contracts.json')
    out=BASE/'presentation_v1';out.mkdir(exist_ok=False)
    (out/'deliver_result_v1.py').write_bytes(Path(__file__).read_bytes())
    groups=defaultdict(list)
    for row in rows:groups[(row['spec']['cohort'],row['spec']['group'])].append(row)
    group_rows=[]
    for (cohort,group),rs in sorted(groups.items()):
        group_rows.append(dict(cohort=cohort,group=group,cases=len(rs),task_failures=sum(not x['success'] for x in rs),
            before_views=sum(x['before'] is not None for x in rs),live_return_views=sum(x['after'] is not None and x['after']['decision_required'] for x in rs),
            static_TRAIN_labels=sum(x['labels']['static_TRAIN_supervised_label_admitted'] for x in rs),
            random_constant=sum(x['labels']['observed_constant_random_sequence'] for x in rs)))
    coverage=[]
    for task in ('push-v3','reach-v3','door-open-v3'):
        for context in ('UNCHANGED','CHANGED'):
            for boundary in (16,32,64):
                for arm in ('CONTINUE','VALIDATE8','MOVE_MEASURE'):
                    fixed=[x for x in rows if x['spec']['cohort']=='TRAIN' and x['spec']['behavior']=='BLOCK_FIXED'
                        and (x['spec']['task'],x['spec']['context'],x['spec']['planned_boundary'],x['spec']['acquisition_action'])==(task,context,boundary,arm)]
                    r.need(len(fixed)==6,'all six independent TRAIN groups per boundary')
                    for t in (.125,.5,2.,8.):
                        observed=[x for x in fixed if x['labels']['static_TRAIN_supervised_label_admitted'] and x['labels']['actual_rates'][0]==t]
                        coverage.append(dict(task=task,context=context,planned_boundary=boundary,acquisition_action=arm,
                            target_static_rate=t,allocated_BLOCK_cases=6,observed_factual_labels=len(observed),
                            independent_groups=len({x['spec']['group'] for x in observed}),
                            not_an_observed_label=6-len(observed),not_a_counterfactual_completion=True))
    r.need(len(group_rows)==19 and len(coverage)==216,'all source groups and static-target cells')
    for name,table in (('all_19_source_groups.csv',group_rows),('all_216_static_label_coverage_cells.csv',coverage)):
        with (out/name).open('x',encoding='utf-8',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=tuple(table[0]));writer.writeheader();writer.writerows(table)
    # Independent count route: target records, not first-rate extraction above.
    actual=sum(x['observed_factual_labels'] for x in coverage)
    targets=sum(v['target_label_status']=='FACTUAL_STATIC_TRAIN' for x in rows for v in x['labels']['static_targets'])
    r.need(actual==targets==result['by_cohort']['TRAIN']['static_TRAIN_labels'],'all coverage and target-label totals')
    report=ROOT/'reports/train_decision_contract_v1_zh.md'
    r.need(not report.exists(),'create-only report')
    report.write_bytes((r.OUT/'report_zh.md').read_bytes())
    c=result['by_cohort']['TRAIN'];n=result['by_cohort']['NATIVE']
    decision=ROOT/'docs/research/correction_scope_after_train_contract_v1_zh.md'
    text=f'''# A主线：完整后继标签审计后的判断 v1

2026-10-29，事后研究判断。A保持accepted；旧接收者及所有负结果保持封存。冻结代码{source}先于实际读取；完整数据审计独立重建通过。本页不是新训练／采集授权协议或算法贡献。

## 已确定的事实

TRAIN全部648、18独立组、失败{c['task_failures']}完整登记；NATIVE36仅验证，失败{n['task_failures']}，不进入训练。TRAIN实际移动前投影{c['before_views']}，返回后投影{c['after_views']}，返回后仍需决策{c['live_after_views']}，实际窗口{c['windows']}。完整36来源任务条件边界格和19来源组保留，没有按可用性删分母。

可准入的实际固定T完整事实监督标签{c['static_TRAIN_labels']}条，每条仅对应实际执行的一个T。另有{c['constant_random']}条RANDOM观测序列恰好固定，不因此成为未加权固定T标签。216个TRAIN任务／条件／边界／获取／T覆盖格明确保存观察标签数及缺失，不补造四T反事实表。

前／后公开输入由实际保存积分、状态、历史和预算重建，预分配行为、未来获取臂、未来T和调度哈希未作为特征。输入相等／差异只针对明示投影，完整组件原因和缺失保留。新环境、重置、物理帧、策略／模型查询、拟合、训练、episode种子和在线LLM全为零。

## 后续判断

**当前数据允许研究一个有限的事实完整程序风险强参考；不支持把所有随机终局当成四个固定程序的训练标签，也不自动证明适应性获取的新方法可学习。** 原行为支持和接收者首次分歧审计继续复用；不用QUAL补齐TRAIN，不追加当前人口，不把首次短窗拟合好当完整收益。

下一独立协议必须先明确目标：若学习固定完整后继风险，仅用真实BLOCK标签，按独立group划分并保留支持不足；若评价变增益或自适应后继，须明确完整路径支持／序贯估计假设或另行分配独立训练数据。当前没有离线政策价值估计，不能把输入别名或观察兼容率称为因果不可识别或可部署增益。

完整风险／DR是强参考，不是当前新颖性。潜在新机制仍须写出对获取改变状态、纠正改变后续访问及模型适用性的具体结构区别，并通过等价性与原始文献检查。若只是同输入多头、普通门控、收益回归、控制混合或更换预测器，保持原否决。任何训练配置、组划分、算法、失败处理和预算必须另行冻结；不能因本审计通过就复活旧bank、延长窗口或调gain。

最终任务比较仍采用截止损失优先，并完整披露成功率、实际获取成本、错误更新及所有失败；强基线含DIRECT_C8、积分补偿、固定PI、始终探测／不更新、被动适应、检测／历史辨识、任务获取、重加权、完整风险／DR。最终评价使用新方法自身形成的独立时序历史，不能以旧来源的离线建议代替。

## 资源与交付边界

本次worker耗时{worker['wall_ns']/1e9:.3f}秒，父进程总耗时{done['total_parent_wall_ns']/1e9:.3f}秒（不含冻结、秘密扫描、呈现及归档），全部IO单列于回执。22项新合成测试；原2695项科学源码／编译回执按SHA复用，不能相加称新实验样本。原始科学统计不变。

历史来源TRAIN648：80390控制步／33048全部重置／16925950物理帧；NATIVE36：5399／1836／944995，合计684：85789／34884／17870945。此前1740完整任务资格费用和训练NN的9000次联合AdamW仍见原成本附录，不重复按程序计费。新审计无模型训练。

完整QUAL raw ZIP、分片与三次恢复仍待磁盘空间，原始本地数据未删；本审计不替代完整数据交付。当前只完成数据准入证据，尚无合格新机制、独立完整任务优势或CCF A目标完成证据。
'''
    with decision.open('x',encoding='utf-8',newline='\n') as stream:stream.write(text)
    r.write(out/'presentation_validation.json',dict(integrity='PASSED_COMPLETE_OUTPUT_PRESENTATION',
        source_freeze_commit=source,analysis_complete_sha256=r.sha(r.OUT/'complete.json'),
        group_rows=19,static_target_coverage_cells=216,factual_static_labels=actual,
        independent_target_status_total=targets,original_gzip_parses=0,counters=r.ZERO,
        presentation_code_finalized_after_analysis=True,not_a_new_semantic_population_analysis=True))
    owned={p.relative_to(ROOT).as_posix() for folder in (r.OUT,out) for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    owned|={report.relative_to(ROOT).as_posix(),decision.relative_to(ROOT).as_posix()}
    def stage(label):
        spec=out/(label+'.nul');owned.add(spec.relative_to(ROOT).as_posix());spec.write_bytes(b'\0'.join(n.encode() for n in sorted(owned))+b'\0')
        for flags in ((),('--renormalize',)):r.git('add',*flags,'--pathspec-from-file='+spec.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    stage('owned_initial');print(json.dumps(dict(stage='COMPLETED_AUDIT_OUTPUTS_PRESENTED',files=len(owned),TRAIN_static_labels=actual)),flush=True)
    scan=perf_counter_ns()
    with (out/'secret_stdout.log').open('xb') as so,(out/'secret_stderr.log').open('xb') as se:
        p=subprocess.run([sys.executable,'-B','scripts/check_tracked_secrets.py','--staged'],cwd=ROOT,stdout=so,stderr=se)
    r.write(out/'secret_receipt.json',dict(returncode=p.returncode,wall_ns=perf_counter_ns()-scan))
    r.need(p.returncode==0,'result secret scan')
    owned.update(p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file());stage('owned_checked')
    r.write(out/'index_disk_proof.json',dict(integrity='PASSED',objects=check_index(owned)))
    r.verify(f['source_sha256']);r.verify(f['input_sha256']);r.verify(f['scientific_source_sha256'])
    r.write(out/'delivery_validation.json',dict(integrity='PASSED_AUDIT_RESULT_DELIVERY',
        new_unique_tests=22,source_bound_scientific_checks_reused=2695,no_simulation_tests_repeated=True,
        source_freeze_commit=source,secret_returncode=0,actual_index_EXTRA_scan=True,
        ordinary_and_staged_diff_checks=True,dependency_and_compile_receipts_source_bound_reused=True,
        tested_source_sha256=f['source_sha256'],wall_ns=perf_counter_ns()-started,counters=r.ZERO))
    owned.update(p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file());stage('owned_final')
    objects=check_index(owned)
    print(json.dumps(dict(integrity='PASSED_READY_FOR_TRAIN_CONTRACT_RESULT_COMMIT',files=len(objects),bytes=sum(v['bytes'] for v in objects.values()))),flush=True)


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');main()

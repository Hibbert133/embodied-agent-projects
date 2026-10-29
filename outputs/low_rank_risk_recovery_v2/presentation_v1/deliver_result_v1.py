"""Present all predeclared cells, failures and paired choices from frozen outputs."""
from pathlib import Path
from time import perf_counter_ns
from fractions import Fraction
import csv
import json
import subprocess
import sys
import zipfile
import numpy as np

ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');BASE=ROOT/'outputs/low_rank_risk_pilot_v1'
sys.path.insert(0,str(BASE/'tools'))
import run_rank_v1 as r
sys.path.insert(0,str(ROOT/'outputs/low_rank_risk_recovery_v2/tools'))
import run_saved_v2 as recover
BASE=recover.BASE
r.OUT=recover.OUT
r.FREEZE=recover.FREEZE
sys.path.insert(0,str(ROOT/'outputs/train_decision_contract_v1/tools'))
from freeze_contract_v1 import check_index


def csv_write(path,rows):
    with path.open('x',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=tuple(rows[0]));writer.writeheader();writer.writerows(rows)


def main():
    started=perf_counter_ns();source=sys.argv[1]
    r.need(len(source)==40 and r.git('rev-parse','HEAD').decode().strip()==source
        and not r.git('status','--porcelain','--untracked-files=no').strip(),'literal clean scientific source')
    complete=r.read(r.OUT/'complete.json');worker=r.read(r.OUT/'worker_complete.json')
    r.need(complete['source_commit']==source and complete['integrity']==worker['integrity']=='PASSED_READ_ONLY_SAVED_MODEL_RECOVERY','complete frozen pilot')
    r.need(r.read(r.OUT/'model_audit.json')['integrity']=='PASSED_SAVED_SOLUTION_ALGEBRA_AND_LEGACY_BASELINE'
        and r.read(r.OUT/'statistics_audit.json')['integrity']=='PASSED_COMPLETE_54_UNIT_31_PROGRAM_RECONSTRUCTION','both independent audits')
    for name,item in complete['artifacts'].items():r.need(r.sha(r.OUT/name)==item['sha256'] and (r.OUT/name).stat().st_size==item['bytes'],'complete recorded artifact '+name)
    freeze=r.read(r.FREEZE);r.verify(freeze['source_sha256']);r.verify(freeze['input_sha256']);r.verify(freeze['scientific_source_sha256'])
    out=BASE/'presentation_v1';out.mkdir(exist_ok=False);(out/'deliver_result_v1.py').write_bytes(Path(__file__).read_bytes())
    typed={}
    for p in recover.ORIGINAL.rglob('*.npz'):
        with zipfile.ZipFile(p) as z:
            r.need(all(n.endswith('.npy') and '/' not in n and '\\' not in n for n in z.namelist()),'only flat numeric NPY members')
        with np.load(p,allow_pickle=False) as arrays:
            r.need(all(arrays[k].dtype.kind in 'iuf' and np.isfinite(arrays[k]).all() for k in arrays.files),'numeric finite arrays only; no strings or pickle')
            typed[p.relative_to(recover.ORIGINAL).as_posix()]=dict(sha256=r.sha(p),bytes=p.stat().st_size,
                arrays={k:dict(shape=list(arrays[k].shape),dtype=str(arrays[k].dtype),nbytes=arrays[k].nbytes) for k in arrays.files})
    r.write(out/'numeric_container_audit.json',dict(integrity='PASSED_ALL_NPZ_NUMERIC_NO_OBJECT_OR_STRING_PAYLOAD',files=typed,
        numeric_member_schema_replaces_plaintext_secret_scanning_of_binary_arrays=True))
    r.write(out/'failed_invocation_outer_timing.json',dict(
        timing_source='exec_command returned wall_time_seconds, not persisted worker self-timing',
        initial_training_parent_wall_seconds=6.403474,first_read_only_recovery_parent_wall_seconds=4.7688939,
        these_include_process_startup_and_parent_work=True,exact_failed_worker_fit_time_unavailable=True,
        original_guard_blocked_stdlib_codec_read=True,original_failed_guard_not_claimed_all_zero=True,
        initial_models_not_refit=True,first_recovery_failed_audit_assertion=True))
    population=r.read(r.OUT/'population.json');selected=r.read(r.OUT/'selected_factual_outcomes.json');statistics=r.read(r.OUT/'statistics.json')
    index={(x['model'],x['unit_index']):x for x in selected};cells=[];group_rows=[];harm=[]
    for name,info in statistics['programs'].items():
        records=[index[(name,i)] for i in range(54)];bad=good=same=changed=decisions=stf=fts=severity=benefit=0
        for rec in records:
            unit=population[rec['unit_index']];chosen=rec['selected_index']
            if chosen is None:delta=0
            else:
                decisions+=1;changed+=int(chosen%4!=1);baseline=4*(chosen//4)+1
                delta=rec['loss']-unit['losses'][baseline]
                stf+=int(unit['successes'][baseline] and not rec['success']);fts+=int(rec['success'] and not unit['successes'][baseline])
            bad+=int(delta>0);good+=int(delta<0);same+=int(delta==0);severity+=max(0,delta);benefit+=max(0,-delta)
        r.need(bad+good+same==54,'all paired rate outcomes')
        harm.append(dict(model=name,cases=54,decisions=decisions,changed_rate_choices=changed,
            adverse_rate_choices=bad,improved_rate_choices=good,equal_rate_outcomes=same,
            adverse_severity_steps=severity,improvement_steps=benefit,success_to_failure=stf,failure_to_success=fts,
            comparator='SAME_ACQUISITION_T0.5_ACTUAL_COMPLETE_BRANCH',post_hoc_descriptive_not_causal=True))
        for g in range(9):group_rows.append(dict(model=name,group=g,cases=6,mean_deadline_loss=info['group_means'][str(g)]))
        for task in ('push-v3','reach-v3','door-open-v3'):
            for context in ('UNCHANGED','CHANGED'):
                for boundary in (16,32,64):
                    rs=[rec for rec in records if (population[rec['unit_index']]['task'],population[rec['unit_index']]['context'],population[rec['unit_index']]['boundary'])==(task,context,boundary)]
                    r.need(len(rs)==3,'all 18 task/context/boundary cells')
                    total=sum(x['loss'] for x in rs)
                    cells.append(dict(model=name,task=task,context=context,boundary=boundary,cases=3,
                        success=sum(x['success'] for x in rs),total_deadline_loss=total,mean_deadline_loss_exact=str(Fraction(total,3)),
                        early_no_decision=sum(x['selected_index'] is None for x in rs)))
    failures=[]
    for u in population:
        for j,success in enumerate(u['successes']):
            if not success:failures.append(dict(unit_index=u['unit_index'],group=u['group'],task=u['task'],context=u['context'],boundary=u['boundary'],
                program_index=j,loss=u['losses'][j],actual_steps=u['actual_steps'][j],source_case_key=json.dumps(u['source_case_keys'][j],ensure_ascii=False),source_case_sha256=u['source_case_sha256'][j]))
    r.need(len(cells)==558 and len(group_rows)==279 and len(harm)==31,'complete report panels')
    # Independent scalar route: sums over cells and over groups must reconstruct
    # every program's total; paired severity differences must reconstruct all
    # corresponding same-acquisition actual leaf comparisons.
    for name,info in statistics['programs'].items():
        from_cells=sum(x['total_deadline_loss'] for x in cells if x['model']==name)
        from_records=sum(x['loss'] for x in selected if x['model']==name)
        r.need(from_cells==from_records and abs(from_records/54-info['mean_deadline_loss'])<1e-10,'independent complete cell totals')
        signed=sum(index[(name,u['unit_index'])]['loss']-u['losses'][4*(index[(name,u['unit_index'])]['selected_index']//4)+1]
            for u in population if index[(name,u['unit_index'])]['selected_index'] is not None)
        h=next(x for x in harm if x['model']==name);r.need(signed==h['adverse_severity_steps']-h['improvement_steps'],'all paired severity totals')
    csv_write(out/'all_558_task_condition_boundary_cells.csv',cells);csv_write(out/'all_279_group_program_rows.csv',group_rows)
    csv_write(out/'all_31_paired_rate_choice_panels.csv',harm)
    r.write(out/'all_source_task_failures.json',failures)
    decision=dict(primary_model='RBF_RR2',necessary_development_point_condition=statistics['necessary_development_point_condition'],
        status='DEVELOPMENT_NECESSARY_POINT_CONDITION_ONLY' if statistics['necessary_development_point_condition'] else 'CLOSED_NEGATIVE_THIS_LOW_RANK_VERSION',
        primary_differences=statistics['primary_development_differences'],no_best_secondary_promoted=True,
        independent_task_qualification=False,algorithm_novelty_established=False,new_collection_authorized_by_result=False,
        original_scientific_qualification_unchanged=True)
    r.write(out/'research_decision.json',decision)
    report=ROOT/'reports/low_rank_risk_pilot_v1_zh.md';r.need(not report.exists(),'new report only')
    supplement=['','## 完整分格与失败交付','',
        f'来源648条真实执行中的{len(failures)}条任务失败全部列出；558任务／条件／边界格、279逐组程序行和31配对选率面板保留。它们是同一旧来源的不同支持选择，不是新增1674次机器人运行。',
        f'研究决定：**{decision["status"]}**。不按次要核／秩结果更换主候选，不用PCA、raw或共同方向的区别代替原创机制。','',
        '|主候选任务|条件|边界|成功/3|完整平均损失|','|---|---|---:|---:|---:|']
    for x in cells:
        if x['model']=='RBF_RR2':supplement.append(f'|{x["task"]}|{x["context"]}|{x["boundary"]}|{x["success"]}/3|{float(Fraction(x["mean_deadline_loss_exact"])):.6f}|')
    supplement+=['','同获取T.5的“不利选率”是实际配对来源结局差，包含后继状态变化和单次噪声实现；不能把它命名为期望因果有害更新率或唯一原因。完整分母54含所有未决策案例，早终止不冒充有效选择。',
        f'worker实际{worker["wall_ns"]/1e9:.6f}秒；全部新风险解、矩阵运算、模型预测与源IO见ledger，原有8模型费用另列。共享base文件的实际NPZ字节共{sum(v["bytes"] for k,v in typed.items() if k.startswith("models/"))}，训练数组缓存／图表另计；不把小输出秩称为整个系统同倍压缩。',
        '全秩冻结基线逐参数一致与独立保存参数代数证书、双公式预测核对通过。原增广LS／QR／SVD未持久化数值回执；原训练的编码失败和首个审计的错误截距恒等式失败均保留，不冒称成功。v2以带权合成反例纠正审计等式，模型和容差不变。原22项、首个恢复11项、v2新增1项构造检查，共34项独特检查（v2执行12项），不冒充180个新测试；原构造开发账本未捕获的限制另列。所有新NPZ为有限数值数组，不含字符串、object或pickle载荷，实际Git／磁盘完整字节另核对。',
        '此为TRAIN事后开发，不是最终独立自己的时序历史；DIRECT_C8、积分、始终获取／不更新、被动适应、检测／历史辨识、任务获取和完整风险／DR等最终对照仍不可删减。原版失败与完整原始记录继续保留，完整QUAL raw交付待空间。',
        '失败成本同样保留：工具外层记录原训练父进程6.403474秒、第一次只读恢复父进程4.7688939秒，包含启动与父进程工作，不等于精确拟合时间；原失败worker未持久化精确内部耗时。原文件守卫确实拒绝过一次标准库编码模块读取，不能将其守卫计数冒称全零；当前v2恢复的零禁用操作另有回执。',
        '方法归属：标准核降秩岭和预测投影参见[Mukherjee与Zhu，2011](https://dept.stat.lsa.umich.edu/~jizhu/pubs/Mukherjee-SADM11.pdf)，排序视角参见[Mandi等，ICML2022](https://proceedings.mlr.press/v162/mandi22a.html)。本实验不以这类已知方法在小型开发集的胜负宣称CCF A贡献。','']
    with report.open('xb') as stream:stream.write((r.OUT/'report_zh.md').read_bytes());stream.write('\n'.join(supplement).encode('utf-8'))
    r.write(out/'presentation_validation.json',dict(integrity='PASSED_ALL_PREDECLARED_PANELS_AND_NUMERIC_CONTAINERS',
        source_freeze_commit=source,analysis_complete_sha256=r.sha(r.OUT/'complete.json'),source_failures=len(failures),
        cells=558,group_rows=279,paired_rate_panels=31,new_original_graph_parses=0,
        extra_model_fits_or_SVD=0,report_statistics_reconstructed_from_saved_outputs=True,counters=r.ZERO))
    owned={p.relative_to(ROOT).as_posix() for folder in (r.OUT,out,recover.ORIGINAL,ROOT/'outputs/low_rank_risk_recovery_v1/analysis_v1') for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    owned.add(report.relative_to(ROOT).as_posix())
    def stage(label):
        spec=out/(label+'.nul');owned.add(spec.relative_to(ROOT).as_posix());spec.write_bytes(b'\0'.join(n.encode() for n in sorted(owned))+b'\0')
        for flags in ((),('--renormalize',)):r.git('add',*flags,'--pathspec-from-file='+spec.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    stage('owned_initial');print(json.dumps(dict(stage='COMPLETE_LOW_RANK_RESULTS_PRESENTED',files=len(owned),decision=decision['status'])),flush=True)
    scan=perf_counter_ns()
    with (out/'secret_stdout.log').open('xb') as so,(out/'secret_stderr.log').open('xb') as se:
        p=subprocess.run([sys.executable,'-B','scripts/check_tracked_secrets.py','--staged'],cwd=ROOT,stdout=so,stderr=se)
    r.write(out/'secret_receipt.json',dict(returncode=p.returncode,wall_ns=perf_counter_ns()-scan))
    r.need(p.returncode==0,'result secret scan')
    owned.update(p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file());stage('owned_checked')
    r.write(out/'index_disk_proof.json',dict(integrity='PASSED_ACTUAL_RESULT_INDEX',objects=check_index(owned)))
    r.verify(freeze['source_sha256']);r.verify(freeze['input_sha256']);r.verify(freeze['scientific_source_sha256'])
    r.write(out/'delivery_validation.json',dict(integrity='PASSED_LOW_RANK_SAVED_RECOVERY_RESULT_DELIVERY',new_unique_tests=34,
        prior_scientific_checks_source_bound_reused=2695,dependency_and_compilation_receipts_reused=True,recovery_new_fits=0,initial_180_model_solutions_inferred_from_saved_artifacts=True,
        actual_numeric_container_validation=True,actual_index_basic_and_EXTRA_scan=True,
        ordinary_and_staged_diff_checks=True,secret_returncode=0,source_freeze_commit=source,
        tested_source_sha256=freeze['source_sha256'],wall_ns=perf_counter_ns()-started,counters=r.ZERO))
    owned.update(p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file());stage('owned_final')
    objects=check_index(owned)
    print(json.dumps(dict(integrity='PASSED_READY_FOR_LOW_RANK_RESULT_COMMIT',files=len(objects),bytes=sum(v['bytes'] for v in objects.values()))),flush=True)


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');main()

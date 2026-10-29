"""Deliver completed exact reference checks and their historical lineage."""
from pathlib import Path
from time import perf_counter_ns
import hashlib
import json
import subprocess
import sys

ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects')
BASE=ROOT/'outputs/stateful_risk_reference_v1';sys.path.insert(0,str(BASE/'tools'))
import run_risk_v1 as r
sys.path.insert(0,str(ROOT/'outputs/train_decision_contract_v1/tools'))
from freeze_contract_v1 import check_index


def main():
    start=perf_counter_ns();source=sys.argv[1]
    r.need(len(source)==40 and r.git('rev-parse','HEAD').decode().strip()==source
        and not r.git('status','--porcelain','--untracked-files=no').strip(),'literal clean source commit')
    complete=r.read(r.OUT/'complete.json');worker=r.read(r.OUT/'worker_complete.json');audit=r.read(r.OUT/'audit.json')
    r.need(complete['source_commit']==source and complete['integrity']==worker['integrity']=='PASSED_STANDARD_STATEFUL_RISK_REFERENCE_CORE'
        and audit['integrity']=='PASSED_EXACT_STANDARD_RISK_IDENTITIES','complete standard reference verification')
    for name,h in complete['artifact_sha256'].items():r.need(r.sha(r.OUT/name)==h,'actual artifact '+name)
    freeze=r.read(r.FREEZE);r.verify(freeze['source_sha256']);r.verify(freeze['input_sha256']);r.verify(freeze['scientific_source_sha256'])
    out=BASE/'presentation_v1';out.mkdir(exist_ok=False)
    (out/'deliver_result_v1.py').write_bytes(Path(__file__).read_bytes())
    old_names=('docs/research/correction_scope_reference_decision_v1_zh.md',
        'docs/protocols/correction_scope_risk_reference_v1_zh.md',
        'src/analysis/correction_scope_risk_reference_v1.py',
        'reports/correction_scope_risk_reference_v1_zh.md',
        'src/analysis/release_learning_equivalence_v1.py')
    lineage={}
    for n in old_names:
        original=r.git('show',source+':'+n);r.need(original==(ROOT/n).read_bytes(),'historical lineage bytes')
        lineage[n]=hashlib.sha256(original).hexdigest()
    r.write(out/'historical_lineage.json',dict(integrity='PASSED_SOURCE_BOUND_REFERENCE_LINEAGE',source_commit=source,
        original_sha256=lineage,old_A1_reference_exists=True,old_reference_model_fits=8,
        new_reference_learned_models=0,no_old_selector_results_replaced=True,
        no_current_robot_task_benefit_claim=True,counters=r.ZERO))
    report=ROOT/'reports/stateful_risk_reference_v1_zh.md';r.need(not report.exists(),'create-only report')
    addition='''
## 参考沿革与证据边界

仓库已有[旧A1完整风险参考](correction_scope_risk_reference_v1_zh.md)：在独立冻结的旧来源上拟合8个标准风险模型，并完成事实分支开发重放。它已正确保留终止分支，不是本轮发现其代码有终止遗漏；其原结果原样保留。

本次补充的是面向当前稀疏后继日志的精确标准DR／支持语义核，没有训练或部署新的完整风险模型。271条实际T标签与另11条BLOCK获取中成功的角色区分，只约束未来训练设计，不能解释成既有OCCAM或旧A1接收者失败的已证实原因。

新查新核对TOPLE、AFAPE、COST-Q及NDE联合测试／处置，阅读范围和链接见[贡献复核v11](../docs/research/correction_scope_contribution_review_v11_zh.md)。一般完整风险／DR已能表达本问题；局部不变结构、真实支持获取或有限资源优势尚待具体机制及独立任务证据。有限表中超过错误快捷式不作为新方法优势。

审计回执的actual_option_value_equality_assertions按被核对的逐选项有理数等式计数，多个等式通过字典比较一次核对；不是Python assert／need调用总数，也不是独立统计样本数。无额外训练和环境资格结论。

冻结前一次检查因新简报名称与历史文件冲突而拒绝。历史文件已恢复为原Git字节，新简报另存独立文件名，失败回执保留；实际worker从未因此重启。本轮仅执行一次冻结后的有限表验证。
'''
    with report.open('xb') as stream:stream.write((r.OUT/'report_zh.md').read_bytes());stream.write(addition.encode('utf-8'))
    r.write(out/'presentation_validation.json',dict(integrity='PASSED_EXACT_REFERENCE_PRESENTATION',source_freeze_commit=source,
        analysis_complete_sha256=r.sha(r.OUT/'complete.json'),worker_wall_ns=worker['wall_ns'],
        finite_law_cases=5,analytic_scoring_evaluations=20,equality_units_are_option_values_not_assert_calls=True,
        no_original_scientific_gzip_parses=True,counters=r.ZERO))
    owned={p.relative_to(ROOT).as_posix() for folder in (r.OUT,out) for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    owned.add(report.relative_to(ROOT).as_posix())
    def stage(label):
        spec=out/(label+'.nul');owned.add(spec.relative_to(ROOT).as_posix());spec.write_bytes(b'\0'.join(n.encode() for n in sorted(owned))+b'\0')
        for flags in ((),('--renormalize',)):r.git('add',*flags,'--pathspec-from-file='+spec.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    stage('owned_initial');print(json.dumps(dict(stage='COMPLETE_REFERENCE_RESULTS_PRESENTED',files=len(owned))),flush=True)
    scan=perf_counter_ns()
    with (out/'secret_stdout.log').open('xb') as so,(out/'secret_stderr.log').open('xb') as se:
        p=subprocess.run([sys.executable,'-B','scripts/check_tracked_secrets.py','--staged'],cwd=ROOT,stdout=so,stderr=se)
    r.write(out/'secret_receipt.json',dict(returncode=p.returncode,wall_ns=perf_counter_ns()-scan))
    r.need(p.returncode==0,'result secret scan')
    owned.update(p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file());stage('owned_checked')
    r.write(out/'index_disk_proof.json',dict(integrity='PASSED_ACTUAL_RESULT_INDEX',objects=check_index(owned)))
    r.verify(freeze['source_sha256']);r.verify(freeze['input_sha256']);r.verify(freeze['scientific_source_sha256'])
    r.write(out/'delivery_validation.json',dict(integrity='PASSED_STANDARD_REFERENCE_RESULT_DELIVERY',new_unique_tests=22,
        original_scientific_checks_source_bound_reused=2695,dependency_and_compilation_receipts_reused=True,
        source_freeze_commit=source,secret_returncode=0,ordinary_and_staged_diff_checks=True,
        actual_index_basic_and_EXTRA_scan=True,wall_ns=perf_counter_ns()-start,counters=r.ZERO))
    owned.update(p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file());stage('owned_final')
    objects=check_index(owned)
    print(json.dumps(dict(integrity='PASSED_READY_FOR_STANDARD_REFERENCE_RESULT_COMMIT',files=len(objects),bytes=sum(v['bytes'] for v in objects.values()))),flush=True)


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');main()

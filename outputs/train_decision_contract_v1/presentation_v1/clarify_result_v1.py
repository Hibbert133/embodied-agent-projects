"""Disclose audit accounting units and present every arm, without source rereads."""
from pathlib import Path
from collections import Counter
import hashlib
import sys

ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects')
BASE=ROOT/'outputs/train_decision_contract_v1';sys.path.insert(0,str(BASE/'tools'))
import run_contract_v1 as r
from freeze_contract_v1 import check_index


def main():
    out=BASE/'presentation_v1'
    done=r.read(out/'delivery_validation.json');r.need(done['integrity']=='PASSED_AUDIT_RESULT_DELIVERY','completed first presentation')
    rows=r.read(r.OUT/'case_contracts.json');result=r.read(r.OUT/'statistics.json');audit=r.read(r.OUT/'audit.json')
    steps=sum(x['total_steps'] for x in rows);windows=sum(len(x['labels']['actual_rates']) for x in rows)
    components=dict(actual_step_units=steps,window_units=windows,per_case_units=30*len(rows),
        overall_and_cohort_panel_units=30,cell_panel_units=10*len(result['cells']),
        alias_member_units=6*len(result['alias_comparisons']),alias_summary_units=len(result['alias_summary']))
    r.need(sum(components.values())==audit['checks']==121240,'literal frozen bookkeeping formula')
    report=ROOT/'reports/train_decision_contract_v1_zh.md';old=report.read_bytes()
    lines=['','## 完整条件配对与计数口径补充','',
        '回执`checks=121240`是冻结代码定义的核对记账量（实际步＋窗口＋每例30单位＋面板／别名单位），并非运行时assert调用次数、标量字段数或独立统计样本数。精确分解保存在checks_accounting_units.json；原冻结分析和回执保持原样。','',
        '|来源|获取臂|时点|相同|不同|缺失|','|---|---|---|---:|---:|---:|']
    cells=[]
    for cohort in ('NATIVE','TRAIN'):
        for arm in ('CONTINUE','VALIDATE8','MOVE_MEASURE'):
            for point in ('before','after'):
                pairs=[x for x in result['alias_comparisons'] if x['comparison']=='context' and x['point']==point
                    and x['key']['cohort']==cohort and x['key']['acquisition_action']==arm]
                tally=Counter('MISSING' if x['all_equal'] is None else 'EQUAL' if x['all_equal'] else 'DIFFERENT' for x in pairs)
                cells.append(dict(cohort=cohort,acquisition_action=arm,point=point,**dict(tally)))
                lines.append('|'+cohort+'|'+arm+'|'+point+'|'+'|'.join(str(tally[k]) for k in ('EQUAL','DIFFERENT','MISSING'))+'|')
    lines+=['','这些配对中，移动前不变／变化条件的声明输入相同。不能由此推断一般不可识别：按条件混合分布学习期望任务风险仍可能有效。',
        '执行普通8步任务延续和移动测量后都会出现条件间输入差异；仅此证据不能把移动的差异归因于独有信息，更不能证明信息价值超过状态／等待成本。后续必须保留同历史被动适应强参考，并在新方法自身独立部署中验证完整任务收益。','']
    with report.open('ab') as stream:stream.write('\n'.join(lines).encode('utf-8'))
    r.need(report.read_bytes()[:len(old)]==old,'append-only clarification to presentation report')
    r.write(out/'checks_accounting_units.json',dict(integrity='PASSED_LITERAL_CHECK_UNITS_DISCLOSURE',
        original_frozen_audit_sha256=r.sha(r.OUT/'audit.json'),frozen_bookkeeping_units=audit['checks'],components=components,
        actual_assertion_invocation_count_not_instrumented=True,not_independent_samples=True,
        original_pre_addendum_report_sha256=hashlib.sha256(old).hexdigest(),all_12_context_pair_cells=cells,counters=r.ZERO))
    owned={n.decode() for n in (out/'owned_final.nul').read_bytes().split(b'\0') if n}
    owned.add((out/'checks_accounting_units.json').relative_to(ROOT).as_posix())
    (out/'clarify_result_v1.py').write_bytes(Path(__file__).read_bytes());owned.add((out/'clarify_result_v1.py').relative_to(ROOT).as_posix())
    spec=out/'owned_addendum.nul';owned.add(spec.relative_to(ROOT).as_posix())
    spec.write_bytes(b'\0'.join(n.encode() for n in sorted(owned))+b'\0')
    for flags in ((),('--renormalize',)):r.git('add',*flags,'--pathspec-from-file='+spec.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    proof=check_index(owned)
    final=out/'final_index_disk_proof.json';r.write(final,dict(integrity='PASSED_PRESENTATION_ADDENDUM_ACTUAL_INDEX',objects=proof,
        previous_index_proof_is_pre_addendum_snapshot=True,full_tracked_scan_reused_before_plaintext_addendum=True,
        final_actual_index_basic_and_EXTRA_scan=True,source_python_or_scientific_inputs_changed=False,counters=r.ZERO))
    owned.add(final.relative_to(ROOT).as_posix());r.git('add','--',final.relative_to(ROOT).as_posix())
    proof=check_index(owned)
    print(dict(integrity='PASSED_READY_FOR_FINAL_RESULT_COMMIT',files=len(proof),bytes=sum(v['bytes'] for v in proof.values()),
        accounting_units=121240,actual_assertions_not_claimed=True),flush=True)


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');main()

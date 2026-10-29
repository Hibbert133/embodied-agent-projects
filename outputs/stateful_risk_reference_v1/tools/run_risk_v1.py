"""Freeze first, then enumerate abstract finite tables and original output counts."""
from pathlib import Path
from time import perf_counter_ns
from fractions import Fraction
from copy import deepcopy
from unittest import mock
import argparse
import json
import subprocess
import sys
import traceback
import risk_core_v1 as core
import risk_audit_v1 as independent
import risk_examples_v1 as examples

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'outputs/train_decision_contract_v1/tools'))
import run_contract_v1 as shared
BASE=ROOT/'outputs/stateful_risk_reference_v1';OUT=BASE/'analysis_v1';FREEZE=BASE/'freeze_v1/complete.json'
PARENT='c6580006d35d5d0afe0ff5f45c4001e565a22fff'
DOCS=('docs/protocols/stateful_risk_reference_v1_zh.md','docs/research/correction_scope_contribution_review_v11_zh.md',
      'docs/research/correction_scope_candidate_register_v11_zh.md','docs/research/correction_scope_stateful_risk_reference_decision_v1_zh.md')
CASE_SOURCE=ROOT/'outputs/train_decision_contract_v1/analysis_v1/case_contracts.json'
CASE_SHA='c7c0eef28a63dfa36db9a1868787d7ccc118057709c665866b2ec03aaa4d2a43'
ZERO=shared.ZERO
sha=shared.sha;read=shared.read;write=shared.write;git=shared.git;verify=shared.verify;need=shared.need


def sources():
    deps=[ROOT/'outputs/train_decision_contract_v1/tools'/n for n in
          ('run_contract_v1.py','contract_core_v1.py','contract_audit_v1.py','freeze_contract_v1.py')]
    return [*sorted((BASE/'tools').glob('*.py')),BASE/'.gitattributes',*(ROOT/n for n in DOCS),*deps]


def inputs():
    return [CASE_SOURCE,ROOT/'outputs/train_decision_contract_v1/freeze_v1/complete.json',
        ROOT/'outputs/train_decision_contract_v1/analysis_v1/complete.json',
        ROOT/'outputs/train_decision_contract_v1/analysis_v1/audit.json',
        ROOT/'outputs/occam_reference_qualification_v1/freeze_validation_v1/complete.json',
        ROOT/'outputs/occam_reference_qualification_v1/freeze_validation_v1/validation_receipt.json']


def encoded(v):
    if type(v) is Fraction:return str(v)
    if isinstance(v,dict):return {k:encoded(x) for k,x in v.items()}
    if isinstance(v,(tuple,list)):return [encoded(x) for x in v]
    return v


def variants(law,means):
    wrong_m={h:{k:Fraction(y)+12 for k,y in m.items()} for h,m in means.items()}
    wrong_p={h:dict(K0='1/2',K1='1/2') for h in means}
    return dict(GOOD_BOTH=(means,law['logging'],'DR'),GOOD_MODEL_ONLY=(means,wrong_p,'DR'),
        GOOD_LOGGING_ONLY=(wrong_m,law['logging'],'DR'),BOTH_WRONG=(wrong_m,wrong_p,'DR'),
        DIRECT_WRONG_MODEL=(wrong_m,law['logging'],'DM'))


def record_terminal_counts(rows):
    result={}
    for b in ('BLOCK_FIXED','RANDOM_WINDOW'):
        selected=[r for r in rows if r['spec']['cohort']=='TRAIN' and r['spec']['behavior']==b
                  and r['missing_reason']=='ENDED_DURING_ACQUISITION']
        result[b]=dict(cases=len(selected),success=sum(r['success'] for r in selected),failure=sum(not r['success'] for r in selected))
    return result


def compute():
    all_examples=examples.definitions();results={}
    for name,(law,means,target) in all_examples.items():
        if name=='NO_OVERLAP':
            try:core.evaluate(law,means,target,law['logging'])
            except ValueError as e:
                need('unsupported target' in str(e),'only planned support failure')
                results[name]=dict(status='REJECTED_NO_LOGGING_SUPPORT',message=str(e),value=None)
            else:raise ValueError('lack of support silently hidden')
            continue
        truth=independent.truth(law,target);values={}
        for variant,(m,p,mode) in variants(law,means).items():
            estimated,count=core.evaluate(law,m,target,p,mode=mode)
            values[variant]=dict(values=estimated,exact_error={a:estimated[a]-truth[a] for a in truth},
                selected_option=core.choose(estimated,tuple(truth)),enumerated_records=count)
        results[name]=dict(status='COMPLETE_EXACT_FINITE_TABLE',truth=truth,variants=values,
            survivor_only_invalid_reference=independent.conditional_selection_shortcut(law,target))
    return results


def admit():
    f=read(FREEZE);need(f['integrity']=='FROZEN_STANDARD_STATEFUL_RISK_REFERENCE_V1','frozen reference core')
    verify(f['source_sha256']);verify(f['input_sha256']);verify(f['scientific_source_sha256'])
    for n,h in f['source_sha256'].items():
        need(__import__('hashlib').sha256(git('show','HEAD:'+n)).hexdigest()==h,'committed tested dependency '+n)
    need(git('show','HEAD:'+FREEZE.relative_to(ROOT).as_posix())==FREEZE.read_bytes(),'committed freeze receipt')
    need(not git('status','--porcelain','--untracked-files=no').strip(),'clean frozen source')
    return f


def worker():
    started=perf_counter_ns();f=admit()
    allowed=[ROOT/n for n in f['source_sha256']|f['input_sha256']|f['scientific_source_sha256']]
    with shared.record_only(OUT,allowed) as guard:
        result=compute();write(OUT/'finite_tables.json',encoded(examples.definitions()));write(OUT/'results.json',encoded(result))
        def deny(*args,**kw):raise RuntimeError('all main risk functions disabled for independent exact audit')
        functions={n:deny for n,v in vars(core).items() if callable(v) and getattr(v,'__module__',None)==core.__name__}
        comparisons=0
        with mock.patch.multiple(core,**functions):
            for name,(law,means,target) in examples.definitions().items():
                if name=='NO_OVERLAP':
                    try:independent.expanded(law,means,target,law['logging'],'DR')
                    except ValueError:pass
                    else:raise ValueError('independent must reject unsupported action')
                    continue
                truth=independent.truth(law,target)
                for variant,(m,p,mode) in variants(law,means).items():
                    expanded=independent.expanded(law,m,target,p,mode)
                    need(expanded==result[name]['variants'][variant]['values'],'independent expanded expectation')
                    comparisons+=len(expanded)
                    if variant.startswith('GOOD_'):need(expanded==truth,'exact DR identity when either nuisance is correct')
        rows=read(CASE_SOURCE);need(sha(CASE_SOURCE)==CASE_SHA and len(rows)==684,'original complete audit output')
        counts=record_terminal_counts(rows)
        # Independent terminal count route, not the main selection helper.
        for behavior,value in counts.items():
            tally=[r['success'] for r in rows if r['spec']['cohort']=='TRAIN' and r['spec']['behavior']==behavior
                and r['before'] is not None and r['after'] is not None and not r['after']['decision_required']]
            need(value==dict(cases=len(tally),success=tally.count(True),failure=tally.count(False)),'all factual terminal branches')
        write(OUT/'original_terminal_branch_counts.json',dict(post_hoc_descriptive_only=True,source_sha256=CASE_SHA,
            registered_cases=684,TRAIN_cases=648,counts=counts,new_original_gzip_parses=0,
            original_static_label_admission_unchanged=271,no_unexecuted_gain_labels_created=True))
        write(OUT/'audit.json',dict(integrity='PASSED_EXACT_STANDARD_RISK_IDENTITIES',
            actual_option_value_equality_assertions=comparisons,finite_examples=5,standard_DM_DR_variants=5,
            main_functions_disabled=sorted(functions),independent_expansion=True,
            shared_Fraction_JSON_infrastructure=True,no_robot_or_statistical_generalization_claim=True))
        report(result,counts)
        verify(f['source_sha256']);verify(f['input_sha256']);verify(f['scientific_source_sha256'])
        need(not any(guard.values()),'zero unplanned file/network/science actions')
        write(OUT/'worker_complete.json',dict(integrity='PASSED_STANDARD_STATEFUL_RISK_REFERENCE_CORE',
            counters=ZERO,finite_law_cases=5,analytic_scoring_evaluations=20,
            learned_model_training_or_deployment=False,all_original_records_and_comparisons_unchanged=True,
            guard=guard,source_IO=shared.IO,wall_ns=perf_counter_ns()-started,publication_goal_complete=False))


def report(result,counts):
    lines=['# 状态改变与终止分支下的标准风险参考核 v1','',
        '**确定性有限表与精确有理数校验，不是机器人实验、训练结果、新方法或任务提升。**',
        'C／V／M和K0／K1仅是抽象选项；M的20代价单位不修改实际机器人移动程序。','',
        '|预定算例|C真实完整剩余损失|V|M|按真实值最优|','|---|---:|---:|---:|---|']
    for name,r in result.items():
        if 'truth' not in r:continue
        truth=r['truth'];lines.append('|'+name+'|'+'|'.join(str(truth.get(a,'无该选项')) for a in ('C','V','M'))+'|'+min(truth,key=truth.get)+'|')
    lines+=['','每个可支持算例，DR在回归正确或日志概率正确时分别等于解析真实值；两者都失配不保证相等。DM／DR和Bellman分解是标准强参考，不命名为原创。',
        'NO_OVERLAP完整保留为拒绝，没有补epsilon、剪权重或归一化造出可评价性。DR伪结局可以超出物理损失范围，未裁剪伪结局。',
        '实际返回后成功时分支损失为n_return−n_before，失败时500−n_before；其中已经含获取费用，不能再加一次。存活分支才用获取费用＋完整后继损失。',
        '只在实际完整静态后继上形成后继标签，拒绝把随机变化程序按首增益重新命名。概率来源必须另行资格确认，当前有限表已知概率不证明机器人历史数据具备同样条件。',
        '对于STATE_CHANGE，若错误地把M的后继状态／风险当成V，M估计为62而实际25，导致选择V的50；这只反驳一个明确失配的快捷计算，不证明标准AFAPE、DR或双重控制无能力处理机器人。',
        'TERMINAL_FAILURE与TERMINAL_SUCCESS展示丢弃终止分支可分别遗漏失败代价或成功收益；survivor-only数值与全部算例和所有失配变体见results.json。','',
        '|真实TRAIN获取中结束行为|全部|成功|失败|','|---|---:|---:|---:|']
    for b,v in counts.items():lines.append(f'|{b}|{v["cases"]}|{v["success"]}|{v["failure"]}|')
    lines+=['','上述计数是读取已有684案例审计输出的事后描述，不是新采集。原271个静态后继标签仍只供实际T监督；另11个BLOCK获取中成功案例没有增益决策，但必须进入移动前完整风险的终止分支。不得新增四个虚构T终局。',
        '下一完整风险训练协议应分别处理终止／存活分支、固定已训练后继的风险对象、概率假设及按独立组划分；不能把271条后继样本直接当成移动前完整人口。尚未训练任何新模型或完成自身历史部署。',
        '新增环境、重置、帧、策略／学习模型查询、拟合、训练、种子和在线LLM全零。单独记录纯表评分、Fraction枚举、文件IO与墙钟；没有统计功效或机器人成功率结论。',
        '查新与候选复核见docs/research/correction_scope_contribution_review_v11_zh.md；标准完整风险／DR、被动适应、重加权及原强基线保留。旧接收者、原负结果和CCF A目标均不因本核通过而改变。','']
    with (OUT/'report_zh.md').open('x',encoding='utf-8',newline='\n') as s:s.write('\n'.join(lines))


def analyze():
    start=perf_counter_ns();admit();OUT.mkdir(exist_ok=False);source=git('rev-parse','HEAD').decode().strip()
    write(OUT/'request.json',dict(source_commit=source,one_attempt_only=True,worker_hard_timeout_seconds=60,counters=ZERO))
    try:
        with (OUT/'stdout.log').open('xb') as so,(OUT/'stderr.log').open('xb') as se:
            p=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'--worker'],cwd=ROOT,stdout=so,stderr=se,timeout=60)
        need(p.returncode==0,'single reference validation failed; preserve without retry')
        done=read(OUT/'worker_complete.json')
        write(OUT/'complete.json',dict(integrity=done['integrity'],source_commit=source,
            freeze_sha256=sha(FREEZE),artifact_sha256={p.name:sha(p) for p in OUT.iterdir() if p.is_file()},
            parent_IO=shared.IO,total_parent_wall_ns=perf_counter_ns()-start,counters=ZERO,
            no_robot_task_qualification=True,publication_goal_complete=False))
        print(json.dumps(dict(integrity=done['integrity'],finite_law_cases=5,counters=ZERO)),flush=True)
    except Exception as e:
        write(OUT/'failure.json',dict(integrity='PRESERVED_STANDARD_REFERENCE_FAILURE',reason=str(e),traceback=traceback.format_exc(),source_commit=source));raise


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');p=argparse.ArgumentParser();p.add_argument('--worker',action='store_true');args=p.parse_args()
    worker() if args.worker else analyze()

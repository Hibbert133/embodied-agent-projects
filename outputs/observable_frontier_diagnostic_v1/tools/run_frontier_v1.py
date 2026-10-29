"""One exact TRAIN information-partition diagnostic, no learned model calls."""
from contextlib import contextmanager
from fractions import Fraction
from pathlib import Path
from time import perf_counter_ns
from unittest import mock
import argparse
import csv
import gzip
import hashlib
import json
import os
import subprocess
import sys
import traceback
import frontier_core_v1 as core
import frontier_audit_v1 as independent

ROOT=Path(__file__).resolve().parents[3];BASE=ROOT/'outputs/observable_frontier_diagnostic_v1';OUT=BASE/'analysis_v1'
FREEZE=BASE/'freeze_v1/complete.json';PARENT='47428e532c74630b9c2408fb34fe8d864bc8c662'
OLD=ROOT/'outputs/correction_scope/risk_reference_v1/run_20261026T094817Z_82a3873cdf1b'
GRAPH=OLD/'train_graphs.jsonl.gz';GRAPH_SHA='15d226d79658ed75c246ccbff940ddbb343e9d224186e6ece6de5e12b7af13c7'
DOCS=('docs/protocols/observable_frontier_diagnostic_v1_zh.md','docs/research/correction_scope_contribution_review_v12_zh.md')
sys.path.insert(0,str(ROOT/'outputs/train_decision_contract_v1/tools'))
import run_contract_v1 as io
sha=io.sha;read=io.read;write=io.write;need=io.need;git=io.git;verify=io.verify
ZERO=dict(environment_creations=0,environment_interactions=0,controlled_resets=0,all_resets=0,physical_frames=0,
          policy_queries=0,predictive_model_queries=0,predictive_model_fits=0,neural_training=0,new_episode_seeds=0,online_LLM_API_calls=0)


def sources():return [*sorted((BASE/'tools').glob('*.py')),BASE/'.gitattributes',*(ROOT/n for n in DOCS),
    *(ROOT/'outputs/train_decision_contract_v1/tools'/n for n in ('run_contract_v1.py','contract_core_v1.py','contract_audit_v1.py','freeze_contract_v1.py'))]


def inputs():return [GRAPH,*(OLD/n for n in ('manifest.json','fit_receipt.json','model_audit.json','replay_audit.json')),
    ROOT/'outputs/low_rank_risk_recovery_v2/freeze_v1/complete.json',ROOT/'outputs/low_rank_risk_pilot_v1/freeze_v1/delivery_validation.json',
    ROOT/'outputs/occam_reference_qualification_v1/freeze_validation_v1/complete.json',
    ROOT/'outputs/occam_reference_qualification_v1/freeze_validation_v1/validation_receipt.json']


def graphs():
    io.IO['gzip_stream_passes']+=1;result=[]
    with gzip.open(GRAPH,'rb') as stream:
        for b in stream:
            io.IO['gzip_rows']+=1;io.IO['gzip_decoded_bytes']+=len(b);result.append(io.loads(b.decode('utf-8')))
    need(len(result)==54 and len({tuple(g['unit']) for g in result})==54,'all source units')
    need(all(sum(g['unit'][1]==i for g in result)==6 for i in range(9)),'all nine equal groups')
    need(all(g['unit'][0]=='TRAIN' and g['unit'][2] in core.TASKS and g['unit'][3] in ('UNCHANGED','CHANGED')
        and g['boundary']==(16,32,64)[g['unit'][1]%3] for g in result),'whole source scope')
    return result


@contextmanager
def guard(allowed):
    allowed={Path(p).resolve() for p in allowed};active=[True];counts=dict(science_imports=0,network_process=0,undeclared_reads=0,outside_writes=0)
    forbidden=('numpy','torch','mujoco','metaworld','gym','gymnasium','src.rollout')
    need(not any(n==p or n.startswith(p+'.') for n in sys.modules for p in forbidden),'pure stdlib process')
    def hook(event,args):
        if not active[0]:return
        if event=='import' and any(args[0]==p or args[0].startswith(p+'.') for p in forbidden):
            counts['science_imports']+=1;raise RuntimeError('no numerical learner or robot libraries')
        if event.startswith('socket.') or event in ('subprocess.Popen','os.system','os.exec','os.posix_spawn'):
            counts['network_process']+=1;raise RuntimeError('no network or processes')
        if event=='open' and isinstance(args[0],(str,bytes,os.PathLike)):
            p=Path(os.fsdecode(args[0])).resolve();mode,flags=args[1:3]
            writing=(isinstance(mode,str) and any(c in mode for c in 'wax+')) or (type(flags) is int and bool(flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC)))
            inside=p==OUT or OUT in p.parents
            if writing and not inside:counts['outside_writes']+=1;raise RuntimeError('outside new output')
            if not writing and not inside and p not in allowed:counts['undeclared_reads']+=1;raise RuntimeError('undeclared source read')
    sys.addaudithook(hook)
    try:yield counts
    finally:active[0]=False


def admit():
    f=read(FREEZE);need(f['integrity']=='FROZEN_OBSERVABLE_FRONTIER_DIAGNOSTIC_V1','frozen diagnostic')
    for key in ('source_sha256','input_sha256','scientific_source_sha256'):verify(f[key])
    for n,h in f['source_sha256'].items():need(hashlib.sha256(git('show','HEAD:'+n)).hexdigest()==h,'committed tested code')
    need(git('show','HEAD:'+FREEZE.relative_to(ROOT).as_posix())==FREEZE.read_bytes(),'committed protocol freeze')
    need(not git('status','--porcelain','--untracked-files=no').strip(),'clean committed source');return f


def table(path,rows):
    with path.open('x',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def summarize(gs,result):
    summaries={};group_rows=[];cells=[]
    for name,total in result['totals'].items():
        rows=[r for r in result['records'] if r['functional']==name]
        means={str(g):str(Fraction(sum(r['loss'] for r in rows if gs[r['unit_index']]['unit'][1]==g),6)) for g in range(9)}
        summaries[name]=dict(cases=54,success=sum(r['success'] for r in rows),total_loss=total,mean_loss_exact=str(Fraction(total,54)),
            group_means_exact=means,early_no_decision=sum(r['chosen_acquisition_index'] is None for r in rows),
            terminal_no_rate=sum(r['chosen_acquisition_index'] is not None and r['rate_index'] is None for r in rows))
        for g in range(9):group_rows.append(dict(functional=name,group=g,cases=6,mean_loss_exact=means[str(g)]))
        for task in core.TASKS:
            for context in ('UNCHANGED','CHANGED'):
                for b in (16,32,64):
                    rs=[r for r in rows if (gs[r['unit_index']]['unit'][2],gs[r['unit_index']]['unit'][3],gs[r['unit_index']]['boundary'])==(task,context,b)]
                    need(len(rs)==3,'complete joint strata');loss=sum(r['loss'] for r in rs)
                    cells.append(dict(functional=name,task=task,context=context,boundary=b,cases=3,success=sum(r['success'] for r in rs),
                        total_loss=loss,mean_loss_exact=str(Fraction(loss,3)),early=sum(r['chosen_acquisition_index'] is None for r in rs)))
    roots=[]
    for p in result['root_classes']:
        ids=p['members'];minima=[min(q['loss'] for q in gs[i]['leaves']) for i in ids]
        static=min(sum(gs[i]['leaves'][j]['loss'] for i in ids) for j in range(12))
        roots.append(dict(**p,source_units=[gs[i]['unit'] for i in ids],unit_clairvoyant_total=sum(minima),root_static_total=static,
            unavoidable_empirical_same_input_gap=static-sum(minima),all_targets_observed_in_hindsight=True))
    return dict(functionals=summaries,root_classes=roots,root_count=len(roots),live_units=sum(g['pre'] is not None for g in gs),
        early_units=sum(g['pre'] is None for g in gs),conflicting_root_classes=sum(p['unavoidable_empirical_same_input_gap']>0 for p in roots),
        total_same_input_gap=sum(p['unavoidable_empirical_same_input_gap'] for p in roots),
        extra_trace_empirical_gain=result['totals']['ROOT_ADAPTIVE_MASK']-result['totals']['ROOT_ADAPTIVE_FULL'],
        contingent_empirical_gain=result['totals']['ROOT_STATIC']-result['totals']['ROOT_ADAPTIVE_FULL'],
        uses_future_labels=True,deployable=False,learnability_established=False,novelty_established=False,independent_task_qualification=False),group_rows,cells


def worker():
    started=perf_counter_ns();f=admit();allowed=[ROOT/n for key in ('source_sha256','input_sha256','scientific_source_sha256') for n in f[key]]
    with guard(allowed) as access:
        gs=graphs();result=core.solve(gs);write(OUT/'empirical_frontier.json',result)
        def deny(*args,**kwargs):raise RuntimeError('main frontier functions disabled')
        blocked={n:deny for n,v in vars(core).items() if callable(v) and getattr(v,'__module__',None)==core.__name__}
        with mock.patch.multiple(core,**blocked):
            second=graphs();need(second==gs,'independent second semantic pass');audit=independent.audit(second,result)
        write(OUT/'independent_audit.json',dict(integrity='PASSED_TYPED_PARTITIONS_AND_EXHAUSTIVE_CONTINGENT_PLANS',**audit,main_functions_disabled=sorted(blocked)))
        stats,groups,cells=summarize(gs,result);write(OUT/'statistics.json',stats)
        with mock.patch.multiple(core,**blocked):strata=independent.audit_strata(second,result,stats,groups,cells)
        write(OUT/'strata_audit.json',dict(integrity='PASSED_ALL_EXACT_STRATA_AND_PUBLIC_CLASSES',**strata))
        table(OUT/'all_162_group_rows.csv',groups);table(OUT/'all_324_joint_cells.csv',cells)
        write(OUT/'all_source_task_failures.json',[dict(unit_index=i,unit=g['unit'],leaf_index=j,**q) for i,g in enumerate(gs) for j,q in enumerate(g['leaves']) if not q['success']])
        write(OUT/'population.json',[dict(unit_index=i,unit=g['unit'],boundary=g['boundary'],pre_available=g['pre'] is not None,
            return_available=[q is not None for q in g['returns']],source_failures=sum(not q['success'] for q in g['leaves']),
            early_reason='ENDED_BEFORE_OR_AT_BOUNDARY' if g['pre'] is None else None) for i,g in enumerate(gs)])
        # Exact bounded derived source, not another environment collection.
        with (OUT/'source_train_graphs.jsonl.gz').open('xb') as stream:stream.write(GRAPH.read_bytes())
        need(sha(OUT/'source_train_graphs.jsonl.gz')==GRAPH_SHA,'reproducible exact source graph')
        report(stats,result,audit)
        for key in ('source_sha256','input_sha256','scientific_source_sha256'):verify(f[key])
        need(not any(access.values()),'strict zero forbidden operations');total=sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file())
        need(total<=64*1024**2,'output cap')
        write(OUT/'worker_complete.json',dict(integrity='PASSED_COMPLETE_OBSERVABLE_FRONTIER_DIAGNOSTIC',
            source_cases=648,source_units=54,groups=9,uses_future_labels=True,deployable=False,empirical_optimization=result['optimization_ledger'],
            independent_exhaustive_plans=audit['exhaustive_contingent_plans'],selection_rows=972,guard=access,source_IO=io.IO,
            old_CAL_TEST_QUAL_semantic_reads=0,counters=ZERO,wall_ns=perf_counter_ns()-started,output_bytes_before_receipt=total,publication_goal_complete=False))


def report(s,result,audit):
    lines=['# 公开历史可区分性与事实前沿诊断 v1','',
        '**事后描述性；使用全部未来结局优化的有限经验表，明确不可部署。没有训练或评价新预测模型，不是机器人新实验。**','',
        f'完整旧TRAIN54单位／9组／648真实分支。{s["live_units"]}个有效根、{s["early_units"]}个提前结束；精确公开根共{s["root_count"]}类，其中{s["conflicting_root_classes"]}类存在相互冲突的单位最优叶。',
        'FULL保留已知根和全部真实返回历史；MASK只屏蔽获取新增轨迹，实际返回当前观测、积分、控制器、预算与根历史都保留。任何相同信息必须采取相同决定。','',
        '|经验泛函|成功/54|完整平均损失|','|---|---:|---:|']
    for n,v in s['functionals'].items():lines.append(f'|{n}|{v["success"]}/54|{float(Fraction(v["mean_loss_exact"])):.6f}|')
    lines+=['',f'同根静态约束相对每单位看未来的总记录差{s["total_same_input_gap"]}步；允许实际返回后选T相对根静态减少{s["contingent_empirical_gain"]}步；FULL相对MASK减少{s["extra_trace_empirical_gain"]}步。它们是这份完整事实表的经验差额，不能改称期望收益、信息纯因果效应或可学习优势。',
        f'独立审计用类型／浮点hex签名和完整穷举，核对{audit["exhaustive_contingent_plans"]}个条件计划及972条叶引用；主分解求解的所有函数禁用。成本整数／有理数精确，无容差、聚类阈值或近似后继。',
        '只有原同一真实获取返回后的四个已执行T可比较；提前结束与获取中成功不制造尾部。成功成本为原总实际步，失败500；已含前缀／移动／验证／探测一次，不重复计费。',
        '全部162组行、324任务／条件／边界格、972叶引用、等价类、获取中结束及源全部任务失败均保留。9组、三任务和两条件不筛选，缺失不填零。源公共图绑定原共同物理状态／随机数／积分审计，公开观测相同不代表物理Markov充分性。','',
        '判断限制：精确唯一输入允许未来表记忆，不能外推新单位。FULL与MASK相同只说明这批有限输入分组没有增加可区分性，不能说额外历史对未知分布无信息。未来表与实际学习接收者表现不同，也不证明唯一失败原因。局部NDE、真实故障、模型可识别性和新颖性均未被证明。',
        '原低秩版本仍封存，原六项／十项及全部负结果不变；这些未来最优表不用于新训练标签、阈值、筛任务或选择新样本。后续必须先有具体新机制、强参考和独立自己的时序历史协议。',
        '新增环境／重置／帧／固定政策和预测模型查询／预测模型拟合／神经训练／种子／在线LLM均0；经验表优化及独立枚举费用单列，不把优化隐瞒为没有计算。历史来源648执行／77563控制步／33048全部重置／16911815帧另列。','',
        '本轮查新新增[UAI2024局部有效性](https://proceedings.mlr.press/v244/lammle24a.html)、[受约束实验规划COPEx](https://arxiv.org/html/2605.26990v1)和[NeurIPS2025条件performative预测](https://papers.nips.cc/paper_files/paper/2025/hash/17da6ad7f0821c9b62a9116ff9c1cf1b-Abstract-Conference.html)。标准局部有效域、停止、动态移动约束和条件预测都不能重新命名为贡献；实际阅读边界及全部旧候选见贡献复核v12。CCF A目标尚未完成。','']
    with (OUT/'report_zh.md').open('x',encoding='utf-8',newline='\n') as stream:stream.write('\n'.join(lines))


def analyze():
    started=perf_counter_ns();admit();need(__import__('shutil').disk_usage(ROOT).free>=256*1024**2,'analysis-only disk margin')
    OUT.mkdir(exist_ok=False);source=git('rev-parse','HEAD').decode().strip()
    write(OUT/'request.json',dict(source_commit=source,source_graph_sha256=GRAPH_SHA,hard_timeout_seconds=600,one_attempt_only=True,uses_future_labels=True,deployable=False,counters=ZERO))
    try:
        with (OUT/'stdout.log').open('xb') as so,(OUT/'stderr.log').open('xb') as se:
            p=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'--worker'],cwd=ROOT,stdout=so,stderr=se,timeout=600)
        need(p.returncode==0,'preserve diagnostic failure, no automatic retry')
        done=read(OUT/'worker_complete.json');write(OUT/'complete.json',dict(integrity=done['integrity'],source_commit=source,freeze_sha256=sha(FREEZE),
            artifacts={p.relative_to(OUT).as_posix():dict(bytes=p.stat().st_size,sha256=sha(p)) for p in OUT.rglob('*') if p.is_file()},
            total_parent_wall_ns=perf_counter_ns()-started,parent_IO=io.IO,counters=ZERO,uses_future_labels=True,deployable=False,publication_goal_complete=False))
        print(json.dumps(dict(integrity=done['integrity'],future_table_not_deployable=True)),flush=True)
    except Exception as error:
        write(OUT/'failure.json',dict(integrity='PRESERVED_OBSERVABLE_FRONTIER_FAILURE',source_commit=source,reason=str(error),traceback=traceback.format_exc()));raise


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');p=argparse.ArgumentParser();p.add_argument('--worker',action='store_true');args=p.parse_args()
    worker() if args.worker else analyze()

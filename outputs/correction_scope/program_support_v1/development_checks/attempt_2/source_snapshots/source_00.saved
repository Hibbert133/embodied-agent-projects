"""Evaluation-only envelopes of complete saved factual programs, never a policy."""
from collections import defaultdict
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from time import perf_counter_ns
import hashlib, subprocess
from src.analysis import correction_scope_risk_reference_v1 as prior

io=prior.io;ROOT=io.ROOT
BASE=ROOT/'outputs/correction_scope/program_support_v1'
CONFIG=ROOT/'configs/movement_task/correction_program_support_v1.json'
A=('CONTINUE','VALIDATE8','MOVE_MEASURE');R=(.125,.5,2.,8.)
T=('push-v3','reach-v3','door-open-v3');C=('UNCHANGED','CHANGED')
FAMILIES={'CONTINUE':tuple(range(4)),'VALIDATE8':tuple(range(4,8)),
          'FREE':tuple(range(8)),'MOVE':tuple(range(8,12)),'ALL':tuple(range(12))}
SOURCES=('src/analysis/correction_program_support_v1.py',
    'src/analysis/correction_program_support_independent_v1.py',
    'scripts/run_correction_program_support_v1.py','tests/test_correction_program_support_v1.py',
    'configs/movement_task/correction_program_support_v1.json',
    'docs/protocols/correction_program_support_v1_zh.md',
    'docs/research/correction_program_support_decision_v1_zh.md',
    'outputs/correction_scope/program_support_v1/validate_freeze.py')


def bindings(config):
    ref=ROOT/config['source_reference_run'];source=ROOT/config['source_A1_run'];trace=ROOT/config['source_trace_run']
    paths=[ref/'train_graphs.jsonl.gz',ref/'model_audit.json',source/'manifest.json',source/'train/audit.json',
        source/'train/summary.json',source/'train/cases.jsonl.gz',source/'train/examples.jsonl.gz',
        ROOT/'outputs/correction_scope/common_state_audit_v1/train.json',trace/'results.json',trace/'replay_audit.json',
        source/'results/statistics.json']
    result={}
    for path in paths:
        name=path.relative_to(ROOT).as_posix()
        data=subprocess.check_output(['git','show',config['source_result_commit']+':'+name],cwd=ROOT)
        io.require(hashlib.sha256(data).hexdigest()==io.sha(path),'immutable committed source '+name)
        result[name]=io.sha(path)
    audit=io.read(source/'train/audit.json');io.require(audit['integrity']=='PASSED','source TRAIN audit')
    for name,digest in audit['collection_sha256'].items():
        path=source/'train'/name;io.require(io.sha(path)==digest,'source raw bytes '+name)
        result[path.relative_to(ROOT).as_posix()]=digest
    io.require(io.read(ref/'model_audit.json')['graph_sha256']['TRAIN']==io.sha(ref/'train_graphs.jsonl.gz'),'audited factual graph')
    io.require(io.read(trace/'replay_audit.json')['results_sha256']==io.sha(trace/'results.json'),'old selector result unchanged')
    io.require(io.read(ROOT/'outputs/correction_scope/common_state_audit_v1/train.json')['integrity']=='PASSED','full hidden-state/RNG/memory source proof')
    return result


def prepare():
    freeze=io.read(BASE/'freeze_validation/complete.json');io.require(freeze['integrity']=='PASSED','freeze passed')
    io.require(not io.git('status','--porcelain','--untracked-files=no'),'committed clean source')
    for name,digest in freeze['source_sha256'].items():
        io.require(io.sha(ROOT/name)==digest and io.git('ls-files','--error-unmatch',name)==name,'committed frozen source')
    io.require(not list(BASE.glob('run_*/manifest.json')),'single audit allocation; do not restart')
    config=io.read(CONFIG);head=io.git('rev-parse','HEAD');source=bindings(config)
    out=BASE/('run_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+head[:12]);out.mkdir(exist_ok=False)
    manifest=dict(protocol=config['protocol'],classification=config['classification'],source_git_commit=head,config=config,
        source_sha256=freeze['source_sha256'],input_sha256=source,CAL_TEST_numeric_data_used=False,
        old_TEST_statistics_bytes_only=True,new_physics=0,new_model_fits=0,online_LLM_API_calls=0)
    manifest['manifest_id']=io.digest(manifest);io.write(out/'manifest.json',manifest)
    return out/'manifest.json'


def checked(path):
    path=Path(path).resolve();manifest=io.read(path);copy=dict(manifest);mid=copy.pop('manifest_id')
    io.require(path.parent.parent==BASE.resolve() and io.digest(copy)==mid and manifest['config']==io.read(CONFIG),'strict frozen support-audit manifest')
    for name,digest in {**manifest['source_sha256'],**manifest['input_sha256']}.items():
        io.require(io.sha(ROOT/name)==digest,'immutable support-audit source '+name)
    return manifest


def validate_graph(graph):
    unit=graph['unit']
    io.require(type(unit) is list and len(unit)==4 and unit[0]=='TRAIN' and type(unit[1]) is int and unit[1] in range(9)
        and unit[2] in T and unit[3] in C,'only complete registered TRAIN units')
    io.require(graph['boundary']==(16,32,64)[unit[1]%3] and len(graph['leaves'])==12 and len(graph['returns'])==3,'complete fixed family and boundary')
    for i,leaf in enumerate(graph['leaves']):
        key=leaf['source_case_key']
        io.require(len(key)==8 and [key[0],key[1],key[2],key[4]]==unit and key[5]==graph['boundary']
            and key[6]==A[i//4] and key[7]==R[i%4],'unique ordered factual source key')
        io.require(type(leaf['success']) is bool and type(leaf['steps']) is int and 0<=leaf['steps']<=500,'valid actual source outcome')
        io.require(type(leaf['loss']) is int and leaf['loss']==(leaf['steps'] if leaf['success'] else 500),'cutoff loss includes failure penalty')
        for name in ('movement_steps','measurement_steps'):
            io.require(type(leaf[name]) is int and 0<=leaf[name]<=leaf['steps'],'actual phase cost')
        io.require(leaf['movement_steps']+leaf['measurement_steps']<=leaf['steps'],'phases cannot exceed total source calls')
        io.require(type(leaf['source_case_sha256']) is str and len(leaf['source_case_sha256'])==64,'source case hash')
    if graph['pre'] is None:
        io.require(all(v is None for v in graph['returns']) and len({(v['loss'],v['steps'],v['success']) for v in graph['leaves']})==1,'early end retained, no invented query')
    for action,node in enumerate(graph['returns']):
        if node is None:
            io.require(len({(v['loss'],v['steps'],v['success']) for v in graph['leaves'][4*action:4*action+4]})==1,'terminal acquisition has no distinct tails')
    return graph


def load_graphs(manifest):
    graphs=[validate_graph(g) for g in io.rows(ROOT/manifest['config']['source_reference_run']/'train_graphs.jsonl.gz')]
    expected={('TRAIN',g,t,c) for g in range(9) for t in T for c in C}
    io.require(len(graphs)==54 and {tuple(g['unit']) for g in graphs}==expected,'all TRAIN source units once')
    return sorted(graphs,key=lambda g:g['unit'])


def envelope(leaves,indices):
    io.require(bool(indices) and len(set(indices))==len(indices) and all(i in range(len(leaves)) for i in indices),'nonempty supported finite family')
    lowest=min(leaves[i]['loss'] for i in indices);ties=[i for i in indices if leaves[i]['loss']==lowest]
    successes=[leaves[i]['success'] for i in ties]
    return dict(loss=lowest,optimal_leaf_indices=ties,all_minima_success=all(successes),any_minimum_success=any(successes))


def unit_row(graph):
    validate_graph(graph);families={name:envelope(graph['leaves'],indices) for name,indices in FAMILIES.items()}
    b=graph['leaves'][1]['loss'];f=families['FREE']['loss'];p=families['MOVE']['loss'];h=families['ALL']['loss']
    return dict(unit=graph['unit'],boundary=graph['boundary'],leaves=graph['leaves'],families=families,baseline_loss=b,
        B_minus_F=b-f,B_minus_P=b-p,F_minus_P=f-p,F_minus_H=f-h,
        prefix_available=graph['pre'] is not None,
        return_availability=['LIVE' if v is not None else 'PREFIX_ALREADY_TERMINAL' if graph['pre'] is None else 'ACQUISITION_ALREADY_TERMINAL' for v in graph['returns']])


def group_average(rows,key):
    groups=defaultdict(list)
    for row in rows:groups[row['unit'][1]].append(row[key])
    io.require(bool(groups),'nonempty complete grouping')
    return sum((Fraction(sum(v),len(v)) for v in groups.values()),Fraction())/len(groups)


def aggregate(rows):
    metrics={key:group_average(rows,key) for key in ('baseline_loss','B_minus_F','B_minus_P','F_minus_P','F_minus_H')}
    families={}
    for name in FAMILIES:
        values=[dict(unit=r['unit'],loss=r['families'][name]['loss']) for r in rows]
        mean=group_average(values,'loss')
        families[name]=dict(mean_loss=float(mean),mean_loss_exact=str(mean),
            minimum_successes=sum(r['families'][name]['all_minima_success'] for r in rows),
            maximum_successes=sum(r['families'][name]['any_minimum_success'] for r in rows))
    return dict(units=len(rows),groups=len({r['unit'][1] for r in rows}),
        means={k:float(v) for k,v in metrics.items()},means_exact={k:str(v) for k,v in metrics.items()},families=families,
        paid_better=sum(r['F_minus_P']>0 for r in rows),paid_worse=sum(r['F_minus_P']<0 for r in rows),paid_tie=sum(r['F_minus_P']==0 for r in rows),
        paid_positive_steps=sum(max(0,r['F_minus_P']) for r in rows),paid_negative_steps=sum(max(0,-r['F_minus_P']) for r in rows),
        prefix_unavailable=sum(not r['prefix_available'] for r in rows),
        unavailable_returns={a:sum(r['return_availability'][i]!='LIVE' for r in rows) for i,a in enumerate(A)})


def analyze(path):
    path=Path(path).resolve();manifest=checked(path);base=path.parent;start=perf_counter_ns();guard={}
    with prior.recorded_guard(guard,base/'analysis_failure.json'):
        graphs=load_graphs(manifest);rows=[unit_row(g) for g in graphs]
        programs=[];pairs=[]
        for i in range(12):
            ll=[r['leaves'][i] for r in rows]
            programs.append(dict(index=i,action=A[i//4],rate=R[i%4],units=54,success=sum(v['success'] for v in ll),
                mean_loss=sum(v['loss'] for v in ll)/54,mean_loss_exact=str(Fraction(sum(v['loss'] for v in ll),54)),
                actual_source_steps=sum(v['steps'] for v in ll),movement_steps=sum(v['movement_steps'] for v in ll),measurement_steps=sum(v['measurement_steps'] for v in ll)))
            for j in range(12):
                d=[r['leaves'][i]['loss']-r['leaves'][j]['loss'] for r in rows]
                pairs.append(dict(left=i,right=j,units=54,mean_difference=sum(d)/54,mean_difference_exact=str(Fraction(sum(d),54)),
                    harm=sum(v>0 for v in d),help=sum(v<0 for v in d),ties=sum(v==0 for v in d),
                    success_to_failure=sum(r['leaves'][j]['success'] and not r['leaves'][i]['success'] for r in rows),
                    failure_to_success=sum(not r['leaves'][j]['success'] and r['leaves'][i]['success'] for r in rows)))
        grouped=[dict(group=g,summary=aggregate([r for r in rows if r['unit'][1]==g])) for g in range(9)]
        panels=[dict(task=t,context=c,boundary=b,summary=aggregate([r for r in rows if r['unit'][2:]==[t,c] and r['boundary']==b])) for t in T for c in C for b in (16,32,64)]
        old=io.read(ROOT/manifest['config']['source_trace_run']/'results.json');lookup={tuple(r['unit']):r for r in rows};selector_rows=[]
        for item in old['results']:
            row=lookup[tuple(item['unit'])];i=A.index(item['action'])*4+R.index(item['rate']);leaf=row['leaves'][i]
            io.require(leaf['source_case_key']==item['source_case_key'] and leaf['source_case_sha256']==item['source_case_sha256']
                and leaf['loss']==item['loss'] and leaf['success']==item['success'],'unchanged actual selector leaf')
            family=('CONTINUE','VALIDATE8','MOVE')[i//4]
            selector_rows.append(dict(unit=row['unit'],selector=item['selector'],source_leaf=i,loss=leaf['loss'],success=leaf['success'],
                same_family_realized_gap=leaf['loss']-row['families'][family]['loss'],
                all_family_realized_gap=leaf['loss']-row['families']['ALL']['loss'],
                difference_to_free_envelope=leaf['loss']-row['families']['FREE']['loss']))
        selectors=[]
        for name in sorted({r['selector'] for r in selector_rows}):
            rr=[r for r in selector_rows if r['selector']==name]
            io.require(len(rr)==54,'all original selectors, no filtering')
            selectors.append(dict(selector=name,units=54,success=sum(r['success'] for r in rr),
                **{key:float(group_average(rr,key)) for key in ('loss','same_family_realized_gap','all_family_realized_gap','difference_to_free_envelope')}))
        io.require(len(rows)==54 and len(programs)==12 and len(pairs)==144 and len(panels)==18 and len(selector_rows)==540,'complete factual ledger dimensions')
        summary=aggregate(rows)
        conclusion=dict(no_paid_leaf_improves_free_factual_envelope=summary['paid_better']==0,
            always_paid_factual_floor_not_below_fixed_baseline=summary['families']['MOVE']['mean_loss']>=summary['means']['baseline_loss'],
            new_collection_or_method_qualified=False,finite_saved_realizations_only=True)
    result=dict(integrity='FOR_INDEPENDENT_SUPPORT_AUDIT',classification=manifest['classification'],manifest_id=manifest['manifest_id'],
        units=rows,summary=summary,group_summaries=grouped,panels=panels,programs=programs,pairwise_programs=pairs,
        existing_selector_rows=selector_rows,existing_selector_summaries=selectors,conclusion=conclusion,
        guard=guard,wall_ns=perf_counter_ns()-start,new_physics=0,new_model_fits=0,new_policy_queries=0,online_LLM_API_calls=0,
        not_a_population_expectation_or_achievable_information_value=True,publication_goal_complete=False)
    io.write(base/'results.json',result);return result

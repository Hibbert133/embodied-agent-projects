"""Literal integer/Fraction audit from raw TRAIN cases and saved public inputs."""
from collections import defaultdict
from fractions import Fraction
from pathlib import Path
from time import perf_counter_ns
from unittest.mock import patch
import math
from src.analysis import correction_program_support_v1 as main

io=main.io
ORDER=('cohort','group','task','seed','context','planned_boundary','acquisition_action','time_constant_s')
ACT=('CONTINUE','VALIDATE8','MOVE_MEASURE');RATE=(.125,.5,2.,8.)
FAM={'CONTINUE':list(range(4)),'VALIDATE8':list(range(4,8)),
     'FREE':list(range(8)),'MOVE':list(range(8,12)),'ALL':list(range(12))}


def denied(*args,**kwargs):raise RuntimeError('main support implementation disabled in literal audit')


def literal_rows(source):
    cases=list(io.rows(source/'train/cases.jsonl.gz'));examples=list(io.rows(source/'train/examples.jsonl.gz'))
    key=lambda c:tuple(c[k] for k in ORDER)
    ex={(key(r['spec']),r['stage']):r['view'] for r in examples}
    assert len(cases)==648 and len(ex)==len(examples)==1296 and all(c['cohort']=='TRAIN' for c in cases)
    by_unit=defaultdict(list)
    for c in cases:
        assert c['completed'] and c['error'] is None and c['close_error'] is None and c['environment_closed']
        assert c['deadline_loss']==(c['total_steps'] if c['success'] else 500)
        by_unit[(c['cohort'],c['group'],c['task'],c['context'])].append(c)
    expected={('TRAIN',g,t,c) for g in range(9) for t in ('push-v3','reach-v3','door-open-v3') for c in ('UNCHANGED','CHANGED')}
    assert set(by_unit)==expected
    rows=[]
    for u,cc in sorted(by_unit.items()):
        mapping={(c['acquisition_action'],c['time_constant_s']):c for c in cc}
        assert len(mapping)==len(cc)==12
        cc=[mapping[a,r] for a in ACT for r in RATE]
        # Candidate action/rate are assignment metadata at PRE; they have not
        # been executed. Compare the complete actual history and memory.
        pre=[]
        for c in cc:
            view=ex[key(c),'PRE']
            pre.append(None if view is None else dict(memory=view['memory'],history=view['history']))
        assert all(v==pre[0] for v in pre)
        available=[]
        for a in range(3):
            views=[ex[key(c),'POST'] for c in cc[4*a:4*a+4]]
            # Original POST views contain the assigned rate. Its zero-time
            # metadata differs; compare the physical/current/memory information.
            from copy import deepcopy
            clean=[]
            for v in views:
                if v is None:clean.append(None);continue
                v=deepcopy(v);v['time_constant_s']=.5;v['memory']['time_constant_s']=.5;clean.append(v)
            assert all(v==clean[0] for v in clean)
            available.append('LIVE' if clean[0] is not None else 'PREFIX_ALREADY_TERMINAL' if pre[0] is None else 'ACQUISITION_ALREADY_TERMINAL')
            if clean[0] is None:assert len({(c['deadline_loss'],c['success'],c['total_steps']) for c in cc[4*a:4*a+4]})==1
        leaves=[dict(loss=c['deadline_loss'],success=c['success'],steps=c['total_steps'],movement_steps=c['movement_steps'],
            measurement_steps=c['measurement_steps'],source_case_key=list(key(c)),source_case_sha256=io.digest(c)) for c in cc]
        ff={}
        for name,indices in FAM.items():
            low=sorted(leaves[i]['loss'] for i in indices)[0]
            choices=[i for i in indices if leaves[i]['loss']==low]
            ff[name]=dict(loss=low,optimal_leaf_indices=choices,
                all_minima_success=not any(not leaves[i]['success'] for i in choices),
                any_minimum_success=any(leaves[i]['success'] for i in choices))
        b=leaves[1]['loss'];f=ff['FREE']['loss'];p=ff['MOVE']['loss'];h=ff['ALL']['loss']
        rows.append(dict(unit=list(u),boundary=cc[0]['planned_boundary'],leaves=leaves,families=ff,baseline_loss=b,
            B_minus_F=b-f,B_minus_P=b-p,F_minus_P=f-p,F_minus_H=f-h,
            prefix_available=pre[0] is not None,return_availability=available))
    return rows


def literal_average(rows,key):
    groups=sorted({r['unit'][1] for r in rows});answer=Fraction()
    for group in groups:
        data=[r[key] for r in rows if r['unit'][1]==group]
        answer+=Fraction(sum(data),len(data))
    return answer/len(groups)


def literal_summary(rows):
    means={key:literal_average(rows,key) for key in ('baseline_loss','B_minus_F','B_minus_P','F_minus_P','F_minus_H')}
    families={}
    for name in FAM:
        rr=[dict(unit=r['unit'],x=r['families'][name]['loss']) for r in rows];value=literal_average(rr,'x')
        families[name]=dict(mean_loss=float(value),mean_loss_exact=str(value),
            minimum_successes=sum(1 for r in rows if r['families'][name]['all_minima_success']),
            maximum_successes=sum(1 for r in rows if r['families'][name]['any_minimum_success']))
    return dict(units=len(rows),groups=len({r['unit'][1] for r in rows}),means={k:float(v) for k,v in means.items()},
        means_exact={k:str(v) for k,v in means.items()},families=families,
        paid_better=sum(r['F_minus_P']>0 for r in rows),paid_worse=sum(r['F_minus_P']<0 for r in rows),paid_tie=sum(r['F_minus_P']==0 for r in rows),
        paid_positive_steps=sum(r['F_minus_P'] for r in rows if r['F_minus_P']>0),paid_negative_steps=-sum(r['F_minus_P'] for r in rows if r['F_minus_P']<0),
        prefix_unavailable=sum(r['prefix_available'] is False for r in rows),
        unavailable_returns={a:sum(r['return_availability'][i]!='LIVE' for r in rows) for i,a in enumerate(ACT)})


def audit(path):
    path=Path(path).resolve();manifest=main.checked(path);base=path.parent;result=io.read(base/'results.json');start=perf_counter_ns()
    assert result['manifest_id']==manifest['manifest_id'] and result['classification']=='POST_HOC_TRAIN_ONLY_FINITE_FACTUAL_SUPPORT_AUDIT'
    fields=0;guard={}
    def compare(actual,expected):
        nonlocal fields
        if isinstance(expected,dict):
            assert type(actual) is dict and set(actual)==set(expected)
            for k in expected:compare(actual[k],expected[k])
        elif isinstance(expected,list):
            assert type(actual) is list and len(actual)==len(expected)
            for a,b in zip(actual,expected):compare(a,b)
        else:
            assert type(actual) is type(expected)
            assert math.isclose(actual,expected,rel_tol=0,abs_tol=1e-12) if isinstance(expected,float) else actual==expected
            fields+=1
    disabled=('validate_graph','load_graphs','envelope','unit_row','group_average','aggregate','analyze')
    with main.prior.recorded_guard(guard,base/'audit_failure.json'),patch.multiple(main,**{name:denied for name in disabled}):
        rows=literal_rows(main.ROOT/manifest['config']['source_A1_run']);compare(result['units'],rows)
        summary=literal_summary(rows);compare(result['summary'],summary)
        compare(result['group_summaries'],[dict(group=g,summary=literal_summary([r for r in rows if r['unit'][1]==g])) for g in range(9)])
        panels=[]
        for t in ('push-v3','reach-v3','door-open-v3'):
            for c in ('UNCHANGED','CHANGED'):
                for b in (16,32,64):panels.append(dict(task=t,context=c,boundary=b,summary=literal_summary([r for r in rows if r['unit'][2:]==[t,c] and r['boundary']==b])))
        compare(result['panels'],panels)
        programs=[];pairs=[]
        for i in range(12):
            ll=[r['leaves'][i] for r in rows];cost=Fraction(sum(v['loss'] for v in ll),54)
            programs.append(dict(index=i,action=ACT[i//4],rate=RATE[i%4],units=54,success=sum(v['success'] for v in ll),mean_loss=float(cost),mean_loss_exact=str(cost),
                actual_source_steps=sum(v['steps'] for v in ll),movement_steps=sum(v['movement_steps'] for v in ll),measurement_steps=sum(v['measurement_steps'] for v in ll)))
            for j in range(12):
                dd=[r['leaves'][i]['loss']-r['leaves'][j]['loss'] for r in rows];mean=Fraction(sum(dd),54)
                pairs.append(dict(left=i,right=j,units=54,mean_difference=float(mean),mean_difference_exact=str(mean),
                    harm=sum(d>0 for d in dd),help=sum(d<0 for d in dd),ties=sum(d==0 for d in dd),
                    success_to_failure=sum(1 for r in rows if r['leaves'][j]['success'] and not r['leaves'][i]['success']),
                    failure_to_success=sum(1 for r in rows if not r['leaves'][j]['success'] and r['leaves'][i]['success'])))
        compare(result['programs'],programs);compare(result['pairwise_programs'],pairs)
        old=io.read(main.ROOT/manifest['config']['source_trace_run']/'results.json');mapping={tuple(r['unit']):r for r in rows};sr=[]
        for s in old['results']:
            row=mapping[tuple(s['unit'])];i=4*ACT.index(s['action'])+RATE.index(s['rate']);leaf=row['leaves'][i]
            assert s['source_case_key']==leaf['source_case_key'] and s['source_case_sha256']==leaf['source_case_sha256']
            assert s['loss']==leaf['loss'] and s['success']==leaf['success']
            sr.append(dict(unit=row['unit'],selector=s['selector'],source_leaf=i,loss=leaf['loss'],success=leaf['success'],
                same_family_realized_gap=leaf['loss']-row['families'][('CONTINUE','VALIDATE8','MOVE')[i//4]]['loss'],
                all_family_realized_gap=leaf['loss']-row['families']['ALL']['loss'],difference_to_free_envelope=leaf['loss']-row['families']['FREE']['loss']))
        compare(result['existing_selector_rows'],sr);summaries=[]
        for name in sorted({s['selector'] for s in sr}):
            rr=[r for r in sr if r['selector']==name];assert len(rr)==54
            summaries.append(dict(selector=name,units=54,success=sum(r['success'] for r in rr),
                **{k:float(literal_average(rr,k)) for k in ('loss','same_family_realized_gap','all_family_realized_gap','difference_to_free_envelope')}))
        compare(result['existing_selector_summaries'],summaries)
        compare(result['conclusion'],dict(no_paid_leaf_improves_free_factual_envelope=summary['paid_better']==0,
            always_paid_factual_floor_not_below_fixed_baseline=Fraction(summary['families']['MOVE']['mean_loss_exact'])>=Fraction(summary['means_exact']['baseline_loss']),
            new_collection_or_method_qualified=False,finite_saved_realizations_only=True))
        source_summary=io.read(main.ROOT/manifest['config']['source_A1_run']/'train/summary.json')
        assert sum(p['actual_source_steps'] for p in programs)==source_summary['control_steps']
    receipt=dict(integrity='PASSED',manifest_id=manifest['manifest_id'],results_sha256=io.sha(base/'results.json'),checked_fields=fields,
        source_cases=648,source_units=54,program_pairs=144,source_graph_reconstructed_from_raw_cases_and_examples=True,
        main_functions_disabled=list(disabled),guard=guard,wall_ns=perf_counter_ns()-start,
        new_physics=0,new_model_fits=0,new_policy_queries=0,online_LLM_API_calls=0,
        not_a_population_or_task_qualification=True)
    io.write(base/'audit.json',receipt);return receipt

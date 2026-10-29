"""Independent typed information classes and exhaustive contingent-plan audit."""
from itertools import product
from fractions import Fraction
import math


def check(ok,msg):
    if not ok:raise ValueError('independent frontier: '+msg)


def signature(v):
    if type(v) is dict:return ('dict',tuple((k,signature(v[k])) for k in sorted(v)))
    if type(v) is list:return ('list',tuple(map(signature,v)))
    if type(v) is float:
        check(math.isfinite(v),'finite public value');return ('float',v.hex())
    if type(v) is bool:return ('bool',v)
    if type(v) is int:return ('int',v)
    if type(v) is str:return ('str',v)
    check(v is None,'known type');return ('null',)


def reconstruct(graphs,limit=1_000_000):
    names=('UNIT_CLAIRVOYANT','ROOT_CONTINUE_ONLY','ROOT_STATIC','ROOT_ADAPTIVE_FULL','ROOT_ADAPTIVE_MASK','GLOBAL_FIXED_BEST',
        *('FIXED_'+str(i).zfill(2) for i in range(12)))
    chosen={n:{} for n in names};roots={};enumerated=0
    for i,g in enumerate(graphs):
        if g['pre'] is None:
            for n in names:chosen[n][i]=(None,None)
        else:roots.setdefault(signature(g['pre']),[]).append(i)
    global_best=min(range(12),key=lambda j:(sum(g['leaves'][j]['loss'] for g in graphs),j))
    for i,g in enumerate(graphs):
        if g['pre'] is None:continue
        options={'UNIT_CLAIRVOYANT':min(range(12),key=lambda j:(g['leaves'][j]['loss'],j)),'GLOBAL_FIXED_BEST':global_best}
        options.update({'FIXED_'+str(j).zfill(2):j for j in range(12)})
        for n,j in options.items():chosen[n][i]=(j//4,None if g['returns'][j//4] is None else j%4)
    for indices in roots.values():
        for name,m in (('ROOT_CONTINUE_ONLY',4),('ROOT_STATIC',12)):
            j=min(range(m),key=lambda j:(sum(graphs[i]['leaves'][j]['loss'] for i in indices),j))
            for i in indices:chosen[name][i]=(j//4,None if graphs[i]['returns'][j//4] is None else j%4)
        for mode in ('FULL','MASK'):
            alternatives=[]
            for a in range(3):
                classes={};terminals=[]
                for i in indices:
                    node=graphs[i]['returns'][a]
                    if node is None:terminals.append(i);continue
                    if mode=='FULL':observed=node
                    else:observed={k:node[k] for k in ('schema','stage','task','completed_steps','current','integral_xy','controller','acquisition_action')}
                    key=(signature(graphs[i]['pre']),signature(observed));classes.setdefault(key,[]).append(i)
                partitions=list(classes.values());plans=4**len(partitions)
                check(enumerated+plans<=limit,'registered total enumeration budget');enumerated+=plans
                best=None;best_choices=None
                for rates in product(range(4),repeat=len(partitions)):
                    cost=sum(graphs[i]['leaves'][4*a]['loss'] for i in terminals)
                    decisions={i:(a,None) for i in terminals}
                    for members,rate in zip(partitions,rates):
                        for i in members:cost+=graphs[i]['leaves'][4*a+rate]['loss'];decisions[i]=(a,rate)
                    candidate=(cost,rates)
                    if best is None or candidate<best:best=candidate;best_choices=decisions
                alternatives.append((best[0],a,best_choices))
            best=min(alternatives,key=lambda v:(v[0],v[1]));chosen['ROOT_ADAPTIVE_'+mode].update(best[2])
    return chosen,enumerated,len(roots)


def audit(graphs,result):
    chosen,enumerated,roots=reconstruct(graphs);rows=result['records'];seen=set();totals={n:0 for n in chosen}
    for row in rows:
        n=row['functional'];i=row['unit_index'];check((n,i) not in seen,'no repeated selection');seen.add((n,i))
        a,rate=chosen[n][i];j=0 if a is None else 4*a+(0 if rate is None else rate);q=graphs[i]['leaves'][j]
        check((row['chosen_acquisition_index'],row['rate_index'],row['factual_leaf_index'])==(a,rate,j),'nonanticipative empirical selection')
        check(row['loss']==q['loss'] and row['success']==q['success'] and row['source_case_key']==q['source_case_key']
            and row['source_case_sha256']==q['source_case_sha256'],'actual complete source leaf')
        check(row['uses_future_labels'] and not row['deployable'] and not row['new_robot_execution'],'oracle status disclosed')
        totals[n]+=q['loss']
    check(len(seen)==18*len(graphs) and totals==result['totals'] and roots==len(result['root_classes']),'all totals/classes')
    return dict(exhaustive_contingent_plans=enumerated,selection_rows=len(rows),root_classes=roots,
        optimizer_uses_future_labels=True,independent_of_main_factorized_solver=True)


def audit_strata(graphs,result,summary,groups,cells):
    by={(r['functional'],r['unit_index']):r for r in result['records']}
    for name,value in summary['functionals'].items():
        total=sum(by[(name,i)]['loss'] for i in range(54))
        check(value['cases']==54 and value['total_loss']==total and value['mean_loss_exact']==str(Fraction(total,54)),'exact overall summary')
        check(value['success']==sum(by[(name,i)]['success'] for i in range(54)),'success denominator')
    check(len(groups)==162 and len(cells)==324,'all strata rows')
    for row in [*groups,*cells]:
        ids=[i for i,g in enumerate(graphs) if (g['unit'][1]==row['group'] if 'group' in row else
            (g['unit'][2],g['unit'][3],g['boundary'])==(row['task'],row['context'],row['boundary']))]
        check(len(ids)==row['cases'],'stratum denominator')
        total=sum(by[(row['functional'],i)]['loss'] for i in ids)
        check(row['mean_loss_exact']==str(Fraction(total,len(ids))),'stratum full-cost mean')
        if 'success' in row:check(row['success']==sum(by[(row['functional'],i)]['success'] for i in ids),'stratum success')
    all_members=[];signatures=set();conflicts=gap=0
    for c in summary['root_classes']:
        indices=c['members'];keys={signature(graphs[i]['pre']) for i in indices}
        check(len(keys)==1 and not (keys & signatures),'one exact public class');signatures.update(keys);all_members.extend(indices)
        static=min(sum(graphs[i]['leaves'][j]['loss'] for i in indices) for j in range(12))
        unit=sum(min(q['loss'] for q in graphs[i]['leaves']) for i in indices);delta=static-unit
        check(c['unavoidable_empirical_same_input_gap']==delta,'information conflict cost')
        conflicts+=int(delta>0);gap+=delta
    check(sorted(all_members)==[i for i,g in enumerate(graphs) if g['pre'] is not None],'all live information classes')
    check(summary['conflicting_root_classes']==conflicts and summary['total_same_input_gap']==gap,'all conflict summaries')
    return dict(group_rows=162,joint_cells=324,all_exact_totals=True,all_live_classes=True)

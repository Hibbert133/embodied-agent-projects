"""Independent temporal reader: receipts from delivered STEP_COMPLETE.after.

No main-selector imports. JSON/SHA/stream codecs are shared infrastructure.
Original private physics/process audits are reused, not replayed here.
"""
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json


def check(ok, text):
    if not ok: raise ValueError('independent: '+text)


def h(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest()


def rebuild(spec, p, events, proposed):
    history, positions, windows = [], {}, []
    pending = query = choice = None
    first = None; program = None; final = None
    for e in events:
        if e['event'] == 'STEP_COMPLETE':
            check(pending is not None and e['logical_step'] == len(history), 'receipt without chronological command')
            # The after observation is delivered to the actor. No executed_action,
            # noise, fault, native witness or private state is copied here.
            row = dict(at_calls=len(history), before=pending['before'], command=pending['command'], after=e['after'],
                       raw_policy=pending['raw_policy'], phase=pending['phase'])
            check(row['before'] == (history[-1]['after'] if history else p['initial']), 'true current state')
            history.append(row); pending = None
        elif e['event'] == 'AGENT_EVENT':
            k, a = e['agent_event'], e['public_payload']
            check(a['at_calls'] == len(history), 'actor at actual receipt time')
            if k == 'PROGRAM':
                program = {z:a[z] for z in ('task', 'boundary', 'window_steps')}
            elif k == 'COMMAND':
                check(pending is None, 'duplicate pending send'); pending = a
            elif k in ('ACQUISITION_CHOICE', 'TASK_MEMORY_RETURN'):
                check(pending is None, 'snapshot before physical receipt')
                before = k == 'ACQUISITION_CHOICE'
                m = a['before_memory' if before else 'memory']
                check(set(m) == {'schema', 'task', 'completed_steps', 'current', 'controller', 'integral_xy', 'time_constant_s'}
                      and m['completed_steps'] == len(history) and m['current'] == (history[-1]['after'] if history else p['initial']), 'memory projection')
                point = 'BEFORE_ACQUISITION' if before else 'AFTER_ACQUISITION'
                v = dict(schema='TRAIN_DECISION_VIEW_V1', decision_point=point, task=program['task'],
                    planned_boundary=program['boundary'], initial=p['initial'], memory=m,
                    remaining_steps=500-len(history), window_steps=program['window_steps'],
                    past_acquisition_action=None if before else spec['acquisition_action'], history=history,
                    decision_required=len(history)<500 and not any(m['current'][x] for x in ('success','terminated','truncated')))
                positions['before' if before else 'after'] = dict(point=point, at_calls=len(history),
                    decision_required=v['decision_required'], view_sha256=h(v),
                    source_anchor=dict(outer_sequence=e['sequence'], public_sequence=a['sequence'], event=k),
                    components_sha256={z:h(x) for z,x in v.items()},
                    reconstruction='whitelisted event memory + public projection prefix + actual COMMAND phase/raw_policy',
                    metadata_and_hashes_are_not_model_features=True)
                if not before: first = deepcopy(m)
            elif k == 'WINDOW_QUERY':
                check(query is None and choice is None and a['value']['history'] == [
                    {z:r[z] for z in ('at_calls','before','command','after')} for r in history], 'query cannot consume future')
                query = a
                if not windows:
                    check(first is not None and first['completed_steps'] == len(history)
                        and first['integral_xy'] == a['value']['integral_xy'], 'actual return memory before first query')
            elif k == 'WINDOW_DECISION':
                check(query is not None and a['input_sequence'] == query['sequence'], 'decision parent'); choice = a
            elif k == 'WINDOW_RESULT':
                check(choice is not None and a['parent_sequence'] == choice['sequence'], 'window label parent')
                windows.append(dict(query=query['value'], selected_rate=choice['declaration']['selected_rate'], measurement=a['measurement']))
                query = choice = None
            elif k == 'OUTCOME': final = a
    check(pending is None and query is None and choice is None and final is not None, 'closed temporal stream')
    check([{z:r[z] for z in ('at_calls','before','command','after')} for r in history] == p['history'], 'all delivered receipts versus independent public projection')
    check(windows == p['windows'], 'all factual future windows')
    check(proposed['before'] == positions.get('before') and proposed['after'] == positions.get('after'), 'both full public view hashes and source anchors')
    n = len(history); success = history[-1]['after']['success']; loss = n if success else 500
    check(proposed['total_steps'] == n and proposed['success'] == success and proposed['deadline_loss'] == loss
        and final['outcome']['deadline_loss'] == loss, 'complete task loss versus physical count')
    rates = [w['selected_rate'] for w in windows]; label = proposed['labels']
    train_fixed = spec['cohort'] == 'TRAIN' and spec['behavior'] == 'BLOCK_FIXED' and bool(rates)
    check(spec['behavior'] != 'BLOCK_FIXED' or len(set(rates)) <= 1, 'fixed complete controller')
    check(label['actual_rates'] == rates and label['static_TRAIN_supervised_label_admitted'] == train_fixed, 'typed training label admission')
    check(label['actual_windows'] == [dict(start_at=w['query']['completed_steps'],end_at=w['measurement']['end_at'],
        selected_rate=w['selected_rate'],full_window=w['measurement']['full_window']) for w in windows]
        and label['source_complete_deadline_loss']==loss and label['complete_labels_include_unexecuted_failure_penalty'] is True,
        'full window and loss label roles')
    check(label['terminal_role'] == ('NO_GAIN_DECISION' if not rates else 'FACTUAL_STATIC_PROGRAM'
        if spec['behavior'] == 'BLOCK_FIXED' else 'FACTUAL_RANDOM_CONTINUATION'), 'terminal cannot be pasted onto first gain')
    for point in ('before', 'after'):
        pos = positions.get(point)
        check(label[point+'_remaining_loss'] == (None if pos is None else loss-pos['at_calls']), 'full remaining loss including failure penalty once')
    check(label['observed_constant_random_sequence'] == (bool(rates) and spec['behavior']=='RANDOM_WINDOW' and len(set(rates))==1), 'future-selected random subsequence')
    check(len(label['static_targets']) == 4, 'all targets retained')
    for t, target in zip((.125,.5,2.,8.), label['static_targets']):
        divergence = next((i for i,v in enumerate(rates) if v != t), None)
        check(target['target_static_rate'] == t and target['first_different_window'] == divergence, 'first actual gain divergence')
        check(target['compatible_observed_rate_sequence'] == (bool(rates) and divergence is None), 'finite observed support only')
        check(target['target_terminal_loss'] == (loss if train_fixed and divergence is None else None), 'no unsupported counterfactual labels')
        status=('FACTUAL_STATIC_TRAIN' if train_fixed and divergence is None else 'NO_GAIN_DECISION' if not rates
            else 'NATIVE_VALIDATION_ONLY' if spec['cohort']!='TRAIN'
            else 'RANDOM_COMPATIBILITY_NOT_UNWEIGHTED_LABEL' if spec['behavior']=='RANDOM_WINDOW' and divergence is None
            else 'DIFFERENT_PROGRAM_NO_COUNTERFACTUAL_OUTCOME')
        check(target['target_label_status']==status,'explicit non-admission reason')
    check(not label['causal_value_or_generalization_qualified'], 'no inference promotion')
    check(proposed['data_role'] == ('TRAIN' if spec['cohort']=='TRAIN' else 'VALIDATION_ONLY'), 'native cannot train')
    reason = 'ENDED_BEFORE_OR_AT_BOUNDARY' if 'before' not in positions else 'ENDED_DURING_ACQUISITION' if not positions['after']['decision_required'] else None
    check(proposed['missing_reason'] == reason, 'all missingness retained')
    return len(history)+len(windows)+30


def audit_summary(rows, result):
    checks = 0
    # Recompute every published scalar count with independent explicit loops.
    def panel(selected):
        missing=Counter(); roles=Counter()
        out=dict(cases=0,task_failures=0,before_views=0,after_views=0,live_after_views=0,windows=0,static_TRAIN_labels=0,constant_random=0)
        for r in selected:
            out['cases']+=1;out['task_failures']+=int(r['success'] is False)
            out['before_views']+=int(r['before'] is not None);out['after_views']+=int(r['after'] is not None)
            out['live_after_views']+=int(r['after'] is not None and r['after']['decision_required'])
            out['windows']+=len(r['labels']['actual_rates']);out['static_TRAIN_labels']+=int(r['labels']['static_TRAIN_supervised_label_admitted'])
            out['constant_random']+=int(r['labels']['observed_constant_random_sequence'])
            missing.update([r['missing_reason'] or 'AVAILABLE']);roles.update([r['labels']['terminal_role']])
        return dict(**out,missing=dict(missing),roles=dict(roles))
    check(result['overall']==panel(rows),'overall denominator');checks+=10
    check(result['group_cells']==len({tuple(r['spec'][k] for k in ('cohort','group','task','context','planned_boundary','acquisition_action','behavior')) for r in rows}), 'all group cells')
    for c,v in result['by_cohort'].items():
        check(v==panel([r for r in rows if r['spec']['cohort']==c]),'cohort denominator');checks+=10
    check(len(result['cells'])==36,'full task condition boundary panels including unavailable native B32/B64')
    for cell in result['cells']:
        check({k:v for k,v in cell.items() if k not in ('cohort','task','context','planned_boundary')}==panel([
            r for r in rows if all(r['spec'][k]==cell[k] for k in ('cohort','task','context','planned_boundary'))]),'full cell');checks+=10
    for alias in result['alias_comparisons']:
        rs=[r for r in rows if all(r['spec'][k]==v for k,v in alias['key'].items())]
        views=[r[alias['point']] for r in rs if r[alias['point']] is not None]
        eq=None if len(views)!=len(rs) else all(v['view_sha256']==views[0]['view_sha256'] for v in views)
        diff=sorted(k for k in (views[0]['components_sha256'] if views else {})
            if any(v['components_sha256'][k]!=views[0]['components_sha256'][k] for v in views))
        check(alias['allocated']==len(rs) and alias['available']==len(views) and alias['missing']==len(rs)-len(views)
              and alias['all_equal']==eq and alias['differing_components']==diff,'all alias members, never equate missing views');checks+=6
        if alias['comparison']=='behavior': check(eq is not False,'paired behavior pre-first-rate history equality')
    for key, value in result['alias_summary'].items():
        variant,point=key.split(':');expected=Counter()
        for a in result['alias_comparisons']:
            if a['comparison']==variant and a['point']==point:
                expected.update(['MISSING' if a['all_equal'] is None else 'EQUAL' if a['all_equal'] else 'DIFFERENT'])
        check(dict(expected)==value,'alias counts');checks+=1
    return checks

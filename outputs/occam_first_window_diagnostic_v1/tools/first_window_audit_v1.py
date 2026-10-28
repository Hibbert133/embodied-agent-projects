"""Independent literal source reader and Fraction arithmetic. No model imports."""
from fractions import Fraction
from itertools import combinations
import hashlib
import json
import math


def need(ok, message):
    if not ok: raise ValueError(message)


def hash_value(value):
    raw = json.dumps(value, separators=(',', ':'), sort_keys=True, allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def signature(row):
    if row is None: return None
    return {'logical_step':row['logical_step'], 'native_sha256':row['witness']['native_sha256'],
            'comparison_python_sha256':row['witness']['comparison_python_sha256'],
            'simulation_time':row['source_witness']['simulation_time'],
            'noise_past_sha256':row['source_witness']['noise_past_sha256']}


def literal_extract(case, spec, events, private):
    need(all(case[k] == v for k,v in spec.items()), 'independent case identity')
    need(case['completed'] and case['environment_closed'] and case['error'] is case['close_error'] is None,
         'independent complete technical result')
    need(case['deadline_loss'] == (case['total_steps'] if case['success'] else 500), 'independent complete loss')
    public = []; steps = []; beginning = None; last = -1; query = decision = result = plan = None
    for row in events:
        need(all(row[k] == v for k,v in spec.items()), 'independent event allocation')
        need(row['saved_ns'] > last, 'independent event ordering'); last = row['saved_ns']
        if row['event'] == 'CONTROLLED_INITIAL':
            need(beginning is None and not steps, 'single initial'); beginning = row['simulation_time']
        if row['event'] == 'STEP_COMPLETE': steps.append(row)
        if row['event'] != 'AGENT_EVENT': continue
        name, payload = row['agent_event'], row['public_payload']; public.append((name,payload))
        if name == 'WINDOW_QUERY': need(query is None, 'first query only'); query = payload
        if name == 'WINDOW_DECISION': need(query is not None and decision is None, 'causal saved decision'); decision = payload
        if name == 'RATE_PLAN': plan = payload
        if name == 'WINDOW_RESULT': result = payload; break
    need((query is None) == (decision is None) == (result is None), 'independent no partial window')
    history = []; before = case['initial']; clock = beginning
    for index, row in enumerate(steps):
        need(row['logical_step'] == index and row['noise_cursor_after'] == index+1
             and row['simulation_time_before'] == clock, 'independent causal noise and clock')
        history.append({'at_calls':index, 'before':before, 'command':row['command'], 'after':row['after']})
        before = row['after']; clock = row['simulation_time_after']
    n = len(steps) if query is None else query['value']['completed_steps']
    memory = None if query is None else plan['before_memory']
    if query is not None:
        q, d, m = query['value'], decision['declaration'], result['measurement']
        need(q['history'] == history[:n] and q['initial'] == case['initial'], 'independent no future input')
        need(query['sequence']+1 == decision['sequence'] and decision['input_sequence'] == query['sequence']
             and d['public_query_sha256'] == hash_value(q), 'independent query/declaration link')
        need(d['declaration_sha256'] == hash_value({k:v for k,v in d.items() if k != 'declaration_sha256'}), 'independent declaration hash')
        need(memory['integral_xy'] == q['integral_xy'] and memory['time_constant_s'] == .5
             and memory['completed_steps'] == n, 'independent current memory')
        need(q['evaluation_steps'] == d['evaluation_steps'] == m['planned_steps'] == min(16,500-n), 'independent planned window')
        need(result['parent_sequence'] == decision['sequence'] and m['rows_sha256'] == hash_value(history[n:])
             and m['actual_steps'] == len(steps)-n and m['start_at'] == n and m['end_at'] == len(steps), 'independent executed first window')
        need(m['full_window'] == (m['actual_steps'] == m['planned_steps'])
             and (m['full_window'] or m['terminal']), 'independent retain terminal short window')
    labels = {}
    for row in private:
        need(all(row[k] == v for k,v in spec.items()) and row['label'] not in labels, 'independent witness identity/uniqueness')
        labels[row['label']] = signature(row)
        if query is not None and row['label'] == 'FIRST_RATE_POST': break
    first_clock = None if query is None else beginning if n == 0 else steps[n-1]['simulation_time_after']
    if query is not None:
        need(labels['FIRST_RATE_PRE'] == labels['FIRST_RATE_POST'] and labels['FIRST_RATE_PRE']['logical_step'] == n
             and labels['FIRST_RATE_PRE']['simulation_time'] == first_clock, 'independent nonphysical rate transition')
    returned = [p['memory'] for name,p in public if name == 'TASK_MEMORY_RETURN']
    bank = next(p['bank_sha256'] for name,p in public if name == 'PROGRAM')
    physical = [{k:r[k] for k in ('command','raw_policy','after','executed_action_oracle',
                                 'simulation_time_before','simulation_time_after','noise_cursor_after','reward')} for r in steps[:n]]
    return {'spec':spec, 'success':case['success'], 'deadline_loss':case['deadline_loss'], 'total_steps':case['total_steps'],
        'initial_sha256':hash_value(case['initial']), 'initial_witness':labels['INITIAL'],
        'post_acquisition_witness':labels.get('POST_ACQUISITION'),
        'post_memory_sha256':hash_value(returned[0]) if returned else None,
        'first_rate_witness':labels.get('FIRST_RATE_PRE'), 'query_sha256':None if query is None else hash_value(query['value']),
        'first_at':None if query is None else n, 'planned_steps':None if query is None else query['value']['evaluation_steps'],
        'first_clock':first_clock, 'initial_clock':beginning, 'noise_cursor_at_query':None if query is None else n,
        'before_memory_sha256':None if memory is None else hash_value(memory),
        'prefix_history_sha256':hash_value(history[:n]), 'prefix_physical_sha256':hash_value(physical),
        'bank_sha256':bank, 'declaration':None if decision is None else decision['declaration'],
        'measurement':None if result is None else result['measurement'],
        'missing_reason':None if query is not None else 'BEFORE_INTERVENTION' if not case['boundary_applied'] else 'AFTER_ACQUISITION_NO_WINDOW'}


def ranks(left, right):
    pairs = []; total = Fraction(); denominator = 0
    for i in range(4):
        for j in range(i+1,4):
            ps = 0 if left[i] == left[j] else 1 if left[i] > left[j] else -1
            rs = 0 if right[i] == right[j] else 1 if right[i] > right[j] else -1
            value = None if rs == 0 else Fraction(1,2) if ps == 0 else Fraction(int(ps != rs))
            if value is not None: total += value; denominator += 1
            pairs.append(dict(indices=[i,j], predicted_sign=ps, actual_sign=rs, error=None if value is None else float(value)))
    return dict(pairs=pairs, actual_ties=6-denominator, comparable_pairs=denominator,
                mean_error=None if denominator == 0 else float(total/denominator))


def verify_context(capsules, row, constant):
    names = ('PI_0125','PI_0500','PI_2000','PI_8000','META_ADAPT','META_FROZEN','ERM_ADAPT','ERM_FROZEN')
    by = {c['spec']['program'].split('__')[0]:c for c in capsules}; need(len(capsules)==8 and set(by) == set(names), 'independent all eight programs')
    need(len(row['learned'])==4, 'independent four learned rows')
    columns = ('initial_sha256','initial_witness','post_acquisition_witness','post_memory_sha256','first_rate_witness',
               'query_sha256','first_at','planned_steps','first_clock','initial_clock','noise_cursor_at_query',
               'before_memory_sha256','prefix_history_sha256','prefix_physical_sha256')
    reasons = ['MISMATCH_'+k.upper() for k in columns if any(c[k] != capsules[0][k] for c in capsules)]
    no_window = sum(c['declaration'] is None for c in capsules)
    if no_window: reasons.append('ALL_NO_FIRST_WINDOW' if no_window == 8 else 'MIXED_WINDOW_AVAILABILITY')
    for a,b in (('META_ADAPT','META_FROZEN'),('ERM_ADAPT','ERM_FROZEN')):
        if by[a]['declaration'] != by[b]['declaration'] or by[a]['bank_sha256'] != by[b]['bank_sha256']:
            reasons.append('FIRST_BANK_DECLARATION_MISMATCH_'+a.split('_')[0])
    checks = {}
    for target in names[4:]:
        dec = by[target]['declaration']; checks[target] = None if dec is None else by[target]['measurement'] == by[names[dec['selected_index']]]['measurement']
        if checks[target] is False: reasons.append('SELECTED_FIRST_WINDOW_MISMATCH_'+target)
    need(row['alignment_reasons'] == reasons and row['selected_first_window_matches'] == checks, 'independent full alignment/missingness')
    cost = None if reasons else [by[name]['measurement']['cost'] for name in names[:4]]
    loss = [by[name]['deadline_loss'] for name in names[:4]]
    need(row['actual_first_costs'] == cost and row['fixed_full_deadline_losses'] == loss, 'independent factual vectors')
    need(row['fixed_successes'] == [by[n]['success'] for n in names[:4]], 'independent fixed failures')
    need(row['fixed_actual_window_steps'] == [None if by[n]['measurement'] is None else by[n]['measurement']['actual_steps'] for n in names[:4]], 'independent short lengths')
    need(row['fixed_first_vs_full_rank'] == (None if cost is None else ranks(cost,loss)), 'independent proxy/task ordering')
    for target, saved in zip(names[4:],row['learned']):
        dec = by[target]['declaration']; p = None if dec is None else [r['mean'][0] for r in dec['predictions']]
        need(saved['target'] == target and saved['saved_predicted_costs'] == p
             and saved['saved_selected_index'] == (None if dec is None else dec['selected_index']), 'independent saved predictions')
        if cost is None: need(saved['metric'] is None, 'unavailable not zero'); continue
        m = saved['metric']; need(m['rank'] == ranks(p,cost), 'independent all six ordering pairs')
        reference = {'MSE':float(sum((Fraction(x)-Fraction(y))**2 for x,y in zip(p,cost))/4),
                     'constant_MSE':float(sum((Fraction(constant)-Fraction(y))**2 for y in cost)/4),
                     'first_window_choice_gap':cost[dec['selected_index']]-min(cost)}
        for key,value in reference.items(): need(math.isclose(m[key],value,rel_tol=1e-12,abs_tol=1e-12), 'independent '+key)


def verify_summary(rows, target, saved):
    need(saved['target'] == target and saved['allocated_contexts'] == len(rows), 'independent complete summary denominator')
    groups = sorted({r['context']['group'] for r in rows})
    need(saved['allocated_groups'] == len(groups) and [g['group'] for g in saved['groups']] == groups, 'independent group census')
    global_means = {}
    for name in ('MSE','constant_MSE','first_window_choice_gap','rank_error','fixed_first_vs_full_rank_error'):
        group_values = []
        for g, record in zip(groups,saved['groups']):
            selected = [r for r in rows if r['context']['group'] == g]; values = []
            need(record['allocated_contexts'] == len(selected), 'independent allocated contexts/group')
            for row in selected:
                m = next(v for v in row['learned'] if v['target'] == target)['metric']
                if m is None: continue
                v = m['rank']['mean_error'] if name == 'rank_error' else row['fixed_first_vs_full_rank']['mean_error'] if name == 'fixed_first_vs_full_rank_error' else m[name]
                if v is not None: values.append(Fraction(v))
            mean = None if not values else float(sum(values)/len(values))
            need(record['available'][name] == len(values), 'independent availability')
            need((mean is None and record['means'][name] is None) or mean is not None and math.isclose(mean,record['means'][name],abs_tol=1e-12,rel_tol=1e-12), 'independent group mean')
            if mean is not None: group_values.append(Fraction(mean))
        aggregate = saved['equal_available_group_means'][name]
        need(aggregate['available_groups'] == len(group_values), 'independent available group count')
        value = None if not group_values else float(sum(group_values)/len(group_values))
        need((value is None and aggregate['mean'] is None) or value is not None and math.isclose(value,aggregate['mean'],abs_tol=1e-12,rel_tol=1e-12), 'independent equal group mean')
    reasons = {}
    for row in rows:
        for reason in row['alignment_reasons']: reasons[reason] = reasons.get(reason,0)+1
    need(saved['missing_reasons'] == reasons, 'independent complete missingness')

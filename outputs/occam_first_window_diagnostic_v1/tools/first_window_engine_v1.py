"""Record-only descriptive diagnostics; no robot, policy or model imports."""
from collections import Counter
from fractions import Fraction
from itertools import combinations, product
import hashlib
import json
import math

RATES = (.125, .5, 2., 8.)
FIXED = ('PI_0125', 'PI_0500', 'PI_2000', 'PI_8000')
TARGETS = ('META_ADAPT', 'META_FROZEN', 'ERM_ADAPT', 'ERM_FROZEN')
ARMS = ('CONTINUE', 'VALIDATE8', 'MOVE_MEASURE')
TASKS = ('push-v3', 'reach-v3', 'door-open-v3')
CONDITIONS = ('UNCHANGED', 'CHANGED')
FIELDS = ('cohort', 'group', 'task', 'seed', 'context', 'planned_boundary', 'program')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def finite(value):
    require(type(value) in (int, float) and math.isfinite(value), 'finite literal scalar')
    return value


def rank_errors(predicted, actual):
    require(len(predicted) == len(actual) == 4, 'complete four-candidate vectors')
    for value in (*predicted, *actual):
        finite(value)
    rows = []
    for i, j in combinations(range(4), 2):
        p = (predicted[i] > predicted[j]) - (predicted[i] < predicted[j])
        a = (actual[i] > actual[j]) - (actual[i] < actual[j])
        error = None if a == 0 else .5 if p == 0 else float(p != a)
        rows.append(dict(indices=[i, j], predicted_sign=p, actual_sign=a, error=error))
    available = [r['error'] for r in rows if r['error'] is not None]
    return dict(pairs=rows, actual_ties=6-len(available), comparable_pairs=len(available),
                mean_error=None if not available else math.fsum(available)/len(available))


def vector_metrics(predicted, actual, selected, constant):
    require(type(selected) is int and 0 <= selected < 4, 'saved selected candidate')
    finite(constant)
    ranks = rank_errors(predicted, actual)
    return dict(MSE=math.fsum((p-a)**2 for p, a in zip(predicted, actual))/4,
                constant_MSE=math.fsum((constant-a)**2 for a in actual)/4,
                first_window_choice_gap=actual[selected]-min(actual), rank=ranks)


def validate_case(case, spec):
    require(all(case[k] == spec[k] for k in FIELDS), 'complete source identity')
    require(case['completed'] is True and case['environment_closed'] is True
            and case['error'] is None and case['close_error'] is None, 'complete technical execution')
    n = case['total_steps']
    require(type(n) is int and 0 <= n <= 500 and type(case['success']) is bool
            and type(case['deadline_loss']) is int
            and case['deadline_loss'] == (n if case['success'] else 500), 'original full cutoff loss')


def witness_signature(row):
    if row is None:
        return None
    w = row['witness']
    return dict(logical_step=row['logical_step'], native_sha256=w['native_sha256'],
                comparison_python_sha256=w['comparison_python_sha256'],
                simulation_time=row['source_witness']['simulation_time'],
                noise_past_sha256=row['source_witness']['noise_past_sha256'])


def extract(case, spec, events, private):
    """Read through the FIRST factual result only. No hypothetical continuation."""
    validate_case(case, spec)
    current = case['initial']; history = []; physical = []; clock = None
    query = decision = memory = measured = None; first_clock = None; initial_clock = None
    first_command_ns = None; last_ns = -1; bank = None; post_memory = None
    for outer in events:
        require(all(outer[k] == spec[k] for k in FIELDS), 'event source identity')
        require(outer['saved_ns'] > last_ns, 'monotone original event clock')
        last_ns = outer['saved_ns']; kind = outer['event']
        if kind == 'CONTROLLED_INITIAL':
            require(initial_clock is None and not history, 'one controlled initial record')
            initial_clock = clock = outer['simulation_time']
        elif kind == 'STEP_COMPLETE':
            at = len(history)
            require(outer['logical_step'] == at and outer['noise_cursor_after'] == at+1
                    and clock == outer['simulation_time_before'], 'continuous noise cursor and clock')
            history.append(dict(at_calls=at, before=current, command=outer['command'], after=outer['after']))
            physical.append({k: outer[k] for k in ('command', 'raw_policy', 'after', 'executed_action_oracle',
                                                  'simulation_time_before', 'simulation_time_after', 'noise_cursor_after', 'reward')})
            current = outer['after']; clock = outer['simulation_time_after']
        elif kind == 'STEP_INTENT' and decision is not None and first_command_ns is None:
            first_command_ns = outer['execution_started_ns'] if 'execution_started_ns' in outer else outer['saved_ns']
        elif kind == 'AGENT_EVENT':
            p = outer['public_payload']; name = outer['agent_event']
            if name == 'PROGRAM': bank = p['bank_sha256']
            elif name == 'TASK_MEMORY_RETURN': post_memory = p['memory']
            elif name == 'WINDOW_QUERY':
                require(query is None, 'first result must precede next query')
                query = p; q = p['value']; first_clock = clock
                require(q['initial'] == case['initial'] and q['history'] == history
                        and q['completed_steps'] == len(history) == p['at_calls'], 'strict causal first query')
                require(q['candidate_time_constant_s'] == .125
                        and q['evaluation_steps'] == min(16, 500-len(history)), 'unaltered query placeholder and planned window')
            elif name == 'WINDOW_DECISION':
                require(query is not None and decision is None and p['input_sequence'] == query['sequence']
                        and p['sequence'] == query['sequence']+1, 'query precedes unique first decision')
                d = p['declaration']; require(d['public_query_sha256'] == digest(query['value'])
                    and d['at_calls'] == len(history) and d['rates'] == list(RATES)
                    and d['evaluation_steps'] == query['value']['evaluation_steps'], 'saved candidate and query binding')
                require(d['declaration_sha256'] == digest({k:v for k,v in d.items() if k != 'declaration_sha256'}), 'saved declaration hash')
                if spec['program'].split('__')[0] in TARGETS:
                    require(d['version'] == 0 and d['beta'] == 0. and d['reward_weights'] == [-1.], 'unupdated first learned declaration')
                    means = [p['mean'][0] for p in d['predictions']]
                    require(len(means) == 4 and d['selected_index'] == min(range(4), key=lambda i: finite(means[i])), 'frozen beta-zero selector')
                require(d['selected_rate'] == RATES[d['selected_index']], 'index/rate mapping')
                decision = p
            elif name == 'RATE_PLAN':
                require(decision is not None and memory is None and p['decision_sequence'] == decision['sequence'], 'first saved rate plan')
                memory = p['before_memory']; q = query['value']
                require(memory['completed_steps'] == q['completed_steps'] and memory['integral_xy'] == q['integral_xy']
                        and memory['current'] == current and memory['time_constant_s'] == .5, 'complete pre-update task memory')
            elif name == 'WINDOW_RESULT':
                require(decision is not None and memory is not None and p['parent_sequence'] == decision['sequence'], 'factual result parent')
                measured = p['measurement']; n = query['value']['completed_steps']; segment = history[n:]
                require(measured['start_at'] == n and measured['end_at'] == len(history)
                        and measured['actual_steps'] == len(segment) and 0 < len(segment) <= measured['planned_steps']
                        and measured['planned_steps'] == query['value']['evaluation_steps']
                        and measured['full_window'] == (len(segment) == measured['planned_steps'])
                        and (measured['full_window'] or measured['terminal']), 'actual full or terminal-short first window')
                require(measured['rows_sha256'] == digest(segment) and measured['host_failure'] is False, 'actual window commands and measurements')
                require(first_command_ns is not None and decision['saved_ns'] < first_command_ns <= outer['saved_ns'], 'decision precedes execution and result')
                finite(measured['cost']); break
    require((query is None) == (decision is None) == (measured is None), 'no incomplete first window')
    witnesses = {}
    for row in private:
        require(all(row[k] == spec[k] for k in FIELDS), 'private source identity')
        label = row['label']; require(label not in witnesses, 'duplicate private witness label')
        witnesses[label] = witness_signature(row)
        if query is not None and label == 'FIRST_RATE_POST': break
    require('INITIAL' in witnesses, 'actual controlled initial witness')
    if query is not None:
        require(witnesses.get('POST_ACQUISITION') is not None and witnesses.get('FIRST_RATE_PRE') == witnesses.get('FIRST_RATE_POST'), 'private pre/post rate continuity')
        require(witnesses['FIRST_RATE_PRE']['logical_step'] == query['at_calls']
                and witnesses['FIRST_RATE_PRE']['simulation_time'] == first_clock, 'query at native witness clock')
    n = len(history) if query is None else query['at_calls']
    return dict(spec=spec, success=case['success'], deadline_loss=case['deadline_loss'], total_steps=case['total_steps'],
        initial_sha256=digest(case['initial']), initial_witness=witnesses['INITIAL'],
        post_acquisition_witness=witnesses.get('POST_ACQUISITION'), post_memory_sha256=None if post_memory is None else digest(post_memory),
        first_rate_witness=witnesses.get('FIRST_RATE_PRE'), query_sha256=None if query is None else digest(query['value']),
        first_at=None if query is None else n, planned_steps=None if query is None else query['value']['evaluation_steps'],
        first_clock=first_clock, initial_clock=initial_clock, noise_cursor_at_query=None if query is None else n,
        before_memory_sha256=None if memory is None else digest(memory),
        prefix_history_sha256=digest(history[:n]), prefix_physical_sha256=digest(physical[:n]),
        bank_sha256=bank, declaration=None if decision is None else decision['declaration'], measurement=measured,
        missing_reason=None if query is not None else 'BEFORE_INTERVENTION' if not case['boundary_applied'] else 'AFTER_ACQUISITION_NO_WINDOW')


ALIGN_FIELDS = ('initial_sha256', 'initial_witness', 'post_acquisition_witness', 'post_memory_sha256',
                'first_rate_witness', 'query_sha256', 'first_at', 'planned_steps', 'first_clock', 'initial_clock',
                'noise_cursor_at_query', 'before_memory_sha256', 'prefix_history_sha256', 'prefix_physical_sha256')


def context_diagnostics(capsules, constant):
    require(len(capsules) == 8, 'all eight same-prefix programs')
    by = {r['spec']['program'].split('__')[0]:r for r in capsules}
    require(set(by) == set(FIXED+TARGETS), 'all fixed and learned programs exactly once')
    base = capsules[0]; reasons = []
    for field in ALIGN_FIELDS:
        if any(r[field] != base[field] for r in capsules[1:]): reasons.append('MISMATCH_'+field.upper())
    if all(r['declaration'] is None for r in capsules): reasons.append('ALL_NO_FIRST_WINDOW')
    elif any(r['declaration'] is None for r in capsules): reasons.append('MIXED_WINDOW_AVAILABILITY')
    for left, right in (('META_ADAPT', 'META_FROZEN'), ('ERM_ADAPT', 'ERM_FROZEN')):
        if by[left]['declaration'] != by[right]['declaration'] or by[left]['bank_sha256'] != by[right]['bank_sha256']:
            reasons.append('FIRST_BANK_DECLARATION_MISMATCH_'+left.split('_')[0])
    selection_checks = {}
    for target in TARGETS:
        d = by[target]['declaration']; okay = None
        if d is not None:
            fixed = by[FIXED[d['selected_index']]]
            okay = fixed['measurement'] == by[target]['measurement']
            if not okay: reasons.append('SELECTED_FIRST_WINDOW_MISMATCH_'+target)
        selection_checks[target] = okay
    actual = [by[n]['measurement']['cost'] for n in FIXED] if not reasons else None
    losses = [by[n]['deadline_loss'] for n in FIXED]
    learned = []
    for target in TARGETS:
        d = by[target]['declaration']; predicted = None if d is None else [p['mean'][0] for p in d['predictions']]
        learned.append(dict(target=target, saved_predicted_costs=predicted,
            saved_selected_index=None if d is None else d['selected_index'],
            metric=None if actual is None else vector_metrics(predicted, actual, d['selected_index'], constant)))
    return dict(context={k:base['spec'][k] for k in ('group', 'task', 'context', 'planned_boundary')},
        acquisition_action=base['spec']['program'].split('__')[1],
        allocated_programs=[r['spec']['program'] for r in capsules], alignment_reasons=reasons,
        selected_first_window_matches=selection_checks, actual_first_costs=actual,
        fixed_full_deadline_losses=losses, fixed_successes=[by[n]['success'] for n in FIXED],
        fixed_actual_window_steps=[None if by[n]['measurement'] is None else by[n]['measurement']['actual_steps'] for n in FIXED],
        fixed_first_vs_full_rank=None if actual is None else rank_errors(actual, losses), learned=learned)


def summary(rows, target):
    """First one metric/context, then one mean/group, then equal available groups."""
    groups = []
    names = ('MSE', 'constant_MSE', 'first_window_choice_gap', 'rank_error', 'fixed_first_vs_full_rank_error')
    for group in sorted({r['context']['group'] for r in rows}):
        part = [r for r in rows if r['context']['group'] == group]; values = {n:[] for n in names}
        for row in part:
            selected = next(x for x in row['learned'] if x['target'] == target); m = selected['metric']
            if m is not None:
                for name in names[:3]: values[name].append(m[name])
                if m['rank']['mean_error'] is not None: values['rank_error'].append(m['rank']['mean_error'])
                f = row['fixed_first_vs_full_rank']['mean_error']
                if f is not None: values['fixed_first_vs_full_rank_error'].append(f)
        groups.append(dict(group=group, allocated_contexts=len(part),
            available={n:len(v) for n,v in values.items()},
            means={n:None if not v else math.fsum(v)/len(v) for n,v in values.items()}))
    macro = {}
    for name in names:
        v = [g['means'][name] for g in groups if g['means'][name] is not None]
        macro[name] = dict(available_groups=len(v), mean=None if not v else math.fsum(v)/len(v))
    return dict(target=target, allocated_contexts=len(rows), allocated_groups=len(groups), groups=groups,
                equal_available_group_means=macro,
                missing_reasons=dict(Counter(reason for r in rows for reason in r['alignment_reasons'])))


def all_statistics(contexts):
    require(len(contexts) == 162, 'all 162 contexts, including unavailable')
    expected = set(product(range(9), TASKS, CONDITIONS, ARMS))
    actual = {(r['context']['group'],r['context']['task'],r['context']['context'],r['acquisition_action']) for r in contexts}
    require(len(actual) == 162 and actual == expected, 'exact independent context population')
    for r in contexts: require(r['context']['planned_boundary'] == (16,32,64)[r['context']['group']%3], 'frozen boundary strata')
    cells = []
    for target, task, condition, boundary, arm in product(TARGETS, TASKS, CONDITIONS, (16,32,64), ARMS):
        part = [r for r in contexts if r['context']['task'] == task and r['context']['context'] == condition
                and r['context']['planned_boundary'] == boundary and r['acquisition_action'] == arm]
        require(len(part) == 3, 'all three independent groups per cell')
        cells.append(dict(task=task, context=condition, boundary=boundary, arm=arm, **summary(part, target)))
    return dict(by_target=[summary(contexts,t) for t in TARGETS], cells=cells,
                contexts=162, cells_count=216, unique_initial_banks_per_context=2,
                adapted_and_frozen_first_predictions_are_not_independent_samples=True,
                post_hoc_descriptive_only=True, new_scientific_gate=False, task_value_estimated=False)

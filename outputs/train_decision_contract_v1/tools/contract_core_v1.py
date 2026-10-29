"""Pure saved-data contracts, not a controller, model, propensity or OPE estimator."""
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
import math
import struct

RATES = (.125, .5, 2., 8.)
KEYS = ('cohort', 'group', 'task', 'seed', 'context', 'planned_boundary', 'acquisition_action', 'behavior')
POINTS = ('BEFORE_ACQUISITION', 'AFTER_ACQUISITION')
TASKS = ('push-v3', 'reach-v3', 'door-open-v3')


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def vector(v, n, bound=None):
    require(type(v) is list and len(v) == n and all(type(x) in (int, float) and math.isfinite(x) for x in v), 'finite public vector')
    require(bound is None or max(abs(x) for x in v) <= bound, 'bounded public vector')


def state(s):
    require(type(s) is dict and set(s) == {'observation', 'terminated', 'truncated', 'success'}, 'strict public state; no oracle extras')
    vector(s['observation'], 39)
    require(all(type(s[k]) is bool for k in ('terminated', 'truncated', 'success')), 'literal public flags')


def live(s, n):
    return n < 500 and not any(s[k] for k in ('terminated', 'truncated', 'success'))


def memory(m):
    require(type(m) is dict and set(m) == {'schema', 'task', 'completed_steps', 'current', 'controller', 'integral_xy', 'time_constant_s'}
        and m['schema'] == 'TASK_MEMORY_OPTION_V1', 'strict public memory')
    require(m['task'] in TASKS and type(m['completed_steps']) is int and 0 <= m['completed_steps'] <= 500, 'public memory position')
    state(m['current']); vector(m['integral_xy'], 2, 2.)
    require(type(m['time_constant_s']) in (int, float) and m['time_constant_s'] in RATES, 'actual prior rate')
    c = m['controller']
    require(type(c) is dict and set(c) == {'source', 'matrix_xy', 'offset'} and c['source'] in ('UNCORRECTED', 'ESTIMATED_AFFINE'), 'public saved controller only')
    require(type(c['matrix_xy']) is list and len(c['matrix_xy']) == 2, 'XY matrix')
    for row in c['matrix_xy']: vector(row, 2, 4.+1e-7)
    vector(c['offset'], 4)
    require(c['offset'][2:] == [0., 0.], 'preserve Z and grip')
    a, b = c['matrix_xy']
    require(abs(a[0]*b[1]-a[1]*b[0]) > 1e-12, 'nonsingular public matrix')
    if c['source'] == 'UNCORRECTED':
        require(c['matrix_xy'] == [[1., 0.], [0., 1.]] and c['offset'] == [0., 0., 0., 0.], 'identity source semantics')


def command(c):
    vector(c, 4, 1.)
    require(all(struct.unpack('f', struct.pack('f', x))[0] == x for x in c), 'literal saved float32 send')


def validate_projection(p):
    require(type(p) is dict and set(p) == {'schema', 'task', 'initial', 'history', 'windows'}
        and p['schema'] == 'OCCAM_PUBLIC_TRAIN_TRAJECTORY_V1' and p['task'] in TASKS, 'saved public trajectory schema')
    state(p['initial']); current = p['initial']
    require(type(p['history']) is list and 0 < len(p['history']) <= 500, 'complete nonempty source execution')
    for i, r in enumerate(p['history']):
        require(type(r) is dict and set(r) == {'at_calls', 'before', 'command', 'after'} and r['at_calls'] == i
            and r['before'] == current and live(current, i), 'actual consecutive history')
        command(r['command']); state(r['after']); current = r['after']
    require(not live(current, len(p['history'])), 'no partial source outcome')
    previous = None
    for w in p['windows']:
        require(set(w) == {'query', 'selected_rate', 'measurement'} and w['selected_rate'] in RATES, 'factual window')
        q, m = w['query'], w['measurement']; n = q['completed_steps']
        require(set(q) == {'schema', 'task', 'completed_steps', 'initial', 'history', 'integral_xy', 'candidate_time_constant_s', 'evaluation_steps'}
            and q['schema'] == 'OCCAM_PUBLIC_HISTORY_V1' and q['task'] == p['task'] and q['initial'] == p['initial'], 'strict original query')
        require(type(n) is int and 0 <= n < len(p['history']) and q['history'] == p['history'][:n]
            and (previous is None or n == previous), 'no future, omitted or reused history')
        require(q['candidate_time_constant_s'] == RATES[0] and q['evaluation_steps'] == min(16, 500-n), 'placeholder is not selected action')
        vector(q['integral_xy'], 2, 2.)
        require(m['start_at'] == n and type(m['end_at']) is int and n < m['end_at'] <= min(n+16, len(p['history'])), 'actual window extent')
        previous = m['end_at']
    require(previous is None or previous == len(p['history']), 'complete factual continuation windows')


def make_view(point, task, boundary, initial, m, enriched_history, past_action):
    """Declared projection only. Metadata/future assignment never passed here."""
    memory(m); state(initial)
    require(point in POINTS and task == m['task'] and boundary in (16, 32, 64), 'public decision definition')
    n = m['completed_steps']
    require(len(enriched_history) == n, 'snapshot cannot include later rows')
    current = initial
    for i, r in enumerate(enriched_history):
        require(set(r) == {'at_calls', 'before', 'command', 'after', 'raw_policy', 'phase'} and r['at_calls'] == i
            and r['before'] == current and live(current, i), 'rich public history continuity')
        command(r['command']); state(r['after'])
        if r['raw_policy'] is not None: vector(r['raw_policy'], 4)
        require(r['phase'] in ('PREFIX_TASK', 'VALIDATION_TASK', 'TAIL_TASK', 'REPOSITION', 'WARM_PROBE'), 'registered public phase')
        require((r['raw_policy'] is None) == (r['phase'] in ('REPOSITION', 'WARM_PROBE')), 'raw policy availability')
        current = r['after']
    require(current == m['current'], 'memory belongs to current true prefix')
    require(past_action is None if point == POINTS[0] else past_action in ('CONTINUE', 'VALIDATE8', 'MOVE_MEASURE'), 'future assigned arm excluded')
    return dict(schema='TRAIN_DECISION_VIEW_V1', decision_point=point, task=task, planned_boundary=boundary,
        initial=deepcopy(initial), memory=deepcopy(m), remaining_steps=500-n, window_steps=16,
        past_acquisition_action=past_action, history=deepcopy(enriched_history), decision_required=live(current, n))


def view_record(view, anchor):
    return dict(point=view['decision_point'], at_calls=view['memory']['completed_steps'],
        decision_required=view['decision_required'], view_sha256=digest(view), source_anchor=anchor,
        components_sha256={k: digest(v) for k, v in view.items()},
        reconstruction='whitelisted event memory + public projection prefix + actual COMMAND phase/raw_policy',
        metadata_and_hashes_are_not_model_features=True)


def label_contract(spec, windows, loss, pre, post):
    rates = [w['selected_rate'] for w in windows]
    require(not rates or spec['behavior'] != 'BLOCK_FIXED' or len(set(rates)) == 1, 'BLOCK_FIXED changed rate')
    eligible = spec['cohort'] == 'TRAIN' and bool(rates) and spec['behavior'] == 'BLOCK_FIXED'
    # Random realizations with one rate are stopping/sequence-selected, not an
    # unweighted static-program risk sample admitted by this protocol.
    role = ('NO_GAIN_DECISION' if not rates else 'FACTUAL_STATIC_PROGRAM' if spec['behavior'] == 'BLOCK_FIXED'
            else 'FACTUAL_RANDOM_CONTINUATION')
    support = []
    for t in RATES:
        differing = next((i for i, r in enumerate(rates) if r != t), None)
        support.append(dict(target_static_rate=t, first_different_window=differing,
            compatible_observed_rate_sequence=bool(rates) and differing is None,
            target_terminal_loss=loss if eligible and differing is None else None,
            target_label_status='FACTUAL_STATIC_TRAIN' if eligible and differing is None else
                'NO_GAIN_DECISION' if not rates else 'NATIVE_VALIDATION_ONLY' if spec['cohort'] != 'TRAIN' else
                'RANDOM_COMPATIBILITY_NOT_UNWEIGHTED_LABEL' if spec['behavior'] == 'RANDOM_WINDOW' and differing is None else
                'DIFFERENT_PROGRAM_NO_COUNTERFACTUAL_OUTCOME'))
    return dict(terminal_role=role, actual_rates=rates,
        actual_windows=[dict(start_at=w['query']['completed_steps'], end_at=w['measurement']['end_at'],
            selected_rate=w['selected_rate'], full_window=w['measurement']['full_window']) for w in windows],
        source_complete_deadline_loss=loss, before_remaining_loss=None if pre is None else loss-pre['at_calls'],
        after_remaining_loss=None if post is None else loss-post['at_calls'],
        complete_labels_include_unexecuted_failure_penalty=True, static_TRAIN_supervised_label_admitted=eligible,
        observed_constant_random_sequence=bool(rates) and spec['behavior'] == 'RANDOM_WINDOW' and len(set(rates)) == 1,
        static_targets=support, causal_value_or_generalization_qualified=False)


def extract(spec, p, events):
    """Main selector uses the separately audited public projection for receipts."""
    validate_projection(p)
    require(p['task'] == spec['task'], 'case task')
    commands, anchors, queries, decisions, results = [], {}, [], [], []
    outcome = None; last_time = -1; local_sequence = 0
    for e in events:
        require(e['saved_ns'] > last_time, 'outer chronology'); last_time = e['saved_ns']
        if e['event'] != 'AGENT_EVENT': continue
        q = e['public_payload']; kind = e['agent_event']
        require(q['sequence'] == local_sequence and q['saved_ns'] <= e['saved_ns'], 'public chronology')
        local_sequence += 1
        if kind == 'PROGRAM':
            require(q['task'] == spec['task'] and q['boundary'] == spec['planned_boundary'] and q['window_steps'] == 16, 'public protocol constants')
        elif kind == 'COMMAND':
            n = q['at_calls']; require(n == len(commands) and n < len(p['history']), 'actual command index')
            row = p['history'][n]
            require(q['before'] == row['before'] and q['command'] == row['command'], 'command/projection binding')
            commands.append(dict(**row, raw_policy=q['raw_policy'], phase=q['phase']))
        elif kind in ('ACQUISITION_CHOICE', 'TASK_MEMORY_RETURN'):
            point = POINTS[0] if kind == 'ACQUISITION_CHOICE' else POINTS[1]
            require(point not in anchors and q['at_calls'] == len(commands), 'unique actual decision anchor')
            m = q['before_memory'] if point == POINTS[0] else q['memory']
            require(q['at_calls'] == m['completed_steps'], 'actual memory time')
            if point == POINTS[0]: require(q['action'] == spec['acquisition_action'], 'actual acquisition')
            v = make_view(point, p['task'], spec['planned_boundary'], p['initial'], m, commands,
                          None if point == POINTS[0] else spec['acquisition_action'])
            anchors[point] = view_record(v, dict(outer_sequence=e['sequence'], public_sequence=q['sequence'], event=kind))
        elif kind == 'WINDOW_QUERY':
            require(q['at_calls'] == len(commands) and q['value']['completed_steps'] == len(commands), 'query real time')
            queries.append(q)
        elif kind == 'WINDOW_DECISION':
            require(queries and q['input_sequence'] == queries[-1]['sequence'] < q['sequence'], 'query precedes action')
            decisions.append(q)
        elif kind == 'WINDOW_RESULT': results.append(q)
        elif kind == 'OUTCOME':
            require(outcome is None, 'unique outcome'); outcome = q
    require(len(commands) == len(p['history']) and outcome is not None and outcome['at_calls'] == len(commands), 'complete actual timeline')
    n = len(commands); end = p['history'][-1]['after']; loss = n if end['success'] else 500
    require(outcome['final'] == end and outcome['outcome']['success'] == end['success']
        and outcome['outcome']['deadline_loss'] == loss and outcome['outcome']['total_steps'] == n, 'public complete loss')
    require(len(queries) == len(decisions) == len(results) == len(p['windows']), 'all windows retained')
    for q, d, r, w in zip(queries, decisions, results, p['windows']):
        require(q['value'] == w['query'] and d['declaration']['selected_rate'] == w['selected_rate']
            and r['measurement'] == w['measurement'] and r['parent_sequence'] == d['sequence'], 'actual full continuation, not first-T relabel')
    pre, post = (anchors.get(k) for k in POINTS)
    require((pre is None) == (post is None), 'both actual acquisition anchors or neither')
    if pre is None:
        require(n <= spec['planned_boundary'] and not queries, 'early end without fabricated boundary')
    else:
        require(pre['at_calls'] == spec['planned_boundary'] and pre['decision_required'], 'live boundary anchor')
        require(post['at_calls'] >= pre['at_calls'], 'return cannot undo acquisition')
        if queries:
            first = queries[0]['value']
            actual_return = next(e['public_payload']['memory'] for e in events
                                 if e['event'] == 'AGENT_EVENT' and e['agent_event'] == 'TASK_MEMORY_RETURN')
            require(post['decision_required'] and first['completed_steps'] == post['at_calls']
                and first['integral_xy'] == actual_return['integral_xy'], 'first query after actual return; no inverse memory reconstruction')
        else: require(not post['decision_required'], 'no missing live first decision')
    return dict(spec=spec, total_steps=n, success=end['success'], deadline_loss=loss,
        data_role='TRAIN' if spec['cohort'] == 'TRAIN' else 'VALIDATION_ONLY', before=pre, after=post,
        missing_reason='ENDED_BEFORE_OR_AT_BOUNDARY' if pre is None else 'ENDED_DURING_ACQUISITION' if not post['decision_required'] else None,
        labels=label_contract(spec, p['windows'], loss, pre, post))


def summarize(rows):
    strata = defaultdict(list)
    for r in rows:
        s = r['spec']; strata[tuple(s[k] for k in ('cohort', 'group', 'task', 'context', 'planned_boundary', 'acquisition_action', 'behavior'))].append(r)
    def counts(rs):
        return dict(cases=len(rs), task_failures=sum(not x['success'] for x in rs),
            before_views=sum(x['before'] is not None for x in rs), after_views=sum(x['after'] is not None for x in rs),
            live_after_views=sum(x['after'] is not None and x['after']['decision_required'] for x in rs),
            windows=sum(len(x['labels']['actual_rates']) for x in rs),
            static_TRAIN_labels=sum(x['labels']['static_TRAIN_supervised_label_admitted'] for x in rs),
            constant_random=sum(x['labels']['observed_constant_random_sequence'] for x in rs),
            missing=dict(Counter(x['missing_reason'] or 'AVAILABLE' for x in rs)),
            roles=dict(Counter(x['labels']['terminal_role'] for x in rs)))
    cells = []
    for cohort in ('NATIVE', 'TRAIN'):
        for task in TASKS:
            for context in ('UNCHANGED', 'CHANGED'):
                for boundary in (16, 32, 64):
                    rs = [r for r in rows if (r['spec']['cohort'], r['spec']['task'], r['spec']['context'], r['spec']['planned_boundary']) == (cohort, task, context, boundary)]
                    cells.append(dict(cohort=cohort, task=task, context=context, planned_boundary=boundary, **counts(rs)))
    pairs = []
    def pair_by(fields, variant, expected):
        buckets = defaultdict(list)
        for r in rows: buckets[tuple(r['spec'][k] for k in fields)].append(r)
        for k, rs in sorted(buckets.items()):
            require(len(rs) == expected and len({r['spec'][variant] for r in rs}) == expected, 'complete alias comparison denominator')
            for point in ('before', 'after'):
                vs = [r[point] for r in rs]; available = [v for v in vs if v is not None]
                components = sorted({name for name in (available[0]['components_sha256'] if available else {})
                    if len({v['components_sha256'][name] for v in available}) > 1})
                pairs.append(dict(comparison=variant, key=dict(zip(fields, k)), point=point,
                    allocated=expected, available=len(available), missing=expected-len(available),
                    all_equal=None if len(available) != expected else len({v['view_sha256'] for v in available}) == 1,
                    differing_components=components))
    pair_by(('cohort', 'group', 'task', 'context', 'planned_boundary', 'acquisition_action'), 'behavior', 2)
    pair_by(('cohort', 'group', 'task', 'planned_boundary', 'acquisition_action', 'behavior'), 'context', 2)
    pair_by(('cohort', 'group', 'task', 'context', 'planned_boundary', 'behavior'), 'acquisition_action', 3)
    return dict(overall=counts(rows), by_cohort={c: counts([r for r in rows if r['spec']['cohort'] == c]) for c in ('NATIVE', 'TRAIN')},
        cells=cells, group_cells=len(strata), alias_comparisons=pairs,
        alias_summary={v+':'+p: dict(Counter('MISSING' if x['all_equal'] is None else 'EQUAL' if x['all_equal'] else 'DIFFERENT'
            for x in pairs if x['comparison'] == v and x['point'] == p))
            for v in ('behavior', 'context', 'acquisition_action') for p in ('before', 'after')},
        warnings=['Declared public projection only, not a sufficient statistic or Bayes impossibility proof.',
            'BLOCK labels are factual supervised associations, not causal-value qualification.',
            'No RANDOM terminal copied to a held-T target; no QUAL outcome used.'])

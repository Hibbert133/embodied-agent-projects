"""Literal Fraction reader; no imports of the main probability/statistics code."""
from fractions import Fraction as F
from collections import Counter, defaultdict
import math


def same(a, b, message):
    if a != b:
        raise ValueError(message)


def number(x):
    same(set(x), {'numerator', 'denominator'}, 'fraction shape')
    value = F(int(x['numerator']), int(x['denominator']))
    same(str(value.numerator), x['numerator'], 'canonical numerator')
    same(str(value.denominator), x['denominator'], 'canonical denominator')
    return value


def joint(actions, profile):
    """Independent joint expression; conditional factors are obtained by ratios."""
    if len(actions) == 0: return F(1)
    random = F(1, 2 ** (2 * len(actions)))
    block = F(1, 4) if all(a == actions[0] for a in actions) else F(0)
    return {'RANDOM_WINDOW': random, 'BLOCK_FIXED': block, 'EQUAL_HIDDEN_MIXTURE': (random + block) * F(1, 2)}[profile]


def verify_trajectory(spec, compact, value, row, saved_steps):
    """Checks every saved field with factual lengths and independent arithmetic."""
    rates = [0.125, 0.5, 2., 8.]
    actions = [rates.index(w['selected_rate']) for w in value['windows']]
    n = len(actions)
    same(row['spec'], spec, 'trajectory allocation')
    for a, b in [('actual_control_steps', 'total_steps'), ('success', 'success'), ('deadline_loss', 'deadline_loss'), ('boundary_applied', 'boundary_applied')]:
        same(row[a], compact[b], 'original task metadata ' + a)
    same(row['actions'], actions, 'observed actions')
    same(row['windows'], n, 'all actual windows')
    same(len(saved_steps), n, 'saved step count')
    same(row['full_windows'], sum(w['measurement']['actual_steps'] == w['measurement']['planned_steps'] for w in value['windows']), 'full count')
    same(row['short_windows'], n - row['full_windows'], 'short count')
    reason = None if n else 'EARLY_END_BEFORE_INTERVENTION' if not compact['boundary_applied'] else 'NO_TASK_WINDOW_AFTER_ACQUISITION'
    same(row['missing_reason'], reason, 'availability reason')
    changed = sum(actions[j] != actions[j-1] for j in range(1, n))
    same(row['action_changes'], changed, 'changes')
    same(row['change_fraction'], changed / (n-1) if n > 1 else None, 'within-trajectory change mean')
    same(row['all_observed_actions_equal'], all(a == actions[0] for a in actions) if n else None, 'constant sequence')
    for profile, prefix in [('RANDOM_WINDOW' if spec['behavior'] == 'RANDOM_WINDOW' else 'BLOCK_FIXED', 'assigned_profile'), ('EQUAL_HIDDEN_MIXTURE', 'hidden_mixture')]:
        p = joint(actions, profile)
        same(number(row[prefix + '_joint_action_factor']), p, 'joint action factor')
        if n: same(number(row[prefix + '_inverse_action_factor']), 1/p, 'inverse factor')
        else: same(row[prefix + '_inverse_action_factor'], None, 'empty inverse unavailable')
    mix = joint(actions, 'EQUAL_HIDDEN_MIXTURE')
    same(row['hidden_mixture_log10_inverse_action_factor'], math.log10(float(1/mix)) if n else None, 'log descriptive factor')
    same(row['hypothetical_block_action_support'], (joint(actions, 'BLOCK_FIXED') != 0) if n else None, 'block support')
    same(row['naive_uniform_joint_factor_equals_hidden_mixture'], (joint(actions, 'RANDOM_WINDOW') == mix) if n else None, 'naive comparison')
    for j, (w, saved) in enumerate(zip(value['windows'], saved_steps)):
        m = w['measurement']
        same(saved['window'], j, 'window ordinal')
        for field in ('start_at','end_at','actual_steps','planned_steps','full_window','terminal'):
            same(saved[field], m[field], 'factual segment field ' + field)
        same(saved['selected_index'], actions[j], 'selected index')
        same(saved['selected_rate'], w['selected_rate'], 'selected rate')
        same(saved['prior_actions'], actions[:j], 'strict past-only prefix')
        for profile, field in [(spec['behavior'], 'assigned_profile_conditional_action_factor'), ('EQUAL_HIDDEN_MIXTURE', 'hidden_mixture_conditional_action_factor')]:
            expected = joint(actions[:j+1], profile) / joint(actions[:j], profile)
            same(number(saved[field]), expected, 'independent prefix likelihood ratio')
    return dict(trajectories=1, windows=n, full_windows=row['full_windows'], short_windows=row['short_windows'])


def verify_summary(rows, summary):
    counts = dict(allocated=len(rows), nonempty=sum(r['windows'] > 0 for r in rows), windows=sum(r['windows'] for r in rows),
                  short_windows=sum(r['short_windows'] for r in rows),
                  before_intervention=sum(r['missing_reason'] == 'EARLY_END_BEFORE_INTERVENTION' for r in rows),
                  after_acquisition_no_window=sum(r['missing_reason'] == 'NO_TASK_WINDOW_AFTER_ACQUISITION' for r in rows),
                  observed_switched_trajectories=sum(r['action_changes'] != 0 for r in rows),
                  naive_uniform_joint_mismatch=sum(r['naive_uniform_joint_factor_equals_hidden_mixture'] is False for r in rows))
    same(summary['counts'], counts, 'census counts')
    by_group = defaultdict(list)
    for row in rows: by_group[row['spec']['group']].append(row)
    same([g['group'] for g in summary['groups']], sorted(by_group), 'all independent groups')
    group_means = defaultdict(list)
    for saved in summary['groups']:
        group = by_group[saved['group']]
        same(saved['trajectories'], len(group), 'group denominator')
        for metric in ('windows', 'change_fraction', 'hidden_mixture_log10_inverse_action_factor'):
            values = [r[metric] for r in group if r[metric] is not None]
            mean = math.fsum(values)/len(values) if values else None
            same(saved['metrics'][metric], dict(available_trajectories=len(values), total_trajectories=len(group), mean=mean), 'group trajectory weighting')
            if mean is not None: group_means[metric].append(mean)
    for metric, saved in summary['equal_group_macro'].items():
        values = group_means[metric]
        same(saved, dict(available_groups=len(values), total_groups=len(by_group), mean=math.fsum(values)/len(values) if values else None), 'equal group macro')
    return counts

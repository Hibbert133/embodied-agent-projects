"""Action-factor algebra only; not an off-policy value estimator or certificate."""
from fractions import Fraction
from collections import Counter
import math

RATES = (0.125, 0.5, 2.0, 8.0)
PROFILES = ('RANDOM_WINDOW', 'BLOCK_FIXED', 'EQUAL_HIDDEN_MIXTURE')
SPEC_KEYS = ('cohort', 'group', 'task', 'seed', 'context', 'planned_boundary', 'acquisition_action', 'behavior')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def check_sequence(sequence):
    require(type(sequence) in (list, tuple) and len(sequence) <= 31,
            'bounded declared action sequence')
    require(all(type(a) is int and 0 <= a < 4 for a in sequence), 'literal legal gain indices')


def action_mass(profile, sequence):
    """Product of working policy kernels, excluding observation/stopping kernels."""
    require(profile in PROFILES, 'registered behavior model')
    check_sequence(sequence)
    if not sequence:
        return Fraction(1)
    random = Fraction(1, 4 ** len(sequence))
    block = Fraction(1, 4) if len(set(sequence)) == 1 else Fraction(0)
    return random if profile == PROFILES[0] else block if profile == PROFILES[1] else (random + block) / 2


def next_probabilities(profile, prefix):
    """Uses only an already observed prefix; never peeks at the next outcome."""
    require(profile in PROFILES, 'registered behavior model')
    check_sequence(prefix)
    require(len(prefix) < 31, 'no decision after allocation')
    if not prefix or profile == 'RANDOM_WINDOW':
        return [Fraction(1, 4)] * 4
    if profile == 'BLOCK_FIXED':
        require(len(set(prefix)) == 1, 'off-support block history')
        return [Fraction(int(a == prefix[0])) for a in range(4)]
    if len(set(prefix)) > 1:
        return [Fraction(1, 4)] * 4
    # Posterior under the explicitly hypothetical 50:50 latent-profile model.
    block_posterior = Fraction(4 ** (len(prefix) - 1), 1 + 4 ** (len(prefix) - 1))
    return [(1 - block_posterior) / 4 + block_posterior * int(a == prefix[0]) for a in range(4)]


def ratio(value):
    return dict(numerator=str(value.numerator), denominator=str(value.denominator))


def inverse(value):
    return ratio(1 / value) if value else None


def describe_windows(spec, panel, compact, value, expected_schedule):
    """Only public declarations/measurement lengths and audited compact metadata."""
    require(type(value) is dict and set(value) == {'schema', 'task', 'initial', 'history', 'windows'}, 'public projection shape')
    require(value['schema'] == 'OCCAM_PUBLIC_TRAIN_TRAJECTORY_V1'
            and value['task'] == spec['task'] and type(value['windows']) is list, 'public task/windows')
    require(type(value['history']) is list and len(value['history']) == compact['total_steps'], 'complete factual history length')
    windows = value['windows']
    require(len(windows) == panel['performance_windows'] == compact['performance_windows'], 'complete window denominator')
    require(0 <= len(windows) <= 31 and len(expected_schedule) == 31, 'declared schedule length')
    actions, steps = [], []
    for j, window in enumerate(windows):
        require(type(window) is dict and set(window) == {'query', 'selected_rate', 'measurement'}, 'factual window shape')
        q, m, rate = window['query'], window['measurement'], window['selected_rate']
        require(q['task'] == spec['task'] and type(q['completed_steps']) is int
                and type(q['history']) is list and len(q['history']) == q['completed_steps'], 'no future history in query')
        require(type(rate) in (int, float) and not isinstance(rate, bool) and rate in RATES, 'legal observed gain')
        index = RATES.index(rate)
        require(index == expected_schedule[j] and q['candidate_time_constant_s'] == RATES[0], 'saved schedule and query input semantics')
        require(type(m['actual_steps']) is int and 0 < m['actual_steps'] <= m['planned_steps'] <= 16, 'actual nonempty bounded window')
        require(m['start_at'] == q['completed_steps'] and m['planned_steps'] == q['evaluation_steps']
                and m['end_at'] == m['start_at'] + m['actual_steps'], 'declaration before same factual window')
        require(m['end_at'] <= compact['total_steps'], 'no future factual window')
        require(m['full_window'] == (m['actual_steps'] == m['planned_steps']), 'short-window marker')
        require(m['full_window'] or (m['terminal'] and j == len(windows) - 1), 'unexplained short window')
        require(j == 0 or (windows[j - 1]['measurement']['end_at'] == m['start_at']
                          and not windows[j - 1]['measurement']['terminal']), 'nonconsecutive windows')
        prefix = actions.copy()
        p = next_probabilities(spec['behavior'], prefix)[index]
        pmix = next_probabilities('EQUAL_HIDDEN_MIXTURE', prefix)[index]
        actions.append(index)
        require(p > 0 and pmix > 0, 'observed sequence outside assigned behavior')
        steps.append(dict(window=j, start_at=m['start_at'], end_at=m['end_at'], actual_steps=m['actual_steps'],
                          planned_steps=m['planned_steps'], full_window=m['full_window'], terminal=m['terminal'],
                          selected_index=index, selected_rate=rate, prior_actions=prefix,
                          assigned_profile_conditional_action_factor=ratio(p),
                          hidden_mixture_conditional_action_factor=ratio(pmix)))
    require(not windows or windows[-1]['measurement']['end_at'] == compact['total_steps'], 'all factual task windows to end')
    reason = None if windows else 'EARLY_END_BEFORE_INTERVENTION' if not compact['boundary_applied'] else 'NO_TASK_WINDOW_AFTER_ACQUISITION'
    n, changes = len(actions), sum(x != y for x, y in zip(actions, actions[1:]))
    mass = action_mass(spec['behavior'], actions)
    pooled = action_mass('EQUAL_HIDDEN_MIXTURE', actions)
    return dict(spec=spec, actual_control_steps=compact['total_steps'], success=compact['success'],
                deadline_loss=compact['deadline_loss'], boundary_applied=compact['boundary_applied'],
                windows=n, full_windows=sum(s['full_window'] for s in steps),
                short_windows=sum(not s['full_window'] for s in steps), missing_reason=reason,
                actions=actions, action_changes=changes, all_observed_actions_equal=(len(set(actions)) == 1) if n else None,
                change_fraction=changes / (n - 1) if n > 1 else None,
                assigned_profile_joint_action_factor=ratio(mass), hidden_mixture_joint_action_factor=ratio(pooled),
                assigned_profile_inverse_action_factor=inverse(mass) if n else None,
                hidden_mixture_inverse_action_factor=inverse(pooled) if n else None,
                hidden_mixture_log10_inverse_action_factor=math.log10(pooled.denominator / pooled.numerator) if n else None,
                hypothetical_block_action_support=(action_mass('BLOCK_FIXED', actions) > 0) if n else None,
                naive_uniform_joint_factor_equals_hidden_mixture=(action_mass('RANDOM_WINDOW', actions) == pooled) if n else None), steps


def summarize(rows):
    """Each trajectory first; group means, then equal group means; no CI or OPE."""
    counter = Counter(allocated=len(rows), nonempty=sum(bool(r['windows']) for r in rows),
                      windows=sum(r['windows'] for r in rows), short_windows=sum(r['short_windows'] for r in rows),
                      before_intervention=sum(r['missing_reason'] == 'EARLY_END_BEFORE_INTERVENTION' for r in rows),
                      after_acquisition_no_window=sum(r['missing_reason'] == 'NO_TASK_WINDOW_AFTER_ACQUISITION' for r in rows),
                      observed_switched_trajectories=sum(r['action_changes'] > 0 for r in rows),
                      naive_uniform_joint_mismatch=sum(r['naive_uniform_joint_factor_equals_hidden_mixture'] is False for r in rows))
    metrics = ('windows', 'change_fraction', 'hidden_mixture_log10_inverse_action_factor')
    groups = []
    for g in sorted({r['spec']['group'] for r in rows}):
        subset = [r for r in rows if r['spec']['group'] == g]
        means = {}
        for metric in metrics:
            values = [r[metric] for r in subset if r[metric] is not None]
            means[metric] = dict(available_trajectories=len(values), total_trajectories=len(subset),
                                 mean=math.fsum(values) / len(values) if values else None)
        groups.append(dict(group=g, trajectories=len(subset), metrics=means))
    macro = {}
    for metric in metrics:
        values = [g['metrics'][metric]['mean'] for g in groups if g['metrics'][metric]['mean'] is not None]
        macro[metric] = dict(available_groups=len(values), total_groups=len(groups),
                             mean=math.fsum(values) / len(values) if values else None)
    return dict(counts=dict(counter), groups=groups, equal_group_macro=macro)

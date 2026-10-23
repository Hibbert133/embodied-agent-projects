"""Independent allocation/record reconstruction, without running the collector.

The frozen fault generator and journal numerical helpers are shared explicitly.
Population loops, compact rows, counters and population ownership are separate.
"""
from collections import Counter
from itertools import groupby
from src.analysis.short_probe_journal_audit_v1 import audit_journal, audit_matched_unit
from src.rollout.chronological_faults import states, blend, fraction

METHODS = ('NO_PROBE', 'ORIGINAL8_UPDATE', 'BALANCED4_UPDATE', 'DOPT4_UPDATE',
           'DOPT8_UPDATE', 'DOPT4_KEEP_AT8', 'DOPT4_FALLBACK8')
TASKS = ('push-v3', 'reach-v3', 'door-open-v3')
FAMILIES = ('BIAS', 'COLUMN_Y', 'DEADZONE')
SCHEDULES = ('UNCHANGED', 'ABRUPT', 'GRADUAL')
IDENTITY = ('experiment_run_id', 'manifest_id', 'source_git_commit')
KEY = ('study_phase', 'stream', 'episode', 'task', 'seed', 'method')
COUNTS = ('total_steps', 'fixed_probe_steps', 'policy_steps', 'online_parameter_fits',
          'optimizer_nfev', 'policy_queries', 'design_verification_candidates')
OUTCOME = ('success', 'stopped', 'end_reason', 'deadline_loss', 'applied_fitted_controller', *COUNTS)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def population(phase):
    require(phase in ('SMOKE', 'MAIN'), 'unknown registered phase')
    result = []
    for sid in range(1 if phase == 'SMOKE' else 54):
        if phase == 'SMOKE':
            family, schedule = 'BIAS', 'SMOKE_ABRUPT'
            a = {'matrix_xy':[[1., 0.], [0., 1.]], 'bias_xy':[.12, -.08], 'deadzone_xy':[0., 0.]}
            b = {**a, 'bias_xy':[-.14, .1]}
        else:
            repeat, cell = divmod(sid, 9);fi, si = divmod(cell, 3)
            family, schedule = FAMILIES[fi], SCHEDULES[si]
            a, b = states(67001+sid, family)
        stream = {'stream':sid, 'family_oracle':family, 'schedule_oracle':schedule}
        if phase == 'MAIN':
            stream['generation_seed_oracle'] = 67001+sid
        stream['cases'] = []
        for episode in range(9 if phase == 'SMOKE' else 12):
            stream['cases'].append({'episode':episode,
                'task':TASKS[(episode+1 if phase == 'SMOKE' else episode+repeat+fi+si)%3],
                'seed':21200+episode if phase == 'SMOKE' else 20200+sid*12+episode,
                'fault_oracle':(a if episode < 5 else b) if phase == 'SMOKE' else blend(a, b, fraction(schedule, episode))})
        result.append(stream)
    return result


def four_step_chain(record):
    choices = {e['public_payload']['sequence'] for e in record['events'] if e['event'] == 'CHOICE'
        and e['public_payload']['action'] == 'RUN_FITTED' and e['public_payload']['fitted_prefix_steps'] == 4}
    return any(row['phase'] == 'POLICY' and row['decision_sequence'] in choices for row in record['trace'])


def audit_records(manifest, phase, summary, records, events, models, designs):
    specs = population(phase)
    require(manifest['population_oracle'][phase] == specs, 'independently reconstructed allocation differs')
    identity = {k:manifest[k] for k in IDENTITY}
    require(all(summary[k] == v for k,v in identity.items()), 'summary identity differs')
    require(summary['phase'] == phase and summary['status'] == 'COLLECTED_FOR_INDEPENDENT_AUDIT'
        and summary['failure'] is None and summary['computation_counters_complete'] is True, 'incomplete collection')
    require(type(summary['wall_ns']) is int and summary['wall_ns'] >= 0, 'invalid collection duration')
    require(all(type(summary[k]) is int and summary[k] == 0 for k in
        ('new_api_calls','new_nominal_training','new_selector_fits','policy_updates')), 'unregistered training/API')
    n = 63 if phase == 'SMOKE' else 4536
    require(summary['completed_executions'] == n and len(summary['rows']) == n, 'incomplete population denominator')
    grouped = iter(groupby(events, lambda e:tuple(e[k] for k in KEY)))
    records = iter(records);ledger = {'counts':{}, 'by_phase':{}};sequence = saved_ns = -1
    count = 0;event_count = 0;totals = Counter();audit_cost = Counter();matches = [];chains = []
    for stream in specs:
        for spec in stream['cases']:
            runs = {}
            for method in METHODS:
                key = {'study_phase':phase, 'stream':stream['stream'], 'episode':spec['episode'],
                    'task':spec['task'], 'seed':spec['seed'], 'method':method}
                row = next(records, None);group = next(grouped, None)
                require(row is not None and group is not None, 'missing execution or journal group')
                require(group[0] == tuple(key[k] for k in KEY), 'foreign/reordered journal execution')
                expected_keys = set(identity) | set(key) | {'family_oracle','schedule_oracle','fault_oracle',
                    'completed','error','close_error','environment_closed','lifecycle_before','lifecycle_after_close','host','public'}
                require(set(row) == expected_keys, 'missing or extra case-record field')
                require(all(row[k] == v for k,v in {**identity, **key}.items()), 'foreign case allocation')
                require(row['family_oracle'] == stream['family_oracle'] and row['schedule_oracle'] == stream['schedule_oracle']
                    and row['fault_oracle'] == spec['fault_oracle'], 'foreign case fault/factor')
                require(row['completed'] is True and row['environment_closed'] is True and row['error'] is None
                    and row['close_error'] is None and row['lifecycle_before'] == ledger, 'incomplete or discontinuous lifecycle')
                checked = audit_journal(list(group[1]), row['public'], row['host'],
                    {**{k:spec[k] for k in ('task','seed','fault_oracle')}, 'method':method},
                    None if method == 'NO_PROBE' else models[spec['task']],
                    design=designs[spec['task']] if method.startswith('DOPT') else None,
                    initial_ledger=ledger, identity={**identity, **key}, previous_sequence=sequence, previous_saved_ns=saved_ns)
                ledger = checked['ledger'];sequence = checked['last_sequence'];saved_ns = checked['last_saved_ns']
                require(row['lifecycle_after_close'] == ledger, 'close changed physical ledger')
                outcome = row['public']['outcome']
                compact = {**key, 'family_oracle':stream['family_oracle'], 'schedule_oracle':stream['schedule_oracle'],
                           **{k:outcome[k] for k in OUTCOME}}
                require(summary['rows'][count] == compact, 'summary differs from audited execution')
                totals.update({k:outcome[k] for k in COUNTS})
                public = checked['public_audit']
                audit_cost.update(policy_queries=checked['policy_queries_recomputed'],
                    parameter_fits=public['fits_recomputed'], optimizer_nfev=public['fit_optimizer_nfev_recomputed'],
                    design_candidates=public['design_candidates_recomputed'])
                if four_step_chain(row['public']):
                    chains.append(key)
                runs[method] = checked;count += 1;event_count += checked['events_checked']
            matches.append({'stream':stream['stream'], 'episode':spec['episode'], **audit_matched_unit(runs)})
    require(next(records, None) is None and next(grouped, None) is None, 'extra unallocated record/journal execution')
    require(summary['lifecycle'] == ledger and summary['controlled_steps'] == totals['total_steps'], 'summary fees differ')
    c = ledger['counts'];limits = manifest['config'][phase.lower()]
    require(c['reset_completed'] == c['reset_attempts'] == n*51
        and ledger['by_phase']['CONTROLLED_RESET']['reset_completed'] == n
        and ledger['by_phase']['CONTROL']['simulation_completed'] == totals['total_steps']
        and c['simulation_frames_completed'] == c['simulation_frames_attempted'] == n*25500+5*totals['total_steps'],
        'full factory/reset/control cost differs')
    require(totals['total_steps'] <= limits['maximum_environment_steps'] and n <= limits['maximum_controlled_resets']
        and c['simulation_frames_attempted'] <= limits['maximum_simulation_frames'], 'study budget exceeded')
    require(phase != 'SMOKE' or bool(chains), 'smoke has no real four-step-fit-to-policy chain')
    return {**identity, 'phase':phase, 'integrity':'PASSED', 'executions_checked':count,
        'events_checked':event_count, 'units_checked':len(matches), 'actual_lifecycle':ledger,
        'online_computation':dict(totals), 'audit_recomputation':dict(audit_cost),
        'required_four_step_policy_chain':bool(chains), 'four_step_policy_chains':chains, 'matched_units':matches,
        'new_environment_steps_during_audit':0, 'new_reset_calls_during_audit':0, 'new_api_calls_during_audit':0,
        'independent_physics_execution':False, 'universal_complete_hidden_state_qualification':False,
        'shared_helpers':['frozen fault states/blend/fraction', 'journal/public numerical estimators/design/controller',
                          'fixed policy get_action', 'normalization/digest', 'NumPy noise generator']}

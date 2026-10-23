"""Fixed population and descriptive/paired statistics for standard cold references."""
import numpy as np
from src.rollout.chronological_faults import states, blend, fraction

METHODS = ('NO_PROBE', 'ORIGINAL8_UPDATE', 'BALANCED4_UPDATE', 'DOPT4_UPDATE',
           'DOPT8_UPDATE', 'DOPT4_KEEP_AT8', 'DOPT4_FALLBACK8')
TASKS = ('push-v3', 'reach-v3', 'door-open-v3')
FAMILIES = ('BIAS', 'COLUMN_Y', 'DEADZONE')
SCHEDULES = ('UNCHANGED', 'ABRUPT', 'GRADUAL')
CONTRASTS = (('DOPT4_FALLBACK8', 'ORIGINAL8_UPDATE'), ('BALANCED4_UPDATE', 'ORIGINAL8_UPDATE'),
    ('DOPT4_UPDATE', 'BALANCED4_UPDATE'), ('DOPT8_UPDATE', 'DOPT4_KEEP_AT8'),
    ('DOPT4_KEEP_AT8', 'DOPT4_UPDATE'), ('DOPT4_FALLBACK8', 'DOPT4_UPDATE'), ('DOPT8_UPDATE', 'ORIGINAL8_UPDATE'))
COUNTS = ('total_steps', 'fixed_probe_steps', 'policy_steps', 'online_parameter_fits', 'optimizer_nfev',
          'policy_queries', 'design_verification_candidates')
OUTCOME = ('success', 'stopped', 'end_reason', 'deadline_loss', 'applied_fitted_controller', *COUNTS)


def population(phase):
    if phase == 'SMOKE':
        a = {'matrix_xy':np.eye(2).tolist(), 'bias_xy':[.12, -.08], 'deadzone_xy':[0., 0.]}
        b = {**a, 'bias_xy':[-.14, .1]}
        return [{'stream':0, 'family_oracle':'BIAS', 'schedule_oracle':'SMOKE_ABRUPT', 'cases':[
            {'episode':i, 'task':TASKS[(i+1)%3], 'seed':21200+i, 'fault_oracle':a if i < 5 else b} for i in range(9)]}]
    if phase != 'MAIN':
        raise ValueError('registered phase required')
    result = []
    for replicate in range(6):
        for fi, family in enumerate(FAMILIES):
            for si, schedule in enumerate(SCHEDULES):
                stream = len(result);a, b = states(67001+stream, family)
                result.append({'stream':stream, 'family_oracle':family, 'schedule_oracle':schedule,
                    'generation_seed_oracle':67001+stream, 'cases':[
                        {'episode':i, 'task':TASKS[(i+replicate+fi+si)%3], 'seed':20200+12*stream+i,
                         'fault_oracle':blend(a, b, fraction(schedule, i))} for i in range(12)]})
    return result


def compact(record):
    keys = ('study_phase', 'stream', 'episode', 'task', 'seed', 'method', 'family_oracle', 'schedule_oracle')
    return {**{k:record[k] for k in keys}, **{k:record['public']['outcome'][k] for k in OUTCOME}}


def validate_rows(rows, phase):
    expected = [(stream, case, method) for stream in population(phase) for case in stream['cases'] for method in METHODS]
    if len(rows) != len(expected):
        raise ValueError('complete seven-method population required')
    keys = {'study_phase', 'stream', 'episode', 'task', 'seed', 'method', 'family_oracle', 'schedule_oracle', *OUTCOME}
    for row, (stream, case, method) in zip(rows, expected):
        if set(row) != keys or any(row[k] != case[k] for k in ('episode', 'task', 'seed')) or row['study_phase'] != phase or row['stream'] != stream['stream'] or row['method'] != method or any(row[k] != stream[k] for k in ('family_oracle', 'schedule_oracle')):
            raise ValueError('population identity/order differs')
        if any(type(row[k]) is not bool for k in ('success', 'stopped', 'applied_fitted_controller')) or any(type(row[k]) is not int or row[k] < 0 for k in (*COUNTS, 'deadline_loss', 'stream', 'episode', 'seed')):
            raise ValueError('strict recorded outcome types required')
        if row['end_reason'] not in ('SUCCESS', 'TERMINATED', 'TRUNCATED', 'STOP_INVALID_FIT', 'BUDGET_EXHAUSTED') or row['success'] != (row['end_reason'] == 'SUCCESS') or row['stopped'] != (row['end_reason'] == 'STOP_INVALID_FIT'):
            raise ValueError('recorded ending differs')
        n = row['total_steps']
        if not 0 < n <= 500 or n != row['fixed_probe_steps']+row['policy_steps'] or row['policy_queries'] != row['policy_steps'] or row['deadline_loss'] != (n if row['success'] else 500) or (row['success'] and row['stopped']):
            raise ValueError('failed/stopped denominator or actual cost differs')


def method_metrics(rows):
    result = {}
    for method in METHODS:
        selected = [r for r in rows if r['method'] == method]
        result[method] = {'cases':len(selected), 'successes':sum(r['success'] for r in selected),
            'failures':sum(not r['success'] for r in selected), 'stops':sum(r['stopped'] for r in selected),
            'mean_deadline_loss':float(np.mean([r['deadline_loss'] for r in selected])),
            **{'mean_'+k:float(np.mean([r[k] for r in selected])) for k in COUNTS}}
    return result


def statistics(rows, phase):
    validate_rows(rows, phase);specs = population(phase);methods = method_metrics(rows)
    # The full population has 12 units in every stream. Resample complete streams
    # jointly across methods, nine strata in family/schedule order, six per cell.
    stream_means = np.asarray([[np.mean([r['deadline_loss'] for r in rows if r['stream'] == s['stream'] and r['method'] == m])
                                for m in METHODS] for s in specs])
    bootstrap = None
    if phase == 'MAIN':
        rng = np.random.default_rng(20261022);bootstrap = np.zeros((10000, len(METHODS)))
        for family in FAMILIES:
            for schedule in SCHEDULES:
                ids = [i for i, s in enumerate(specs) if s['family_oracle'] == family and s['schedule_oracle'] == schedule]
                if len(ids) != 6:
                    raise ValueError('six whole streams per stratum required')
                draw = rng.choice(ids, size=(10000, 6), replace=True)
                bootstrap += stream_means[draw].sum(axis=1)
        bootstrap /= 54
    contrasts = []
    for i, (left, right) in enumerate(CONTRASTS):
        a, b = METHODS.index(left), METHODS.index(right)
        contrasts.append({'left':left, 'right':right, 'mean_loss_difference':float(np.mean(stream_means[:, a]-stream_means[:, b])),
            'ci95':None if bootstrap is None else np.quantile(bootstrap[:, a]-bootstrap[:, b], [.025, .975]).tolist(),
            'primary':i == 0, 'multiplicity':'PRIMARY' if i == 0 else 'UNADJUSTED_SECONDARY'})
    groups = []
    for field, labels in (('task', TASKS), ('family_oracle', FAMILIES), ('schedule_oracle', SCHEDULES if phase == 'MAIN' else ('SMOKE_ABRUPT',))):
        for label in labels:
            selected = [r for r in rows if r[field] == label]
            if selected:
                groups.append({'field':field, 'value':label, 'methods':method_metrics(selected)})
    return {'phase':phase, 'units':len(rows)//7, 'executions':len(rows), 'streams':len(specs), 'methods':methods,
        'contrasts':contrasts, 'descriptive_groups':groups,
        'bootstrap_samples':10000 if bootstrap is not None else 0, 'bootstrap_seed':20261022,
        'interval_scope':'WHOLE_STREAM_STRATIFIED_PAIRED' if bootstrap is not None else 'SINGLE_SMOKE_STREAM_NO_POPULATION_INTERVAL',
        'negative_loss_difference_favors_left':True, 'algorithm_promotion_claim':False}


def costs(summary):
    units = len(summary['rows'])//7
    source = {'environment_steps':3840, 'controlled_resets':480, 'all_reset_calls':24480, 'simulation_frames':12259200}
    per_method = {}
    for method in METHODS:
        rows = [r for r in summary['rows'] if r['method'] == method]
        dependent = method != 'NO_PROBE'
        per_method[method] = {'executions':len(rows), 'online_environment_steps':sum(r['total_steps'] for r in rows),
            'online_controlled_resets':len(rows), 'online_all_reset_calls':51*len(rows),
            'online_simulation_frames':25500*len(rows)+5*sum(r['total_steps'] for r in rows),
            'full_prior_nominal_source':source if dependent else {k:0 for k in source},
            'source_amortization_units':units, 'prior_source_steps_per_unit':3840/units if dependent else 0.,
            **{k:sum(r[k] for r in rows) for k in COUNTS}}
    return {'phase':summary['phase'], 'actual_lifecycle':summary['lifecycle'], 'methods':per_method,
        'shared_historical_nominal_source_paid_once':source, 'prior_nominal_design_preparation':{'enumerations':3, 'candidate_rows':432},
        'collection_wall_ns':summary['wall_ns'], 'new_api_calls':0, 'new_nominal_training':0, 'new_selector_fits':0,
        'source_fees_are_historical_not_new_collection':True}

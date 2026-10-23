"""Separate numerical reconstruction; does not import the analysis functions.

NumPy's registered PRNG and quantile implementation are shared. Arithmetic,
selection, denominators and cost aggregation are independently implemented.
"""
import math
import numpy as np
from src.analysis.short_probe_study_audit_v1 import METHODS, TASKS, FAMILIES, SCHEDULES, COUNTS, population, require

PAIRS = (('DOPT4_FALLBACK8','ORIGINAL8_UPDATE'), ('BALANCED4_UPDATE','ORIGINAL8_UPDATE'),
    ('DOPT4_UPDATE','BALANCED4_UPDATE'), ('DOPT8_UPDATE','DOPT4_KEEP_AT8'),
    ('DOPT4_KEEP_AT8','DOPT4_UPDATE'), ('DOPT4_FALLBACK8','DOPT4_UPDATE'), ('DOPT8_UPDATE','ORIGINAL8_UPDATE'))


def metrics(rows):
    result = {}
    for method in METHODS:
        chosen = [r for r in rows if r['method'] == method];n = len(chosen)
        successes = sum(1 for r in chosen if r['success'])
        result[method] = {'cases':n, 'successes':successes, 'failures':n-successes,
            'stops':sum(1 for r in chosen if r['stopped'])}
        for key in ('deadline_loss', *COUNTS):
            result[method]['mean_'+key] = math.fsum(r[key] for r in chosen)/n
    return result


def reconstruct(summary):
    phase = summary['phase'];rows = summary['rows'];specs = population(phase)
    expected = [(s,c,m) for s in specs for c in s['cases'] for m in METHODS]
    require(len(rows) == len(expected), 'numeric audit requires full denominator')
    for row,(stream,case,method) in zip(rows, expected):
        wanted = {'study_phase':phase, 'stream':stream['stream'], 'episode':case['episode'], 'task':case['task'],
            'seed':case['seed'], 'method':method, 'family_oracle':stream['family_oracle'], 'schedule_oracle':stream['schedule_oracle']}
        require(all(row[k] == v for k,v in wanted.items()), 'numeric population mismatch')
        require(all(type(row[k]) is bool for k in ('success','stopped','applied_fitted_controller'))
            and all(type(row[k]) is int and row[k] >= 0 for k in (*COUNTS, 'deadline_loss')), 'numeric outcome type mismatch')
        require(0 < row['total_steps'] <= 500 and row['deadline_loss'] == (row['total_steps'] if row['success'] else 500)
            and not (row['success'] and row['stopped']) and row['policy_queries'] == row['policy_steps']
            and row['total_steps'] == row['policy_steps']+row['fixed_probe_steps'], 'outcome/cost denominator mismatch')
    estimates = metrics(rows);units = len(rows)//7
    # Consecutive rows are complete seven-method units, grouped in whole streams.
    cube = np.array([r['deadline_loss'] for r in rows], dtype=float).reshape(len(specs), -1, 7)
    means = cube.sum(axis=1)/cube.shape[1]
    draws = []
    if phase == 'MAIN':
        generator = np.random.default_rng(20261022)
        for cell in range(9):
            draws.append(generator.choice(list(range(cell,54,9)), size=(10000,6), replace=True))
    contrasts = []
    for i,(left,right) in enumerate(PAIRS):
        a,b = METHODS.index(left), METHODS.index(right);differences = means[:,a]-means[:,b]
        values = None
        if draws:
            values = np.zeros(10000)
            for selection in draws:
                values += differences[selection].sum(axis=1)
            values /= 54
        contrasts.append({'left':left, 'right':right, 'mean_loss_difference':math.fsum(differences)/len(specs),
            'ci95':None if values is None else np.quantile(values,[.025,.975]).tolist(), 'primary':i == 0,
            'multiplicity':'PRIMARY' if i == 0 else 'UNADJUSTED_SECONDARY'})
    groups = []
    for field,labels in (('task',TASKS),('family_oracle',FAMILIES),('schedule_oracle',SCHEDULES if phase == 'MAIN' else ('SMOKE_ABRUPT',))):
        for label in labels:
            subset = [r for r in rows if r[field] == label]
            if subset:
                groups.append({'field':field, 'value':label, 'methods':metrics(subset)})
    statistics = {'phase':phase, 'units':units, 'executions':len(rows), 'streams':len(specs), 'methods':estimates,
        'contrasts':contrasts, 'descriptive_groups':groups, 'bootstrap_samples':10000 if draws else 0,
        'bootstrap_seed':20261022, 'interval_scope':'WHOLE_STREAM_STRATIFIED_PAIRED' if draws else 'SINGLE_SMOKE_STREAM_NO_POPULATION_INTERVAL',
        'negative_loss_difference_favors_left':True, 'algorithm_promotion_claim':False}
    historical = {'environment_steps':3840, 'controlled_resets':480, 'all_reset_calls':24480, 'simulation_frames':12259200}
    cost_methods = {}
    for method in METHODS:
        selected = [r for r in rows if r['method'] == method];totals = {k:sum(r[k] for r in selected) for k in COUNTS}
        count = len(selected);fee = {k:(0 if method == 'NO_PROBE' else v) for k,v in historical.items()}
        cost_methods[method] = {'executions':count, 'online_environment_steps':totals['total_steps'],
            'online_controlled_resets':count, 'online_all_reset_calls':count*51,
            'online_simulation_frames':count*51*500+totals['total_steps']*5, 'full_prior_nominal_source':fee,
            'source_amortization_units':units, 'prior_source_steps_per_unit':fee['environment_steps']/units, **totals}
    costs = {'phase':phase, 'actual_lifecycle':summary['lifecycle'], 'methods':cost_methods,
        'shared_historical_nominal_source_paid_once':historical,
        'prior_nominal_design_preparation':{'enumerations':3,'candidate_rows':432},
        'collection_wall_ns':summary['wall_ns'], 'new_api_calls':0, 'new_nominal_training':0, 'new_selector_fits':0,
        'source_fees_are_historical_not_new_collection':True}
    return statistics,costs


def compare(actual, expected):
    fields = 0;maximum = 0.
    def check(a,b,path):
        nonlocal fields,maximum
        if type(b) is dict:
            require(type(a) is dict and set(a) == set(b), 'numeric object keys differ at '+path)
            for key,value in b.items():
                check(a[key],value,path+'.'+key)
        elif type(b) is list:
            require(type(a) is list and len(a) == len(b), 'numeric list differs at '+path)
            for i,(x,y) in enumerate(zip(a,b)):
                check(x,y,path+f'[{i}]')
        elif type(b) is float:
            require(type(a) in (int,float) and math.isfinite(a) and math.isfinite(b), 'nonfinite numeric field at '+path)
            delta = abs(a-b);maximum = max(maximum,delta);fields += 1
            require(delta <= 1e-9, 'numeric reconstruction differs at '+path)
        else:
            fields += 1
            require(type(a) is type(b) and a == b, 'exact numeric/semantic field differs at '+path)
    check(actual,expected,'root')
    return {'fields_checked':fields,'maximum_absolute_difference':maximum,'absolute_tolerance':1e-9}

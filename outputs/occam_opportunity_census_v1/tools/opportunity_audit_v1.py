"""Separate CSV/scalar reconstruction, without importing the census engine."""
from collections import Counter
from fractions import Fraction


def verify(registry_csv, panels_csv, result, original_program_csv, original_cells_csv):
    checked = [0]

    def same(actual, expected, name):
        checked[0] += 1
        if actual != expected:
            raise ValueError('independent opportunity audit: ' + name)

    tags = ('PI_0125', 'PI_0500', 'PI_2000', 'PI_8000')
    bases = tags + ('META_ADAPT', 'META_FROZEN', 'ERM_ADAPT', 'ERM_FROZEN')
    arms = ('CONTINUE', 'VALIDATE8', 'MOVE_MEASURE')
    names = tuple(base+'__'+arm for arm in arms for base in bases) + (
        'GLOBAL_PI_0125', 'GLOBAL_PI_2000', 'GLOBAL_PI_8000', 'DIRECT_C8', 'MOVE_INTEGRAL')
    key_names = ('cohort', 'group', 'task', 'seed', 'context', 'planned_boundary', 'program')
    same(len(registry_csv), 1740, 'all allocations')
    same(len(panels_csv), 1566, 'all QUAL panels')
    registry = {}
    for raw in registry_csv:
        k = tuple(raw[n] for n in key_names)
        same(k in registry, False, 'unique allocation')
        same(raw['status'], 'COMPLETE', 'no unresolved imputation')
        same(raw['success'] in ('True', 'False'), True, 'Boolean label')
        registry[k] = {**{n: raw[n] for n in ('cohort', 'task', 'context', 'program', 'status')},
            **{n: int(raw[n]) for n in ('group', 'seed', 'planned_boundary', 'case_index', 'deadline_loss', 'total_steps')},
            'success': raw['success'] == 'True'}
    for phase, size in (('NATIVE', 174), ('QUAL', 1566)):
        selected = [r for r in registry.values() if r['cohort'] == phase]
        same(len(selected), size, 'cohort allocation')
        same(sorted(r['case_index'] for r in selected), list(range(1, size+1)), 'cohort indices')
    buckets = {}
    for raw in panels_csv:
        key = tuple(raw[n] for n in key_names)
        same(raw['cohort'], 'QUAL', 'QUAL only')
        assignment = registry[key]
        for n in ('deadline_loss', 'total_steps'):
            same(int(raw[n]), assignment[n], 'panel '+n)
        same(raw['success'] == 'True', assignment['success'], 'panel success')
        ukey = (int(raw['group']), raw['task'], raw['context'], int(raw['planned_boundary']), int(raw['seed']))
        if ukey not in buckets:
            buckets[ukey] = {}
        same(raw['program'] in buckets[ukey], False, 'unique unit/program')
        buckets[ukey][raw['program']] = {**assignment, 'boundary_applied': raw['boundary_applied'] == 'True',
                                        'filter_updates': int(raw['filter_updates'])}
    same(len(buckets), 54, 'all units')
    same(set(k[0] for k in buckets), set(range(9)), 'nine groups')
    for g in range(9):
        keys = [k for k in buckets if k[0] == g]
        same(len(keys), 6, 'six units/group')
        same({(k[1], k[2]) for k in keys}, {(t, c) for t in ('push-v3', 'reach-v3', 'door-open-v3') for c in ('UNCHANGED', 'CHANGED')}, 'all task/conditions')
        same(len(set(k[3] for k in keys)), 1, 'one boundary/group')
    same(Counter(next(k[3] for k in buckets if k[0] == g) for g in range(9)), Counter({16: 3, 32: 3, 64: 3}), 'three groups/boundary')
    out_units = {(u['group'], u['task'], u['context'], u['planned_boundary'], u['seed']): u for u in result['units']}
    same(len(result['units']), 54, 'unit denominator')
    same(set(out_units), set(buckets), 'unit outputs')
    records = {}
    for key, source in sorted(buckets.items()):
        same(set(source), set(names), 'full 29-program menu')
        row = out_units[key]
        early = {source[b+'__'+a]['boundary_applied'] for a in arms for b in bases}
        same(len(early), 1, 'same prefix boundary')
        before = False in early
        if before:
            same({(source[b+'__'+a]['success'], source[b+'__'+a]['deadline_loss'], source[b+'__'+a]['total_steps'])
                  for a in arms for b in bases}, {(True, source['PI_0125__CONTINUE']['deadline_loss'], source['PI_0125__CONTINUE']['total_steps'])}, 'early ties')
        ordered = {a: sorted((source[t+'__'+a]['deadline_loss'], t+'__'+a) for t in tags) for a in arms}
        c, v, m = [ordered[a][0][0] for a in arms]
        r = sorted((c, v, m))[0]
        values = dict(C=c, V=v, M=m, R=r, acquisition_opportunity=c-r)
        for tag in tags:
            baseline = source[tag+'__CONTINUE']['deadline_loss']
            values.update({'baseline_'+tag: baseline, 'gain_'+tag: baseline-c, 'total_'+tag: baseline-r})
            same(row['baseline_by_T'][tag], baseline, 'baseline loss')
            same(row['gain_by_T'][tag], baseline-c, 'gain opportunity')
            same(row['total_by_T'][tag], baseline-r, 'total opportunity')
            same((baseline-c)+(c-r), baseline-r, 'integer identity')
        for field in ('C', 'V', 'M', 'R', 'acquisition_opportunity'):
            same(row[field], values[field], field)
        same(row['before_boundary_success'], before, 'early success retained')
        same(row['minimizing_programs'], sorted(n for a in arms for loss, n in ordered[a] if loss == r), 'all minimizing ties')
        for tag in tags:
            for arm in arms:
                n = tag+'__'+arm
                same(row['fixed_programs'][n], {f: source[n][f] for f in ('case_index', 'deadline_loss', 'total_steps', 'success')}, 'factual fixed result only')
        records[key] = {**values, 'before': before}

    def aggregate(selected):
        groups = sorted(set(k[0] for k in selected))
        fields = [f for f in next(iter(records.values())) if f != 'before']
        means = {}
        for f in fields:
            subtotal = Fraction(0)
            for g in groups:
                block = [records[k][f] for k in selected if k[0] == g]
                subtotal += Fraction(sum(block), len(block))
            means[f] = str(subtotal / len(groups))
        return dict(units=len(selected), independent_groups=len(groups), group_ids=groups,
            equal_group_mean_exact=means,
            validation_strictly_better=sum(records[k]['V'] < records[k]['C'] for k in selected),
            movement_strictly_better=sum(records[k]['M'] < records[k]['C'] for k in selected),
            both_strictly_better=sum(records[k]['V'] < records[k]['C'] and records[k]['M'] < records[k]['C'] for k in selected),
            no_acquisition_gap=sum(records[k]['C'] == records[k]['R'] for k in selected),
            before_boundary_success=sum(records[k]['before'] for k in selected))

    same(result['overall'], aggregate(list(records)), 'all-group means and counts')
    same(result['groups'], [dict(group=g, **aggregate([k for k in records if k[0] == g])) for g in range(9)], 'all groups')
    cells = []
    for task in ('push-v3', 'reach-v3', 'door-open-v3'):
        for context in ('UNCHANGED', 'CHANGED'):
            for boundary in (16, 32, 64):
                selected = [k for k in records if (k[1], k[2], k[3]) == (task, context, boundary)]
                same(len(selected), 3, 'all cells')
                cells.append(dict(task=task, context=context, planned_boundary=boundary, **aggregate(selected)))
    same(result['cells'], cells, '18 cells')
    for f in next(iter(records.values())):
        if f != 'before':
            same(result['exact_severity_frequencies'][f], [dict(difference=d, units=n) for d, n in sorted(Counter(records[k][f] for k in records).items())], 'full severity frequencies')
    original = {r['program']: r for r in original_program_csv}
    same(set(original), set(names), 'original 29 programs')
    same(len(result['programs']), 29, 'program denominator')
    same(set(p['program'] for p in result['programs']), set(names), 'program outputs')
    same(len(result['group_programs']), 261, 'all group/program rows')
    for p in result['programs']:
        rows = [v for b in buckets.values() for n, v in b.items() if n == p['program']]
        loss = Fraction(sum(r['deadline_loss'] for r in rows), 54)
        expected = dict(program=p['program'], executions=54, success=sum(r['success'] for r in rows),
            failure=sum(not r['success'] for r in rows), mean_deadline_loss_exact=str(loss),
            actual_steps=sum(r['total_steps'] for r in rows), filter_updates=sum(r['filter_updates'] for r in rows))
        same(p, expected, 'program reconstructed')
        o = original[p['program']]
        for f in ('executions', 'success', 'failure', 'actual_steps', 'filter_updates'):
            same(int(o[f]), p[f], 'original program '+f)
        same(float(o['mean_deadline_loss']), float(loss), 'original program exact mean')
    for p in result['group_programs']:
        rows = [v for key, b in buckets.items() if key[0] == p['group'] for n, v in b.items() if n == p['program']]
        same(p, dict(group=p['group'], program=p['program'], executions=6, success=sum(r['success'] for r in rows),
            failure=sum(not r['success'] for r in rows),
            mean_deadline_loss_exact=str(Fraction(sum(r['deadline_loss'] for r in rows), 6)),
            actual_steps=sum(r['total_steps'] for r in rows), filter_updates=sum(r['filter_updates'] for r in rows)), 'group/program values')
    same({(p['group'], p['program']) for p in result['group_programs']}, {(g, n) for g in range(9) for n in names}, 'group/program coverage')
    original_cells = {(r['program'], r['task'], r['context'], int(r['boundary'])): r for r in original_cells_csv}
    same(len(original_cells), 522, 'original program cells')
    same(len(result['program_cells']), 522, 'output program cells')
    seen = set()
    for p in result['program_cells']:
        key = (p['program'], p['task'], p['context'], p['planned_boundary'])
        same(key in seen, False, 'unique program cell')
        seen.add(key)
        rows = [v for k, b in buckets.items() if (k[1], k[2], k[3]) == key[1:] for n, v in b.items() if n == key[0]]
        exact = Fraction(sum(r['deadline_loss'] for r in rows), 3)
        same(p, dict(program=key[0], task=key[1], context=key[2], planned_boundary=key[3], executions=3,
            success=sum(r['success'] for r in rows), mean_deadline_loss_exact=str(exact), actual_steps=sum(r['total_steps'] for r in rows)), 'program cell values')
        same(int(original_cells[key]['executions']), 3, 'original cell denominator')
        same(int(original_cells[key]['success']), p['success'], 'original cell success')
        same(float(original_cells[key]['mean_loss']), float(exact), 'original cell loss')
    same(seen, set(original_cells), 'all original cells retained')
    same(result['registered_executions'], 1740, 'registry retained')
    same(result['registered_QUAL_executions'], 1566, 'QUAL retained')
    same(result['cohort_failures'], {c: sum(not r['success'] for r in registry.values() if r['cohort'] == c) for c in ('NATIVE', 'QUAL')}, 'all failures')
    same(result['all_task_failures'], [r for r in registry.values() if not r['success']], 'full failure records')
    for field, expected in [('post_hoc_descriptive_only', True), ('future_outcomes_used', True),
                            ('deployable_selector', False), ('expected_benefit_bound', False),
                            ('pure_information_value_estimated', False), ('publication_goal_complete', False)]:
        same(result[field], expected, 'interpretation flag ' + field)
    return dict(integrity='PASSED_INDEPENDENT_CSV_SCALAR_FRACTION_AUDIT', checked_fields=checked[0],
        registered_executions=1740, QUAL_executions=1566, units=54, independent_groups=9, cells=18,
        production_census_functions_disabled=True, CSV_JSON_SHA_helpers_shared=True,
        independent_physics_resimulation=False, original_29_programs_reconstructed=True,
        new_environment_interactions=0, new_model_queries=0, new_fits=0, online_LLM_API_calls=0)

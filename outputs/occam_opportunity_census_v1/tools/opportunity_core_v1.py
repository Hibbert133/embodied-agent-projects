"""Exact, descriptive census of already executed complete programs; no learner."""
from collections import Counter, defaultdict
from fractions import Fraction

TASKS = ('push-v3', 'reach-v3', 'door-open-v3')
CONTEXTS = ('UNCHANGED', 'CHANGED')
ARMS = ('CONTINUE', 'VALIDATE8', 'MOVE_MEASURE')
TAGS = ('PI_0125', 'PI_0500', 'PI_2000', 'PI_8000')
BASES = (*TAGS, 'META_ADAPT', 'META_FROZEN', 'ERM_ADAPT', 'ERM_FROZEN')
PROGRAMS = tuple(p + '__' + a for a in ARMS for p in BASES) + (
    'GLOBAL_PI_0125', 'GLOBAL_PI_2000', 'GLOBAL_PI_8000', 'DIRECT_C8', 'MOVE_INTEGRAL')
KEYS = ('cohort', 'group', 'task', 'seed', 'context', 'planned_boundary', 'program')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(row, name, lo=0, hi=None):
    value = row[name]
    require(type(value) is str, 'CSV scalar must be text: ' + name)
    n = int(value)
    require(str(n) == value and n >= lo and (hi is None or n <= hi), 'invalid integer: ' + name)
    return n


def boolean(row, name):
    require(row[name] in ('True', 'False'), 'invalid Boolean: ' + name)
    return row[name] == 'True'


def normalize(row, *, panel=False):
    require(row['cohort'] in ('NATIVE', 'QUAL'), 'unknown cohort')
    require(row['task'] in TASKS and row['context'] in CONTEXTS, 'unknown task/condition')
    require(row['program'] in PROGRAMS, 'unknown program')
    d = {k: row[k] for k in KEYS}
    for k in ('group', 'seed', 'planned_boundary'):
        d[k] = number(row, k)
    require(d['planned_boundary'] in (16, 32, 64), 'unknown boundary')
    d.update(success=boolean(row, 'success'), deadline_loss=number(row, 'deadline_loss', hi=500),
             total_steps=number(row, 'total_steps', hi=500))
    require((d['deadline_loss'] == d['total_steps']) if d['success'] else (d['deadline_loss'] == 500), 'cutoff semantics')
    if panel:
        d.update(boundary_applied=boolean(row, 'boundary_applied'), filter_updates=number(row, 'filter_updates'))
    else:
        require(row['status'] == 'COMPLETE', 'technical unresolved is not a zero or task failure')
        d.update(case_index=number(row, 'case_index', lo=1), status=row['status'])
    return d


def row_key(row):
    return tuple(row[k] for k in KEYS)


def unit_key(row):
    return tuple(row[k] for k in ('group', 'task', 'context', 'planned_boundary', 'seed'))


def prepare(registry_rows, panel_rows):
    registry = [normalize(r) for r in registry_rows]
    panels = [normalize(r, panel=True) for r in panel_rows]
    require(len(registry) == 1740 and len(panels) == 1566, 'full allocated population only')
    assigned = {row_key(r): r for r in registry}
    require(len(assigned) == len(registry), 'duplicate allocation')
    for cohort, n in (('NATIVE', 174), ('QUAL', 1566)):
        cases = [r for r in registry if r['cohort'] == cohort]
        require(len(cases) == n and {r['case_index'] for r in cases} == set(range(1, n+1)), 'complete cohort indices')
    require(len({row_key(r) for r in panels}) == 1566, 'duplicate audited panel')
    for p in panels:
        require(p['cohort'] == 'QUAL' and row_key(p) in assigned, 'panel allocation mismatch')
        a = assigned[row_key(p)]
        require(all(p[k] == a[k] for k in ('success', 'deadline_loss', 'total_steps')), 'original tables disagree')
        p['case_index'] = a['case_index']
    return registry, panels


def metrics(unit):
    result = {k: unit[k] for k in ('C', 'V', 'M', 'R', 'acquisition_opportunity')}
    for tag in TAGS:
        for family in ('baseline', 'gain', 'total'):
            result[family + '_' + tag] = unit[family + '_by_T'][tag]
    return result


def summary(units):
    require(bool(units), 'empty strata stay unavailable; no zero mean')
    grouped = defaultdict(list)
    for u in units:
        grouped[u['group']].append(metrics(u))
    means = {k: str(sum((sum((Fraction(r[k]) for r in rows), Fraction()) / len(rows)
                         for rows in grouped.values()), Fraction()) / len(grouped))
             for k in metrics(units[0])}
    return dict(units=len(units), independent_groups=len(grouped), group_ids=sorted(grouped),
                equal_group_mean_exact=means, validation_strictly_better=sum(u['V'] < u['C'] for u in units),
                movement_strictly_better=sum(u['M'] < u['C'] for u in units),
                both_strictly_better=sum(u['V'] < u['C'] and u['M'] < u['C'] for u in units),
                no_acquisition_gap=sum(u['C'] == u['R'] for u in units),
                before_boundary_success=sum(u['before_boundary_success'] for u in units))


def census(registry, panels):
    by = defaultdict(dict)
    for p in panels:
        key = unit_key(p)
        require(p['program'] not in by[key], 'duplicate program/unit')
        by[key][p['program']] = p
    require(len(by) == 54, 'all 54 QUAL units')
    require({k[0] for k in by} == set(range(9)), 'all nine independent groups')
    for group in range(9):
        keys = [k for k in by if k[0] == group]
        require(len(keys) == 6 and {(k[1], k[2]) for k in keys} == {(t, c) for t in TASKS for c in CONTEXTS}, 'all task/conditions per group')
        require(len({k[3] for k in keys}) == 1, 'group has one boundary stratum')
    require(all(len({k[0] for k in by if k[3] == b}) == 3 for b in (16, 32, 64)), 'three independent groups per boundary')
    units = []
    for key, programs in sorted(by.items()):
        require(set(programs) == set(PROGRAMS), 'every one of 29 programs retained')
        common = [programs[b+'__'+a] for a in ARMS for b in BASES]
        require(len({r['boundary_applied'] for r in common}) == 1, 'shared prefix boundary mismatch')
        early = not common[0]['boundary_applied']
        if early:
            require(all(r['success'] for r in common) and len({(r['deadline_loss'], r['total_steps']) for r in common}) == 1,
                    'early identical prefix must preserve all actual ties')
        fixed = {b+'__'+a: programs[b+'__'+a] for a in ARMS for b in TAGS}
        c, v, m = [min(programs[b+'__'+a]['deadline_loss'] for b in TAGS) for a in ARMS]
        best = min(c, v, m)
        baseline = {b: programs[b+'__CONTINUE']['deadline_loss'] for b in TAGS}
        gain = {b: baseline[b]-c for b in TAGS}
        total = {b: baseline[b]-best for b in TAGS}
        require(all(total[b] == gain[b]+c-best >= 0 for b in TAGS), 'exact menu identity')
        units.append(dict(group=key[0], task=key[1], context=key[2], planned_boundary=key[3], seed=key[4],
            before_boundary_success=early, C=c, V=v, M=m, R=best, acquisition_opportunity=c-best,
            baseline_by_T=baseline, gain_by_T=gain, total_by_T=total,
            minimizing_programs=sorted(n for n, r in fixed.items() if r['deadline_loss'] == best),
            fixed_programs={n: {k: r[k] for k in ('case_index', 'deadline_loss', 'total_steps', 'success')} for n, r in fixed.items()}))
    programs = []
    group_programs = []
    for name in PROGRAMS:
        rows = [p for p in panels if p['program'] == name]
        for group in (None, *range(9)):
            selected = rows if group is None else [p for p in rows if p['group'] == group]
            item = dict(program=name, executions=len(selected), success=sum(p['success'] for p in selected),
                failure=sum(not p['success'] for p in selected),
                mean_deadline_loss_exact=str(Fraction(sum(p['deadline_loss'] for p in selected), len(selected))),
                actual_steps=sum(p['total_steps'] for p in selected), filter_updates=sum(p['filter_updates'] for p in selected))
            if group is None:
                programs.append(item)
            else:
                group_programs.append(dict(group=group, **item))
    cells = []
    for task in TASKS:
        for context in CONTEXTS:
            for boundary in (16, 32, 64):
                selected = [u for u in units if (u['task'], u['context'], u['planned_boundary']) == (task, context, boundary)]
                require(len(selected) == 3, 'all 18 complete cells')
                cells.append(dict(task=task, context=context, planned_boundary=boundary, **summary(selected)))
    program_cells = []
    for name in PROGRAMS:
        for cell in cells:
            selected = [p for p in panels if p['program'] == name and
                        (p['task'], p['context'], p['planned_boundary']) == (cell['task'], cell['context'], cell['planned_boundary'])]
            require(len(selected) == 3, 'all 522 program cells')
            program_cells.append(dict(program=name, task=cell['task'], context=cell['context'], planned_boundary=cell['planned_boundary'],
                executions=3, success=sum(p['success'] for p in selected),
                mean_deadline_loss_exact=str(Fraction(sum(p['deadline_loss'] for p in selected), 3)),
                actual_steps=sum(p['total_steps'] for p in selected)))
    return dict(registered_executions=len(registry), registered_QUAL_executions=len(panels),
        cohort_failures={c: sum(not r['success'] for r in registry if r['cohort'] == c) for c in ('NATIVE', 'QUAL')},
        all_task_failures=[r for r in registry if not r['success']], units=units, overall=summary(units),
        groups=[dict(group=g, **summary([u for u in units if u['group'] == g])) for g in range(9)],
        cells=cells, programs=programs, group_programs=group_programs, program_cells=program_cells,
        exact_severity_frequencies={k: [dict(difference=d, units=n) for d, n in sorted(Counter(metrics(u)[k] for u in units).items())] for k in metrics(units[0])},
        post_hoc_descriptive_only=True, future_outcomes_used=True, deployable_selector=False,
        expected_benefit_bound=False, pure_information_value_estimated=False, publication_goal_complete=False)

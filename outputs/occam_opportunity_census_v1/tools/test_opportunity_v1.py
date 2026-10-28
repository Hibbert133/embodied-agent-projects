"""Pure constructed CSV fixtures; no original scientific outcomes are read here."""
from copy import deepcopy
from fractions import Fraction
from unittest import TestCase, mock
import opportunity_core_v1 as c
import opportunity_audit_v1 as a
from pathlib import Path
import tempfile


def fixture():
    panels = []
    for g in range(9):
        for ti, task in enumerate(c.TASKS):
            for ci, context in enumerate(c.CONTEXTS):
                base = 100+g+2*ti+ci
                for name in c.PROGRAMS:
                    if '__' in name:
                        controller, arm = name.split('__')
                        index = c.TAGS.index(controller) if controller in c.TAGS else 1
                        extra = {'CONTINUE': 0, 'VALIDATE8': 8, 'MOVE_MEASURE': 12}[arm]
                        if arm == 'VALIDATE8' and g % 3 == 1 and ti == 0 and ci == 1:
                            extra = -5
                        if arm == 'MOVE_MEASURE' and g % 3 == 0 and ti == 2 and ci == 1:
                            extra = -20
                        loss = base+3*abs(index-g % 4)+extra
                    else:
                        loss = base+40
                    panels.append(dict(cohort='QUAL', group=str(g), task=task, context=context,
                        seed=str(1000+3*g+ti), planned_boundary=str((16, 32, 64)[g//3]), program=name,
                        success='True', deadline_loss=str(loss), total_steps=str(loss), boundary_applied='True',
                        filter_updates='2' if 'ADAPT' in name else '0'))
    return panels


def tables(panels):
    registry = []
    for phase, rows in (('NATIVE', panels[:174]), ('QUAL', panels)):
        for i, p in enumerate(rows, 1):
            registry.append({**{n: p[n] for n in (*c.KEYS, 'success', 'deadline_loss', 'total_steps')},
                             'cohort': phase, 'case_index': str(i), 'status': 'COMPLETE'})
    original = []
    cells = []
    for name in c.PROGRAMS:
        rows = [p for p in panels if p['program'] == name]
        original.append(dict(program=name, executions='54', success=str(sum(p['success'] == 'True' for p in rows)),
            failure=str(sum(p['success'] == 'False' for p in rows)),
            mean_deadline_loss=str(sum(int(p['deadline_loss']) for p in rows)/54),
            actual_steps=str(sum(int(p['total_steps']) for p in rows)), filter_updates=str(sum(int(p['filter_updates']) for p in rows))))
        for task in c.TASKS:
            for context in c.CONTEXTS:
                for boundary in (16, 32, 64):
                    chosen = [p for p in rows if (p['task'], p['context'], p['planned_boundary']) == (task, context, str(boundary))]
                    cells.append(dict(program=name, task=task, context=context, boundary=str(boundary), executions='3',
                        success=str(sum(p['success'] == 'True' for p in chosen)),
                        mean_loss=str(sum(int(p['deadline_loss']) for p in chosen)/3)))
    return registry, original, cells


def compute(panels):
    registry, original, cells = tables(panels)
    r, p = c.prepare(registry, panels)
    return registry, c.census(r, p), original, cells


class OpportunityTests(TestCase):
    def test_known_gain_identity(self):
        _, result, _, _ = compute(fixture())
        u = next(x for x in result['units'] if (x['group'], x['task'], x['context']) == (3, 'push-v3', 'UNCHANGED'))
        self.assertEqual((u['C'], u['R'], u['gain_by_T']['PI_0125'], u['total_by_T']['PI_0125']), (103, 103, 9, 9))

    def test_known_acquisition_difference(self):
        _, result, _, _ = compute(fixture())
        u = next(x for x in result['units'] if (x['group'], x['task'], x['context']) == (0, 'door-open-v3', 'CHANGED'))
        self.assertEqual((u['C'], u['M'], u['R'], u['acquisition_opportunity']), (105, 85, 85, 20))

    def test_overlapping_acquisition_counts_are_not_partitioned(self):
        p = fixture()
        for row in p:
            if (row['group'], row['task'], row['context']) == ('0', 'push-v3', 'UNCHANGED'):
                if row['program'] in ('PI_0125__VALIDATE8', 'PI_0125__MOVE_MEASURE'):
                    row['deadline_loss'] = row['total_steps'] = '90'
        _, result, _, _ = compute(p)
        self.assertEqual(result['groups'][0]['both_strictly_better'], 1)

    def test_all_ties_retained_without_choosing_a_winner(self):
        p = fixture()
        for row in p:
            if (row['group'], row['task'], row['context']) == ('0', 'push-v3', 'UNCHANGED') and row['program'].split('__')[0] in c.TAGS:
                row['deadline_loss'] = row['total_steps'] = '200'
        _, result, _, _ = compute(p)
        u = next(x for x in result['units'] if (x['group'], x['task'], x['context']) == (0, 'push-v3', 'UNCHANGED'))
        self.assertEqual(len(u['minimizing_programs']), 12)
        self.assertEqual(u['acquisition_opportunity'], 0)

    def test_early_success_keeps_zero_opportunity(self):
        p = fixture()
        for row in p:
            if (row['group'], row['task'], row['context']) == ('0', 'push-v3', 'UNCHANGED') and '__' in row['program']:
                row.update(deadline_loss='10', total_steps='10', boundary_applied='False')
        _, result, _, _ = compute(p)
        u = next(x for x in result['units'] if (x['group'], x['task'], x['context']) == (0, 'push-v3', 'UNCHANGED'))
        self.assertTrue(u['before_boundary_success'])
        self.assertEqual(set(u['total_by_T'].values()), {0})

    def test_inconsistent_early_prefix_is_rejected(self):
        p = fixture()
        for row in p:
            if (row['group'], row['task'], row['context']) == ('0', 'push-v3', 'UNCHANGED') and '__' in row['program']:
                row['boundary_applied'] = 'False'
        with self.assertRaises(ValueError):
            compute(p)

    def test_failure_penalty_does_not_invent_physical_steps(self):
        p = fixture()
        p[0].update(success='False', deadline_loss='500', total_steps='0')
        _, result, _, _ = compute(p)
        self.assertEqual(result['cohort_failures'], dict(NATIVE=1, QUAL=1))
        self.assertEqual(result['all_task_failures'][0]['total_steps'], 0)
        self.assertEqual(result['all_task_failures'][0]['deadline_loss'], 500)

    def test_missing_duplicate_and_unknown_programs_fail_closed(self):
        p = fixture()
        registry, _, _ = tables(p)
        for invalid in (p[:-1], p+[deepcopy(p[0])], [deepcopy(p[0])]+p[:-1]):
            with self.subTest(size=len(invalid)), self.assertRaises(ValueError):
                c.prepare(registry, invalid)
        p[0]['program'] = 'UNKNOWN'
        with self.assertRaises(ValueError):
            c.prepare(registry, p)

    def test_invalid_numbers_and_booleans_are_not_zero(self):
        for field, value in [('deadline_loss', ''), ('deadline_loss', 'NaN'), ('deadline_loss', '10.5'),
                             ('total_steps', '-1'), ('total_steps', '501'), ('success', 'missing')]:
            p = fixture()
            registry, _, _ = tables(p)
            p[0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises((ValueError, KeyError)):
                c.prepare(registry, p)

    def test_unresolved_allocation_is_not_a_task_failure(self):
        p = fixture()
        registry, _, _ = tables(p)
        registry[0]['status'] = 'UNRESOLVED'
        with self.assertRaises(ValueError):
            c.prepare(registry, p)

    def test_original_allocation_disagreement_is_detected(self):
        p = fixture()
        registry, _, _ = tables(p)
        p[0]['deadline_loss'] = p[0]['total_steps'] = '150'
        with self.assertRaises(ValueError):
            c.prepare(registry, p)

    def test_independent_audit_with_production_functions_disabled(self):
        p = fixture()
        registry, result, original, cells = compute(p)
        def deny(*args, **kwargs):
            raise RuntimeError('production function disabled')
        with mock.patch.multiple(c, prepare=deny, census=deny, summary=deny, metrics=deny, normalize=deny, number=deny,
                                 boolean=deny, row_key=deny, unit_key=deny, require=deny):
            proof = a.verify(registry, p, result, original, cells)
        self.assertEqual(proof['integrity'], 'PASSED_INDEPENDENT_CSV_SCALAR_FRACTION_AUDIT')

    def test_audit_detects_dropped_cells_future_claim_and_changed_minimum(self):
        p = fixture()
        registry, result, original, cells = compute(p)
        cases = []
        changed = deepcopy(result);changed['units'][0]['R'] += 1;cases.append(changed)
        changed = deepcopy(result);changed['cells'].pop();cases.append(changed)
        changed = deepcopy(result);changed['deployable_selector'] = True;cases.append(changed)
        for wrong in cases:
            with self.assertRaises(ValueError):
                a.verify(registry, p, wrong, original, cells)

    def test_group_equal_weighting_not_time_or_row_weighting(self):
        _, result, _, _ = compute(fixture())
        u = deepcopy(result['units'][0]);u['group'] = 0;u['C'] = 100
        v = deepcopy(result['units'][0]);v['group'] = 1;v['C'] = 200
        answer = c.summary([u, deepcopy(u), deepcopy(u), v])
        self.assertEqual(Fraction(answer['equal_group_mean_exact']['C']), 150)

    def test_empty_stratum_is_not_filled_with_zero(self):
        with self.assertRaises(ValueError):
            c.summary([])

    def test_record_only_guard_blocks_science_network_and_source_writes(self):
        from run_opportunity_v1 import record_only
        import socket
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / 'allowed'
            destination.mkdir()
            with record_only(destination) as counts:
                with self.assertRaises(RuntimeError):
                    __import__('mujoco')
                with self.assertRaises(RuntimeError):
                    socket.create_connection(('127.0.0.1', 9))
                with self.assertRaises(RuntimeError):
                    (Path(folder) / 'outside.txt').write_text('blocked', encoding='utf-8')
                (destination / 'allowed.txt').write_text('allowed', encoding='utf-8')
            self.assertEqual(counts, dict(scientific_import_attempts=1, network_or_process_attempts=1, outside_output_write_attempts=1))
            self.assertFalse((Path(folder) / 'outside.txt').exists())

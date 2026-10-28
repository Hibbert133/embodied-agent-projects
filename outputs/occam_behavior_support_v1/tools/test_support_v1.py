"""Finite-tree and constructed records only; zero physics, fits or policy calls."""
from copy import deepcopy
from fractions import Fraction as F
from itertools import product
import unittest
import support_core_v1 as c
import support_audit_v1 as a
from unittest.mock import patch


def fixture(indices=(0, 1), short=False):
    spec = dict(cohort='TRAIN', group=0, task='push-v3', seed=172100,
                context='UNCHANGED', planned_boundary=16, acquisition_action='CONTINUE', behavior='RANDOM_WINDOW')
    end = 16 + 16 * len(indices) - int(short and bool(indices)) * 7
    value = dict(schema='OCCAM_PUBLIC_TRAIN_TRAJECTORY_V1', task=spec['task'], initial={}, history=[{}] * end, windows=[])
    for j, a in enumerate(indices):
        n, k = 16 + 16 * j, 9 if short and j == len(indices) - 1 else 16
        value['windows'].append(dict(selected_rate=c.RATES[a],
            query=dict(task='push-v3', completed_steps=n, evaluation_steps=16, candidate_time_constant_s=c.RATES[0], history=[{}] * n),
            measurement=dict(start_at=n, end_at=n+k, planned_steps=16, actual_steps=k,
                             full_window=k == 16, terminal=j == len(indices)-1)))
    panel = dict(performance_windows=len(indices))
    compact = dict(performance_windows=len(indices), total_steps=end, success=True, deadline_loss=end, boundary_applied=bool(indices))
    schedule = list(indices) + [0] * (31 - len(indices))
    return spec, panel, compact, value, schedule


class SupportTests(unittest.TestCase):
    def test_all_finite_trees_normalize(self):
        for k in range(1, 7):
            sequences = list(product(range(4), repeat=k))
            for profile in c.PROFILES:
                self.assertEqual(sum((c.action_mass(profile, a) for a in sequences), F()), 1)

    def test_conditional_products_equal_joint(self):
        for sequence in product(range(4), repeat=5):
            for profile in c.PROFILES:
                if c.action_mass(profile, sequence) == 0:
                    continue
                value = F(1)
                for j, a in enumerate(sequence):
                    p = c.next_probabilities(profile, list(sequence[:j]))
                    self.assertEqual(sum(p), 1)
                    value *= p[a]
                self.assertEqual(value, c.action_mass(profile, sequence))

    def test_block_zero_support(self):
        self.assertEqual(c.action_mass('BLOCK_FIXED', [0, 1]), 0)
        with self.assertRaises(ValueError): c.next_probabilities('BLOCK_FIXED', [0, 1])

    def test_uniform_weight_counterexamples(self):
        self.assertEqual(c.action_mass('EQUAL_HIDDEN_MIXTURE', [0, 0]), F(5, 32))
        self.assertEqual(c.action_mass('EQUAL_HIDDEN_MIXTURE', [0, 1]), F(1, 32))
        self.assertEqual(c.action_mass('RANDOM_WINDOW', [0, 1]), F(1, 16))

    def test_mixture_not_redrawn_each_step(self):
        p = c.next_probabilities('EQUAL_HIDDEN_MIXTURE', [0, 0])
        self.assertEqual(p[0], F(17, 20))
        self.assertEqual(p[1], F(1, 20))

    def test_future_suffix_cannot_affect_prefix(self):
        for suffix in product(range(4), repeat=4):
            seq = [2, 2] + list(suffix)
            self.assertEqual(c.next_probabilities('EQUAL_HIDDEN_MIXTURE', seq[:2]), [F(1,20), F(1,20), F(17,20), F(1,20)])

    def test_after_switch_mixture_is_random(self):
        self.assertEqual(c.next_probabilities('EQUAL_HIDDEN_MIXTURE', [3, 3, 1]), [F(1,4)] * 4)

    def test_empty_product_not_available_weight(self):
        for profile in c.PROFILES: self.assertEqual(c.action_mass(profile, []), 1)
        row, steps = c.describe_windows(*fixture(()))
        self.assertEqual(steps, []); self.assertIsNone(row['hidden_mixture_inverse_action_factor'])
        self.assertEqual(row['missing_reason'], 'EARLY_END_BEFORE_INTERVENTION')

    def test_no_window_after_acquisition_remains_explicit(self):
        args = list(fixture(())); args[2]['boundary_applied'] = True
        row, _ = c.describe_windows(*args)
        self.assertEqual(row['missing_reason'], 'NO_TASK_WINDOW_AFTER_ACQUISITION')

    def test_single_window_and_terminal_short(self):
        row, steps = c.describe_windows(*fixture((3,), short=True))
        self.assertIsNone(row['change_fraction']); self.assertEqual(row['short_windows'], 1)
        self.assertEqual(steps[0]['actual_steps'], 9)

    def test_schedule_mapping_mismatch_rejected(self):
        args = list(fixture()); args[-1][0] = 2
        with self.assertRaises(ValueError): c.describe_windows(*args)

    def test_future_history_rejected(self):
        args = list(fixture()); args[3]['windows'][0]['query']['history'].append({})
        with self.assertRaises(ValueError): c.describe_windows(*args)

    def test_short_nonterminal_rejected(self):
        args = list(fixture((0,), short=True)); args[3]['windows'][0]['measurement']['terminal'] = False
        with self.assertRaises(ValueError): c.describe_windows(*args)

    def test_unknown_projection_field_rejected(self):
        args = list(fixture()); args[3]['future_private'] = 1
        with self.assertRaises(ValueError): c.describe_windows(*args)

    def test_illegal_bool_and_length_rejected(self):
        for sequence in ([True], [4], [-1], [0] * 32):
            with self.assertRaises(ValueError): c.action_mass('RANDOM_WINDOW', sequence)

    def test_zero_length_groups_have_null_mean(self):
        row, _ = c.describe_windows(*fixture(()))
        s = c.summarize([row]); self.assertEqual(s['counts']['allocated'], 1)
        self.assertIsNone(s['equal_group_macro']['change_fraction']['mean'])

    def test_equal_trajectory_then_group_weight(self):
        a, _ = c.describe_windows(*fixture((0, 1, 2)))
        b = deepcopy(a); b['change_fraction'] = 0; b['spec']['group'] = 1
        d = deepcopy(a); d['change_fraction'] = 0
        s = c.summarize([a, d, b])
        self.assertEqual(s['equal_group_macro']['change_fraction']['mean'], .25)

    def test_exact_large_fraction_is_lossless_text(self):
        r = c.action_mass('EQUAL_HIDDEN_MIXTURE', [0,1] + [0] * 29)
        self.assertEqual(c.inverse(r), dict(numerator=str(2 * 4 ** 31), denominator='1'))

    def test_independent_reader_with_main_arithmetic_disabled(self):
        args = fixture((0, 0, 1), short=True)
        row, steps = c.describe_windows(*args); summary = c.summarize([row])
        def denied(*args, **kwargs): raise AssertionError('main arithmetic used')
        with patch.multiple(c, action_mass=denied, next_probabilities=denied, describe_windows=denied, summarize=denied):
            self.assertEqual(a.verify_trajectory(args[0], args[2], args[3], row, steps)['windows'], 3)
            self.assertEqual(a.verify_summary([row], summary)['allocated'], 1)

    def test_independent_reader_detects_future_and_wrong_probability(self):
        args = fixture((0, 0)); row, steps = c.describe_windows(*args)
        wrong = deepcopy(steps); wrong[0]['prior_actions'] = [0]
        with self.assertRaises(ValueError): a.verify_trajectory(args[0], args[2], args[3], row, wrong)
        wrong = deepcopy(steps); wrong[1]['hidden_mixture_conditional_action_factor'] = c.ratio(F(1,4))
        with self.assertRaises(ValueError): a.verify_trajectory(args[0], args[2], args[3], row, wrong)

    def test_duplicate_json_field_rejected(self):
        import run_support_v1 as runner
        with self.assertRaises(ValueError): runner.loads('{"a":1,"a":2}')

    def test_guard_denies_undeclared_qualification_read(self):
        import run_support_v1 as runner
        guard = runner.Guard([]); guard.enabled = True
        with self.assertRaises(RuntimeError):
            guard('open', (str(runner.ROOT/'outputs/not_an_allowed_qualification/case.json'), 'r', 0))
        self.assertEqual(guard.counts['blocked_file_reads'], 1)

    def test_guard_denies_network_process_and_old_writes(self):
        import run_support_v1 as runner
        guard = runner.Guard([]); guard.enabled = True
        for event in ('socket.connect', 'subprocess.Popen'):
            with self.assertRaises(RuntimeError): guard(event, ())
        with self.assertRaises(RuntimeError): guard('open', (str(runner.TRAIN/'train/summary.json'), 'w', 0))
        self.assertEqual(guard.counts['process_or_network_attempts'], 2)
        self.assertEqual(guard.counts['blocked_file_writes'], 1)

    def test_saved_denominator_mismatch_rejected(self):
        args = list(fixture()); args[1]['performance_windows'] = 1
        with self.assertRaises(ValueError): c.describe_windows(*args)


if __name__ == '__main__': unittest.main()

"""No simulator, fitted models or original-policy re-evaluation in these checks."""
from copy import deepcopy
import unittest
from src.analysis import passive_continuation_replay_v1 as main
from src.analysis import passive_continuation_independent_v1 as independent
from tests.test_release_learning_v1 import fixture,observation
from dataclasses import asdict
from src.analysis.capsule_record_json_v2 import normalize


def saved(end_at=80):
    r,events,sends,_,_=fixture('VALIDATE_NO_UPDATE',end_at=end_at)
    after={e['payload']['command_sequence']:e['payload']['after'] for e in events if e['kind']=='STEP_RESULT'}
    steps=[{k:s[k] for k in ('at_calls','before','command','raw_policy')}|{'after':after[s['sequence']]} for s in sends]
    return normalize(asdict(observation())),steps,normalize(r)


class PassiveContinuationSupport(unittest.TestCase):
    def test_no_update_validation_and_normal_continuation_have_identical_real_commands(self):
        initial,steps,_=saved()
        raw,s0=main.run('push-v3',16,initial,steps,'RAW')
        validated,s1=main.run('push-v3',16,initial,steps,'VALIDATE_NO_UPDATE')
        self.assertEqual(s0.executed_commands,s1.executed_commands)
        self.assertEqual(raw['outcome']['final_memory'],validated['outcome']['final_memory'])
        self.assertEqual(raw['outcome']['total_steps'],80);self.assertEqual(validated['outcome']['total_steps'],80)
        self.assertEqual(raw['outcome']['warm_probe_steps'],0);self.assertEqual(validated['outcome']['warm_probe_steps'],8)

    def test_independent_arithmetic_recovers_entire_memory_and_window(self):
        initial,steps,r=saved();v=independent.reference(initial,steps,'push-v3',16)
        self.assertEqual(v['final_memory'],r['outcome']['final_memory']);self.assertEqual(v['available_validation_steps'],8)
        self.assertEqual(v['after_memory'],r['outcome']['learning']['saved_return']['record']['post_memory'])

    def test_full_and_masked_fixed_receiver_do_not_change_physics(self):
        initial,steps,_=saved()
        one,s1=main.run('push-v3',16,initial,steps,'TAIL_VALIDATE8_1')
        two,s2=main.run('push-v3',16,initial,steps,'VALIDATE_NO_UPDATE')
        self.assertEqual(s1.executed_commands,s2.executed_commands);self.assertEqual(one['outcome']['final_memory'],two['outcome']['final_memory'])

    def test_divergent_gain_never_consumes_the_next_recorded_outcome(self):
        initial,steps,_=saved()
        with self.assertRaises(main.Divergence) as caught:main.run('push-v3',16,initial,steps,'TAIL_VALIDATE8_0')
        self.assertEqual(caught.exception.step,24);self.assertEqual(caught.exception.outcomes_read,24)

    def test_early_end_before_boundary_has_no_validation(self):
        initial,steps,_=saved(10);r,s=main.run('push-v3',16,initial,steps,'VALIDATE_NO_UPDATE')
        v=independent.reference(initial,steps,'push-v3',16)
        self.assertIsNone(r['outcome']['learning']);self.assertEqual(s.cursor,10)
        self.assertEqual(v['available_validation_steps'],0);self.assertIsNotNone(v['missing_reason'])

    def test_early_end_within_window_keeps_partial_actual_history(self):
        initial,steps,_=saved(18);r,s=main.run('push-v3',16,initial,steps,'VALIDATE_NO_UPDATE')
        v=independent.reference(initial,steps,'push-v3',16)
        self.assertEqual(r['outcome']['warm_probe_steps'],2);self.assertEqual(v['available_validation_steps'],2)
        self.assertEqual(v['missing_reason'],'SHORT_WINDOW_EARLY_END');self.assertEqual(s.outcomes_read,18)

    def test_end_exactly_at_boundary_is_not_an_available_window(self):
        initial,steps,_=saved(16);v=independent.reference(initial,steps,'push-v3',16)
        self.assertIsNone(v['after_memory']);self.assertEqual(v['available_validation_steps'],0)

    def test_extra_private_or_future_fields_are_rejected(self):
        initial,steps,_=saved();steps[0]['future_loss']=1
        with self.assertRaises(ValueError):main.SavedFeedback(initial,steps)

    def test_reordered_history_is_rejected(self):
        initial,steps,_=saved();steps[1],steps[2]=steps[2],steps[1]
        with self.assertRaises(ValueError):main.SavedFeedback(initial,steps)

    def test_stale_policy_query_is_rejected_without_outcome_access(self):
        initial,steps,_=saved();s=main.SavedFeedback(initial,steps);wrong=deepcopy(initial['observation']);wrong[0]+=1
        with self.assertRaises(ValueError):s.policy(wrong)
        self.assertEqual(s.outcomes_read,0)

    def test_source_corruption_detected_by_independent_formula(self):
        initial,steps,_=saved();steps[0]['command'][0]=0.
        with self.assertRaises(ValueError):independent.reference(initial,steps,'push-v3',16)

    def test_divergence_does_not_inspect_corrupted_future_outcome(self):
        initial,steps,_=saved();steps[24]['after']['observation']=['not_disclosed']*39
        with self.assertRaises(main.Divergence) as caught:main.run('push-v3',16,initial,steps,'TAIL_VALIDATE8_0')
        self.assertEqual(caught.exception.outcomes_read,24)

    def test_frozen_config_has_exact_json_roundtrip(self):
        import json
        from src.analysis.passive_continuation_support_v1 import config
        self.assertEqual(config(),json.loads(json.dumps(config())))


if __name__=='__main__':unittest.main()

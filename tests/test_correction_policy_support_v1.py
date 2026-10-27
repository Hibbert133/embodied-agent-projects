"""Array feedback fixtures only: no world creation, reset, advance or API."""
from copy import deepcopy
from dataclasses import asdict
import unittest
import numpy as np
from src.analysis import correction_policy_support_v1 as main
from src.analysis import correction_policy_support_independent_v1 as independent
from src.analysis.capsule_record_json_v2 import normalize
from src.probe import correction_scope_program_v1 as legacy
from src.probe.continuous import StepObservation
from src.probe.physical_reprobe_v1 import StepReceipt


def initial():
    o=[0.]*39;o[:3]=[.1,.8,.25];o[4:7]=[.5,.1,.05]
    return dict(observation=o,success=False,terminated=False,truncated=False)


class Fixed:
    def __init__(self,value=(.25,-.125,.2,-1.)):self.value=value
    def get_action(self,observation):return np.asarray(self.value,np.float32)


def fixture(action='CONTINUE',rate=.125,end=40,*,deadline=False,saturated=False):
    first=initial();current=deepcopy(first);steps=[];sequence=0;policy=Fixed((2.5,-2.5,.2,-1.)) if saturated else Fixed()
    def emit(kind,payload):
        nonlocal sequence
        ack=dict(normalize(payload),sequence=sequence,saved_ns=sequence+1);sequence+=1;return ack
    def step(saved):
        nonlocal current
        o=list(current['observation']);o[:3]=[o[i]+.005*saved['command'][i] for i in range(3)]
        current=dict(observation=o,success=len(steps)+1>=end and not deadline,terminated=False,truncated=False)
        steps.append(dict(command=deepcopy(saved['command']),after=deepcopy(current)));return StepReceipt(StepObservation(**current),len(steps))
    legacy.run('push-v3',StepObservation(**first),16,action,rate,policy.get_action,step,emit,bank=None)
    return first,steps,policy


class PoisonAfter(dict):
    def __getitem__(self,key):
        if key=='after':raise AssertionError('future response accessed before command agreement')
        return super().__getitem__(key)


def request(current,command,at=0):return dict(at_calls=at,before=current,command=command)


class SupportTests(unittest.TestCase):
    def test_first_difference_does_not_read_its_response(self):
        first=initial();reader=main.CausalReader(first,[PoisonAfter(command=[.5,0.,0.,0.])])
        with self.assertRaises(main.DifferentCommand):reader.consume(request(first,[.25,0.,0.,0.]))
        self.assertEqual((reader.responses,reader.matched,reader.examined),(0,0,1))
        with self.assertRaises(ValueError):reader.consume(request(first,[.5,0.,0.,0.]))

    def test_float32_single_bit_difference_is_unknown(self):
        first=initial();small=float(np.nextafter(np.float32(0),np.float32(1)))
        reader=main.CausalReader(first,[PoisonAfter(command=[small,0.,0.,0.])])
        with self.assertRaises(main.DifferentCommand):reader.consume(request(first,[0.,0.,0.,0.]))
        self.assertNotEqual(main.bounded_bits([0.,0.,0.,0.]),main.bounded_bits([small,0.,0.,0.]))

    def test_bad_command_is_error_not_unknown(self):
        for command in ([float('nan'),0,0,0],[2,0,0,0],[0,0,0]):
            reader=main.CausalReader(initial(),[PoisonAfter(command=[0.,0.,0.,0.])])
            with self.subTest(command=command),self.assertRaises(ValueError):reader.consume(request(initial(),command))

    def test_private_initial_field_rejected(self):
        bad=dict(initial(),seed=90000)
        with self.assertRaises(ValueError):main.CausalReader(bad,[])

    def test_actual_success_before_boundary_has_no_late_query(self):
        first,steps,policy=fixture(end=10)
        for entry in (main.replay,independent.replay):
            answer=entry(first,steps,'push-v3',16,'MOVE_MEASURE',8.,policy=policy)
            self.assertEqual(answer['status'],'SUPPORTED_FACTUAL_OUTCOME');self.assertEqual(answer['supported_loss'],10)
            self.assertEqual(answer['replay_fixed_policy_queries'],10)

    def test_actual_deadline_stays_loss500(self):
        first,steps,policy=fixture(end=500,deadline=True)
        answer=main.replay(first,steps,'push-v3',16,'CONTINUE',.125,policy=policy)
        self.assertEqual(answer['matched_prefix_steps'],500);self.assertEqual(answer['supported_loss'],500);self.assertFalse(answer['supported_success'])

    def test_own_memory_matches_complete_factual_static_program(self):
        first,steps,policy=fixture()
        for entry in (main.replay,independent.replay):
            answer=entry(first,steps,'push-v3',16,'CONTINUE',.125,policy=policy)
            self.assertEqual(answer['supported_loss'],40);self.assertEqual(answer['source_responses_consumed'],40)

    def test_different_rate_stops_before_any_different_response(self):
        first,steps,policy=fixture()
        answers=[entry(first,steps,'push-v3',16,'CONTINUE',8.,policy=policy) for entry in (main.replay,independent.replay)]
        for a in answers:
            self.assertEqual(a['status'],'UNKNOWN_AFTER_COMMAND_DIFFERENCE');self.assertEqual(a['matched_prefix_steps'],16)
            self.assertEqual(a['source_responses_consumed'],16);self.assertIsNone(a['supported_loss'])
        self.assertEqual(answers[0]['first_difference'],answers[1]['first_difference'])

    def test_same_acquisition_label_not_sufficient_for_supported_outcome(self):
        first,steps,policy=fixture('VALIDATE8',.125)
        answer=main.replay(first,steps,'push-v3',16,'VALIDATE8',8.,policy=policy)
        self.assertEqual(answer['matched_prefix_steps'],24);self.assertIsNone(answer['supported_success'])

    def test_matching_MOVE_macro_preserves_task_integral_and_returns_to_tail(self):
        first,steps,policy=fixture('MOVE_MEASURE',.5,end=170)
        for entry in (main.replay,independent.replay):
            answer=entry(first,steps,'push-v3',16,'MOVE_MEASURE',.5,policy=policy)
            self.assertEqual(answer['status'],'SUPPORTED_FACTUAL_OUTCOME');self.assertEqual(answer['matched_prefix_steps'],170)
            self.assertLess(answer['replay_fixed_policy_queries'],170)

    def test_different_rate_labels_can_be_identical_after_clipping(self):
        first,steps,policy=fixture(rate=.125,saturated=True)
        for entry in (main.replay,independent.replay):
            answer=entry(first,steps,'push-v3',16,'CONTINUE',8.,policy=policy)
            self.assertEqual(answer['status'],'SUPPORTED_FACTUAL_OUTCOME');self.assertEqual(answer['supported_loss'],40)

    def test_both_readers_detect_future_or_changed_current_state(self):
        reader=main.CausalReader(initial(),[dict(command=[0.,0.,0.,0.],after=initial())]);bad=initial();bad['observation'][0]+=.01
        with self.assertRaises(ValueError):reader.consume(request(bad,[0.,0.,0.,0.]))

    def test_source_exhaustion_nonterminal_is_not_factual_support(self):
        with self.assertRaises(ValueError):main.CausalReader(initial(),[]).summary()

    def test_empty_already_terminal_is_vacuous_and_not_adaptation(self):
        first=dict(initial(),success=True)
        answer=main.replay(first,[],'push-v3',16,'CONTINUE',.125,policy=Fixed())
        self.assertEqual(answer['supported_loss'],0);self.assertEqual(answer['replay_fixed_policy_queries'],0)

    def test_unknown_bound_uses_longest_prefix_and_keeps500_upper(self):
        first=initial();trace=[dict(command=[0.,0.,0.,0.],after=first) for _ in range(3)]
        programs=main.native.PROGRAMS;attempts=[dict(source_program=p,status='UNKNOWN_AFTER_COMMAND_DIFFERENCE',matched_prefix_steps=n) for p,n in zip(programs,(1,3,2))]
        bound=main.one_bound(attempts,{p:(first,trace) for p in programs})
        self.assertEqual((bound['lower'],bound['upper']),(4,500));self.assertIsNone(bound['success'])

    def test_inconsistent_factual_prefixes_rejected(self):
        first=initial();other=initial();other['observation'][0]+=.01;programs=main.native.PROGRAMS
        attempts=[dict(source_program=p,status='UNKNOWN_AFTER_COMMAND_DIFFERENCE',matched_prefix_steps=1) for p in programs]
        traces={p:(first,[dict(command=[0.,0.,0.,0.],after=first if i else other)]) for i,p in enumerate(programs)}
        with self.assertRaises(ValueError):main.one_bound(attempts,traces)

    def test_complete_conflicting_losses_rejected(self):
        first=initial();programs=main.native.PROGRAMS
        attempts=[dict(source_program=p,status='SUPPORTED_FACTUAL_OUTCOME',matched_prefix_steps=0,supported_loss=i,supported_success=True) for i,p in enumerate(programs)]
        with self.assertRaises(ValueError):main.one_bound(attempts,{p:(first,[]) for p in programs})

    def test_missing_or_extra_source_program_rejected(self):
        programs=main.native.PROGRAMS;attempts=[dict(source_program=p,status='UNKNOWN_AFTER_COMMAND_DIFFERENCE',matched_prefix_steps=0) for p in programs]
        for bad in (attempts[:2],[*attempts[:2],dict(attempts[2],source_program='OTHER')]):
            with self.assertRaises(ValueError):main.one_bound(bad,{p:(initial(),[]) for p in programs})

    def test_independent_byte_rule_matches_known_float32_values(self):
        for u in ([0.,-0.,1.,-1.],[.25,-.125,.2,-1.]):self.assertEqual(main.bounded_bits(u),independent.bits(u))

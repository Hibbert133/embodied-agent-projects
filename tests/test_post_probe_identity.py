import copy
from collections import deque
from contextlib import contextmanager
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import run_post_probe_identity as run
from scripts import analyze_post_probe_identity as audit
from src.probe.lifecycle_ledger import LifecycleLedger
from src.probe.operator_identification import identity_controller
from src.analysis.post_probe_identity import statistics
from tests.test_acquisition_value import FakeEnv, FakeSimulator, FixedPolicy, model


class PostProbeIdentityTest(unittest.TestCase):
    def setUp(self):
        self.events=[]
        def emit(kind,payload):
            value={"event":kind,"sequence":len(self.events)+1,"saved_ns":run.perf_counter_ns(),**run.normal(payload)}
            self.events.append(value);return value
        self.emit=emit;self.ledger=LifecycleLedger(emit,1000000);self.factory=SimpleNamespace(_make_tasks=lambda:None)
        self.key={"experiment_run_id":"unit","manifest_id":"unit","source_git_commit":"unit","stream":0,
                  "task":"push-v3","replicate":0,"seed":13000,"operator_id_oracle":"A"}
        self.operator={"matrix_xy":[[.8,.1],[0,1.1]],"bias_xy":[.1,-.08]}

    @contextmanager
    def fixtures(self):
        witness=lambda env:{"fixture":True,"time":env.data.time,"observation":env.observation.tolist()}
        with self.ledger.instrument(FakeEnv,FakeSimulator,self.factory),patch.object(run,"create_task_environment",side_effect=lambda *a:FakeEnv()),patch.object(run,"create_task_policy",return_value=FixedPolicy()),patch.object(run,"physics_witness",side_effect=witness):yield

    def branch(self,method,future=0):
        return run.normal(run.execute({**self.key,"method":method,"replicate":future},self.operator,model(),.0001,self.emit,self.ledger))

    def replay(self,record):
        events=deque(e for e in self.events if not e['event'].startswith('LIFECYCLE'))
        audit.verify_record(record,model(),.0001,self.operator,events,.01)
        self.assertFalse(events)

    def test_all_ten_saved_programs_replay_and_keep_one_reset(self):
        with self.fixtures():
            for method in run.METHODS:
                self.events.clear();r=self.branch(method);self.replay(r)
                self.assertEqual(r['outcome']['environment_resets'],1)
                self.assertEqual(r['outcome']['noise_rows_consumed'],r['outcome']['total_steps'])
                if method.startswith('IDENTITY_'):
                    decision=next(d for d in r['decisions'] if d['action']=='RUN_IDENTITY_CONTINUATION')
                    self.assertEqual(decision['controller'],identity_controller())
                    boundary=8 if method=='IDENTITY_AFTER8' else 16
                    self.assertEqual(decision['at_host_calls'],boundary)
                    for row in r['trace'][boundary:]:self.assertEqual(row['command'],run.command(identity_controller(),row['raw_policy']).tolist())

    def test_three_causal_pairs_match_only_the_declared_live_prefix(self):
        with self.fixtures():
            for method,base,boundary in run.MATCHED_PAIRS:
                left,right=self.branch(method),self.branch(base)
                self.assertEqual(run.prefix_match(left,right,boundary),f'MATCHED_ACTIVE_PREFIX_{boundary}')
                altered=copy.deepcopy(left);altered['trace'][boundary-1]['noise_after_hash']='changed'
                with self.assertRaises(ValueError):run.prefix_match(altered,right,boundary)
        self.assertNotIn('POINT16_WIDE',run.PORTFOLIO);self.assertNotIn('NO_PROBE',run.PORTFOLIO)

    def test_no_probe_result_cannot_be_used_as_post_probe_identity(self):
        with self.fixtures():
            raw=self.branch('NO_PROBE');after=self.branch('IDENTITY_AFTER8')
        with self.assertRaises(ValueError):run.prefix_match(raw,after)
        self.assertEqual(raw['outcome']['fixed_probe_steps'],0)
        self.assertEqual(after['outcome']['fixed_probe_steps'],8)

    def test_identity_probe_controls_do_not_consult_the_nominal_model(self):
        with self.fixtures(),patch.object(run.GaussianReference,'from_visible',side_effect=AssertionError('unexpected fit')),patch.object(run,'infer_operator',side_effect=AssertionError('unexpected fit')):
            for method in ('IDENTITY_AFTER8','IDENTITY_AFTER16_CYCLE'):
                r=self.branch(method);self.assertTrue(any(d['action']=='RUN_IDENTITY_CONTINUATION' for d in r['decisions']))

    def test_controller_substitution_after_saved_identity_is_rejected(self):
        with self.fixtures():
            r=self.branch('IDENTITY_AFTER16_PASSIVE')
            d=next(x for x in r['decisions'] if x['action']=='RUN_IDENTITY_CONTINUATION')
            d['controller']={'kind':'OTHER'}
            next(e for e in self.events if e['sequence']==d['sequence'])['controller']=copy.deepcopy(d['controller'])
            with self.assertRaises(ValueError):self.replay(r)

    def test_passive_fit_failure_stops_instead_of_substituting_identity(self):
        with self.fixtures(),patch.object(run.GaussianReference,'from_visible',side_effect=ValueError('no finite point')):
            r=self.branch('IDENTITY_AFTER16_PASSIVE')
        self.assertTrue(r['outcome']['stopped']);self.assertFalse(r['outcome']['success'])
        self.assertEqual(r['outcome']['total_steps'],8);self.assertEqual(r['outcome']['deadline_loss'],500)
        self.assertFalse(any(d['action']=='RUN_IDENTITY_CONTINUATION' for d in r['decisions']))

    def test_fresh_registration_does_not_change_historical_seed_reservations(self):
        c=json.loads(run.CONFIG.read_text(encoding='utf-8'));run.validate(c)
        self.assertEqual(run.task_seed(0,'push-v3'),13000);self.assertEqual(run.task_seed(15,'door-open-v3'),13047)
        self.assertEqual(len(run.operators(c)),16);self.assertEqual(c['reserved_seeds'],[13048,13399])
        for changes in ({'seed_start':12600},{'methods':list(run.METHODS)[:-1]},{'api_calls':1}):
            with self.assertRaises(ValueError):run.validate({**c,**changes})

    def test_statistics_preserve_stops_and_distinguish_nominal_source_requirements(self):
        c=json.loads(run.CONFIG.read_text(encoding='utf-8'));rows=[];pairs=[];repeated=[]
        for s in range(16):
            for task in run.TASKS:
                for f in range(2):
                    for method in run.METHODS:
                        rows.append(dict(stream=s,task=task,replicate=f,method=method,success=True,stopped=False,total_steps=50,deadline_loss=50,fixed_probe_steps=8,policy_measure_steps=0))
                    for method in run.PORTFOLIO:pairs.append(dict(stream=s,task=task,replicate=f,method=method,reference='DIRECT_G8',boundary=8,reason='MATCHED_ACTIVE_PREFIX_8'))
                    for method,base,boundary in run.MATCHED_PAIRS[1:]:pairs.append(dict(stream=s,task=task,replicate=f,method=method,reference=base,boundary=boundary,reason='MATCHED_ACTIVE_PREFIX_16'))
                for method in run.METHODS:repeated.append(dict(stream=s,task=task,replicate=1,method=method,reason='MATCHED_ACTIVE_PREFIX_8'))
        stopped=next(r for r in rows if r['method']=='IDENTITY_AFTER8')
        stopped.update(success=False,stopped=True,total_steps=10,deadline_loss=500)
        result=statistics({'config':c},rows,pairs,repeated,run.METHODS,run.TASKS)
        self.assertEqual(result['methods']['IDENTITY_AFTER8']['cases'],96)
        self.assertEqual(result['methods']['IDENTITY_AFTER8']['successes'],95)
        self.assertEqual(result['methods']['IDENTITY_AFTER8']['nominal_offline_steps'],0)
        self.assertEqual(result['methods']['IDENTITY_AFTER16_PASSIVE']['nominal_offline_steps'],21010)
        self.assertAlmostEqual(result['registered_contrasts'][0]['statistics']['deadline_loss']['difference'],450/96)
        with self.assertRaises(ValueError):statistics({'config':c},rows[:-1],pairs,repeated,run.METHODS,run.TASKS)


if __name__=='__main__':unittest.main()

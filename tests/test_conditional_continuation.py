import copy
from collections import deque
from contextlib import contextmanager
import hashlib
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np
from scripts import run_conditional_continuation as run
from scripts import analyze_conditional_continuation as audit
from src.probe.conditional_noise import ConditionalNoiseTape, apply_affine_tape
from src.probe.conditional_continuation import OfflineTrainingLosses, choose_training
from src.probe.lifecycle_ledger import LifecycleLedger
from tests.test_acquisition_value import FakeEnv, FakeSimulator, FixedPolicy, model


class ConditionalNoiseTest(unittest.TestCase):
    def test_shared_prefix_and_distinct_future_without_reseed_or_restore(self):
        a, b = ConditionalNoiseTape(12200,0,0), ConditionalNoiseTape(12200,0,1)
        self.assertEqual(a.commitment_oracle["prefix_sha256"], b.commitment_oracle["prefix_sha256"])
        self.assertNotEqual(a.commitment_oracle["future_sha256"], b.commitment_oracle["future_sha256"])
        self.assertEqual(a.past_hash(), b.past_hash())
        for _ in range(8): np.testing.assert_array_equal(a.consume(), b.consume())
        self.assertEqual(a.past_hash(), b.past_hash())
        self.assertFalse(np.array_equal(a.consume(),b.consume())); self.assertNotEqual(a.past_hash(), b.past_hash())
        self.assertFalse(a._values.flags.writeable)
        for name in ("reset","reseed","rewind","restore"):
            self.assertFalse(hasattr(a,name))

    def test_independent_namespace_reconstruction_and_exact_consumption_limit(self):
        tape = ConditionalNoiseTape(12203,2,3)
        prefix_seed = int(np.random.SeedSequence([12203,2,46003]).generate_state(1)[0])
        future_seed = int(np.random.SeedSequence([12203,2,46005,4]).generate_state(1)[0])
        expected = np.concatenate((np.random.default_rng(prefix_seed).normal(0,.05,(8,3)),
                                   np.random.default_rng(future_seed).normal(0,.05,(492,3)))).astype("<f4")
        actual = np.asarray([tape.consume() for _ in range(500)])
        np.testing.assert_array_equal(actual,expected)
        self.assertEqual(tape.past_hash(),hashlib.sha256(expected.tobytes()).hexdigest())
        self.assertEqual(tape.cursor,500)
        with self.assertRaises(ValueError): tape.consume()
        for args in ((True,0,0),(12200,3,0),(12200,0,4)):
            with self.assertRaises(ValueError): ConditionalNoiseTape(*args)

    def test_copy_isolation_and_bounded_affine_injection(self):
        tape = ConditionalNoiseTape(12200,0,0)
        expected_noise = tape._values[0].copy(); first = tape.consume(); first[:] = 99
        np.testing.assert_array_equal(tape._values[0], expected_noise)
        tape = ConditionalNoiseTape(12200,0,0); command = np.array([1.,-1.,.7,.3],np.float32)
        expected = command.copy(); expected[:2] = [[1.2,.2],[0,.8]] @ expected[:2] + np.array([.1,-.1])
        expected[:3] += tape._values[0]
        actual = apply_affine_tape(command,[[1.2,.2],[0,.8]],[.1,-.1],tape)
        np.testing.assert_allclose(actual,np.clip(expected,-1,1),atol=1e-7,rtol=0)
        self.assertEqual(tape.cursor,1); self.assertEqual(actual[3],command[3])


class ConditionalExecutionTest(unittest.TestCase):
    def setUp(self):
        self.events=[]
        def emit(kind,payload):
            item={"event":kind,"sequence":len(self.events)+1,"saved_ns":run.perf_counter_ns(),**run.normal(payload)}
            self.events.append(item); return item
        self.emit=emit; self.ledger=LifecycleLedger(emit,1000000); self.factory=SimpleNamespace(_make_tasks=lambda:None)
        self.key={"experiment_run_id":"test","manifest_id":"manifest","source_git_commit":"source","stream":0,
                  "task":"push-v3","replicate":0,"seed":12200,"operator_id_oracle":"A"}
        self.operator={"matrix_xy":[[.8,.1],[0,1.1]],"bias_xy":[.1,-.08]}

    @contextmanager
    def fixtures(self):
        witness=lambda env:{"fixture":True,"time":env.data.time,"observation":env.observation.tolist()}
        with self.ledger.instrument(FakeEnv,FakeSimulator,self.factory), patch.object(run,"create_task_environment",side_effect=lambda *a:FakeEnv()), \
             patch.object(run,"create_task_policy",return_value=FixedPolicy()), patch.object(run,"physics_witness",side_effect=witness):
            yield

    def branch(self,method,future=0):
        return run.normal(run.execute({**self.key,"method":method,"replicate":future},self.operator,model(),.0001,self.emit,self.ledger))

    def replay(self,record):
        business=deque(e for e in self.events if not e["event"].startswith("LIFECYCLE"))
        audit.verify_record(record,model(),.0001,self.operator,business,.01)
        self.assertFalse(business)

    def test_all_seven_methods_replay_saved_controllers_and_continuous_noise(self):
        with self.fixtures():
            for method in run.METHODS:
                self.events.clear(); record=self.branch(method); self.replay(record)
                self.assertEqual(record["outcome"]["environment_resets"],1)
                self.assertEqual(record["outcome"]["noise_rows_consumed"],record["outcome"]["total_steps"])
                self.assertLessEqual(record["outcome"]["fixed_probe_steps"],16)
                if method=="PASSIVE_G16": self.assertEqual(record["outcome"]["policy_measure_steps"],8)

    def test_four_future_prefixes_match_for_all_methods_and_feasible_branches(self):
        records={}
        with self.fixtures():
            for method in run.METHODS:
                for future in range(4): records[(method,future)]=self.branch(method,future)
        for method in run.METHODS:
            for future in range(1,4): self.assertEqual(run.prefix_match(records[(method,future)],records[(method,0)]),"MATCHED_ACTIVE_PREFIX")
        for method in ("DIRECT_G8","KEEP_G8_AFTER16","PASSIVE_G16"):
            controllers=[next(d["controller"] for d in records[(method,r)]["decisions"] if d["action"]=="BUILD_GAUSSIAN" and d["at_host_calls"]==8) for r in range(4)]
            self.assertTrue(all(value==controllers[0] for value in controllers))
        for method in run.PORTFOLIO:
            for future in range(4): self.assertEqual(run.prefix_match(records[(method,future)],records[("DIRECT_G8",future)]),"MATCHED_ACTIVE_PREFIX")
        with self.assertRaises(ValueError): run.prefix_match(records[("POINT16_WIDE",0)],records[("DIRECT_G8",0)])
        self.assertNotEqual(records[("DIRECT_G8",0)]["trace"][8]["noise_after_hash"],records[("DIRECT_G8",1)]["trace"][8]["noise_after_hash"])

    def test_keep_controller_and_future_commitment_substitution_are_rejected(self):
        with self.fixtures():
            record=self.branch("KEEP_G8_AFTER16")
            choice=next(d for d in record["decisions"] if d["action"]=="RUN_KEEP_GAUSSIAN")
            choice["controller"]["mean"][2]+=.1
            event=next(e for e in self.events if e["sequence"]==choice["sequence"]); event["controller"]=copy.deepcopy(choice["controller"])
            with self.assertRaises(ValueError): self.replay(record)
            self.events.clear(); record=self.branch("DIRECT_G8")
            record["noise_commitment_oracle"]["future_sha256"]="altered"
            self.events[0]["noise_commitment_oracle"]=copy.deepcopy(record["noise_commitment_oracle"])
            with self.assertRaises(ValueError): self.replay(record)


class ConditionalLookupTest(unittest.TestCase):
    def test_fresh_population_and_reservations(self):
        c=json.loads(run.CONFIG.read_text(encoding="utf-8")); run.validate(c)
        operators=run.operators(c)
        self.assertEqual(len(operators),8)
        self.assertEqual(len({json.dumps(r["states_oracle"][0],sort_keys=True) for r in operators}),8)
        self.assertEqual(run.task_seed(7,"door-open-v3"),12223)
        with self.assertRaises(ValueError): run.validate({**c,"future_loss":1})

    def test_heldout_poison_cannot_change_strict_training_input_or_choice(self):
        losses=np.array([[100.]*5,[100.]*5,[100.]*5,[100.]*5]); losses[:,3]=80.
        def training(values): return OfflineTrainingLosses(tuple(tuple(values[r,m] for r in (0,1,3)) for m in range(5)))
        before=training(losses); poisoned=losses.copy(); poisoned[2]=500.
        self.assertEqual(before,training(poisoned))
        self.assertEqual(choose_training(before)["selected_branch"],"UPDATE_G16")
        self.assertEqual(choose_training(before),choose_training(training(poisoned)))
        for forbidden in ("heldout_loss","true_operator","seed","future_outcome"):
            with self.assertRaises(TypeError): OfflineTrainingLosses(before.values,**{forbidden:1})
        with self.assertRaises(ValueError): choose_training({"values":before.values})
        with self.assertRaises(ValueError): OfflineTrainingLosses(tuple((1.,2.,3.,4.) for _ in range(5)))

    def test_training_mean_and_low_probe_tie_order(self):
        training=OfflineTrainingLosses(((100.,100.,100.),(120.,120.,120.),(120.,120.,120.),(0.,150.,0.),(120.,120.,120.)))
        self.assertEqual(choose_training(training)["selected_branch"],"UPDATE_G16")
        equal=OfflineTrainingLosses(tuple((100.,100.,100.) for _ in range(5)))
        self.assertEqual(choose_training(equal)["selected_branch"],"DIRECT_G8")

    def population(self,stochastic=False):
        rows=[]; pairs=[]; repetitions=[]
        for s in range(8):
            for t in run.TASKS:
                for r in range(4):
                    for m in run.PORTFOLIO: pairs.append({"stream":s,"task":t,"replicate":r,"method":m,"reason":"MATCHED_ACTIVE_PREFIX"})
                    for m in run.METHODS:
                        length=(20 if r%2==0 else 150) if stochastic and m=="UPDATE_G16" else 80 if m=="UPDATE_G16" else 100 if m=="DIRECT_G8" else 120
                        probe=0 if m=="NO_PROBE" else 8 if m in ("DIRECT_G8","PASSIVE_G16") else 16
                        rows.append({"stream":s,"task":t,"replicate":r,"method":m,"success":True,"stopped":False,
                                     "total_steps":length,"deadline_loss":length,"fixed_probe_steps":probe,
                                     "policy_measure_steps":8 if m=="PASSIVE_G16" else 0,"point_fit_failures":0})
                for m in run.METHODS:
                    for r in range(1,4): repetitions.append({"stream":s,"task":t,"replicate":r,"method":m,"reason":"MATCHED_ACTIVE_PREFIX"})
        return rows,pairs,repetitions

    def test_full_population_lookup_interval_and_no_online_execution_claim(self):
        m={"config":json.loads(run.CONFIG.read_text(encoding="utf-8"))}; run.validate(m["config"])
        rows,pairs,repeated=self.population(); stats=audit.statistics(m,rows,pairs,repeated)
        self.assertEqual(stats["lookup"]["selected_counts"]["UPDATE_G16"],96)
        self.assertEqual(stats["lookup"]["contrast_minus_direct"]["deadline_loss"]["paired_cluster_percentile_95"],[-20.,-20.])
        self.assertEqual(stats["lookup"]["operator_streams"],8)
        self.assertFalse(stats["lookup"]["deployable_agent"]); self.assertFalse(stats["lookup"]["true_optimal_policy_bound"])
        self.assertEqual(stats["lookup"]["new_online_lookup_executions"],0)
        for r in stats["lookup_decisions"]: self.assertNotIn(r["held_out_future"],r["training_futures"])
        with self.assertRaises(ValueError): audit.statistics(m,rows[:-1],pairs,repeated)
        with self.assertRaises(ValueError): audit.statistics(m,rows,pairs,repeated[:-1])

    def test_small_training_lookup_can_fail_even_when_true_conditional_mean_better(self):
        m={"config":json.loads(run.CONFIG.read_text(encoding="utf-8"))}; rows,pairs,repeated=self.population(stochastic=True)
        stats=audit.statistics(m,rows,pairs,repeated)
        self.assertEqual(stats["conditional_contexts"][0]["methods"]["UPDATE_G16"]["mean_loss"],85.)
        self.assertEqual(stats["lookup"]["mean_deadline_loss"],125.)
        self.assertEqual(stats["lookup"]["contrast_minus_direct"]["deadline_loss"]["difference"],25.)


if __name__=="__main__": unittest.main()

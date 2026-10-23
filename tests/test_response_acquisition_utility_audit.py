import copy
import unittest
from scripts.audit_response_acquisition_utility import eligibility,comparison,summarize,aligned_population,unit


class ResponseAcquisitionUtilityAuditTest(unittest.TestCase):
    def pair(self):
        base={"stream":0,"task":"push-v3","scenario":"STATIONARY","episode_in_stream":1,"seed":10801,"operator_id_oracle":"A",
              "cache_before":{"matrix_xy":[[1,0],[0,1]],"bias_xy":[0,0]},"initial":{"success":False},"initial_rng_hash":"initial",
              "cache_version_before":1,"cache_version_after":1}
        def make(method,phase):
            record=copy.deepcopy(base);record["method"]=method
            record["trace"]=[{"host_calls":i,"phase":phase,"command":[0,0,0,1],"raw_policy":[0,0,0,1],
                "before":{"success":False,"terminated":False,"truncated":False},"after":{"success":False,"terminated":False,"truncated":False},
                "rng_before":"rng"+str(i),"rng_after":"rng"+str(i+1)} for i in range(1,7)]
            record["decisions"]=[{"controller":{},"action":"REUSE_CACHE","validation":{"assessment":{"status":"UNRESOLVED"}}}]
            record["outcome"]={"total_steps":6,"prefix_steps":6 if method!="CACHE_ONLY" else 0,"micro_steps":0,"fixed_probe_steps":0,
                "policy_steps":6 if method=="CACHE_ONLY" else 0,"success":False,"environment_resets":1,"actuator_resets":1,
                "stopped":False,"point_fit_failures":0,"cache_updates":0}
            return record
        return make("RESPONSE_SET","PREFIX_POLICY"),make("CACHE_ONLY","POLICY")

    def test_matching_is_exact_and_not_selected_by_future_outcomes(self):
        target,reference=self.pair();self.assertEqual(eligibility(target,reference),"MATCHED")
        target["outcome"]["success"]=True
        self.assertEqual(eligibility(target,reference),"MATCHED")
        target["cache_before"]["bias_xy"][0]=1e-15
        self.assertEqual(eligibility(target,reference),"UNEQUAL_OLD_CACHE")

    def test_prefix_action_observation_rng_and_short_history_are_rejected(self):
        for field,value in (("command",[1,0,0,1]),("before",{"success":True}),("rng_after","restarted")):
            target,reference=self.pair();target["trace"][0][field]=value
            with self.subTest(field=field):self.assertEqual(eligibility(target,reference),"DIFFERENT_PHYSICAL_PREFIX")
        target,reference=self.pair();target["trace"]=target["trace"][:5]
        self.assertEqual(eligibility(target,reference),"SHORT_PREFIX")

    def test_shared_ended_prefix_is_not_an_acquisition_decision(self):
        target,reference=self.pair()
        for record in (target,reference):record["trace"][-1]["after"]["success"]=True
        self.assertEqual(eligibility(target,reference),"ENDED_BY_SHARED_PREFIX")

    def test_missing_cache_foreign_unit_initialization_and_program(self):
        target,reference=self.pair();target["cache_before"]=None
        self.assertEqual(eligibility(target,reference),"NO_OLD_CACHE")
        for field,value in (("seed",999),("method","FIXED16"),("initial_rng_hash","different"),("initial",{"success":True})):
            target,reference=self.pair();target[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):eligibility(target,reference)
        target,reference=self.pair();target["trace"][0]["phase"]="MICRO_PROBE"
        self.assertEqual(eligibility(target,reference),"DIFFERENT_PREFIX_PROGRAM")

    def test_complete_population_alignment_rejects_short_duplicate_or_foreign_data(self):
        target,reference=self.pair();identity={"experiment_run_id":"test","manifest_id":"manifest","source_git_commit":"source"}
        target.update(identity);reference.update(identity);expected={unit(target)}
        self.assertEqual(len(list(aligned_population([target],[reference],"RESPONSE_SET",expected,identity))),1)
        for targets,references in (([target],[]),([],[reference]),([],[]),([target,target],[reference,reference])):
            with self.subTest(lengths=(len(targets),len(references))),self.assertRaises(ValueError):
                list(aligned_population(targets,references,"RESPONSE_SET",expected,identity))
        reference["manifest_id"]="other"
        with self.assertRaises(ValueError):list(aligned_population([target],[reference],"RESPONSE_SET",expected,identity))

    def test_real_pair_comparison_counts_stops_and_remaining_cost(self):
        target,reference=self.pair();row=comparison(target,reference)
        self.assertEqual(row["paired_outcome"],"BOTH_FAILED")
        self.assertEqual(row["target_remaining_steps"],0)
        target["cache_before"]=None
        with self.assertRaises(ValueError):comparison(target,reference)
        summary=summarize([row]);self.assertEqual(summary["cases"],1)
        self.assertEqual(summary["mean_step_difference"],0)
        self.assertIsNone(summarize([])["mean_step_difference"])

    def test_actual_trace_success_and_stopped_branch_remain_in_denominator(self):
        target,reference=self.pair()
        target["trace"][-1]["after"]["success"]=True
        reference["trace"][-1]["after"]["success"]=True
        self.assertEqual(eligibility(target,reference),"ENDED_BY_SHARED_PREFIX")
        target,reference=self.pair()
        end=copy.deepcopy(target["trace"][-1]);end.update(host_calls=7,phase="POLICY")
        end["after"]["success"]=True;target["trace"].append(end)
        target["outcome"].update(total_steps=7,policy_steps=1,success=True)
        helpful=comparison(target,reference)
        self.assertEqual(helpful["paired_outcome"],"HELPFUL")
        self.assertEqual(helpful["target_remaining_steps"],1)
        target,reference=self.pair();target["decisions"][-1]["controller"]=None;target["outcome"]["stopped"]=True
        stopped=comparison(target,reference)
        summary=summarize([helpful,stopped])
        self.assertEqual((summary["cases"],summary["target_successes"],summary["target_stops"]),(2,1,1))
        self.assertEqual(summary["target_total_steps"],13)


if __name__=="__main__":unittest.main()

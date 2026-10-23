import copy
from contextlib import redirect_stdout
import gzip
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import report_action_response as reporter
from scripts.report_action_response import case_metrics,matching_audit,validation_summary,cost_ablation_issue
from scripts.audit_metaworld_setup_cost import infer_counts


class ActionResponseReportTest(unittest.TestCase):
    def record(self):
        return {"trace":[{"host_calls":i,"phase":p,"after":{"success":i==4}} for i,p in
                         enumerate(("PREFIX_POLICY","MICRO_PROBE","FIXED_PROBE","POLICY"),1)],
            "decisions":[{"controller":{},"fit":{"valid":False}},{"controller":{}}],
            "cache_version_before":1,"cache_version_after":2,
            "outcome":{"total_steps":4,"prefix_steps":1,"micro_steps":1,"fixed_probe_steps":1,"policy_steps":1,
                       "success":True,"environment_resets":1,"actuator_resets":1,"stopped":False,"point_fit_failures":1,"cache_updates":1}}

    def test_phase_cost_success_stop_and_fit_are_reconstructed(self):
        result=case_metrics(self.record())
        self.assertEqual(result["total_steps"],4)
        self.assertEqual(result["micro_steps"],1)
        self.assertTrue(result["success"])
        self.assertFalse(result["stopped"])
        self.assertEqual(result["point_fit_failures"],1)

    def test_forged_cost_success_reset_and_chronology_are_rejected(self):
        for field,value in (("total_steps",3),("success",False),("environment_resets",2),("stopped",True)):
            record=self.record();record["outcome"][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):case_metrics(record)
        record=self.record();record["trace"][0]["host_calls"]=2
        with self.assertRaises(ValueError):case_metrics(record)
        record=self.record();record["trace"][0]["phase"]="UNREGISTERED"
        with self.assertRaises(ValueError):case_metrics(record)
        record=self.record();record["trace"]=[{"host_calls":k,"phase":"POLICY"} for k in range(1,502)]
        with self.assertRaises(ValueError):case_metrics(record)

    def test_zero_step_stop_preserves_initial_outcome(self):
        record=self.record();record["trace"]=[];record["initial"]={"success":False};record["decisions"]=[{"controller":None}]
        record["cache_version_after"]=1
        record["outcome"].update(total_steps=0,prefix_steps=0,micro_steps=0,fixed_probe_steps=0,policy_steps=0,
                                 success=False,stopped=True,point_fit_failures=0,cache_updates=0)
        result=case_metrics(record);self.assertEqual(result["total_steps"],0);self.assertTrue(result["stopped"])

    def test_partial_failed_and_foreign_audits_cannot_authorize_a_report(self):
        identity={"experiment_run_id":"test","manifest_id":"test","source_git_commit":"test"}
        audit={**identity,"integrity":"PASSED","episodes":4608,"environment_resets":4608,"api_calls":0,"memory_writes":0,"status":"COMPLETED_COMPETITIVE_FAILED"}
        matching_audit(identity,audit)
        for field,value in (("integrity","FAILED"),("episodes",4607),("status","RUNNING"),("manifest_id","foreign"),("api_calls",1)):
            bad=copy.deepcopy(audit);bad[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):matching_audit(identity,bad)

    def test_assessments_count_cases_separately_from_repeated_measurement_calls(self):
        record={"decisions":[{"action":"REQUEST_VISIBLE_PREFIX"},
            {"action":"REQUEST_MICRO_PROBE","validation":{"assessment":{"status":"UNRESOLVED"},"program_id":"WIDE_X4"}},
            {"action":"REFRESH_FIXED16","validation":{"assessment":{"status":"CONTRACT_REJECTED"},"program_id":None}}]}
        result=validation_summary(record)
        self.assertEqual(result["first_status"],"UNRESOLVED")
        self.assertEqual(result["final_status"],"CONTRACT_REJECTED")
        self.assertEqual(result["assessment_calls"],2)
        self.assertEqual(result["micro_program_counts"],{"WIDE_X4":1})
        self.assertIsNone(validation_summary({"decisions":[{"action":"RUN_UNCORRECTED"}]}))
        record["decisions"][-1]["validation"]["assessment"]["status"]="UNREGISTERED"
        with self.assertRaises(ValueError):validation_summary(record)

    def test_cost_ablation_early_refresh_is_not_hidden_by_successful_execution(self):
        record={"method":"RESPONSE_NO_COST","episode_index":1,"stream":0,"task":"push-v3","scenario":"STATIONARY",
            "episode_in_stream":1,"seed":10801,"trace":[{"phase":"PREFIX_POLICY"}]*6+[{"phase":"FIXED_PROBE"}]*16,
            "decisions":[{"action":"REFRESH_NUMERICAL_DESIGN","validation":{"assessment":{"status":"UNRESOLVED"},"program_id":None}}]}
        issue=cost_ablation_issue(record)
        self.assertEqual(issue["actual_micro_steps_before_refresh"],0)
        self.assertEqual(issue["micro_step_shortfall"],16)
        record["trace"]=record["trace"]+[{"phase":"MICRO_PROBE"}]*16
        self.assertIsNotNone(cost_ablation_issue(record))  # Later evidence cannot pay an earlier acquisition requirement.
        record["trace"]=[{"phase":"PREFIX_POLICY"}]*6+[{"phase":"MICRO_PROBE"}]*16+[{"phase":"FIXED_PROBE"}]*16
        self.assertIsNone(cost_ablation_issue(record))
        record["trace"]=[{"phase":"FIXED_PROBE"}]*16;record["method"]="RESPONSE_SET"
        self.assertIsNone(cost_ablation_issue(record))

    def test_complete_synthetic_population_rebuilds_costs_and_writes_bound_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);raw=root/"raw";raw.mkdir();fig=root/"figure";fig.mkdir()
            identity={"experiment_run_id":"synthetic","manifest_id":"synthetic","source_git_commit":"synthetic"}
            (root/"old.json").write_text(json.dumps({"integrity":"PASSED","physical_steps":21010,"environment_resets":288}),encoding="utf-8")
            manifest={**identity,"config":{"forward_audit_path":"old.json"},"input_sha256":{},
                      "operators_oracle":[{"family_oracle":"BIAS_SHIFT"} for _ in range(8)]}
            (raw/"manifest.json").write_text(json.dumps(manifest),encoding="utf-8")
            expected={}
            for method in reporter.METHODS:
                with gzip.open(raw/("episodes_"+method+".jsonl.gz"),"wt",encoding="utf-8") as handle:
                    for stream in range(8):
                        for task in reporter.TASKS:
                            for scenario in reporter.SCENARIOS:
                                for episode in range(6):
                                    record=self.record();record.update(identity,stream=stream,task=task,scenario=scenario,
                                        episode_in_stream=episode,method=method,seed=1,operator_id_oracle="A")
                                    record["outcome"].update(reused_cache=False,final_action="SYNTHETIC")
                                    handle.write(json.dumps(record)+"\n")
                offline=0 if method in ("NO_PROBE","ORACLE16") else 21010
                expected[method]={"successes":288,"denominator":288,"stops":0,"mean_online_steps":4.,"mean_probe_steps":2.,
                    "reused_cases":0,"point_fit_failures":288,"cache_updates":288,"offline_steps":offline,
                    "offline_resets":288 if offline else 0,"mean_amortized_steps":4.+offline/288,
                    "success_by_task":{t:96 for t in reporter.TASKS},"success_by_scenario":{s:144 for s in reporter.SCENARIOS}}
            audit={**identity,"integrity":"PASSED","status":"COMPLETED_COMPETITIVE_FAILED","episodes":4608,
                "environment_resets":4608,"physical_steps":18432,"api_calls":0,"memory_writes":0,"matched_git_inputs":0,
                "replayed_choices":9216,"replayed_step_intents":18432,
                "statistics":{"methods":expected,"strong_baseline_competitive_gate":False,"primary_contrasts":{},"dominating_admissible_baselines":["NO_PROBE"]},
                "artifact_sha256":{p.name:reporter.sha(p) for p in raw.iterdir()}}
            audit_path=root/"audit.json";audit_path.write_text(json.dumps(audit),encoding="utf-8")
            scope={**identity,"primary_audit_sha256":reporter.sha(audit_path),"method_summaries":{},"posttransition_decision_lags":{}}
            scope_path=root/"scope.json";scope_path.write_text(json.dumps(scope),encoding="utf-8")
            for name in ("figure.png","failure_cases.md"):(fig/name).write_bytes(b"synthetic fixture")
            figure={**identity,"audit_sha256":reporter.sha(audit_path),"artifact_sha256":{p.name:reporter.sha(p) for p in fig.iterdir()}}
            (fig/"figure.json").write_text(json.dumps(figure),encoding="utf-8")
            setup={**identity,"primary_audit_sha256":reporter.sha(audit_path),"counts":infer_counts(4608,288,50)}
            setup_path=root/"setup.json";setup_path.write_text(json.dumps(setup),encoding="utf-8")
            report_path=root/"report.md"
            with patch.object(reporter,"ROOT",root),redirect_stdout(StringIO()):
                reporter.report(raw/"manifest.json",audit_path,scope_path,fig,root/"derived",report_path,setup_path)
            result=json.loads((root/"derived/report_metrics.json").read_text(encoding="utf-8"))
            self.assertEqual(result["physical_steps"],18432)
            self.assertEqual(result["methods"]["RESPONSE_SET"]["mean_amortized_steps"],4.+21010/288)
            self.assertEqual(result["phase_totals"]["RESPONSE_SET"]["prefix_steps"],288)
            self.assertEqual(result["report_sha256"],reporter.sha(report_path))
            self.assertIn("强基线竞争门未通过",report_path.read_text(encoding="utf-8"))
            self.assertIn("230400",report_path.read_text(encoding="utf-8"))
            self.assertEqual(result["setup_cost_audit_sha256"],reporter.sha(setup_path))
            setup["manifest_id"]="foreign";setup_path.write_text(json.dumps(setup),encoding="utf-8")
            with patch.object(reporter,"ROOT",root),self.assertRaisesRegex(ValueError,"foreign initialization"):
                reporter.report(raw/"manifest.json",audit_path,scope_path,fig,root/"rejected",root/"rejected.md",setup_path)
            self.assertFalse((root/"rejected").exists())


if __name__=="__main__":unittest.main()

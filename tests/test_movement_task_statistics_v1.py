from copy import deepcopy
from pathlib import Path
import gzip
import json
import tempfile
import unittest
from unittest.mock import patch

from scripts.audit_movement_task_statistics_v1 import check_statistics
from scripts import evaluate_movement_task_v1 as evaluator
from scripts import audit_movement_task_statistics_v1 as independent
from src.analysis import movement_task_io_v1 as io
from src.analysis.movement_model_source_v1 import load_bank
from src.analysis.movement_task_statistics_v1 import statistics


def synthetic_rows():
    rows=[]
    for spec in io.population():
        method=io.method(spec["variant"]);g=spec["unit"]//3
        move=0 if method=="DIRECT_C8" else 8
        steps={"DIRECT_C8":150,"MOVE_KEEP_C8":155,"MOVE_INTEGRAL":130,"MOVE_ARX_KEEP":125}[method]+g%17
        success=not(method=="MOVE_ARX_KEEP" and g%13==0 and spec["task"]=="push-v3" and spec["variant"].startswith("CHANGED"))
        if not success:steps=500
        fitting=int(method=="MOVE_ARX_KEEP")
        row={**spec,"completed":True,"success":success,"total_steps":steps,"deadline_loss":steps if success else 500,
            "boundary_ready":True,"stopped":False,"action":{"DIRECT_C8":"RUN_SAVED_C8","MOVE_KEEP_C8":"RUN_SAVED_C8",
                "MOVE_INTEGRAL":"RUN_SAVED_INTEGRAL","MOVE_ARX_KEEP":"RUN_SAVED_ARX"}[method],
            "reposition_steps":move,"task_steps":steps-spec["planned_boundary"]-move,"policy_queries":steps-8-move,
            "parameter_fit_attempts":2+fitting,"parameter_fit_results":2+fitting,"optimizer_nfev":2+2*fitting,
            "movement_fit_attempts":fitting,"movement_fit_results":fitting,"movement_optimizer_nfev":2*fitting}
        if spec["unit"] in (0,1):
            early=spec["unit"]==0
            row.update(success=early,total_steps=6 if early else 8,deadline_loss=6 if early else 500,
                boundary_ready=False,stopped=not early,action="NO_LIVE_BOUNDARY",reposition_steps=0,task_steps=0,policy_queries=0,
                parameter_fit_attempts=1 if early else 2,parameter_fit_results=1 if early else 2,optimizer_nfev=1 if early else 2,
                movement_fit_attempts=0,movement_fit_results=0,movement_optimizer_nfev=0)
        rows.append(row)
    return rows


class MovementTaskStatisticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config=io.expected_config();cls.rows=synthetic_rows()
        _,source=load_bank(Path(__file__).resolve().parents[1]);cls.costs=source["costs"]
        cls.result=statistics(cls.rows,cls.config,cls.costs)

    def test_early_success_and_stops_stay_in_all_method_denominators(self):
        for method,cell in self.result["methods"].items():
            self.assertEqual(cell["cases"],324);self.assertEqual(cell["stops"],2)
            part=[r for r in self.rows if io.method(r["variant"])==method]
            self.assertEqual(cell["successes"],sum(r["success"] for r in part))
            self.assertAlmostEqual(cell["mean_deadline_loss"],sum(r["deadline_loss"] for r in part)/324)

    def test_historical_fees_are_charged_once_per_method_not_once_per_condition(self):
        arx=self.result["methods"]["MOVE_ARX_KEEP"];integral=self.result["methods"]["MOVE_INTEGRAL"]
        self.assertEqual((arx["historical_source_environment_steps"],integral["historical_source_environment_steps"]),(27154,3840))
        self.assertAlmostEqual(arx["mean_amortized_actual_steps"]-arx["mean_total_steps"],27154/324)
        self.assertTrue(self.result["historical_native_and_all_reset_total_unknown"])

    def test_uncertainty_uses_54_groups_and_preserves_one_primary_comparison(self):
        self.assertEqual(self.result["independent_groups"],54)
        self.assertEqual(self.result["boundary_strata_groups"],[18,18,18])
        self.assertEqual(sum(c["role"]=="PRIMARY" for c in self.result["contrasts"]),1)
        primary=self.result["contrasts"][0]
        self.assertEqual((primary["method"],primary["reference"]),("MOVE_ARX_KEEP","MOVE_INTEGRAL"))
        self.assertEqual(len(primary["group_values"]),54)

    def test_independent_table_audit_reconstructs_every_reported_value(self):
        with patch("src.analysis.movement_task_statistics_v1.statistics",side_effect=AssertionError("no production statistics")):
            result=check_statistics(self.rows,self.result,self.config,self.costs)
        self.assertEqual(result["executions_checked"],1296);self.assertEqual(result["contrasts_checked"],6)
        self.assertGreater(result["statistics_leaves_checked"],1000)

    def test_missing_duplicated_or_relabelled_outcomes_cannot_change_denominator(self):
        for mode in ("missing","duplicate","loss","success","metadata"):
            rows=deepcopy(self.rows)
            if mode=="missing":rows.pop()
            elif mode=="duplicate":rows[-1]=deepcopy(rows[0])
            elif mode=="loss":rows[8]["deadline_loss"]=8
            elif mode=="success":rows[8]["success"]=True
            else:rows[0]["seed"]+=1
            with self.subTest(mode=mode),self.assertRaises(ValueError):statistics(rows,self.config,self.costs)
            with self.subTest(mode=mode),self.assertRaises(ValueError):check_statistics(rows,self.result,self.config,self.costs)

    def test_changed_intervals_source_fees_groups_or_novelty_claim_are_rejected(self):
        for mode in ("interval","cost","groups","claim","count"):
            result=deepcopy(self.result)
            if mode=="interval":result["contrasts"][0]["metrics"]["deadline_loss"]["paired_group_percentile_95"][0]+=.1
            elif mode=="cost":result["methods"]["MOVE_ARX_KEEP"]["historical_source_environment_steps"]-=1
            elif mode=="groups":result["independent_groups"]=324
            elif mode=="claim":result["algorithm_novelty_demonstrated"]=True
            else:result["methods"]["DIRECT_C8"]["cases"]-=1
            with self.subTest(mode=mode),self.assertRaises(ValueError):check_statistics(self.rows,result,self.config,self.costs)

    def artifact_pipeline(self, *, tamper=False):
        identity={"experiment_run_id":"STATISTICS_SOFTWARE_ONLY","manifest_id":"SYNTHETIC","source_git_commit":"SYNTHETIC"}
        manifest={**identity,"config":self.config,"arx_source_receipt":{"costs":self.costs}}
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);path=root/"manifest.json";io.write(path,manifest)
            folder=root/"collection";folder.mkdir()
            for name in ("events.jsonl.gz","state_witnesses.jsonl.gz"):
                with gzip.open(folder/name,"xt",encoding="utf-8") as handle:handle.write("")
            with gzip.open(folder/"cases.jsonl.gz","xt",encoding="utf-8") as handle:
                for row in self.rows:handle.write(json.dumps(row)+"\n")
            for name in ("summary.json","status.json"):io.write(folder/name,{"software_fixture":True})
            hashes={p.name:io.sha(p) for p in folder.iterdir()}
            (root/"audit").mkdir()
            io.write(root/"audit/record_audit.json",{**identity,"integrity":"PASSED","executions":1296,
                "rows":self.rows,"collection_artifact_sha256":hashes,"costs":{"software_fixture":True},"audit_computations":{}})
            with patch.object(io,"load",return_value=(manifest,{},{})):
                result=evaluator.evaluate(path)
                if tamper:
                    source=root/"analysis/summary.json";changed=io.read(source)
                    changed["statistics"]["contrasts"][0]["metrics"]["deadline_loss"]["difference"]+=1
                    io.write(source,changed,exclusive=False)
                    done=io.read(root/"analysis/completion.json");done["artifact_sha256"][source.name]=io.sha(source)
                    io.write(root/"analysis/completion.json",done,exclusive=False)
                    with self.assertRaises(ValueError):independent.audit(path)
                    self.assertEqual(io.read(root/"statistics_audit/failed_audit.json")["integrity"],"FAILED")
                else:
                    checked=independent.audit(path);self.assertEqual(checked["integrity"],"PASSED")
                    self.assertEqual(result["statistics"],self.result)
                    self.assertEqual(len(io.read(root/"analysis/all_cases.json")),1296)
                    self.assertTrue(any(r["success"] and r["action"]=="NO_LIVE_BOUNDARY" for r in io.read(root/"analysis/failures_and_rejections.json")))
                    with self.assertRaises(FileExistsError):independent.audit(path)
                with self.assertRaises(FileExistsError):evaluator.evaluate(path)

    def test_artifact_evaluation_and_independent_audit_are_complete_and_exclusive(self):self.artifact_pipeline()

    def test_self_consistent_artifact_hash_cannot_hide_changed_statistics(self):self.artifact_pipeline(tamper=True)


if __name__=="__main__":unittest.main()

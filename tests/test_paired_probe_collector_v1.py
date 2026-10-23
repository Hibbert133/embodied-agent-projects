"""Collector failure transactions using software-only callbacks, no task creation."""
from contextlib import ExitStack, nullcontext
import copy
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from scripts import run_paired_probe_effects_v1 as collector


class SoftwareEnv:
    def reset(self, *, seed):return np.zeros(39), {}
    def close(self):pass


class SoftwareSession:
    fail_during_execution=False

    def __init__(self,env,policy,initial,task,seed,fault,emit,ledger,budget):
        self.emit,self.budget=emit,budget
        self.completed=self.attempts=self.policy_queries=self.captures=self.restores=0
        self.capture_ns=self.restore_ns=0;self.ctx={'calls':0}

    def execute(self,program,model,*args,**kwargs):
        if model!={'task':'push-v3','marker':'SOFTWARE_ONLY'}:raise ValueError('task-specific model was not routed')
        self.completed=3;self.attempts=4 if self.fail_during_execution else 3
        self.policy_queries=2;self.ctx['calls']=3;self.budget['completed']+=3
        self.emit('SOFTWARE_EXECUTION_FIXTURE',{'no_robot_task_created':True})
        if self.fail_during_execution:raise RuntimeError('injected partial execution failure')
        outcome={'success':False,'stopped':False,'total_steps':3,'suffix_steps':3,'deadline_loss':500,
            'fixed_probe_suffix_steps':3,'policy_suffix_steps':0,'online_parameter_fits':0,'optimizer_nfev':0,
            'policy_queries':2,'applied_new_controller':False}
        record={'role':'SOURCE','future':0,'program':'COLD8','outcome':outcome,'fit':None,'fit_prefix':None}
        return record,{'fit':None,'fit_prefix':None}


class PairedProbeCollectorTest(unittest.TestCase):
    def test_main_rejects_failed_pipeline_or_report_even_with_passed_numeric_audit(self):
        identity={k:'SOFTWARE_ONLY' for k in collector.io.IDENTITY}
        records={
            'smoke_audit.json':{**identity,'integrity':'PASSED','required_host_coverage':True,'summary_sha256':'SHA','events_sha256':'SHA'},
            'smoke_statistics_audit.json':{**identity,'integrity':'PASSED','summary_sha256':'SHA','statistics_sha256':'SHA'},
            'smoke_pipeline_completion.json':{**identity,'status':'COMPLETED_FOR_REVIEW','failure':None,'steps':[{'returncode':0}]*6},
            'report_receipt.json':{**identity,'report_path':'reports/paired_probe_effects_smoke_v1.md','report_sha256':'SHA','statistics_sha256':'SHA',
                'record_audit_sha256':'SHA','numeric_audit_sha256':'SHA'}}
        with patch.object(collector.io,'read',side_effect=lambda path:records[path.name]),patch.object(collector.io,'sha',return_value='SHA'):
            collector.require_smoke_ready(Path('SOFTWARE_ONLY/manifest.json'),identity)
            for name,key,value in [('smoke_pipeline_completion.json','status','FAILED_SAVED_NOT_RETRIED'),
                ('report_receipt.json','report_sha256','CHANGED'),('smoke_audit.json','required_host_coverage',False)]:
                old=records[name][key];records[name][key]=value
                with self.subTest(key=key),self.assertRaises(ValueError):collector.require_smoke_ready(Path('SOFTWARE_ONLY/manifest.json'),identity)
                records[name][key]=old

    def exercise(self, *, fail_status=False, fail_execution=False):
        with tempfile.TemporaryDirectory() as directory:
            manifest=Path(directory)/'manifest.json'
            identity={k:'SOFTWARE_ONLY' for k in collector.io.IDENTITY}
            config=copy.deepcopy(collector.io.read(collector.CONFIG))
            m={**identity,'config':config,'population_oracle':{'SMOKE':[{
                'stream':0,'family_oracle':'SOFTWARE_ONLY','schedule_oracle':'SOFTWARE_ONLY',
                'cases':[{'episode':0,'task':'push-v3','seed':700777,'fault_oracle':{}}]}]}}
            original_write=collector.io.write

            def write(path,value,**kwargs):
                if fail_status and path.name=='status.json' and value.get('status')=='RUNNING':
                    raise OSError('injected status persistence failure')
                return original_write(path,value,**kwargs)

            with ExitStack() as stack:
                for name,value in [('load',lambda path:(m,{'push-v3':{'task':'push-v3','marker':'SOFTWARE_ONLY'}})),('ProbeSession',SoftwareSession),
                                   ('create_task_environment',lambda *args:SoftwareEnv()),
                                   ('create_task_policy',lambda *args:object())]:
                    stack.enter_context(patch.object(collector,name,value))
                stack.enter_context(patch.object(collector.io,'clean',lambda:None))
                stack.enter_context(patch.object(collector.io,'git',lambda *args:'SOFTWARE_ONLY'))
                stack.enter_context(patch.object(collector.io,'write',write))
                stack.enter_context(patch.object(collector.LifecycleLedger,'instrument',lambda *args:nullcontext()))
                stack.enter_context(patch.object(SoftwareSession,'fail_during_execution',fail_execution))
                with self.assertRaises(SystemExit) as failure:collector.run(manifest,'SMOKE')
                self.assertEqual(failure.exception.code,1)
            folder=manifest.parent/'smoke'
            with gzip.open(folder/'cases_00.jsonl.gz','rt',encoding='utf-8') as handle:
                rows=[json.loads(line) for line in handle]
            summary=collector.io.read(folder/'summary.json')
            completion=collector.io.read(folder/'completion.json')
            self.assertEqual(completion['status'],'FAILED_SAVED_NOT_RETRIED')
            for name,expected in completion['artifact_sha256'].items():
                self.assertEqual(collector.io.sha(folder/name),expected)
            return rows,summary

    def test_status_failure_does_not_append_already_saved_case_again(self):
        rows,summary=self.exercise(fail_status=True)
        self.assertEqual(len(rows),1)
        self.assertEqual(summary['source_units'],1)
        self.assertEqual(summary['failure']['type'],'OSError')
        self.assertTrue(summary['cases'][0]['case_write_attempted_before_failure'])
        self.assertNotIn('error',rows[0])
        self.assertIn('error',summary['cases'][0])
        self.assertFalse(summary['computation_counters_complete'])
        self.assertEqual(summary['controlled_steps'],3)

    def test_partial_failure_keeps_one_failed_case_and_actual_attempt_costs(self):
        rows,summary=self.exercise(fail_execution=True)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows,summary['cases'])
        self.assertFalse(rows[0]['case_write_attempted_before_failure'])
        partial=rows[0]['partial_actual']
        self.assertEqual((partial['completed_steps'],partial['attempted_steps'],partial['policy_queries']),(3,4,2))
        self.assertFalse(summary['computation_counters_complete'])
        self.assertEqual(summary['controlled_steps'],3)

    def test_only_successful_actually_applied_new_source_fit_renews_cache(self):
        previous=object();fit={'valid':True};result={'fit':fit,'fit_prefix':object()};model=object()
        record={'outcome':{'success':False,'applied_new_controller':True}}
        self.assertEqual(collector.commit_source(previous,record,result,model,3,'push-v3'),(None,None))
        record['outcome'].update(success=True,applied_new_controller=False)
        with patch.object(collector,'accepted_cache') as accept:
            self.assertIs(collector.commit_source(previous,record,result,model,3,'push-v3')[0],previous);accept.assert_not_called()
        record['outcome']['applied_new_controller']=True;renewed=object()
        with patch.object(collector,'accepted_cache',return_value=renewed) as accept:
            self.assertIs(collector.commit_source(previous,record,result,model,3,'push-v3')[0],renewed)
            self.assertIs(accept.call_args.kwargs['joint_model'],model)
        with patch.object(collector,'accepted_cache',side_effect=ValueError('invalid source belief')):
            self.assertEqual(collector.commit_source(previous,record,result,model,3,'push-v3'),(None,'invalid source belief'))


if __name__=='__main__':unittest.main()

"""Independent arithmetic compared with registered analysis on artificial records."""
import copy
import unittest
from scripts.analyze_paired_probe_effects_v1 import statistics
from scripts.audit_paired_probe_statistics_v1 import rebuild,compare,remove_scope

ARMS=('REUSE_OLD','PROBE_KEEP','PROBE_UPDATE','PROBE_UPDATE_KEEP')


def fixture(phase):
    matrices=[[[100,110,80,80],[500,90,500,90],[100,120,80,80]],
              [[60,40,500,40],[50,45,30,30],[60,65,55,55]],
              [[80,85,75,75],[90,85,500,85],[100,95,90,90]]]
    rows=[]
    for i,table in enumerate(matrices):
        evaluations=[]
        for j,losses in enumerate(table,1):
            for arm,loss in zip(ARMS,losses):
                stopped=arm=='PROBE_UPDATE' and loss==500
                actual=8 if stopped else loss
                evaluations.append({'future':j,'program':arm,'outcome':{'deadline_loss':loss,'success':loss<500,'stopped':stopped,
                    'total_steps':actual,'suffix_steps':actual-4,'fixed_probe_suffix_steps':0 if arm=='REUSE_OLD' else 4,
                    'policy_suffix_steps':actual-4 if arm=='REUSE_OLD' else actual-8}})
        rows.append({'stream':0 if i==0 else 1,'disposition':'WARM_ELIGIBLE','task':('push-v3','reach-v3','door-open-v3')[i],
            'family_oracle':'SOFTWARE','schedule_oracle':'TEST','evaluations':evaluations,
            'references':{'UNCERTAINTY4':{'action':'RUN_CACHED' if i<2 else 'STOP_PUBLIC_CHECK'},'TASK_IVR4':{'action':'REFRESH8'}}})
    rows.append({'stream':2,'disposition':'COLD_SOURCE','evaluations':[]})
    manifest={'config':{phase.lower():{'fresh_futures':3}},'population_oracle':{phase:[{'stream':i,'family_oracle':'SOFTWARE','schedule_oracle':'TEST'} for i in range(3)]}}
    return manifest,{'source_units':len(rows),'cases':rows}


class PairedProbeNumericAuditTest(unittest.TestCase):
    def test_all_smoke_covariances_and_failure_penalties_independently_rebuilt(self):
        m,s=fixture('SMOKE');actual=remove_scope(statistics(m,s,'SMOKE'));expected=rebuild(m,s,'SMOKE')
        fields,difference=compare(actual,expected)
        self.assertGreater(fields,200);self.assertLess(difference,1e-8)
        self.assertEqual(actual['methods']['PROBE_UPDATE']['stops'],3)
        actual=copy.deepcopy(actual);actual['nested']['mc_mean_noise_covariance'][0][0]+=1
        with self.assertRaises(ValueError):compare(actual,expected)

    def test_whole_stream_ratio_with_unequal_context_counts_and_empty_stream(self):
        m,s=fixture('MAIN');actual=remove_scope(statistics(m,s,'MAIN'));expected=rebuild(m,s,'MAIN')
        fields,difference=compare(actual,expected)
        self.assertGreater(fields,200);self.assertLess(difference,1e-8)
        self.assertEqual(actual['stream_bootstrap']['source_streams'],3)
        self.assertGreater(actual['stream_bootstrap']['undefined_draws'],0)
        self.assertIsNone(actual['stream_bootstrap']['percentile_95'])

    def test_missing_branch_or_unknown_saved_action_not_relabelled(self):
        m,s=fixture('SMOKE');s['cases'][0]['evaluations'].pop()
        with self.assertRaises(ValueError):rebuild(m,s,'SMOKE')
        m,s=fixture('SMOKE');s['cases'][0]['references']['UNCERTAINTY4']['action']='ORACLE_WINNER'
        with self.assertRaises(ValueError):rebuild(m,s,'SMOKE')


if __name__=='__main__':unittest.main()

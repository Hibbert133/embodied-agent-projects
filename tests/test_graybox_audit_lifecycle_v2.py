"""Whole audit lifecycle regression; tiny constructed algebra, no environment."""
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
import tempfile,unittest
import numpy as np
from src.analysis import graybox_response_training_audit_v1 as old,graybox_response_training_audit_v2 as fixed
from src.analysis import graybox_response_io_v1 as a
io=a.io

class AuditLifecycle(unittest.TestCase):
    def run_audit(self,module):
        with tempfile.TemporaryDirectory() as name,ExitStack() as stack:
            root=Path(name);out=root/'training';out.mkdir();path=root/'manifest.json'
            nominal=[dict(task=t,group=0,trace=dict(initial_xy=[0.,.6],steps=[dict(at_calls=0,command=[0.]*4,after_xy=[0.,.6])])) for t in io.TASKS]
            result=dict(scale=[1.],coef=[[0.]])
            rls=dict(input_scale=[1.],coef=[[0.]],covariance=[[1.]])
            models=dict(bank=dict(by_task={t:dict(PLANTS=[dict(rho=0.,kappa=.05)]*2,RLS_ARX=rls,INSTANT=result,FIR=result) for t in io.TASKS}),
                nominal_fit_metadata={t:dict(zero_length_source_groups=[],RLS_short_history_source_groups=[0],per_candidate_per_axis_nll=[[0.,0.]]*9,selected_grid_indices=[0,0]) for t in io.TASKS})
            io.write(out/'models.json',models);io.write(out/'completion.json',dict(integrity='TRAINED_FOR_INDEPENDENT_AUDIT',models_sha256=io.sha(out/'models.json')))
            io.write(out/'public_nominal_traces.json',nominal);io.write(out/'public_train_families.json',[])
            def grid(traces,counter):counter['independent_nominal_grid_passes']=counter.get('independent_nominal_grid_passes',0)+9;return [[0.,0.]]*9
            def fit(value):np.linalg.lstsq(np.eye(1),np.zeros((1,1)),rcond=None);return value
            for obj,key,value in ((a,'checked',lambda *x:{}),(module,'sources',lambda *x:(nominal,[])),(module.math,'nominal_scores',grid),
                (module,'rls_fit',lambda *x:fit(rls)),(module,'linear_data',lambda *x:([],[],[])),(module.math,'augmented_linear',lambda *x:fit(result))):
                stack.enter_context(patch.object(obj,key,value))
            value=module.audit(path)
            self.assertEqual(value['guard']['operation_counts']['lstsq_attempts'],9);self.assertEqual(value['independent_counts']['independent_nominal_grid_passes'],27)
            self.assertTrue((root/'training_audit_repair_v2.json').exists());self.assertFalse((out/'audit.json').exists())
    def test_original_guard_read_fails_after_numerical_work(self):
        with self.assertRaisesRegex(KeyError,'operation_counts'):self.run_audit(old)
    def test_fixed_guard_read_occurs_after_context_exit(self):self.run_audit(fixed)

if __name__=='__main__':unittest.main()

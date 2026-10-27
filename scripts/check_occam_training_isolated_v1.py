"""Bounded constructed optimizer/data-path checks in the existing CPU runtime."""
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
from time import perf_counter_ns
import argparse,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import torch,numpy as np
from src.analysis import response_qualification_io_v1 as io
from src.analysis.occam_reference_learner_v1 import public_only_guard


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);v=p.parse_args();out=Path(v.output).resolve()
    io.require(out.is_relative_to((ROOT/'outputs/occam_reference_train').resolve()),'owned software output');out.mkdir(parents=True,exist_ok=False)
    io.require(torch.__version__=='2.2.2+cpu' and np.__version__=='1.26.4' and not torch.cuda.is_available(),'existing pinned CPU runtime')
    torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.use_deterministic_algorithms(True)
    start=perf_counter_ns();guard={};counts=dict(Torch_solve_attempts=0,covariance_spectra=0,synthetic_Adam_attempts=0);ids=[]
    def counted(fn,key,cap):
        def call(*a,**kw):counts[key]+=1;io.require(counts[key]<=cap,'software numerical cap '+key);return fn(*a,**kw)
        return call
    with ExitStack() as st:
        st.enter_context(public_only_guard(guard,out/'constructed_public.json',out/'constructed_spec.json',out))
        st.enter_context(patch.object(torch.linalg,'solve',counted(torch.linalg.solve,'Torch_solve_attempts',1000)))
        st.enter_context(patch.object(torch.linalg,'eigvalsh',counted(torch.linalg.eigvalsh,'covariance_spectra',5000)))
        st.enter_context(patch.object(torch.optim.AdamW,'step',counted(torch.optim.AdamW.step,'synthetic_Adam_attempts',1)))
        with (out/'tests.log').open('x',encoding='utf8',newline='\n') as log:
            suite=unittest.defaultTestLoader.loadTestsFromName('tests.test_occam_training_torch_v1')
            def collect(s):
                for t in s:
                    if isinstance(t,unittest.TestSuite):collect(t)
                    else:ids.append(t.id())
            collect(suite);r=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    io.write(out/'complete.json',dict(integrity='PASSED' if r.wasSuccessful() else 'FAILED',tests=r.testsRun,ids=ids,guard=guard,operation_counts=counts,
        skipped=r.skipped,scientific_model_training=0,wall_ns=perf_counter_ns()-start))
    io.require(r.wasSuccessful() and r.testsRun==7 and not r.skipped,'all7 isolated checks');print(dict(integrity='PASSED',tests=7,operations=counts),flush=True)


if __name__=='__main__':main()

"""Pinned CPU-only constructed tests and upstream mathematical cross-check."""
from pathlib import Path
from contextlib import ExitStack,contextmanager
from unittest.mock import patch
from time import perf_counter_ns
import argparse,ast,builtins,hashlib,importlib.abc,io as stream_io,subprocess,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import numpy as np
import torch
from src.analysis import response_qualification_io_v1 as io
from src.probe import occam_performance_core_v1 as core
from src.analysis import occam_meta_torch_v1 as meta
from src.analysis.occam_performance_independent_v1 import batch_posterior
BASE=ROOT/'outputs/occam_performance_core'
UPSTREAM_COMMIT='f0d3afb3b9369d19b3ed3cd20408c88628296b02'


@contextmanager
def guard(receipt):
    counts={'forbidden_physics_import_attempts':0,'old_experiment_data_open_attempts':0};network={}
    forbidden=('metaworld','mujoco','gymnasium','src.rollout')
    class Block(importlib.abc.MetaPathFinder):
        def find_spec(self,fullname,path=None,target=None):
            if any(fullname==p or fullname.startswith(p+'.') for p in forbidden):
                counts['forbidden_physics_import_attempts']+=1;raise RuntimeError('physics modules forbidden in isolated software check')
    assert not any(any(n==p or n.startswith(p+'.') for p in forbidden) for n in sys.modules)
    original=builtins.open
    def opened(file,*args,**kw):
        if isinstance(file,(str,Path)):
            p=Path(file).resolve()
            if p.is_relative_to((ROOT/'outputs').resolve()) and not p.is_relative_to(BASE.resolve()):
                counts['old_experiment_data_open_attempts']+=1;raise RuntimeError('old experimental data forbidden')
        return original(file,*args,**kw)
    blocker=Block();sys.meta_path.insert(0,blocker)
    try:
        with io.forbid_online_calls(network),patch.object(builtins,'open',opened),patch.object(stream_io,'open',opened):yield
    finally:
        sys.meta_path.remove(blocker);receipt.update(counts=counts,network=network,new_physics=0,online_LLM_API_calls=0)


def execute(out,repository,source_provenance):
    started=perf_counter_ns();out=Path(out).resolve();io.require(out.is_relative_to(BASE.resolve()),'owned isolated check output');out.mkdir(parents=True,exist_ok=False)
    io.require(torch.__version__=='2.2.2+cpu' and np.__version__=='1.26.4' and not torch.cuda.is_available(),'existing isolated CPU runtime')
    torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.use_deterministic_algorithms(True)
    code=subprocess.check_output(['git','-C',str(repository),'show',UPSTREAM_COMMIT+':learned_ctrlr_opt/meta_learning/basis_kf.py'])
    provenance=io.read(source_provenance);ref=next(r for r in provenance['files_read'] if r['path'].endswith('/basis_kf.py'))
    io.require(hashlib.sha256(code).hexdigest()==ref['sha256'] and provenance['commit']==UPSTREAM_COMMIT,'locked reviewed upstream mathematical source')
    parsed=ast.parse(code);functions=[n for n in parsed.body if isinstance(n,ast.FunctionDef) and n.name=='kalman_step'];io.require(len(functions)==1,'only reviewed pure helper')
    namespace={'torch':torch,'__builtins__':{}};exec(compile(ast.Module(body=functions,type_ignores=[]),'<locked_upstream_kalman_step>','exec'),namespace)
    upstream=namespace['kalman_step'];operations={};receipt={};ids=[];cases=[]
    def counted(obj,name,label,maximum=1000):
        fn=getattr(obj,name)
        def f(*args,**kw):
            operations[label]=operations.get(label,0)+1;io.require(operations[label]<=maximum,'constructed operation budget '+label);return fn(*args,**kw)
        return patch.object(obj,name,f)
    with guard(receipt),ExitStack() as stack,(out/'tests.log').open('x',encoding='utf8',newline='\n') as log:
        for obj,name,label,maximum in ((np.linalg,'solve','numpy_solve_attempts',1000),(torch.linalg,'solve','torch_solve_attempts',1000),
            (torch.linalg,'inv','reviewed_upstream_inverse_attempts',12),(core,'update','numpy_filter_entries',1000),
            (meta,'filter_step','torch_filter_entries',1000),(meta.PerformanceBasis,'forward','basis_forward_calls',5000),
            (np.linalg,'eigvalsh','numpy_covariance_spectra',5000),(torch.linalg,'eigvalsh','torch_covariance_spectra',5000),
            (torch.optim.Adam,'step','synthetic_Adam_steps',1)):
            stack.enter_context(counted(obj,name,label,maximum))
        suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromName(n) for n in ('tests.test_occam_performance_core_v1','tests.test_occam_meta_torch_v1')])
        def collect(s):
            for t in s:
                if isinstance(t,unittest.TestSuite):collect(t)
                else:ids.append(t.id())
        collect(suite);result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
        if result.wasSuccessful():
            rng=np.random.default_rng(202610281)
            for bases,outputs in ((1,1),(3,1),(3,2),(5,3)):
                for replicate in range(3):
                    m=rng.normal(size=bases);a=rng.normal(size=(bases,bases));P=a@a.T+.2*np.eye(bases)
                    q=rng.normal(size=(bases,bases));Q=q@q.T*.02 if replicate else np.zeros((bases,bases))
                    r=rng.normal(size=(outputs,outputs));R=r@r.T+.3*np.eye(outputs);H=rng.normal(size=(outputs,bases));y=rng.normal(size=outputs)
                    actual=core.update(m,P,H,y,Q,R);tm,tp=meta.filter_step(*map(torch.tensor,(m,P,H,y,Q,R)))
                    um,up,uk=upstream(*map(torch.tensor,(m,P,y,H.T,Q,R)));bm,bp=batch_posterior(m,P,[H],[y],Q,R)
                    differences=[np.max(abs(actual['mean']-v)) for v in (tm.detach().numpy(),um.detach().numpy(),bm)]
                    differences += [np.max(abs(actual['covariance']-v)) for v in (tp.detach().numpy(),up.detach().numpy(),bp)]
                    io.require(max(differences)<=1e-10,'upstream / NumPy / differentiable / whole-Gaussian contract')
                    cases.append(dict(bases=bases,outputs=outputs,replicate=replicate,max_absolute_difference=float(max(differences))))
            torch.manual_seed(202610282)
            fixture=meta.PerformanceBasis(4,3,bases=3,outputs=2,context_size=3,encoder_hidden=(5,),head_hidden=(6,))
            fh=torch.randn(5,4,dtype=torch.float64);fd=torch.randn(5,3,dtype=torch.float64)
            io.write(out/'constructed_export_fixture.json',dict(schema='CONSTRUCTED_EXPORT_CHECK_NOT_ROBOT_MODEL',history=fh.tolist(),descriptor=fd.tolist(),
                basis=fixture.export(),expected_basis=fixture(fh,fd).detach().numpy().tolist(),trained_on_robot_data=False,optimizer_updates=0))
    payload=dict(integrity='PASSED' if result.wasSuccessful() and len(cases)==12 else 'FAILED',tests=result.testsRun,ids=ids,skipped=len(result.skipped),
        guard=receipt,operation_counts=operations,source_contract_cases=cases,upstream_commit=UPSTREAM_COMMIT,upstream_file_sha256=ref['sha256'],
        only_reviewed_upstream_function_executed=True,upstream_training_and_collection_not_executed=True,
        runtime=dict(python=sys.version,torch=torch.__version__,numpy=np.__version__,cuda=False,threads=torch.get_num_threads()),
        wall_ns=perf_counter_ns()-started,new_physics=0,scientific_model_training=0,online_LLM_API_calls=0)
    io.write(out/'complete.json',payload)
    io.require(payload['integrity']=='PASSED' and result.testsRun==len(set(ids))==24 and not result.skipped and operations['synthetic_Adam_steps']==1
        and operations['reviewed_upstream_inverse_attempts']==12,'24 constructed checks / one Adam step /12 source helpers')
    print(dict(integrity='PASSED',tests=24,source_cases=12,operations=operations),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--upstream-repository',required=True);p.add_argument('--source-provenance',required=True)
    args=p.parse_args();execute(args.output,args.upstream_repository,args.source_provenance)

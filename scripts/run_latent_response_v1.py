"""Frozen phase runner with accurate physical/fit guard accounting and failures."""
from pathlib import Path
from contextlib import ExitStack,contextmanager
from unittest.mock import patch
from time import perf_counter_ns
import argparse,sys,traceback
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis import latent_response_io_v1 as a


@contextmanager
def readonly_guard(receipt,maximum_ridge_systems=0):
    import numpy as np
    import scipy.optimize
    from metaworld.sawyer_xyz_env import SawyerXYZEnv
    from gymnasium.envs.mujoco import MujocoEnv
    from src.probe import cold_start_response,short_joint_reference_v1,operator_identification
    counts={'environment_creations':0,'resets':0,'simulation':0,'forbidden_fits':0,'ridge_linear_systems':0};network={}
    def deny(key):
        def f(*args,**kwargs):counts[key]+=1;raise RuntimeError('Forbidden operation in read-only response phase: '+key)
        return f
    solve=np.linalg.solve
    def counted_solve(*args,**kwargs):
        counts['ridge_linear_systems']+=1
        a.io.require(counts['ridge_linear_systems']<=maximum_ridge_systems,'registered closed-form fit budget')
        return solve(*args,**kwargs)
    with ExitStack() as stack:
        stack.enter_context(a.io.forbid_online_calls(network))
        for obj,name,key in ((SawyerXYZEnv,'__init__','environment_creations'),(SawyerXYZEnv,'reset','resets'),(MujocoEnv,'do_simulation','simulation'),
            (np.linalg,'lstsq','forbidden_fits'),(scipy.optimize,'least_squares','forbidden_fits'),(cold_start_response,'least_squares','forbidden_fits'),
            (short_joint_reference_v1,'least_squares','forbidden_fits'),(operator_identification,'least_squares','forbidden_fits')):stack.enter_context(patch.object(obj,name,deny(key)))
        stack.enter_context(patch.object(np.linalg,'solve',counted_solve))
        try:yield
        finally:receipt.update({'blocked_operations':counts,'network':network,'zero_new_physical_interactions':not any(counts[k] for k in ('environment_creations','resets','simulation')),
            'registered_ridge_budget':maximum_ridge_systems,'online_LLM_API_calls':0})


def run(phase,path,split):
    if phase=='prepare':return str(a.prepare())
    a.io.require(path is not None,'owned manifest');a.checked(path)
    if phase=='collect':
        from src.analysis.latent_response_collect_v1 import collect
        return collect(path,split)
    receipt={};limit=30 if phase in ('train','models-audit') else 0
    try:
        with readonly_guard(receipt,limit):
            if phase=='records-audit':
                from src.analysis.latent_response_record_audit_v1 import audit
                from src.analysis import latent_response_host_v1 as host
                def deny(*args,**kwargs):raise RuntimeError('Main native observer/query/predictor disabled during record audit')
                with ExitStack() as stack:
                    for name in ('native_values','run_live','make_query','predict'):stack.enter_context(patch.object(host,name,deny))
                    return audit(path,split)
            if phase=='train':
                from src.analysis.latent_response_training_v1 import train
                return train(path)
            if phase=='models-audit':
                from src.analysis.latent_response_model_audit_v1 import complete_audit
                from src.analysis import latent_response_training_v1 as training
                def deny(*args,**kwargs):raise RuntimeError('Main fitting/normalization disabled in independent numerical audit')
                with ExitStack() as stack:
                    for name in ('fit_direct','fit_baselines','statistics'):stack.enter_context(patch.object(training,name,deny))
                    return complete_audit(path)
            if phase=='evaluate':
                from src.analysis.latent_response_evaluation_v1 import evaluate
                return evaluate(path,split)
            if phase=='statistics-audit':
                from src.analysis.latent_response_statistics_audit_v1 import audit
                from src.analysis import latent_response_evaluation_v1 as main
                def deny(*args,**kwargs):raise RuntimeError('Main losses and statistics disabled')
                with ExitStack() as stack:
                    for name in ('score','loss_rows','statistics','quantile'):stack.enter_context(patch.object(main,name,deny))
                    return audit(path,split)
            if phase=='lock':
                from src.analysis.latent_response_evaluation_v1 import lock
                return lock(path)
            raise ValueError('unknown phase')
    finally:a.io.write(path.parent/(phase.replace('-','_')+'_'+str(split)+'_guard.json'),receipt)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=('prepare','collect','records-audit','train','models-audit','evaluate','statistics-audit','lock'))
    p.add_argument('--manifest',type=Path);p.add_argument('--split',choices=a.SPLITS);v=p.parse_args();start=perf_counter_ns();failure=None;result=None
    try:result=run(v.phase,v.manifest.resolve() if v.manifest else None,v.split)
    except BaseException as error:failure={'type':type(error).__name__,'message':str(error),'traceback':traceback.format_exc()}
    receipt={'phase':v.phase,'split':v.split,'status':'PASSED' if failure is None else 'FAILED','wall_ns':perf_counter_ns()-start,'failure':failure,'online_LLM_API_calls':0}
    if v.manifest:a.io.write(v.manifest.parent/('cli_'+v.phase.replace('-','_')+'_'+str(v.split)+'_process_receipt.json'),receipt)
    if v.phase=='prepare' and failure is None:print(result,flush=True)
    else:print(receipt,flush=True)
    if failure is not None:raise SystemExit(1)

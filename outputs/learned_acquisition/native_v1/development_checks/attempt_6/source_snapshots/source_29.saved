"""No-physics/no-network analysis guard with separately charged numerical fits."""
from contextlib import contextmanager,ExitStack
from unittest.mock import patch
from src.analysis.response_qualification_io_v1 import forbid_online_calls,require


@contextmanager
def read_only(receipt,*,max_solve=0,max_lstsq=0,max_cold_fits=0):
    import numpy as np
    import scipy.optimize
    from metaworld.sawyer_xyz_env import SawyerXYZEnv
    from gymnasium.envs.mujoco import MujocoEnv
    from src.probe import cold_start_response,short_joint_reference_v1,operator_identification,task_passive_program_v1
    counts=dict(environment_creations=0,resets=0,simulation=0,solve_attempts=0,lstsq_attempts=0,cold_fit_attempts=0,
        cold_estimator_entries=0,cold_linear_solve_attempts=0,cold_linear_lstsq_attempts=0);network={};cold_depth=0
    def denied(key):
        def f(*args,**kw):counts[key]+=1;raise RuntimeError('Forbidden physical operation in read-only learning phase: '+key)
        return f
    def counted(fn,key,maximum):
        def f(*args,**kw):
            counts[key]+=1;require(counts[key]<=maximum,'registered numerical budget exceeded: '+key);return fn(*args,**kw)
        return f
    def linear(fn,key,maximum,cold_key):
        def f(*args,**kw):
            if cold_depth:counts[cold_key]+=1;return fn(*args,**kw)
            counts[key]+=1;require(counts[key]<=maximum,'registered risk-fit numerical budget exceeded: '+key);return fn(*args,**kw)
        return f
    def estimator(fn):
        def f(*args,**kw):
            nonlocal cold_depth
            counts['cold_estimator_entries']+=1;require(counts['cold_estimator_entries']<=max_cold_fits,'registered legacy C4/C8 refit entries')
            cold_depth+=1
            try:return fn(*args,**kw)
            finally:cold_depth-=1
        return f
    with ExitStack() as stack:
        stack.enter_context(forbid_online_calls(network))
        for obj,name,key in ((SawyerXYZEnv,'__init__','environment_creations'),(SawyerXYZEnv,'reset','resets'),(MujocoEnv,'do_simulation','simulation')):
            stack.enter_context(patch.object(obj,name,denied(key)))
        stack.enter_context(patch.object(np.linalg,'solve',linear(np.linalg.solve,'solve_attempts',max_solve,'cold_linear_solve_attempts')))
        stack.enter_context(patch.object(np.linalg,'lstsq',linear(np.linalg.lstsq,'lstsq_attempts',max_lstsq,'cold_linear_lstsq_attempts')))
        for name in ('infer_four','infer_operator'):stack.enter_context(patch.object(task_passive_program_v1,name,estimator(getattr(task_passive_program_v1,name))))
        for obj in (scipy.optimize,cold_start_response,short_joint_reference_v1,operator_identification):
            stack.enter_context(patch.object(obj,'least_squares',counted(obj.least_squares,'cold_fit_attempts',max_cold_fits)))
        try:yield
        finally:receipt.update(operation_counts=counts,network=network,zero_new_physical_interactions=not any(counts[k] for k in ('environment_creations','resets','simulation')),
            registered_budgets=dict(solve=max_solve,lstsq=max_lstsq,cold_fits=max_cold_fits),online_LLM_API_calls=0)

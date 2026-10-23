"""Complete read-only post-hoc diagnostics; no environment or fitting entry point."""
from pathlib import Path
import sys
from contextlib import ExitStack
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis.task_passive_diagnosis_v1 import run


if __name__=='__main__':
    from metaworld.sawyer_xyz_env import SawyerXYZEnv
    from gymnasium.envs.mujoco import MujocoEnv
    from src.analysis import task_passive_diagnosis_v1 as pipeline
    import scipy.optimize
    import numpy as np
    from src.probe import cold_start_response,short_joint_reference_v1,operator_identification
    counters={'environment_creations':0,'environment_resets':0,'physical_simulation_calls':0,'fit_attempts':0}
    def deny(key):
        def blocked(*a,**k): counters[key]+=1; raise RuntimeError('Forbidden interaction/fit during descriptive replay')
        return blocked
    with ExitStack() as stack:
        for obj,name,key in ((SawyerXYZEnv,'__init__','environment_creations'),(SawyerXYZEnv,'reset','environment_resets'),
            (MujocoEnv,'do_simulation','physical_simulation_calls'),(scipy.optimize,'least_squares','fit_attempts'),
            (cold_start_response,'least_squares','fit_attempts'),(short_joint_reference_v1,'least_squares','fit_attempts'),
            (operator_identification,'least_squares','fit_attempts'),(np.linalg,'lstsq','fit_attempts')):
            stack.enter_context(patch.object(obj,name,deny(key)))
        folder=run()
    assert not any(counters.values())
    pipeline.io.write(folder/'interaction_guard.json',{'integrity':'PASSED','counters':counters,'new_api_calls':0,
        'source_sha256':pipeline.io.sha(__file__),'scope':'Actual analysis process blocked environment creation/reset/simulation and parameter fitting'})

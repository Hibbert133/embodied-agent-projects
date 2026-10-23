"""Analyze saved records with environment, fitting and network operations blocked."""
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
import argparse
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis.acquisition_support_v1 import analyze
from src.analysis import acquisition_support_sources_v1 as src
io=src.io


def guarded(function):
    counters={'environment_creations':0,'resets':0,'simulation':0,'fits':0};network={}
    from metaworld.sawyer_xyz_env import SawyerXYZEnv
    from gymnasium.envs.mujoco import MujocoEnv
    import numpy as np
    import scipy.optimize
    from src.probe import cold_start_response,short_joint_reference_v1,operator_identification
    def deny(key):
        def blocked(*args,**kw):counters[key]+=1;raise RuntimeError('Forbidden new interaction or fit in support analysis')
        return blocked
    with ExitStack() as stack:
        stack.enter_context(io.forbid_online_calls(network))
        for obj,name,key in ((SawyerXYZEnv,'__init__','environment_creations'),(SawyerXYZEnv,'reset','resets'),(MujocoEnv,'do_simulation','simulation'),
            (np.linalg,'lstsq','fits'),(scipy.optimize,'least_squares','fits'),(cold_start_response,'least_squares','fits'),
            (short_joint_reference_v1,'least_squares','fits'),(operator_identification,'least_squares','fits')):stack.enter_context(patch.object(obj,name,deny(key)))
        value=function()
    io.require(not any(counters.values()) and network=={'attempted_network_calls':0},'zero-interaction support analysis')
    return value,{'integrity':'PASSED','blocked_operations':counters,'network':network,'new_environment_steps':0,'new_model_fits':0,'new_online_LLM_API_calls':0}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);a=p.parse_args()
    result,guard=guarded(lambda:analyze(a.manifest));io.write(a.manifest.parent/'interaction_guard.json',guard);print(result,flush=True)

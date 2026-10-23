"""Independent descriptive audit with interaction/fitting transports blocked."""
import argparse
from pathlib import Path
import sys
from contextlib import ExitStack
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis.task_passive_diagnosis_audit_v1 import audit,io


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('folder',type=Path);args=parser.parse_args()
    from metaworld.sawyer_xyz_env import SawyerXYZEnv
    from gymnasium.envs.mujoco import MujocoEnv
    import numpy as np
    import scipy.optimize
    counts={'environment_creations':0,'resets':0,'simulation':0,'fits':0};network={}
    def deny(key):
        def blocked(*a,**k):counts[key]+=1;raise RuntimeError('Read-only audit attempted forbidden interaction/fit')
        return blocked
    with ExitStack() as stack:
        stack.enter_context(io.forbid_online_calls(network))
        for obj,name,key in ((SawyerXYZEnv,'__init__','environment_creations'),(SawyerXYZEnv,'reset','resets'),
            (MujocoEnv,'do_simulation','simulation'),(np.linalg,'lstsq','fits'),(scipy.optimize,'least_squares','fits')):
            stack.enter_context(patch.object(obj,name,deny(key)))
        result=audit(args.folder)
    assert not any(counts.values()) and network=={'attempted_network_calls':0}
    io.write(args.folder/'audit_interaction_guard.json',{'integrity':'PASSED','counters':counts,'network_guard':network,'source_sha256':io.sha(__file__)})
    print(result)

"""Read-only independent audit with native environment creation/advance blocked."""
import argparse
from contextlib import ExitStack
from unittest.mock import patch
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis.response_action_audit_v1 import audit
from src.analysis.response_action_io_v1 import io


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);p.add_argument('--cohort',choices=('SOFTWARE_NATIVE','DEV','QUAL'),required=True);a=p.parse_args()
    from metaworld.sawyer_xyz_env import SawyerXYZEnv
    from gymnasium.envs.mujoco import MujocoEnv
    counters={'environment_creations':0,'resets':0,'simulation':0};network={}
    def deny(key):
        def blocked(*args,**kw):counters[key]+=1;raise RuntimeError('Independent audit must not interact with environment')
        return blocked
    with ExitStack() as stack:
        stack.enter_context(io.forbid_online_calls(network))
        for obj,name,key in ((SawyerXYZEnv,'__init__','environment_creations'),(SawyerXYZEnv,'reset','resets'),(MujocoEnv,'do_simulation','simulation')):stack.enter_context(patch.object(obj,name,deny(key)))
        result=audit(a.manifest,a.cohort)
    assert not any(counters.values()) and network=={'attempted_network_calls':0}
    io.write(a.manifest.parent/a.cohort.lower()/'audit_interaction_guard.json',{'integrity':'PASSED','counters':counters,'network':network,
        'source_sha256':io.sha(__file__),'C4_C8_refits_separately_charged':result['costs'].get('independent_c4_c8_refits',0)})
    print({'audit':'PASSED','cohort':a.cohort,'executions':result['executions'],'costs':result['costs'],'native_contract':result['native_software_contract']})

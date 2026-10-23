"""Record audit blocks all new physics; C4/C8 replay fits charged separately."""
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
import argparse,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis import memory_reset_io_v1 as a
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);p.add_argument('--cohort',choices=('SOFTWARE_NATIVE','QUAL'));p.add_argument('--statistics',action='store_true');v=p.parse_args()
    extension=a.BASE/'audit_validation_v2/complete.json';qa=a.io.read(extension)
    a.io.require(qa['integrity']=='PASSED','frozen reader repair required')
    for name,h in qa['source_sha256'].items():a.io.require(a.io.sha(a.ROOT/name)==h,'reader extension source changed')
    if v.statistics:
        from scripts.analyze_acquisition_support_v1 import guarded
        from src.analysis.memory_reset_statistics_audit_v1 import audit
        with patch('src.analysis.memory_reset_statistics_v1.compute',side_effect=RuntimeError('Main statistic called')):
            result,guard=guarded(lambda:audit(v.manifest))
        a.io.write(v.manifest.parent/'qual/statistics_audit_guard.json',guard);print(result,flush=True)
    else:
        if v.cohort is None:p.error('cohort required')
        from metaworld.sawyer_xyz_env import SawyerXYZEnv
        from gymnasium.envs.mujoco import MujocoEnv
        from src.analysis.memory_reset_streaming_audit_v2 import compute as audit
        counters={'environment_creations':0,'resets':0,'simulation':0};network={}
        def deny(key):
            def blocked(*args,**kw):counters[key]+=1;raise RuntimeError('Independent audit cannot interact with a world')
            return blocked
        with ExitStack() as stack:
            stack.enter_context(a.io.forbid_online_calls(network))
            for obj,name,key in ((SawyerXYZEnv,'__init__','environment_creations'),(SawyerXYZEnv,'reset','resets'),(MujocoEnv,'do_simulation','simulation')):stack.enter_context(patch.object(obj,name,deny(key)))
            result=audit(v.manifest,v.cohort)
        result['reader_extension_freeze_sha256']=a.io.sha(extension)
        result['reader_extension_git_commit']=a.io.git('rev-parse','HEAD')
        a.io.write(v.manifest.parent/v.cohort.lower()/'audit.json',result)
        a.io.require(not any(counters.values()) and network=={'attempted_network_calls':0},'read-only audit guard')
        a.io.write(v.manifest.parent/v.cohort.lower()/'audit_interaction_guard.json',{'integrity':'PASSED','counters':counters,'network':network,
            'initial_C4_C8_refits_separately_charged':result['costs'].get('independent_c4_c8_refits',0),'new_response_training':0,'new_online_LLM_API_calls':0})
        print({k:result[k] for k in ('integrity','cohort','native_software_contract','executions','actual_reference_modes','costs')},flush=True)

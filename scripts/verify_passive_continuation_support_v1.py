"""Frozen saved-record semantics, not a new robot collection or trained method."""
from pathlib import Path
import argparse,sys,traceback
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis import passive_continuation_support_v1 as a
from src.analysis.release_learning_guard_v1 import read_only


def run(phase,path=None):
    guard={}
    try:
        with read_only(guard):
            if phase=='prepare':return a.prepare()
            if phase=='analyze':return a.compute(path)
            if phase=='audit':
                from src.analysis.passive_continuation_support_audit_v1 import audit
                from src.probe import release_learning_actor_v1
                from src.probe.task_passive_pi_v1 import PIPlan
                from unittest.mock import patch
                def denied(*args,**kwargs):raise RuntimeError('Main actor and semantic replay disabled in independent audit')
                with patch.object(a,'compute',denied),patch.object(a.replay,'run',denied),patch.object(release_learning_actor_v1,'run',denied),patch.object(PIPlan,'numbers',denied):return audit(path)
            raise ValueError('unknown phase')
    except BaseException:
        if path is not None:
            from datetime import datetime,timezone
            stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
            a.io.write(Path(path).parent/('failure_'+phase+'_'+stamp+'.json'),dict(phase=phase,traceback=traceback.format_exc()))
        raise
    finally:
        if path is not None:a.io.write(Path(path).parent/(phase+'_guard.json'),guard)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('phase',choices=('prepare','analyze','audit'));parser.add_argument('--manifest',type=Path);v=parser.parse_args()
    result=run(v.phase,v.manifest)
    print(str(result) if isinstance(result,Path) else {k:result[k] for k in ('integrity','counts','fields_checked') if k in result},flush=True)

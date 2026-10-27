"""Minimal inference bundle; public-node input only, no case/seed/future registry."""
from copy import deepcopy
from pathlib import Path
from src.analysis import correction_scope_risk_reference_v1 as old
from src.analysis import correction_transfer_learning_v1 as network
from src.probe.learned_acquisition_actor_v1 import validate_decision
io=old.io


class FrozenRiskClient:
    def __init__(self,path,*,maximum_calls=None):
        path=Path(path).resolve();b=io.read(path);copy=dict(b);bid=copy.pop('bundle_id')
        io.require(set(b)=={'schema','precritic','receiver','bundle_id'} and b['schema']=='FROZEN_RISK_BUNDLE_V1' and io.digest(copy)==bid,'minimal versioned bundle')
        io.require(set(b['precritic'])=={'file','sha256','kind','fixed_receiver_sha256'} and b['precritic']['kind']=='RBF','minimal precritic')
        io.require(set(b['receiver'])=={'file','sha256','variant'} and b['receiver']['variant']=='JOINT_SPO','minimal receiver')
        io.require(b['precritic']['fixed_receiver_sha256']==b['receiver']['sha256'],'precritic bound to this exact receiver')
        for m in (b['precritic'],b['receiver']):
            io.require(Path(m['file']).name==m['file'] and io.sha(path.parent/m['file'])==m['sha256'],'immutable local model blob')
        io.require(maximum_calls is None or type(maximum_calls) is int and maximum_calls>=0,'explicit inference budget')
        self.folder=path.parent;self.bundle=deepcopy(b);self.calls=0;self.maximum_calls=maximum_calls;self.last=None
    def __call__(self,node):
        old.validate_node(node);self.calls+=1
        io.require(self.maximum_calls is None or self.calls<=self.maximum_calls,'frozen native inference budget exceeded')
        pre=node['stage']=='PRE';model=self.bundle['precritic' if pre else 'receiver']
        scores=old.predict(model,self.folder,node) if pre else network.receiver_prediction(model,self.folder,node)['scores'][0].tolist()
        selected=old.choice(scores)
        result=validate_decision(node,dict(schema='LIVE_RISK_DECISION_V1',stage=node['stage'],action=selected if pre else None,
            rate=None if pre else selected,scores=scores,model_sha256=model['sha256'],input_sha256=io.digest(node),kind='FROZEN_MODEL'))
        self.last=deepcopy(result);return result


def forced_reference(action,rate):
    ai=old.ACTIONS.index(action);ri=old.RATES.index(rate)
    def decide(node):
        old.validate_node(node);pre=node['stage']=='PRE';index=ai if pre else ri;scores=[1.]*(3 if pre else 4);scores[index]=0.
        result=validate_decision(node,dict(schema='LIVE_RISK_DECISION_V1',stage=node['stage'],action=ai if pre else None,
            rate=None if pre else ri,scores=scores,model_sha256='FORCED_REFERENCE_V1',input_sha256=io.digest(node),kind='FORCED_REFERENCE'))
        decide.last=deepcopy(result);return result
    decide.last=None
    return decide

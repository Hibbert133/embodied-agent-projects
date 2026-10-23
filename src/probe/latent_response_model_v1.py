"""Known-input eight-step predictors; no private state, fitting or policy execution."""
import numpy as np
from src.probe.latent_response_query_v1 import ForecastQuery,context,baseline20,require


def linear(value,parameters):return value@np.asarray(parameters['weight']).T+np.asarray(parameters['bias'])


def neural_predict(model,queries):
    method=model['method'];x=np.array([context(q,model['normalization'],method) for q in queries])
    h=np.tanh(linear(np.tanh(linear(x,model['encoder1'])),model['encoder2']))
    commands=np.array([q.planned_commands for q in queries],float)/.8
    if method=='DIRECT_MLP_H8':return .01*linear(np.tanh(linear(np.c_[h,commands.reshape(-1,32)],model['direct1'])),model['direct2']).reshape(-1,8,2)
    out=[];position=np.zeros((len(queries),2),float)
    for k in range(8):
        h=np.tanh(h+linear(np.tanh(linear(np.c_[h,commands[:,k]],model['transition1'])),model['transition2']))
        position=position+.01*linear(h,model['output']);out.append(position.copy())
    return np.stack(out,axis=1)


def predict(model,queries):
    require(all(type(q) is ForecastQuery and q.task==model['task'] for q in queries),'matching strict public queries')
    if not queries:return np.empty((0,8,2))
    method=model['method']
    if method=='PERSIST_ZERO':out=np.zeros((len(queries),8,2),float)
    elif method.startswith('SS_') or method=='DIRECT_MLP_H8':out=neural_predict(model,queries)
    elif method=='DIRECT_RIDGE_H8':
        x=np.array([np.r_[1.,context(q,model['normalization'],method),np.asarray(q.planned_commands).ravel()/.8] for q in queries])
        out=np.stack([x@np.asarray(c) for c in model['horizon_coefficients']],axis=1)
    else:
        require(method in ('HISTORY_LINEAR10','QUADRATIC_STATE20'),'registered model')
        v=np.array([baseline20(q) for q in queries]);v=v[:,3:13] if method=='HISTORY_LINEAR10' else v
        z=(v-np.asarray(model['mean']))/model['scale'];x=np.c_[np.ones(len(z)),z]
        if method=='QUADRATIC_STATE20':i,j=np.triu_indices(20);x=np.c_[x,z[:,i]*z[:,j]]
        out=(x@np.asarray(model['coefficients']))[:,None,:]
    require(out.shape==(len(queries),1 if method in ('HISTORY_LINEAR10','QUADRATIC_STATE20') else 8,2) and np.isfinite(out).all(),'finite forecast without response feedback')
    return out

"""Literal scalar conditioning and separate batch audit, never the online provider.

Strict public feature extraction is shared and disclosed; dense network forward,
four-candidate scoring and scalar posterior arithmetic are reimplemented here.
"""
from copy import deepcopy
import numpy as np
from src.probe.occam_public_history_v1 import features
from src.probe.occam_performance_core_v1 import digest,RATES
from src.probe.occam_qualification_program_v1 import program_spec
from src.analysis.occam_performance_independent_v1 import batch_posterior


def require(x,message):
    if not x:raise ValueError(message)


def near(x,y,message,tolerance=1e-9):
    a=np.asarray(x,float);b=np.asarray(y,float)
    require(a.shape==b.shape and np.isfinite(a).all() and np.isfinite(b).all() and np.allclose(a,b,rtol=1e-10,atol=tolerance),message)


def literal_bases(bank,query):
    history=[];descriptor=[]
    for rate in RATES:
        h,x=features({**deepcopy(query),'candidate_time_constant_s':rate},8);history.append(h);descriptor.append(x)
    def dense(value,layers):
        result=np.array(value,float)
        for index,layer in enumerate(layers):
            result=np.dot(result,np.transpose(layer['weight']))+np.array(layer['bias'],float)
            if index+1<len(layers):result=np.where(result>0,result,0.)
        return result
    context=dense(history,bank['encoder']);basis=dense(np.column_stack([descriptor,context]),bank['head'])
    return basis.reshape((4,1,bank['dimensions']['bases']))


def audit_windows(program,public,bank,constant):
    settings=program_spec(program);trained=settings['kind']=='TRAINED';query=declaration=measurement=None
    ordinal=updates=0;diagnostics=[];past=[];targets=[];pending=None
    if trained:
        prior=bank['prior'];mean=np.array(prior['mean'],float);P=np.array(prior['covariance'],float)
        Q=np.array(prior['process_covariance'],float);R=np.array(prior['measurement_covariance'],float)
    for event in public:
        kind=event['agent_event'];p=event['public_payload']
        if kind=='WINDOW_QUERY':
            require(query is None and declaration is None,'one factual pending query');query=p
        elif kind=='WINDOW_DECISION':
            require(query is not None and p['input_sequence']==query['sequence'],'decision follows saved query')
            d=p['declaration'];require(d['public_query_sha256']==digest(query['value']) and d['at_calls']==query['at_calls'],'actual query digest/time')
            declaration=p;pending=d
            if trained:
                phi=literal_bases(bank,query['value']);near(d['bases'],phi,'independent network bases',1e-10)
                means=[]
                for index in range(4):
                    expected=float(phi[index,0]@mean);var=float(phi[index,0]@P@phi[index,0]);pred=d['predictions'][index]
                    near(pred['mean'],[expected],'pre-feedback mean');near(pred['latent_covariance'],[[var]],'latent variance')
                    near(pred['observation_covariance'],[[var+R[0,0]]],'observation variance')
                    means.append(float(pred['mean'][0]));near(d['scores'][index],-float(pred['mean'][0]),'fixed beta0 score')
                require(d['selected_index']==int(np.argmin(means)) and d['selected_rate']==RATES[d['selected_index']]
                    and d['version']==updates and d['beta']==0. and d['reward_weights']==[-1.],'all-candidate selection, fixed beta and model version')
            else:
                index=RATES.index(settings['rate']);require(d['selected_index']==index and d['selected_rate']==settings['rate'],'all fixed controls retained')
        elif kind=='WINDOW_RESULT':
            require(declaration is not None and measurement is None and p['parent_sequence']==declaration['sequence'],'factual label parent')
            measurement=p['measurement'];require(measurement['start_at']==pending['at_calls'] and measurement['end_at']==p['at_calls'],'label time')
        elif kind=='WINDOW_FEEDBACK':
            require(declaration is not None and measurement is not None and p['decision_sequence']==declaration['sequence'],'no early/future feedback')
            f=p['feedback'];d=pending;y=measurement['cost']
            require(f['declaration_sha256']==d['declaration_sha256'] and f['completed_steps']==measurement['end_at'],'feedback identity/time')
            if trained:
                h=phi[d['selected_index'],0];prediction=float(h@mean);latent=float(h@P@h)
                diagnostics.append(dict(window_ordinal=ordinal,at_calls=d['at_calls'],end_at=measurement['end_at'],
                    selected_rate=d['selected_rate'],model_version_before=updates,actual_cost=y,predicted_cost=prediction,
                    squared_error=(prediction-y)**2,constant_squared_error=(constant-y)**2,
                    latent_variance=latent,observation_variance=latent+float(R[0,0]),
                    prospective_innovation_variance=float(h@(P+Q)@h+R[0,0]),
                    full_window=measurement['full_window'],terminal=measurement['terminal']))
                actual_update=settings['adapt'] and measurement['full_window']
                require(f['adaptation_enabled']==settings['adapt'] and f['update_applied']==actual_update,'update/freeze factor never selected from results')
                if actual_update:
                    before=P+Q;s=float(h@before@h+R[0,0]);require(s>0 and np.isfinite(s),'positive scalar innovation')
                    gain=(before@h)/s;innovation=y-prediction;mean=mean+gain*innovation
                    I=np.eye(len(mean))-np.outer(gain,h);P=I@before@I.T+np.outer(gain,gain)*R[0,0];P=(P+P.T)/2
                    updates+=1;v=f['result']['posterior']
                    near(v['mean'],mean,'independent scalar mean');near(v['covariance'],P,'independent scalar posterior')
                    near(v['innovation'],[innovation],'independent innovation');near(v['innovation_covariance'],[[s]],'innovation variance before conditioning')
                    near(v['gain'],gain[:,None],'independent scalar gain');past.append(h[None,:]);targets.append([y])
                else:
                    require(f['model_state_before_sha256']==f['model_state_after_sha256'],'no-update path must retain state')
                    require('posterior' not in f['result'],'frozen or partial feedback cannot hide an update')
                require(f['version']==updates,'only actual full feedback advances model')
            else:require(f['online_filter_updates']==0,'fixed gain cannot adapt a model')
            ordinal+=1;query=declaration=measurement=pending=None
    require(query is None and declaration is None and measurement is None,'no dangling prediction')
    batch_solves=0
    if trained and past:
        m,b=batch_posterior(prior['mean'],prior['covariance'],np.asarray(past),np.asarray(targets),Q,R);batch_solves=1
        near(m,mean,'final whole-history batch mean',1e-8);near(b,P,'final whole-history batch covariance',1e-8)
    return dict(windows=ordinal,updates=updates,batch_solves=batch_solves,diagnostics=diagnostics,
        mse=None if not diagnostics else float(np.mean([v['squared_error'] for v in diagnostics])),
        constant_mse=None if not diagnostics else float(np.mean([v['constant_squared_error'] for v in diagnostics])),
        missing_reason='NOT_A_PREDICTOR' if not trained else 'EARLY_END_WITHOUT_WINDOW' if not diagnostics else None)

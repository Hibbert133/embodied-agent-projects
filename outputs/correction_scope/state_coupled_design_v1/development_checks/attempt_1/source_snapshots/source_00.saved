"""DESIGN ONLY: evaluator-side spatial command map, no environment adapter.

Oracle diagnostics from this module must not be placed in an online Agent View.
This is an abstract stress-test operator, not a calibrated friction model.
"""
from copy import deepcopy
import numpy as np

KINDS=('FLAT_LEFT','FLAT_RIGHT','SMOOTH_STATE')
SPEC_KEYS={'kind','axis','center','half_width','left','right'}
END_KEYS={'matrix_xy','bias_xy','deadzone_xy'}


def require(ok,message):
    if not ok:raise ValueError(message)


def endpoint(value):
    require(type(value) is dict and set(value)==END_KEYS,'strict evaluator endpoint')
    a=np.asarray(value['matrix_xy'],float);b=np.asarray(value['bias_xy'],float);z=np.asarray(value['deadzone_xy'],float)
    require(a.shape==(2,2) and b.shape==z.shape==(2,) and all(np.isfinite(x).all() for x in (a,b,z)),'finite endpoint shapes')
    require(all(.75<=a[i,i]<=1.25 for i in range(2)) and abs(a[0,1])<=.2 and abs(a[1,0])<=.2 and np.max(abs(b))<=.2,'declared bounded endpoint palette')
    require(np.array_equal(z,np.zeros(2)),'this design has zero deadzone, do not silently change family')
    return deepcopy(value)


def spec(value):
    require(type(value) is dict and set(value)==SPEC_KEYS,'strict spatial evaluator spec')
    require(value['kind'] in KINDS and type(value['axis']) is int and value['axis'] in range(3),'registered kind/public hand axis')
    require(type(value['center']) in (int,float) and np.isfinite(value['center']) and type(value['half_width']) in (int,float)
        and np.isfinite(value['half_width']) and value['half_width']>0,'finite positive spatial scale')
    endpoint(value['left']);endpoint(value['right']);return deepcopy(value)


def before_state(value):
    require(type(value) is dict and set(value)=={'at_calls','current'},'only declared pre-action public fields')
    require(type(value['at_calls']) is int and 0<=value['at_calls']<500,'one legal next-step index')
    current=value['current'];require(type(current) is dict and set(current)=={'observation','success','terminated','truncated'},'strict public current observation')
    observation=np.asarray(current['observation'],float)
    require(observation.shape==(39,) and np.isfinite(observation).all(),'finite actual public observation shape')
    require(all(type(current[k]) is bool for k in ('success','terminated','truncated')) and not any(current[k] for k in ('success','terminated','truncated')),'no step after task end')
    return deepcopy(value)


def weight(position,definition):
    d=spec(definition);require(type(position) in (int,float) and np.isfinite(position),'finite public hand coordinate')
    if d['kind']=='FLAT_LEFT':return 0.
    if d['kind']=='FLAT_RIGHT':return 1.
    z=max(0.,min(1.,.5+.5*(position-d['center'])/d['half_width']))
    return z*z*(3.-2.*z)


def local_endpoint(position,definition):
    d=spec(definition);w=weight(position,d)
    result={key:((1.-w)*np.asarray(d['left'][key],float)+w*np.asarray(d['right'][key],float)).tolist() for key in END_KEYS}
    return result,w


def evaluate(before,command,noise_xyz,definition):
    """One pure evaluator calculation; caller must separately prove causal timing.

    It does not own/advance a noise cursor, clock or physical state. A future
    collector is still required to bind these arrays to a real saved command.
    """
    before=before_state(before);d=spec(definition)
    u=np.asarray(command,np.float32);noise=np.asarray(noise_xyz,np.float32)
    require(u.shape==(4,) and noise.shape==(3,) and np.isfinite(u).all() and np.isfinite(noise).all() and np.max(abs(u))<=1,'bounded finite sent action and one noise row')
    coordinate=float(before['current']['observation'][d['axis']]);fault,w=local_endpoint(coordinate,d)
    a=np.asarray(fault['matrix_xy'],np.float32);b=np.asarray(fault['bias_xy'],np.float32)
    transformed=u.copy();latent=a@u[:2]+b
    # Preserve the legacy zero-deadzone arithmetic, including signed zero.
    transformed[:2]=np.sign(latent)*np.maximum(abs(latent),np.float32(0))/np.float32(1)
    noisy=transformed.copy();noisy[:3]+=noise;executed=np.clip(noisy,-1,1)
    det=float(a[0,0])*float(a[1,1])-float(a[0,1])*float(a[1,0])
    return dict(schema='EVALUATOR_STATE_COUPLED_ACTION_V1',at_calls=before['at_calls'],state_weight_oracle=w,
        matrix_xy_oracle=a.astype(float).tolist(),bias_xy_oracle=b.astype(float).tolist(),matrix_det_oracle=det,
        transformed_action_oracle=transformed.astype(float).tolist(),noise_xyz_oracle=noise.astype(float).tolist(),
        before_final_clip_oracle=noisy.astype(float).tolist(),executed_action_oracle=executed.astype(float).tolist(),
        final_clip_oracle=(abs(noisy)>1).tolist())


def fixture_definition(kind='SMOOTH_STATE',identity_matrix=False):
    left={'matrix_xy':[[1.,.12],[-.08,.9]],'bias_xy':[.12,-.08],'deadzone_xy':[0.,0.]}
    right={'matrix_xy':[[.8,-.17],[.15,1.1]],'bias_xy':[-.12,.08],'deadzone_xy':[0.,0.]}
    if identity_matrix:left['matrix_xy']=right['matrix_xy']=[[1.,0.],[0.,1.]]
    return dict(kind=kind,axis=0,center=0.,half_width=.1,left=left,right=right)


def fixture_before(x,at_calls=0):
    obs=[0.]*39;obs[0]=x
    return dict(at_calls=at_calls,current=dict(observation=obs,success=False,terminated=False,truncated=False))


def adoption_counterexample():
    """Known kinematic arithmetic only, not a MetaWorld rollout or task outcome."""
    definition=fixture_definition(identity_matrix=True);answer=[]
    for label,sent in (('SMALL',.01),('LARGE',.5)):
        before=fixture_before(-.4);command=[sent,0.,0.,0.]
        first=evaluate(before,command,[0.,0.,0.],definition)
        flat=deepcopy(definition);flat['kind']='FLAT_LEFT'
        initial_prediction=evaluate(before,command,[0.,0.,0.],flat)['executed_action_oracle'][0]
        # Explicitly invented, dimensionless toy dynamics x_next=x+applied_x.
        # This equation is not asserted for MetaWorld or a real robot.
        x_next=-.4+first['executed_action_oracle'][0]
        next_before=fixture_before(x_next,1);second=evaluate(next_before,command,[0.,0.,0.],definition)
        repeated_prediction=evaluate(next_before,command,[0.,0.,0.],flat)['executed_action_oracle'][0]
        answer.append(dict(label=label,initial_x=-.4,command_x=sent,initial_weight=first['state_weight_oracle'],
            initial_prediction_error=first['executed_action_oracle'][0]-initial_prediction,
            invented_kinematic_next_x=x_next,next_weight=second['state_weight_oracle'],
            next_prediction_error=second['executed_action_oracle'][0]-repeated_prediction,
            endpoint_matrix_determinants=[1.,1.],not_a_robot_or_task_result=True))
    return answer


def collection_allocation():
    raise ValueError('DESIGN_ONLY: no robot population, seeds, collector or native qualification is allocated')

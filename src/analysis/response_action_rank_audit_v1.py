"""Independent raw-coefficient reconstruction; never calls rank/model prediction code."""
import numpy as np
from src.analysis.response_qualification_io_v1 import require,digest


def same(a,b,message):require(digest(a)==digest(b),message)
def near(a,b,message):require(np.allclose(a,b,rtol=1e-9,atol=1e-15),message)


def audit_rank(plan,sent,spec,current,history,raw,model):
    require(set(plan)=={'schema','query','kind','model_key','model_sha256','predictions_xy_m','numbers','new_model_fits',
        'physical_inverse_qualified','task_benefit_established','safety_guarantee'},'rank saved-plan fields')
    same(plan['schema'],'RESPONSE_ACTION_RANK_SAVED_PLAN_V1','rank schema')
    q=plan['query'];require(set(q)=={'schema','task','step','current','observation_steps','observations','raw_policy','controller','regularization_weight'},'rank query fields')
    same(q['schema'],'RESPONSE_ACTION_RANK_QUERY_V1','query schema');same(q['task'],spec['task'],'task mapping')
    same(q['step'],len(history)-1,'causal query step');same(q['current'],current,'actual current observation')
    same(q['observations'],history[-3:],'last three actual observations');same(q['observation_steps'],list(range(len(history)-3,len(history))),'history timestamps')
    same(q['raw_policy'],raw,'one original policy query');same(q['regularization_weight'],float(spec['regularization_weight']),'weight lock')
    same(plan['kind'],spec['style'],'rank program');same(plan['new_model_fits'],0,'unexpected fit')
    for key in ('physical_inverse_qualified','task_benefit_established','safety_guarantee'):same(plan[key],False,'unqualified claim')
    c=q['controller'];require(set(c)=={'source','matrix_xy','offset'} and c['source'] in ('ESTIMATED_AFFINE','UNCORRECTED'),'saved visible controller')
    base=np.clip(np.asarray(raw,np.float32),-1,1).astype(float)
    base[:2]=np.asarray(c['matrix_xy'])@base[:2]+np.asarray(c['offset'])[:2];base=np.clip(base,-1,1).astype(np.float32).astype(float)
    commands=[base.copy()]
    for delta in ((.25,0.),(-.25,0.),(0.,.25),(0.,-.25)):
        u=base.copy();u[:2]=np.clip(u[:2]+delta,-1,1);commands.append(u.astype(np.float32).astype(float))
    predictions=[]
    if model is not None:
        key,sha,p=model;same(plan['model_key'],key,'model/source key');same(plan['model_sha256'],sha,'model/source hash')
        a,b,o=np.asarray(history[-3:]);past=np.r_[o[:3]-b[:3],b[:3]-a[:3]]
        for u in commands:
            x=np.r_[o[:3],past,u,o[3],o[4:7]-o[:3],o[-3:]-o[:3]]
            predictions.append(np.r_[1.,(x-np.asarray(p.mean))/np.asarray(p.scale)]@np.asarray(p.coefficient))
    else:
        same(plan['model_key'],'KINEMATIC_PROXY_0.01_M_PER_COMMAND','kinematic descriptor');same(plan['model_sha256'],None,'kinematic no learned source')
        predictions=[.01*u[:2] for u in commands]
    near(plan['predictions_xy_m'],predictions,'full conditional raw-coefficient prediction')
    desired=.01*np.clip(np.asarray(raw,float),-1,1)[:2]
    n=plan['numbers'];require(set(n)=={'reference_displacement_xy_m','baseline_command','candidates','selected_action_id','selected_command','tie_rule','mocap_shaped_reference_is_physical_hand_response'},'rank numbers fields')
    near(n['reference_displacement_xy_m'],desired,'reference units');same(n['baseline_command'],base.tolist(),'bounded C8 base')
    same(n['mocap_shaped_reference_is_physical_hand_response'],False,'reference not a hand plant')
    same(n['tie_rule'],'FIRST_LABEL_BASELINE_X_PLUS_X_MINUS_Y_PLUS_Y_MINUS','tie ordering')
    labels=('BASELINE','X_PLUS','X_MINUS','Y_PLUS','Y_MINUS');scores=[]
    for row,label,u,pred in zip(n['candidates'],labels,commands,predictions):
        require(set(row)=={'action_id','sent_command','predicted_displacement_xy_m','tracking_squared_m2','regularization_m2','score_m2'},'candidate fields')
        same(row['action_id'],label,'candidate order');same(row['sent_command'],u.tolist(),'float32 sends before prediction');near(row['predicted_displacement_xy_m'],pred,'candidate prediction')
        tracking=float(np.sum((pred-desired)**2));regularization=float(float(spec['regularization_weight'])*.01**2*np.sum((u[:2]-base[:2])**2))
        near(row['tracking_squared_m2'],tracking,'tracking cost');near(row['regularization_m2'],regularization,'regularization units');near(row['score_m2'],tracking+regularization,'total score')
        scores.append(tracking+regularization)
    require(len(n['candidates'])==5,'all five labels, including clipped duplicates')
    chosen=min(range(5),key=lambda i:(scores[i],i));same(n['selected_action_id'],labels[chosen],'argmin and exact tie')
    same(n['selected_command'],commands[chosen].tolist(),'saved selection command');same(sent,n['selected_command'],'executor consumed saved selection')
    return {'rank_plans':1,'rank_changed_command_steps':int(np.any(np.asarray(sent)!=base)),
        'independent_rank_score_fields':5*3,'independent_rank_raw_coefficient_forecasts':5 if model is not None else 0}

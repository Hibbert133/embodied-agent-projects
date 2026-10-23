"""Independent rational tree and expanded DR algebra, never calls main estimator/world."""
from pathlib import Path
from fractions import Fraction as F
from itertools import product
from time import perf_counter_ns
import csv,math,json
from src.analysis import response_qualification_io_v1 as io
A=('CONTINUE','VALIDATE','MOVE_VALIDATE');B=('KEEP','UPDATE')
FIRST=('MIXED','ONLY_CONTINUE','ONLY_VALIDATE','ONLY_MOVE');TAIL=('POSTSTATE_ADAPTIVE','KEEP_ONLY')
MODES=('P_TRUE_Q_ZERO','P_TRUE_Q_WRONG','P_WRONG_Q_TRUE','P1_TRUE_Q2_TRUE','Q1_TRUE_P2_TRUE','BOTH_WRONG')
TRUE1=(F(3,10),F(3,10),F(2,5));TRUE2=(F(1,2),F(1,2));WRONG1=(F(3,5),F(1,5),F(1,5));WRONG2=(F(4,5),F(1,5))


def read_rows(path):
    with path.open(encoding='utf-8') as f:
        for line in f:yield json.loads(line)


def pre(x):return {'schema':'SYNTHETIC_BRANCH_HISTORY1_V1','completed_steps':16+16*x,'observed_code':x,'integral_xy':[.2+.2*x,-.1],'time_constant_s':.5}
def position_probs(x,a):return ((F(3,5),F(3,10)) if x==0 else (F(2,5),F(1,2)))+(F(1,20),F(1,20)) if a=='VALIDATE' else ((F(2,5),F(1,2)) if x==0 else (F(17,20),F(1,20)))+(F(1,20),F(1,20))
def pfirst(x,name):return ((F(1,2),F(2,5),F(1,10)) if x==0 else (F(1,5),F(3,10),F(1,2))) if name=='MIXED' else tuple(F(name==k) for k in FIRST[1:])
def ptail(s,name):return (F(1),F(0)) if name=='KEEP_ONLY' else (F(1,10),F(9,10)) if s=='NEAR' else (F(9,10),F(1,10))


def cost_failure(x,a,s,b):
    if s=='NEAR':return (60+10*x,F(1+x,50)) if b=='KEEP' else (20+5*x,F(1,20) if a=='VALIDATE' else F(1,100))
    return (140+15*x,F(3,20)) if b=='KEEP' else (50+10*x,F(3,5) if a=='VALIDATE' else F(3,10))


def qtail(x,a,s):
    left=500-(16+16*x)-(8 if a=='VALIDATE' else 16);v=[]
    for b in B:
        c,p=cost_failure(x,a,s,b);v.append((1-p)*c+p*left)
    return tuple(v)


def qfirst(x,tail):
    t=16+16*x;left=500-t;fail=F(1+x,50);result=[(1-fail)*(60+10*x)+fail*left]
    for a in A[1:]:
        prob=position_probs(x,a);c=8 if a=='VALIDATE' else 16
        v=sum(prob[k]*(c+sum(p*q for p,q in zip(ptail(s,tail),qtail(x,a,s)))) for k,s in enumerate(('NEAR','FAR')))
        result.append(v+prob[2]*2+prob[3]*left)
    return tuple(result)


def independent_atoms():
    result=[]
    for x in (0,1):
        h=pre(x);t=h['completed_steps'];fail=F(1+x,50)
        for success,p in ((True,1-fail),(False,fail)):
            c=60+10*x if success else 65+10*x
            record={'schema':'LOGGED_TERMINAL_BRANCH_V1','before':h,'action':'CONTINUE','option_actual_steps':c,'option_ended':'SUCCESS' if success else 'FAILURE',
                'after':None,'tail_action':None,'tail_actual_steps':None,'tail_success':None,'full_deadline_loss':t+c if success else 500}
            result.append((F(1,2)*TRUE1[0]*p,record))
        for a in A[1:]:
            weights=position_probs(x,a);c=8 if a=='VALIDATE' else 16
            for k,s in enumerate(('NEAR','FAR')):
                integral=[h['integral_xy'][0]+.08,h['integral_xy'][1]-.04] if a=='VALIDATE' else list(h['integral_xy'])
                after={'schema':'SYNTHETIC_BRANCH_HISTORY2_V1','prehistory_sha256':io.digest(h),'action':a,'completed_steps':t+c,
                    'observed_position_bin':s,'measured_residual':.001 if s=='NEAR' else .003,'integral_xy':integral}
                for b in B:
                    steps,pfail=cost_failure(x,a,s,b)
                    for success,p in ((True,1-pfail),(False,pfail)):
                        actual=steps if success else steps+5
                        record={'schema':'LOGGED_TERMINAL_BRANCH_V1','before':h,'action':a,'option_actual_steps':c,'option_ended':'NONE','after':after,
                            'tail_action':b,'tail_actual_steps':actual,'tail_success':success,'full_deadline_loss':t+c+actual if success else 500}
                        result.append((F(1,2)*TRUE1[A.index(a)]*weights[k]*F(1,2)*p,record))
            for status,p,c in (('SUCCESS',weights[2],2),('FAILURE',weights[3],3)):
                record={'schema':'LOGGED_TERMINAL_BRANCH_V1','before':h,'action':a,'option_actual_steps':c,'option_ended':status,'after':None,
                    'tail_action':None,'tail_actual_steps':None,'tail_success':None,'full_deadline_loss':t+c if status=='SUCCESS' else 500}
                result.append((F(1,2)*TRUE1[A.index(a)]*p,record))
    return result


def arguments(r,first,tail,mode):
    x=r['before']['observed_code'];after=r['after']
    b1=TRUE1 if mode in ('P_TRUE_Q_ZERO','P_TRUE_Q_WRONG','P1_TRUE_Q2_TRUE') else WRONG1
    b2=None if after is None else TRUE2 if mode in ('P_TRUE_Q_ZERO','P_TRUE_Q_WRONG','Q1_TRUE_P2_TRUE') else WRONG2
    q1=qfirst(x,tail) if mode in ('P_WRONG_Q_TRUE','Q1_TRUE_P2_TRUE') else (F(0),)*3 if mode=='P_TRUE_Q_ZERO' else (F(100),)*3
    q2=None if after is None else qtail(x,r['action'],after['observed_position_bin']) if mode in ('P_WRONG_Q_TRUE','P1_TRUE_Q2_TRUE') else (F(0),)*2 if mode=='P_TRUE_Q_ZERO' else (F(30),)*2
    return {'behavior1':b1,'target1':pfirst(x,first),'q1':q1,'behavior2':b2,'target2':None if after is None else ptail(after['observed_position_bin'],tail),'q2':q2}


def expanded(r,p):
    t=r['before']['completed_steps'];c=r['option_actual_steps'];y=r['full_deadline_loss']-t-c;i=A.index(r['action'])
    r1=p['target1'][i]/p['behavior1'][i];v1=sum(a*b for a,b in zip(p['target1'],p['q1']))
    if r['after'] is None:
        r2=v2=None;post=F(y);whole=t+v1+r1*(c+y-p['q1'][i]);tail_is=F(y)
    else:
        j=B.index(r['tail_action']);r2=p['target2'][j]/p['behavior2'][j];v2=sum(a*b for a,b in zip(p['target2'],p['q2']))
        # Expanded form is independent of the main recursive D1/D2 code.
        post=v2+r2*(y-p['q2'][j]);whole=t+v1+r1*(c+v2-p['q1'][i])+r1*r2*(y-p['q2'][j]);tail_is=r2*y
    return {'first_importance_ratio':r1,'second_importance_ratio':r2,'first_value_prediction':v1,'post_value_prediction':v2,
        'post_DR':post,'remaining_DR':whole-t,'whole_DR':whole,'whole_IS':t+r1*(c+tail_is),'whole_regression':t+v1,
        'logged_whole_loss':r['full_deadline_loss'],'observed_terminal_remaining_loss':y,'estimate_clipped':False,'conditional_safety_or_task_improvement_established':False}


def converted(v):
    if isinstance(v,F):return float(v)
    if isinstance(v,dict):return {k:converted(w) for k,w in v.items()}
    if isinstance(v,(tuple,list)):return [converted(x) for x in v]
    return v


def same(got,want,label):
    want=converted(want)
    if isinstance(want,dict):
        io.require(type(got) is dict and set(got)==set(want),'fields '+label);return sum(same(got[k],v,label+'/'+k) for k,v in want.items())
    if isinstance(want,list):
        io.require(isinstance(got,(list,tuple)) and len(got)==len(want),'length '+label);return sum(same(a,b,label) for a,b in zip(got,want))
    if isinstance(want,(float,int)) and not isinstance(want,bool):io.require(type(got) in (int,float) and math.isclose(got,want,rel_tol=1e-11,abs_tol=1e-9),'number '+label)
    else:io.require(got==want,'value '+label)
    return 1


def audit(path):
    start=perf_counter_ns();path=path.resolve();out=path.parent;m=io.read(path);body=dict(m);mid=body.pop('manifest_id');io.require(io.digest(body)==mid,'manifest identity')
    for n,h in m['source_sha256'].items():io.require(io.sha(io.ROOT/n)==h,'frozen source changed')
    done=io.read(out/'completion.json');io.require(done['status']=='ENUMERATED_FOR_INDEPENDENT_ARITHMETIC_AUDIT' and done['manifest_id']==mid,'complete mathematical output')
    for n,h in done['artifact_sha256'].items():io.require(io.sha(out/n)==h,'numerical artifact changed')
    atoms=independent_atoms();saved=list(read_rows(out/'finite_atoms.jsonl'));io.require(len(atoms)==len(saved)==44 and sum(p for p,r in atoms)==1,'complete rational population')
    fields=0
    for i,((p,r),got) in enumerate(zip(atoms,saved)):
        fields+=same(got,{'atom_id':'atom-'+str(i).zfill(3),'probability_under_true_behavior':p,'synthetic_finite_model_atom':True,'record':r},'atom')
    estimates=iter(read_rows(out/'estimates.jsonl'));summaries=[];estimate_rows=0
    for first,tail,mode in product(FIRST,TAIL,MODES):
        target=F(0)
        # Direct joint target-law integration, not the main truth function.
        for p,r in atoms:
            x=r['before']['observed_code'];ratio=pfirst(x,first)[A.index(r['action'])]/TRUE1[A.index(r['action'])]
            if r['after'] is not None:ratio*=ptail(r['after']['observed_position_bin'],tail)[B.index(r['tail_action'])]/TRUE2[B.index(r['tail_action'])]
            target+=p*ratio*r['full_deadline_loss']
        rows=[]
        for i,(p,r) in enumerate(atoms):
            args=arguments(r,first,tail,mode);value=expanded(r,args)
            expected={'first_target_policy':first,'tail_target_policy':tail,'mode':mode,'atom_id':'atom-'+str(i).zfill(3),'population_atom_probability':p,
                'prediction_input_before':r['before'],'prediction_input_after':r['after'],'prediction_and_policy_arguments':args,'estimate':value,
                'nuisance_models_are_fixed_or_evaluator_oracle_fixtures':True,'not_a_robot_or_sampled_trajectory':True}
            fields+=same(next(estimates),expected,'estimate');rows.append((p,value));estimate_rows+=1
        metrics={}
        for k in ('whole_DR','whole_IS','whole_regression','logged_whole_loss'):
            mean=sum(p*v[k] for p,v in rows);metrics[k]={'mean':mean,'bias':mean-target,'variance':sum(p*(v[k]-mean)**2 for p,v in rows),'MSE':sum(p*(v[k]-target)**2 for p,v in rows)}
        correct=mode!='BOTH_WRONG'
        if correct:io.require(metrics['whole_DR']['bias']==0,'exact rational stagewise identity')
        summaries.append({'first_target_policy':first,'tail_target_policy':tail,'mode':mode,'known_target_whole_loss':target,'finite_atoms':44,
            'expected_unbiased_under_declared_fixture':correct,'DR_identity_within_tolerance':abs(metrics['whole_DR']['bias'])<=F(1,10**9),'estimators':metrics,
            'DR_atoms_outside_0_500':sum(not 0<=v['whole_DR']<=500 for p,v in rows),'not_a_robot_task_success_test':True})
    io.require(next(estimates,None) is None and estimate_rows==2112,'all mathematical settings')
    contrasts=[]
    for x in (0,1):
        t=16+16*x;q=qfirst(x,'POSTSTATE_ADAPTIVE')
        for a,mu in zip(A,q):
            subset=[(p,r) for p,r in atoms if r['before']['observed_code']==x and r['action']==a]
            marginal=sum(p*r['full_deadline_loss'] for p,r in subset)/sum(p for p,r in subset)
            contrasts.append({'visible_code':x,'first_action':a,'fixed_poststate_policy_whole_loss':t+mu,'behavior_marginal_whole_loss':marginal,'synthetic_counterexample_not_robot_gain':True})
    expected={'qualification':'PASSED_STANDARD_REFERENCE_IDENTITIES_ONLY','classification':'FULLY_ENUMERATED_SYNTHETIC_MODEL_NOT_ROBOT_VALIDATION',
        'finite_atoms':44,'estimate_rows':2112,'setting_summaries':summaries,'conditional_action_comparisons':contrasts,'robust_identities_passed':40,
        'both_wrong_settings_preserved':8,'clipping_used':False,'numerical_estimator_calls':2112,'new_robot_executions':0,'new_environment_steps':0,'new_resets':0,'new_physical_frames':0,
        'new_model_fits':0,'new_online_LLM_API_calls':0,'new_random_streams':0,'publication_goal_complete':False}
    fields+=same(io.read(out/'results.json'),expected,'summary')
    with (out/'setting_summaries.csv').open(encoding='utf-8-sig',newline='') as f:table=list(csv.DictReader(f))
    io.require(len(table)==48,'all exported settings')
    for got,s in zip(table,summaries):
        flat={k:v for k,v in s.items() if k!='estimators'}|{key+'_'+metric:value for key,values in s['estimators'].items() for metric,value in values.items()}
        io.require(set(got)==set(flat),'CSV fields')
        for k,v in flat.items():
            if isinstance(v,(int,float,F)) and not isinstance(v,bool):io.require(math.isclose(float(got[k]),float(v),rel_tol=1e-11,abs_tol=1e-9),'CSV number '+k)
            else:io.require(got[k]==str(v),'CSV identity '+k)
            fields+=1
    result={'integrity':'PASSED','exact_rational_identities':40,'both_wrong_cases_retained':8,'finite_atoms':44,'estimate_rows':2112,'fields_checked':fields,
        'auditor_sha256':io.sha(__file__),'completion_sha256':io.sha(out/'completion.json'),'artifact_sha256':done['artifact_sha256'],'wall_ns':perf_counter_ns()-start,
        'main_world_estimator_and_truth_functions_not_called':True,'new_environment_steps':0,'new_model_fits':0,'new_online_LLM_API_calls':0,
        'scope':'Independent rational finite tree and expanded estimator arithmetic; not unseen-data or robot-task qualification'}
    io.write(out/'audit.json',result);return result

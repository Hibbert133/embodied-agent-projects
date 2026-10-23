"""Independent scalar/Fraction audit; imports no new main mechanism functions."""
from fractions import Fraction
import hashlib,json,math,struct
from pathlib import Path


def check(ok,message):
    if not ok:raise ValueError('Independent signal-release audit: '+message)


def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def f32(x):return struct.unpack('<f',struct.pack('<f',x))[0]
def clip(x,lo,hi):return max(lo,min(hi,x))


def observation(o):
    check(set(o)=={'observation','success','terminated','truncated'} and len(o['observation'])==39,'public observation schema')
    check(all(type(n) in (int,float) and math.isfinite(n) for n in o['observation']),'finite public coordinates')
    check(all(type(o[k]) is bool for k in ('success','terminated','truncated')),'exact stop flags')


def memory_features(m):
    c=m['current'];b=m['controller']
    return [m['completed_steps']/500,*c['observation'],float(c['terminated']),float(c['truncated']),float(c['success']),
        *[v for row in b['matrix_xy'] for v in row],*b['offset'],*m['integral_xy'],math.log2(m['time_constant_s'])]


def expected_tensors(view):
    tasks=('push-v3','reach-v3','door-open-v3');actions=('CONTINUE','VALIDATE8','MOVE_MEASURE')
    phases=('VALIDATION_TASK','REPOSITION','MEASUREMENT');reasons=('NO_ACQUISITION','COMPLETE','EARLY_END','PARTIAL','BUDGET_KEEP')
    c=view['common'];before=c['before_memory'];after=c['post_memory']
    common=[float(t==before['task']) for t in tasks]+memory_features(before)+memory_features(after)
    common.extend(float(a==c['action']) for a in actions);common.append(c['paid_acquisition_steps']/72)
    common.extend(c['phase_counts'].get(p,0)/(64 if p=='REPOSITION' else 8) for p in phases);common.extend(float(v==c['reason']) for v in reasons)
    trace=[]
    for s in view['signal'] or []:
        trace.append([s['at_calls']/500,*s['command'],*s['before']['observation'],*s['after']['observation'],*[float(p==s['phase']) for p in phases]])
    flat=[v for row in trace for v in row]+[0.]*(72-len(trace))*86
    return dict(common=common,trace_present=trace,valid_steps=len(trace),trace_shape=[72,86],
        trace_sha256=hashlib.sha256(struct.pack('<'+'d'*len(flat),*flat)).hexdigest(),
        mask_sha256=hashlib.sha256(bytes([1]*len(trace)+[0]*(72-len(trace)))).hexdigest())


def audit_value(value):
    check(value['schema']=='INFORMATION_RELEASE_CONSTRUCTED_VERIFICATION_V1' and value['classification']=='SOFTWARE_ONLY_NOT_ROBOT_POPULATION','constructed scope')
    check(len(value['public_cases'])==18 and len(value['algebra_cases'])==36,'complete registered constructed population')
    scope={(c['task'],c['action'],c['terminal']) for c in value['public_cases']}
    check(scope=={(t,a,e) for t in ('push-v3','reach-v3','door-open-v3') for a in ('CONTINUE','VALIDATE8','MOVE_MEASURE') for e in (False,True)},'unique complete public fixture scope')
    scope={(c['probability'],tuple(c['constructed_potential_losses']),tuple(c['nuisance'])) for c in value['algebra_cases']}
    check(scope=={(p,y,m) for p in ('1/4','1/2','3/4') for y in ((40,200),(200,40),(200,200),(500,60)) for m in ((0,0),(100,100),(120,320))},'unique complete algebra scope')
    rows=views=commands=positive=negative=zero=unclipped=0
    for case in value['public_cases']:
        s=case['saved_return'];r=s['record'];b=r['before_memory'];a=r['post_memory'];trace=r['steps'];prior=b['current']
        check(b['task']==a['task']==case['task'] and r['action']==case['action'] and any(a['current'][k] for k in ('success','terminated','truncated'))==case['terminal'],'case/actual-record links')
        check(s['physical_finished_sequence']==100 and s['record_sha256']==digest(r),'sealed record binding')
        check(a['completed_steps']==b['completed_steps']+len(trace) and b['integral_xy']==a['integral_xy'],'continuous clock/carried integral')
        for i,step in enumerate(trace):
            check(step['at_calls']==b['completed_steps']+i and step['before']==prior,'consecutive actual trace within constructed fixture')
            check(all(not prior[k] for k in ('success','terminated','truncated')),'no step after stop')
            observation(step['before']);observation(step['after']);prior=step['after']
        check(prior==a['current'],'returned endpoint')
        for j,v in enumerate(case['views']):
            z=v['receipt'];binding=z['binding'];mv=z['model_view'];common=mv['common'];expose=bool(j)
            check(binding['record_sha256']==digest(r) and binding['view_sha256']==digest(mv),'release/view identity')
            check(binding['assigned_exposure']==expose and binding['assignment_probability']==.5 and binding['random_uniform']==(.25 if expose else .75),'registered assignment')
            check(binding['release_sequence']>binding['physical_finished_sequence']==100,'release follows physical return')
            check(common['before_memory']==b and common['post_memory']==a and common['paid_acquisition_steps']==len(trace),'same actual common information')
            check(mv['signal']==(trace if expose and trace else None),'supplemental trace only')
            check(v['tensors']==expected_tensors(mv),'independent feature bytes and masks')
            if case['terminal']:check(v['receiver_decision'] is None and v['next_command'] is None,'no receiver after stop')
            else:
                p=v['receiver_decision'];q=v['next_command'];use=[130,180,90,210] if expose and trace else [180,140,160,200]
                rates=(.125,.5,2.,8.);best=min(range(4),key=lambda i:(use[i],rates[i]!=.5,i));rate=rates[best]
                check(p['choice']['time_constant_s']==rate and p['choice']['risk_vector']==use,'saved choice genuinely determines gain')
                check(p['release_receipt_sha256']==digest(z),'saved receiver bound to assignment')
                after=p['gain_plan']['after_memory'];check({**after,'time_constant_s':a['time_constant_s']}==a,'rate changes no other returned state')
                check(p['gain_plan']['before_memory_sha256']==digest(a) and q['before_memory_sha256']==digest(after),'consume exact saved gain before next command')
                numbers=q['pi_plan']['numbers'];raw=q['pi_plan']['query']['raw_policy'];base=[f32(clip(x,-1,1)) for x in raw]
                expected=list(base)
                for d in (0,1):
                    integral=clip(a['integral_xy'][d]+.0125*raw[d]/rate,-2,2)
                    expected[d]=f32(clip(base[d]+integral,-1,1))
                check(numbers['sent_command']==expected,'independent scalar float32 next send')
                check(q['pi_plan_sha256']==digest(q['pi_plan']),'next plan bytes');commands+=1
            views+=1
        check(case['views'][0]['receipt']['model_view']['common']==case['views'][1]['receipt']['model_view']['common'],'all paired common views equal')
        if not trace:check(case['views'][0]['receipt']['model_view']==case['views'][1]['receipt']['model_view'],'empty trace full/masked identity')
        rows+=1
    for c in value['algebra_cases']:
        p=Fraction(c['probability']);y0,y1=map(Fraction,c['constructed_potential_losses']);m0,m1=map(Fraction,c['nuisance']);got=[]
        for release,(y,z) in enumerate(zip((y0,y1),c['outcomes'])):
            check(z['cutoff_loss']==y and z['release_receipt']['binding']['assigned_exposure']==bool(release),'constructed potential loss/assignment linkage')
            masked=m0+(y-m0)/(1-p) if not release else m0;full=m1+(y-m1)/p if release else m1
            t=z['target'];expected=(masked,full,full-masked)
            actual=(t['masked_full_program_risk'],t['released_full_program_risk'],t['supplemental_information_effect'])
            check(all(abs(float(x)-v)<1e-9 for x,v in zip(expected,actual)) and t['pseudo_targets_clipped'] is False,'independent signed Fraction AIPW values')
            got.append(expected);unclipped+=int(masked<0 or masked>500 or full<0 or full>500)
        check((1-p)*got[0][0]+p*got[1][0]==y0 and (1-p)*got[0][1]+p*got[1][1]==y1
            and (1-p)*got[0][2]+p*got[1][2]==y1-y0,'exact assignment expectation, only within constructed assumptions')
        positive+=int(y1>y0);negative+=int(y1<y0);zero+=int(y1==y0)
    return dict(integrity='PASSED',constructed_public_cases=rows,constructed_release_views=views,independently_rebuilt_next_commands=commands,
        constructed_algebra_settings=len(value['algebra_cases']),exact_positive_effects=positive,exact_negative_effects=negative,exact_zero_effects=zero,
        assignment_rows_with_unclipped_out_of_range_risks=unclipped,robot_population_size=0,new_environment_steps=0,new_model_fits=0,
        online_LLM_API_calls=0,physical_randomization_or_task_benefit_verified=False)


def audit_file(path):return audit_value(json.loads(Path(path).read_text(encoding='utf-8')))

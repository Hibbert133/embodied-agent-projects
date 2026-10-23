"""Separate public-feature, target, coefficient and selection reconstruction."""
from pathlib import Path
from collections import defaultdict
from time import perf_counter_ns
import math
import numpy as np
from src.analysis import release_learning_io_v1 as a
from src.analysis.release_learning_regression_v1 import independent_refit
io=a.io


def close(x,y,message):io.require(np.allclose(np.asarray(x,float),np.asarray(y,float),rtol=3e-10,atol=3e-10),message)
def same(x,y,message):io.require(io.digest(x)==io.digest(y),message)
def gid(c):return c['cohort']+'/'+str(c['group'])
def cid(c):return '/'.join(str(c[k]) for k in a.KEYS)


def source_cases(root,cohort):
    d=Path(root)/cohort.lower();r=io.read(d/'audit.json');io.require(r['integrity']=='PASSED','complete audited factual source')
    io.require(io.sha(d/'cases.jsonl.gz')==r['artifact_sha256']['cases.jsonl.gz'],'source actual-case bytes unchanged');return list(io.rows(d/'cases.jsonl.gz'))


def summary(rows):
    if not rows:return [0.]*18
    u=[r['command'] for r in rows];delta=[[r['after']['observation'][j]-r['before']['observation'][j] for j in range(3)] for r in rows]
    def mean(values):return math.fsum(values)/len(values)
    def sd(values):
        m=mean(values);return math.sqrt(math.fsum((v-m)**2 for v in values)/len(values))
    return [*[mean([r[j] for r in u]) for j in range(4)],*[sd([r[j] for r in u]) for j in range(4)],
        *[mean([r[j] for r in delta]) for j in range(3)],*[sd([r[j] for r in delta]) for j in range(3)],
        *[mean([x[i]*y[j] for x,y in zip(u,delta)]) for i in range(2) for j in range(2)]]


def memory(m):
    c=m['current'];b=m['controller']
    return [m['completed_steps']/500,*c['observation'],float(c['terminated']),float(c['truncated']),float(c['success']),
        *[v for row in b['matrix_xy'] for v in row],*b['offset'],*m['integral_xy'],math.log2(m['time_constant_s'])]


def pre_features(l):
    m=l['pre_memory'];h=l['prefix_history']
    return [float(t==m['task']) for t in ('push-v3','reach-v3','door-open-v3')]+memory(m)+summary(h)+summary(h[-8:])


def post_features(l,present):
    r=l['saved_return']['record'];b=r['before_memory'];p=r['post_memory'];steps=r['steps'];action=r['action']
    counts={phase:sum(s['phase']==phase for s in steps) for phase in ('VALIDATION_TASK','REPOSITION','MEASUREMENT')}
    common=[float(t==b['task']) for t in ('push-v3','reach-v3','door-open-v3')]+memory(b)+memory(p)
    common.extend(float(s==action) for s in ('CONTINUE','VALIDATE8','MOVE_MEASURE'));common.append(len(steps)/72)
    common.extend(counts[p]/(64 if p=='REPOSITION' else 8) for p in ('VALIDATION_TASK','REPOSITION','MEASUREMENT'))
    common.extend(float(s==r['reason']) for s in ('NO_ACQUISITION','COMPLETE','EARLY_END','PARTIAL','BUDGET_KEEP'))
    common+=summary(l['prefix_history'])+summary(l['prefix_history'][-8:])
    signal=[v for phase in ('VALIDATION_TASK','REPOSITION','MEASUREMENT') for v in summary([s for s in steps if s['phase']==phase] if present else [])]
    io.require(len(common)==159 and len(signal)==54,'independent feature dimensions');return common,common+signal


def predict(m,x):
    z=[(v-a)/s if active else 0. for v,a,s,active in zip(x,m['mean'],m['scale'],m['active'])];n=max(1,sum(m['active']));width=m['width']
    phi=[1.]+[math.exp(-math.fsum((v-a)**2 for v,a in zip(z,c))/(2*width**2*n)) for c in m['centers']]
    return math.fsum(p*b for p,b in zip(phi,m['coefficients']))


def receiver_risks(bundle,l):
    common,full=post_features(l,True);m=bundle['model'];base=[predict(v,common) for v in m['common']]
    present=bool(l['saved_return']['record']['steps']);masked=[v+predict(s,common) for v,s in zip(base,m['common_residual'])] if present else base
    enriched=[v+predict(s,full) for v,s in zip(base,m['signal_residual'])] if present else base
    return [round(min(500,max(0,v)),6) for v in masked],[round(min(500,max(0,v)),6) for v in enriched]


def check_tail_data(root,cohort,data):
    source=source_cases(root,cohort);lookup={r['case_id']:r for r in data['rows']};registry=data['complete_case_registry']
    io.require(len(registry)==len(source) and len(lookup)==len(data['rows']),'complete source/eligibility census');eligible=0
    for c,reg in zip(source,registry):
        l=c['learning'];why='EARLY_END_BEFORE_BOUNDARY' if l is None else 'ENDED_DURING_ACQUISITION' if l['receiver_decision'] is None else None
        same(reg,dict(case_id=cid(c),eligible=why is None,missing_reason=why,success=c['success'],deadline_loss=c['deadline_loss']),'independent tail missing reason')
        if why is not None:continue
        row=lookup[cid(c)];common,full=post_features(l,bool(l['saved_return']['record']['steps']))
        close(row['common'],common,'independent actual common features');close(row['full'],full,'independent actual signal features')
        same(row['y'],c['deadline_loss'],'actual fixed-rate task label');same(row['group'],gid(c),'independent group provenance')
        same(row['rate'],l['receiver_decision']['choice']['time_constant_s'],'factual consumed rate');same(row['present'],bool(l['saved_return']['record']['steps']),'actual nonempty signal')
        eligible+=1
    same(eligible,len(lookup),'extra synthetic/off-policy tail label');return source


def audit_receiver_bank(path):
    a.checked(path);root=Path(path).parent;folder=root/'models';start=perf_counter_ns();bank=io.read(folder/'receiver_bank.json');data=io.read(folder/'receiver_training_data.json')
    io.require(not (root/'tail_select').exists(),'bank audited before SELECT data');check_tail_data(root,'TAIL_TRAIN',data);ledger=[];errors=[]
    same(bank['data_sha256'],io.sha(folder/'receiver_training_data.json'),'receiver training bytes')
    for j,b in enumerate(bank['banks']):
        m=b['model'];width,ridge=a.GRID[j];same(b['receiver_version'],io.digest(m),'frozen receiver version');same((m['width'],m['ridge']),(width,ridge),'registered receiver grid')
        for k,rate in enumerate((.125,.5,2.,8.)):
            rows=[r for r in data['rows'] if r['rate']==rate];base=m['common'][k]
            same(base['width'],width,'common kernel width')
            errors.append(independent_refit(base,[r['common'] for r in rows],[r['y'] for r in rows],[r['group'] for r in rows],ridge,ledger,role=f'AUDIT_RECEIVER/{j}/COMMON/{k}',expected_centers=64))
            rows=[r for r in rows if r['present']];residual=[r['y']-predict(base,r['common']) for r in rows];signal=m['signal_residual'][k]
            matched=m['common_residual'][k];same(matched['width'],width,'matched common kernel width')
            errors.append(independent_refit(matched,[r['common'] for r in rows],residual,[r['group'] for r in rows],ridge,ledger,role=f'AUDIT_RECEIVER/{j}/MATCHED_COMMON/{k}',expected_centers=64))
            same(signal['width'],width,'signal kernel width')
            errors.append(independent_refit(signal,[r['full'] for r in rows],residual,[r['group'] for r in rows],ridge,ledger,role=f'AUDIT_RECEIVER/{j}/SIGNAL/{k}',expected_centers=64))
    same(len(bank['banks']),9,'full receiver bank');same(len(ledger),108,'all independent refits')
    result=dict(integrity='PASSED',source_bank_sha256=io.sha(folder/'receiver_bank.json'),training_data_sha256=io.sha(folder/'receiver_training_data.json'),
        independent_refit_ledger=ledger,independent_candidate_results=errors,max_coefficient_error=max(e['max_coefficient_error'] for e in errors),new_environment_steps=0,
        new_scientific_risk_refits=108,new_response_model_training=0,online_LLM_API_calls=0,wall_ns=perf_counter_ns()-start)
    io.write(folder/'receiver_bank_audit.json',result);return result


def group_mean(groups,values):
    rows=defaultdict(list)
    for g,y in zip(groups,values):rows[g].append(y)
    return math.fsum(math.fsum(y)/len(y) for y in rows.values())/len(rows)


def audit_receiver_selection(path):
    a.checked(path);root=Path(path).parent;folder=root/'models';start=perf_counter_ns();data=io.read(folder/'receiver_select_data.json');source=check_tail_data(root,'TAIL_SELECT',data)
    bank=io.read(folder/'receiver_bank.json');chosen=io.read(folder/'receiver_freeze.json');scores=[]
    for b in bank['banks']:
        losses=[]
        for r in data['rows']:
            k=(.125,.5,2.,8.).index(r['rate']);v=predict(b['model']['common'][k],r['common']);f=v+predict(b['model']['signal_residual'][k],r['full']) if r['present'] else v
            masked=v+predict(b['model']['common_residual'][k],r['common']) if r['present'] else v
            losses.append(.5*((min(500,max(0,masked))-r['y'])**2+(min(500,max(0,f))-r['y'])**2))
        scores.append(group_mean([r['group'] for r in data['rows']],losses))
    close(scores,chosen['selection_scores'],'independent entire SELECT factual MSE')
    index=next(j for j,v in enumerate(chosen['selection_scores']) if v<=min(chosen['selection_scores'])+1e-6)
    io.require(scores[index]<=min(scores)+1e-6+1e-7,'independent receiver winner tolerance')
    same(index,chosen['selected_index'],'independent receiver winner');same(chosen['model'],bank['banks'][index]['model'],'no post-SELECT refit')
    fixed=[math.fsum(c['deadline_loss'] for c in source if c['program']==p)/sum(c['program']==p for c in source) for p in a.programs('TAIL_SELECT')]
    j=min(range(len(fixed)),key=lambda i:(fixed[i],a.programs('TAIL_SELECT')[i]!='TAIL_CONTINUE_1',i));same(chosen['best_fixed_program']['program'],a.programs('TAIL_SELECT')[j],'independent full-population fixed program')
    close(fixed,chosen['best_fixed_program']['all_mean_cutoff_losses'],'all fixed programs retained')
    io.require(not (root/'gate_train').exists(),'receiver locked before GATE data');same(chosen['receiver_version'],io.digest(chosen['model']),'selected receiver identity')
    used=sorted({g for m in chosen['model']['common'] for g in m['training_groups']}|{r['group'] for r in data['rows']})
    same(chosen['development_groups_used'],used,'all receiver fitting and model-selection groups retained')
    result=dict(integrity='PASSED',selected_index=index,receiver_version=chosen['receiver_version'],receiver_artifact_sha256=io.sha(folder/'receiver_freeze.json'),
        selection_data_sha256=io.sha(folder/'receiver_select_data.json'),new_model_fits=0,new_environment_steps=0,online_LLM_API_calls=0,wall_ns=perf_counter_ns()-start)
    io.write(folder/'receiver_audit.json',result);return result


def check_gate_data(root,data):
    source=source_cases(root,'GATE_TRAIN');lookup={r['case_id']:r for r in data['rows']};registry=data['complete_case_registry']
    bundle=io.read(Path(root)/'models/receiver_freeze.json');same(data['receiver_sha256'],io.sha(Path(root)/'models/receiver_freeze.json'),'fixed receiver source')
    same(data['receiver_version'],bundle['receiver_version'],'target closure version')
    groups=bundle['development_groups_used'];same(data['nuisance_training_groups'],groups,'all independent nuisance fit/selection groups')
    same(len(registry),len(source),'complete GATE eligibility population');same(len(lookup),len(data['rows']),'no duplicate labels');count=0
    for c,reg in zip(source,registry):
        l=c['learning'];same(reg,dict(case_id=cid(c),eligible=l is not None,missing_reason=None if l is not None else 'EARLY_END_BEFORE_BOUNDARY',deadline_loss=c['deadline_loss']),'complete gate missing reasons')
        if l is None:continue
        row=lookup[cid(c)];close(row['x'],pre_features(l),'independent actual pre-acquisition history')
        same(row['action'],l['saved_return']['record']['action'],'actual acquisition action label');same(row['group'],gid(c),'source group')
        io.require(gid(c) not in groups and all(g.startswith(('TAIL_TRAIN/','TAIL_SELECT/')) for g in groups),'honest entire-group nuisance exclusion including selection')
        b=l['release_receipt']['binding'];same(b['receiver_version'],bundle['receiver_version'],'actually deployed receiver binding');same(b['assignment_probability'],.5,'known propensity')
        same(row['release'],b['assigned_exposure'],'actual randomized assignment');same(row['y'],c['deadline_loss'],'actual full-program terminal label')
        base,full=receiver_risks(bundle,l)
        io.require(abs(row['mu0']-min(base))<=1.01e-6 and abs(row['mu1']-min(full))<=1.01e-6,'independent frozen nuisance risks, one microstep numerical resolution')
        post=l['saved_return']['record']['post_memory'];terminal=any(post['current'][k] for k in ('success','terminated','truncated')) or post['completed_steps']==500
        identical=terminal or not l['saved_return']['record']['steps'];y=c['deadline_loss'];mu0=row['mu0'];mu1=row['mu1'];expose=row['release']
        if identical:masked=full=y
        else:
            masked=mu0 if expose else mu0+2*(y-mu0)
            full=mu1+2*(y-mu1) if expose else mu1
        t=row['target'];close([t['masked_full_program_risk'],t['released_full_program_risk'],t['supplemental_information_effect']],
            [masked,full,full-masked],'independent signed unclipped AIPW labels')
        same(t['pseudo_targets_clipped'],False,'no target clipping');same(t['known_before_release_terminal'],terminal,'known actual terminal before receiving')
        same(t['identical_views_or_pre_release_terminal'],identical,'known structural equality');count+=1
    same(count,len(lookup),'no unexecuted or old-source label');return source


def audit_pre_bank(path):
    a.checked(path);root=Path(path).parent;folder=root/'models';start=perf_counter_ns();data=io.read(folder/'gate_training_data.json');check_gate_data(root,data)
    bank=io.read(folder/'pre_bank.json');same(bank['gate_data_sha256'],io.sha(folder/'gate_training_data.json'),'training target bytes')
    io.require(not (root/'cal').exists(),'pre-risk bank before calibration outcomes');ledger=[];errors=[]
    def refit(model,rows,y,ridge,role):
        errors.append(independent_refit(model,[r['x'] for r in rows],y,[r['group'] for r in rows],ridge,ledger,role=role,expected_centers=32))
    for j,b in enumerate(bank['banks']):
        width,ridge=a.GRID[j];same((b['width'],b['ridge']),(width,ridge),'independent pre-risk grid')
        body={k:v for k,v in b.items() if k!='policy_version'};same(b['policy_version'],io.digest(body),'pre-bank policy version')
        for action in ('CONTINUE','VALIDATE8','MOVE_MEASURE'):
            rows=[r for r in data['rows'] if r['action']==action];m=b['effect'][action]
            same(m['masked']['width'],width,'pre-risk kernel width');refit(m['masked'],rows,[r['target']['masked_full_program_risk'] for r in rows],ridge,f'AUDIT_PRE/{j}/{action}/M')
            if action!='CONTINUE':
                same(m['effect']['width'],width,'effect kernel width');refit(m['effect'],rows,[r['target']['supplemental_information_effect'] for r in rows],ridge,f'AUDIT_PRE/{j}/{action}/D')
                for expose,key in ((False,'masked'),(True,'full')):
                    observed=[r for r in rows if r['release']==expose];d=b['direct'][action][key];same(d['width'],width,'direct matched-capacity width')
                    refit(d,observed,[r['y'] for r in observed],ridge,f'AUDIT_PRE/{j}/{action}/DIRECT/{key}')
            else:
                same(m['effect'],None,'empty action has no effect model');d=b['direct'][action]['masked'];same(d['width'],width,'direct empty-action width')
                refit(d,rows,[r['y'] for r in rows],ridge,f'AUDIT_PRE/{j}/{action}/DIRECT')
    same(len(ledger),90,'all independent pre-risk fits')
    result=dict(integrity='PASSED',source_bank_sha256=io.sha(folder/'pre_bank.json'),gate_data_sha256=io.sha(folder/'gate_training_data.json'),
        independent_refit_ledger=ledger,independent_candidate_results=errors,new_scientific_risk_refits=90,max_coefficient_error=max(e['max_coefficient_error'] for e in errors),
        new_environment_steps=0,new_response_model_training=0,online_LLM_API_calls=0,wall_ns=perf_counter_ns()-start)
    io.write(folder/'pre_bank_audit.json',result);return result


def audit_policy_lock(path):
    a.checked(path);root=Path(path).parent;folder=root/'models';lock=io.read(folder/'policy_lock.json');bank=io.read(folder/'pre_bank.json');source=source_cases(root,'CAL')
    units=defaultdict(dict)
    for c in source:
        key=(c['group'],c['task'],c['context']);io.require(c['program'] not in units[key],'duplicate calibration arm');units[key][c['program']]=c
    scores={k:[[] for _ in a.GRID] for k in ('effect','direct')}
    for arms in units.values():
        same(sorted(arms),sorted(a.programs('CAL')),'all five actual CAL procedures');l=arms['CAL_CONTINUE_MASK']['learning']
        for j in range(9):
            for kind in scores:
                if l is None:loss=arms['CAL_CONTINUE_MASK']['deadline_loss']
                else:
                    p=l['cal_predictions'][j][kind];name='CAL_'+p['action']+('_FULL' if p['expose'] and p['action']!='CONTINUE' else '_MASK')
                    io.require(name in arms,'unexecuted calibration outcome');loss=arms[name]['deadline_loss']
                scores[kind][j].append(loss)
    score={k:[math.fsum(v)/len(v) for v in vv] for k,vv in scores.items()};close(score['effect'],lock['CAL_mean_full_cutoff_losses']['effect'],'entire calibration effect selection')
    close(score['direct'],lock['CAL_mean_full_cutoff_losses']['direct'],'entire calibration direct selection')
    for kind in scores:
        j=min(range(9),key=lambda q:(score[kind][q],q));same(j,lock['selected_grid_indices'][kind],'frozen CAL winner');same(lock[kind],bank['banks'][j][kind],'no model alteration on CAL')
    io.require(not (root/'dev').exists(),'policy lock audited before own-history deployment')
    result=dict(integrity='PASSED',policy_version=lock['policy_version'],policy_lock_sha256=io.sha(folder/'policy_lock.json'),
        new_model_fits=0,new_environment_steps=0,online_LLM_API_calls=0)
    io.write(folder/'policy_lock_audit.json',result);return result

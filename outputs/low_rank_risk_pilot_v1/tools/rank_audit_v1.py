"""Second decoder, augmented LS/QR/SVD instead of main dual solve/eigenfit."""
import numpy as np


def check(ok,msg):
    if not ok:raise ValueError('independent: '+msg)


def feature_vector(v):
    check(set(v)=={'schema','stage','task','completed_steps','current','integral_xy','controller','history','acquisition_action'}
        and v['schema']=='COMPLETE_RISK_PUBLIC_NODE_V1' and v['stage']=='PRE' and v['acquisition_action'] is None,'public PRE schema')
    task=v['task'];n=v['completed_steps'];check(n in (16,32,64) and len(v['history'])==n,'boundary')
    values=[int(task==t) for t in ('push-v3','reach-v3','door-open-v3')]
    values+=v['current']['observation']+v['integral_xy']+[n/500,0,0,0]
    for row in v['history']:
        values.extend(row['before']['observation']);values.extend(row['command']);values.extend(row['after']['observation']);values.append(1)
    values.extend([0]*(41548-len(values)));return np.asarray(values,dtype=np.float64)


def group_weights(g):
    counts={k:sum(int(v==k) for v in g) for k in set(g)}
    return np.asarray([len(g)/len(counts)/counts[k] for k in g],float)


def coordinates():
    columns=[]
    for j in range(11):
        v=np.array([int(k==j)-int(k==11) for k in range(12)],float)
        for b in columns:v=v-np.sum(v*b)*b
        columns.append(v/np.sqrt(np.sum(v*v)))
    return np.stack(columns,axis=1)


def canonical(v,spectrum):
    values=np.zeros(v.shape[1]);values[:len(spectrum)]=spectrum
    tol=1e-10*max(1.,float(np.max(np.abs(values))));start=0
    while start<len(values):
        stop=start+1
        while stop<len(values) and abs(values[stop]-values[start])<=tol:stop+=1
        if stop-start>1:
            old=v[:,start:stop];p=old@old.T;chosen=[]
            for j in range(len(p)):
                q=p[:,j].copy()
                for b in chosen:q=q-np.sum(b*q)*b
                length=np.sqrt(np.sum(q*q))
                if length>1e-8:chosen.append(q/length)
                if len(chosen)==stop-start:break
            check(len(chosen)==stop-start,'canonical degeneracy');v[:,start:stop]=np.stack(chosen,axis=1)
        start=stop
    return v


def gram(x,y,kind):
    d=max(1,x.shape[1])
    if kind=='LINEAR':return x@y.T/d
    dist=np.maximum(np.einsum('ij,ij->i',x,x)[:,None]+np.einsum('ij,ij->i',y,y)[None,:]-2*x@y.T,0)/d
    return np.exp(-.5*dist)


def reconstruct(x,y,groups,kind,x_test,ledger):
    w=group_weights(list(map(int,groups)));p=w/np.sum(w);a=np.where(np.max(x,axis=0)!=np.min(x,axis=0))[0]
    mean=np.sum(x[:,a]*p[:,None],axis=0);scale=np.maximum(np.sqrt(np.sum((x[:,a]-mean)**2*p[:,None],axis=0)),.05)
    z=np.minimum(10,np.maximum(-10,(x[:,a]-mean)/scale));zz=np.minimum(10,np.maximum(-10,(x_test[:,a]-mean)/scale))
    k=gram(z,z,kind);one=np.ones((len(x),1));h=np.eye(len(x))-one*p[None,:];kc=h@k@h.T
    eig,u=np.linalg.eigh((kc+kc.T)/2);ledger['kernel_eigendecompositions']+=1
    check(eig.min()>=-1e-8*max(1.,np.abs(eig).max()),'PSD within numerical roundoff')
    root=u*np.sqrt(np.maximum(eig,0))[None,:];sw=np.sqrt(w)
    design=np.vstack([sw[:,None]*root,np.sqrt(.01)*np.eye(len(x))]);ym=np.sum(y*p[:,None],axis=0)
    yc=y-ym;target=np.vstack([sw[:,None]*yc,np.zeros_like(yc)])
    beta=np.linalg.lstsq(design,target,rcond=None)[0];ledger['augmented_lstsq']+=1
    q,_=np.linalg.qr(design,mode='reduced');ledger['augmented_QR']+=1
    t=q.T@target;d=coordinates()
    _,s,raw_v=np.linalg.svd(t,full_matrices=True);ledger['rank_SVD']+=1;raw=canonical(raw_v.T.copy(),s*s)
    _,s,rv=np.linalg.svd(t@d,full_matrices=True);ledger['rank_SVD']+=1;contrast=d@canonical(rv.T.copy(),s*s)
    # This extra PCA SVD is independent of kernel; counted once per kernel here.
    _,s,pv=np.linalg.svd((sw[:,None]*yc)@d,full_matrices=True);ledger['PCA_SVD']+=1;pca=d@canonical(pv.T.copy(),s*s)
    alpha=w[:,None]*(yc-root@beta)/.01
    kk=gram(zz,z,kind);centered=kk-(p@k)[None,:]-(kk@p)[:,None]+float(p@k@p)
    predictions={};projectors={}
    definitions=[('FULL',12,'FULL')]+[('RR'+str(r),r,'C') for r in (1,2,4)]+[('PCA'+str(r),r,'P') for r in (1,2,4)]+[('RAW_RR2',2,'R'),('RAW_RR3',3,'R')]
    for name,r,mode in definitions:
        if mode=='FULL':project=np.eye(12)
        else:
            b=raw if mode=='R' else pca if mode=='P' else contrast
            project=b[:,:r]@b[:,:r].T
            if mode!='R':project=project+np.ones((12,12))/12
        projectors[kind+'_'+name]=project
        predictions[kind+'_'+name]=centered@(alpha@project)+ym;ledger['reconstructed_model_solutions']+=1
    return predictions,projectors


def audit_metrics(records,population,summary,score_rows):
    programs=list(summary['programs']);check(len(programs)==31,'18 learned + empirical mean + 12 fixed programs')
    by={(r['model'],r['unit_index']):r for r in records};check(len(by)==len(records)==31*54,'all supported selections')
    scores={(r['unit_index'],r['model']):np.array(r['scores']) for r in score_rows}
    for r in score_rows:
        check(r['training_groups']==[g for g in range(9) if g!=population[r['unit_index']]['group']],'no heldout groups in score provenance')
    for r in records:
        u=population[r['unit_index']];name=r['model']
        if not u['pre_available']:index=None
        elif name.startswith('FIXED_'):index=int(name[-2:])
        else:
            if name=='TASK_BOUNDARY_MEAN':
                train=[q for q in population if q['pre_available'] and q['group']!=u['group']]
                for mode in (0,1,2):
                    selected=[q for q in train if mode==2 or q['task']==u['task'] and (mode==1 or q['boundary']==u['boundary'])]
                    if selected:break
                per_group=[]
                for group in sorted({q['group'] for q in selected}):
                    per_group.append(np.mean([q['losses'] for q in selected if q['group']==group],axis=0))
                vector=np.mean(per_group,axis=0)/500
            else:vector=scores[(u['unit_index'],name)]
            bounded=np.maximum(0,np.minimum(1,vector));index=next(i for i,v in enumerate(bounded) if v<=min(bounded)+1e-10)
        leaf=0 if index is None else index
        check(r['selected_index']==index and r['loss']==u['losses'][leaf] and r['success']==u['successes'][leaf]
            and r['source_case_key']==u['source_case_keys'][leaf] and r['source_case_sha256']==u['source_case_sha256'][leaf],'selected factual complete leaf')
    for model in programs:
        rows=[by[(model,i)] for i in range(54)];groups={}
        for g in range(9):
            rs=[r for r in rows if population[r['unit_index']]['group']==g]
            check(len(rs)==6,'all task/context units');groups[str(g)]=sum(r['loss'] for r in rs)/6
        score=summary['programs'][model]
        check(abs(score['mean_deadline_loss']-sum(groups.values())/9)<1e-10 and score['group_means']==groups,'equal-group full loss')
        check(score['success']==sum(r['success'] for r in rows),'success denominator')
        if 'factual_prediction' in score:
            m={};cc={};counts={}
            for group in range(9):
                eligible=[q for q in population if q['group']==group and q['pre_available']];counts[str(group)]=len(eligible)
                full=[];contrast=[]
                for q in eligible:
                    v=np.maximum(0,np.minimum(1,scores[(q['unit_index'],model)]));actual=np.asarray(q['losses'])/500
                    full.append(sum((float(v[i])-float(actual[i]))**2 for i in range(12))/12)
                    dv=v-sum(v)/12;dy=actual-sum(actual)/12;contrast.append(sum((float(dv[i])-float(dy[i]))**2 for i in range(12))/12)
                m[str(group)]=sum(full)/len(full) if full else None;cc[str(group)]=sum(contrast)/len(contrast) if contrast else None
            target=score['factual_prediction'];check(target['available_by_group']==counts and target['available']==sum(counts.values()),'prediction availability')
            check(abs(target['full_vector_normalized_MSE']-sum(v for v in m.values() if v is not None)/sum(v is not None for v in m.values()))<1e-10
                and abs(target['contrast_normalized_MSE']-sum(v for v in cc.values() if v is not None)/sum(v is not None for v in cc.values()))<1e-10,'prediction quality separate from task value')
    return len(records)

"""Public-only learning handoff and independent mathematical export audit."""
from pathlib import Path
from time import perf_counter_ns
import numpy as np
from src.analysis import occam_reference_train_io_v3 as a
from src.analysis.occam_training_data_v1 import project,weighted_stats,normalize
from src.analysis.occam_performance_independent_v1 import batch_posterior
from src.probe.occam_performance_core_v1 import basis_forward,forecast,update
io=a.io


def prepare_learning(path):
    path=Path(path).resolve();m=a.checked(path);out=path.parent;train=io.read(out/'train/audit.json')
    io.require(not (out/'CLOSED_TECHNICAL_FAILURE.json').exists(),'closed allocation cannot train')
    for phase in ('native','train'):
        process=io.read(out/phase/'process_audit.json')
        io.require(process['integrity']=='PASSED_ISOLATED_PROCESS_AND_BYTE_CONTINUITY_ONLY' and process['executions']==(36 if phase=='native' else 648),'both complete process audits before learning')
    io.require(train['integrity']=='PASSED' and train['counts']['executions']==648,'complete independently audited TRAIN')
    io.require(not (out/'learning_spec.json').exists(),'one learning handoff')
    public=out/'train/public_trajectories.jsonl.gz';io.require(io.sha(public)==train['public_trajectories_sha256'],'audited public input')
    needed=['src/analysis/occam_reference_learner_v3.py','src/analysis/occam_training_data_v1.py',
        'src/analysis/occam_meta_torch_v1.py','src/probe/occam_performance_core_v1.py','src/probe/occam_public_history_v1.py',
        'src/probe/occam_window_cost_v1.py','src/analysis/response_qualification_io_v1.py','scripts/train_occam_reference_v3.py']
    for n in needed:io.require(io.sha(a.ROOT/n)==m['source_sha256'][n],'frozen learner source')
    spec=dict(schema='OCCAM_PUBLIC_LEARNING_SPEC_V1',learning=a.learning(),allocated_episodes=648,
        public_trajectories=str(public),public_sha256=io.sha(public),learning_source_sha256={n:io.sha(a.ROOT/n) for n in needed},
        source_manifest_id=m['manifest_id'],no_private_or_registry_input=True)
    io.write(out/'learning_spec.json',spec);return out/'learning_spec.json'


def audit_learning(path):
    from src.analysis.release_learning_guard_v1 import read_only
    path=Path(path).resolve();a.checked(path);base=path.parent;out=base/'learning';result=io.read(out/'complete.json');start=perf_counter_ns()
    io.require(result['integrity']=='PASSED','failed training cannot promote a bank');spec=io.read(base/'learning_spec.json')
    io.require(io.sha(spec['public_trajectories'])==spec['public_sha256']==result['public_source_sha256'],'public bytes fixed')
    guard={};checks={};solves=0
    with read_only(guard,max_solve=5000):
        sequences=[project(r['value']) for r in io.rows(spec['public_trajectories'])];io.require(len(sequences)==648,'all TRAIN episodes')
        expected=weighted_stats(sequences);saved=io.read(out/'normalization.json')
        for k in expected:
            if isinstance(expected[k],list) or type(expected[k]) is float:io.require(np.allclose(expected[k],saved[k],atol=1e-11,rtol=1e-12),'TRAIN-only stats across runtimes '+k)
            else:io.require(expected[k]==saved[k],'normalization provenance '+k)
        for label in ('PRETRAIN','META_FINAL','MATCHED_ERM_FINAL'):
            bank=io.read(out/(label+'_raw.json'));normalized=io.read(out/(label+'_normalized.json'));c=io.read(out/(label+'_export_checks.json'))
            io.require(io.sha(out/(label+'_raw.json'))==c['raw_bank_sha256']==result['checkpoints'][label]['raw_sha256'],'frozen exported bank')
            max_basis=max_prediction=max_posterior=0.;episodes=0
            for fixture in c['fixtures']:
                actual=basis_forward(bank,np.asarray(fixture['history']),np.asarray(fixture['descriptor']));max_basis=max(max_basis,float(np.max(abs(actual-np.asarray(fixture['expected_raw_basis'])))))
            for seq in sequences:
                if not len(seq['targets']):continue
                H,X,Y=normalize(saved,seq['history'],seq['descriptor'],seq['targets']);phi=basis_forward(normalized,H,X);raw_phi=basis_forward(bank,seq['history'],seq['descriptor'])
                pn=normalized['prior'];pr=bank['prior'];mu=np.asarray(pn['mean']);P=np.asarray(pn['covariance']);rm=np.asarray(pr['mean']);RP=np.asarray(pr['covariance']);history=[];ys=[]
                for j in range(len(Y)):
                    f=forecast(mu,P,phi[j],pn['measurement_covariance']);g=forecast(rm,RP,raw_phi[j],pr['measurement_covariance'])
                    max_prediction=max(max_prediction,abs(float(g['mean'][0]-(f['mean'][0]*saved['target_scale']+saved['target_mean']))))
                    io.require(np.allclose(g['latent_covariance'],f['latent_covariance']*saved['target_scale']**2,atol=1e-10,rtol=1e-10),'physical covariance units')
                    if seq['full_window'][j]:
                        n=update(mu,P,phi[j],Y[j],pn['process_covariance'],pn['measurement_covariance']);r=update(rm,RP,raw_phi[j],seq['targets'][j],pr['process_covariance'],pr['measurement_covariance'])
                        mu,P=n['mean'],n['covariance'];rm,RP=r['mean'],r['covariance'];history.append(raw_phi[j]);ys.append(seq['targets'][j]);solves+=2
                if history:
                    bm,bp=batch_posterior(pr['mean'],pr['covariance'],np.asarray(history),np.asarray(ys),pr['process_covariance'],pr['measurement_covariance']);solves+=1
                    max_posterior=max(max_posterior,float(np.max(abs(bm-rm))),float(np.max(abs(bp-RP))))
                episodes+=1
                if episodes==16:break
            io.require(episodes>0 and max_basis<=1e-10 and max_prediction<=1e-9 and max_posterior<=1e-8,'independent export/recursive/batch numerical agreement')
            checks[label]=dict(episodes=episodes,max_basis_difference=max_basis,max_prediction_difference=max_prediction,max_batch_posterior_difference=max_posterior)
    final=dict(integrity='PASSED',checks=checks,independent_analysis_solves=solves,guard=guard,source_public_sha256=spec['public_sha256'],
        no_independent_training_repeated=True,no_predictive_or_task_qualification_claim=True,new_environment_interactions=0,online_LLM_API_calls=0,wall_ns=perf_counter_ns()-start)
    io.write(out/'model_audit.json',final);a.checked(path);return final

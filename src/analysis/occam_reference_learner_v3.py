"""Pinned CPU performance-reference training; no simulator or private data API."""
from copy import deepcopy
from contextlib import contextmanager
from pathlib import Path
from time import perf_counter_ns
from unittest.mock import patch
import builtins,hashlib,importlib.abc,io as streams,json,sys
import numpy as np
import torch
from src.analysis import response_qualification_io_v1 as io
from src.analysis.occam_training_data_v1 import project,weighted_stats,normalize,export_raw
from src.analysis.occam_meta_torch_v1 import PerformanceBasis,meta_loss
from src.probe.occam_performance_core_v1 import basis_forward
from src.analysis import occam_reference_train_io_v3 as allocation


@contextmanager
def public_only_guard(receipt,public_path,spec_path,out):
    forbidden=('metaworld','mujoco','gymnasium','src.rollout');counts={'physics_import_attempts':0,'private_or_old_output_read_attempts':0};network={}
    class Block(importlib.abc.MetaPathFinder):
        def find_spec(self,fullname,path=None,target=None):
            if any(fullname==p or fullname.startswith(p+'.') for p in forbidden):
                counts['physics_import_attempts']+=1;raise RuntimeError('physics forbidden in isolated training')
    io.require(not any(any(n==p or n.startswith(p+'.') for p in forbidden) for n in sys.modules),'clean physics-free learner process')
    original=builtins.open;allowed={Path(public_path).resolve(),Path(spec_path).resolve()};out=Path(out).resolve()
    def opened(file,*args,**kw):
        if isinstance(file,(str,Path)):
            p=Path(file).resolve()
            if p.is_relative_to((io.ROOT/'outputs').resolve()) and p not in allowed and not p.is_relative_to(out):
                counts['private_or_old_output_read_attempts']+=1;raise RuntimeError('private/old output forbidden in learning')
        return original(file,*args,**kw)
    blocker=Block();sys.meta_path.insert(0,blocker)
    try:
        with io.forbid_online_calls(network),patch.object(builtins,'open',opened),patch.object(streams,'open',opened):yield
    finally:sys.meta_path.remove(blocker);receipt.update(counts=counts,network=network,new_physics=0,online_LLM_API_calls=0)


def sequence_loss(model,seq,mode,rng,max_support):
    if not len(seq['targets']):return None,0
    H=torch.as_tensor(seq['history'],dtype=torch.float64);X=torch.as_tensor(seq['descriptor'],dtype=torch.float64);Y=torch.as_tensor(seq['targets'],dtype=torch.float64)
    eligible=np.flatnonzero(seq['full_window'] & ~seq['terminal']).tolist()
    n=int(rng.integers(0,min(max_support,len(eligible))+1)) if mode=='META' else 0
    if n:return meta_loss(model,H,X,Y,eligible[:n])[0],n
    phi=model(H,X);mean=model.prior()[0];return ((torch.einsum('tyb,b->ty',phi,mean)-Y)**2).mean(),0


def stage(model,optimizer,sequences,*,attempts,batch_size,mode,rng,max_support,counters,progress=None,support_rng=None,deadline_ns=None):
    io.require(mode in ('ERM','META') and type(attempts) is int and attempts>=0,'declared stage')
    for attempt in range(attempts):
        if deadline_ns is not None:io.require(perf_counter_ns()<=deadline_ns,'frozen training wall budget reached')
        optimizer.zero_grad(set_to_none=True);losses=[];supports=0;indices=rng.integers(0,len(sequences),batch_size).tolist()
        for index in indices:
            loss,n=sequence_loss(model,sequences[index],mode,rng if support_rng is None else support_rng,max_support);supports+=n
            if loss is not None:losses.append(loss)
        counters['allocated_episode_draws']+=batch_size;counters['inner_filter_updates']+=supports;counters['attempts']+=1
        if losses:
            loss=sum(losses)/batch_size;io.require(torch.isfinite(loss).item(),'nonfinite training loss')
            loss.backward();grads=[p.grad for p in model.parameters() if p.grad is not None]
            io.require(grads and all(torch.isfinite(g).all().item() for g in grads),'nonfinite gradients')
            torch.nn.utils.clip_grad_norm_(model.parameters(),10.,error_if_nonfinite=True);counters['optimizer_step_attempts']+=1
            optimizer.step();counters['Adam_updates']+=1
            mean,P,Q,R=model.prior();io.require(all(torch.isfinite(v).all().item() for v in (mean,P,Q,R)) and R[0,0].item()>0,'invalid learned prior after optimizer')
            last=float(loss.detach())
        else:counters['empty_batches']+=1;last=None
        if progress is not None and (attempt%100==0 or attempt==attempts-1):progress(attempt+1,last,indices)


def validate_spec(spec,spec_path,out):
    io.require(type(spec) is dict and set(spec)=={'schema','learning','allocated_episodes','public_trajectories','public_sha256','learning_source_sha256',
        'source_manifest_id','no_private_or_registry_input'} and spec['schema']=='OCCAM_PUBLIC_LEARNING_SPEC_V1','strict public learning spec')
    spec_path=Path(spec_path).resolve();out=Path(out).resolve()
    io.require(spec_path.name=='learning_spec.json' and spec_path.parent.parent==allocation.OUTPUT.resolve()
        and out==spec_path.parent/'learning' and Path(spec['public_trajectories']).resolve()==spec_path.parent/'train/public_trajectories.jsonl.gz','only owned TRAIN source; no CAL/QUAL/NATIVE')
    io.require(spec['learning']==allocation.learning() and spec['allocated_episodes']==648 and spec['no_private_or_registry_input'] is True,'frozen actual learning allocation')


def train(spec_path,out):
    spec_path=Path(spec_path).resolve();spec=io.read(spec_path);out=Path(out).resolve()
    validate_spec(spec,spec_path,out)
    out.mkdir(exist_ok=False)
    cfg=spec['learning'];public=Path(spec['public_trajectories']);start=perf_counter_ns();counts=dict(Adam_updates=0,optimizer_step_attempts=0,attempts=0,allocated_episode_draws=0,inner_filter_updates=0,empty_batches=0);guard={};solves=0
    io.require(torch.__version__=='2.2.2+cpu' and np.__version__=='1.26.4' and not torch.cuda.is_available(),'pinned existing CPU training runtime')
    torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.use_deterministic_algorithms(True);torch.manual_seed(cfg['model_init_rng_seed'])
    original_solve=torch.linalg.solve;failure=None;checkpoints={};raw_arrays=[];model=None;active_model=None;available_by_task={}
    def solve(*args,**kw):
        nonlocal solves
        solves+=1;io.require(solves<=cfg['all_training_linear_solves_max'],'training solve cap');return original_solve(*args,**kw)
    def progress(label):
        def saved(attempt,loss,indices):
            io.write(out/'status.json',dict(status='RUNNING',stage=label,stage_attempt=attempt,loss=loss,counters=counts,solve_attempts=solves,
                last_draws=indices,wall_ns=perf_counter_ns()-start),exclusive=False)
        return saved
    try:
        with public_only_guard(guard,public,spec_path,out),patch.object(torch.linalg,'solve',solve):
            io.require(io.sha(public)==spec['public_sha256'],'audited TRAIN public bytes')
            for n,h in spec['learning_source_sha256'].items():io.require(io.sha(io.ROOT/n)==h,'frozen learner source changed '+n)
            for i,row in enumerate(io.rows(public)):
                io.require(type(row) is dict and set(row)=={'sequence','value'} and row['sequence']==i,'all sequential public TRAIN episodes')
                raw_arrays.append(project(row['value']))
            io.require(len(raw_arrays)==spec['allocated_episodes'],'complete TRAIN denominator')
            available_by_task={t:sum(s['task']==t and len(s['targets'])>0 for s in raw_arrays) for t in ('push-v3','reach-v3','door-open-v3')}
            io.require(all(available_by_task.values()),'no observed labels for a registered task; do not resample')
            stats=weighted_stats(raw_arrays);io.write(out/'normalization.json',stats);sequences=[]
            for seq in raw_arrays:
                H,X,Y=normalize(stats,seq['history'],seq['descriptor'],seq['targets']);sequences.append({**seq,'history':H,'descriptor':X,'targets':Y})
            model=PerformanceBasis(664,87,bases=cfg['bases'],outputs=1,context_size=cfg['context_size'],encoder_hidden=tuple(cfg['encoder_hidden']),head_hidden=tuple(cfg['head_hidden']))
            active_model=model
            with torch.no_grad():model.prior_mean.fill_(1/np.sqrt(cfg['bases']))
            optimizer=torch.optim.AdamW(model.parameters(),lr=cfg['learning_rate'],weight_decay=cfg['weight_decay'])
            rng=np.random.default_rng(cfg['optimizer_rng_seed'])
            def save(label,value):
                normalized=value.export();raw=export_raw(normalized,stats);io.write(out/(label+'_normalized.json'),normalized);io.write(out/(label+'_raw.json'),raw)
                fixture=[]
                for ordinal,seq in enumerate(raw_arrays):
                    if len(seq['targets']):
                        h=seq['history'][:1];x=seq['descriptor'][:1];nh,nx,_=normalize(stats,h,x)
                        with torch.no_grad():expected=value(torch.as_tensor(nh,dtype=torch.float64),torch.as_tensor(nx,dtype=torch.float64)).numpy()
                        actual=basis_forward(raw,h,x);expected=np.concatenate([expected*stats['target_scale'],np.full((*expected.shape[:2],1),stats['target_mean'])],axis=2)
                        io.require(np.allclose(actual,expected,atol=1e-10,rtol=1e-12),'folded Torch/NumPy raw basis differs')
                        fixture.append(dict(episode_ordinal=ordinal,history=h.tolist(),descriptor=x.tolist(),expected_raw_basis=expected.tolist()))
                    if len(fixture)==32:break
                io.write(out/(label+'_export_checks.json'),dict(integrity='PASSED',fixtures=fixture,raw_bank_sha256=io.sha(out/(label+'_raw.json'))))
                checkpoints[label]=dict(normalized_sha256=io.sha(out/(label+'_normalized.json')),raw_sha256=io.sha(out/(label+'_raw.json')))
            deadline=start+int(cfg['training_wall_seconds_max']*1e9)
            stage(model,optimizer,sequences,attempts=cfg['pretrain_attempts'],batch_size=cfg['batch_episodes'],mode='ERM',rng=rng,max_support=cfg['max_support'],counters=counts,progress=progress('PRETRAIN'),deadline_ns=deadline)
            save('PRETRAIN',model);erm=deepcopy(model);erm_optimizer=torch.optim.AdamW(erm.parameters(),lr=cfg['learning_rate'],weight_decay=cfg['weight_decay']);erm_optimizer.load_state_dict(deepcopy(optimizer.state_dict()))
            matched_draws=deepcopy(rng);support_rng=np.random.default_rng(np.random.SeedSequence([cfg['optimizer_rng_seed'],1]))
            stage(model,optimizer,sequences,attempts=cfg['meta_attempts'],batch_size=cfg['batch_episodes'],mode='META',rng=rng,max_support=cfg['max_support'],counters=counts,progress=progress('META'),support_rng=support_rng,deadline_ns=deadline)
            save('META_FINAL',model)
            active_model=erm
            stage(erm,erm_optimizer,sequences,attempts=cfg['matched_ERM_attempts'],batch_size=cfg['batch_episodes'],mode='ERM',rng=matched_draws,max_support=cfg['max_support'],counters=counts,progress=progress('MATCHED_ERM'),deadline_ns=deadline)
            save('MATCHED_ERM_FINAL',erm);io.require(counts['Adam_updates']<=cfg['Adam_updates_max'] and counts['inner_filter_updates']<=cfg['meta_linear_solves_max'],'frozen optimizer caps')
    except BaseException as error:
        import traceback
        failure=dict(type=type(error).__name__,message=str(error),traceback=traceback.format_exc())
        if active_model is not None:
            try:
                np.savez_compressed(out/'failed_state_arrays.npz',**{n:v.detach().numpy() for n,v in active_model.state_dict().items()})
                failure['retained_parameter_arrays_sha256']=io.sha(out/'failed_state_arrays.npz')
            except BaseException as saved_error:failure['parameter_save_error']=repr(saved_error)
    result=dict(integrity='PASSED' if failure is None else 'FAILED_PARTIAL',failure=failure,guard=guard,counters=counts,Torch_solve_attempts=solves,
        checkpoints=checkpoints,public_source_sha256=spec['public_sha256'],allocated_episodes=len(raw_arrays),nonempty_episodes=sum(bool(len(s['targets'])) for s in raw_arrays),
        available_episodes_by_task=available_by_task,
        no_checkpoint_selection=True,new_environment_interactions=0,online_LLM_API_calls=0,wall_ns=perf_counter_ns()-start,publication_goal_complete=False)
    io.write(out/'complete.json',result);io.write(out/'status.json',result,exclusive=False)
    if failure is not None:raise RuntimeError('One-shot learner stopped; retained '+str(failure))
    return result

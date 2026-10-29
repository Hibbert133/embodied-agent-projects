"""One frozen TRAIN-only development learning pilot, no robot or old-QUAL replay."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['OMP_NUM_THREADS']='1'
from contextlib import contextmanager
from pathlib import Path
from time import perf_counter_ns
from unittest import mock
import argparse
import gzip
import hashlib
import json
import subprocess
import sys
import traceback
import zipfile
import numpy as np
import rank_core_v1 as core
import rank_audit_v1 as audit

ROOT=Path(__file__).resolve().parents[3];BASE=ROOT/'outputs/low_rank_risk_pilot_v1';OUT=BASE/'development_v1'
FREEZE=BASE/'freeze_v1/complete.json';PARENT='00d40b1673fb9ffe8d524f211952710fa7731618'
OLD=ROOT/'outputs/correction_scope/risk_reference_v1/run_20261026T094817Z_82a3873cdf1b'
GRAPH=OLD/'train_graphs.jsonl.gz';GRAPH_SHA='15d226d79658ed75c246ccbff940ddbb343e9d224186e6ece6de5e12b7af13c7'
DOCS=('docs/protocols/low_rank_risk_pilot_v1_zh.md','docs/research/low_rank_risk_pilot_decision_v1_zh.md')
sys.path.insert(0,str(ROOT/'outputs/train_decision_contract_v1/tools'))
import run_contract_v1 as shared
sha=shared.sha;read=shared.read;write=shared.write;git=shared.git;verify=shared.verify;need=shared.need
ZERO=dict(environment_interactions=0,controlled_resets=0,all_resets=0,physical_frames=0,policy_queries=0,
          neural_training=0,response_model_fits=0,new_episode_seeds=0,online_LLM_API_calls=0)


def sources():
    return [*sorted((BASE/'tools').glob('*.py')),BASE/'.gitattributes',*(ROOT/n for n in DOCS),
        *(ROOT/'outputs/train_decision_contract_v1/tools'/n for n in ('run_contract_v1.py','contract_core_v1.py','contract_audit_v1.py','freeze_contract_v1.py'))]


def inputs():
    return [GRAPH,*(OLD/n for n in ('manifest.json','fit_receipt.json','model_audit.json','replay_audit.json','models/static_LINEAR.npz','models/static_RBF.npz')),
        ROOT/'outputs/stateful_risk_reference_v1/freeze_v1/complete.json',
        ROOT/'outputs/occam_reference_qualification_v1/freeze_validation_v1/complete.json',
        ROOT/'outputs/occam_reference_qualification_v1/freeze_validation_v1/validation_receipt.json']


def graphs():
    shared.IO['gzip_stream_passes']+=1
    with gzip.open(GRAPH,'rb') as stream:
        for b in stream:
            shared.IO['gzip_rows']+=1;shared.IO['gzip_decoded_bytes']+=len(b)
            yield shared.loads(b.decode('utf-8'))


def dataset(decoder):
    registry=[];xx=[];yy=[];groups=[];indices=[]
    for i,g in enumerate(graphs()):
        u=g['unit'];need(len(u)==4 and u[0]=='TRAIN' and u[1] in range(9),'only all old TRAIN groups')
        need(g['boundary']==(16,32,64)[u[1]%3] and len(g['leaves'])==12,'full source fixed menu')
        costs=[];success=[];steps=[]
        for leaf in g['leaves']:
            need(type(leaf['loss']) is int and type(leaf['steps']) is int and type(leaf['success']) is bool
                and leaf['loss']==(leaf['steps'] if leaf['success'] else 500),'complete factual loss')
            costs.append(leaf['loss']);success.append(leaf['success']);steps.append(leaf['steps'])
        available=g['pre'] is not None
        if available:
            need(g['pre']['task']==u[2] and g['pre']['completed_steps']==g['boundary'],'public source binding')
            xx.append(decoder(g['pre']));yy.append(np.asarray(costs)/500);groups.append(u[1]);indices.append(i)
        else:need(len(set(zip(costs,success,steps)))==1,'early terminal has no fabricated choices')
        registry.append(dict(unit_index=i,group=u[1],task=u[2],context=u[3],boundary=g['boundary'],
            pre_available=available,missing_reason=None if available else 'ENDED_BEFORE_OR_AT_BOUNDARY',
            losses=costs,successes=success,actual_steps=steps,
            source_case_keys=[leaf['source_case_key'] for leaf in g['leaves']],
            source_case_sha256=[leaf['source_case_sha256'] for leaf in g['leaves']]))
    need(len(registry)==54 and len({(x['group'],x['task'],x['context']) for x in registry})==54,'all 54 TRAIN units')
    need(len(xx)>0,'available causal PRE nodes')
    return np.stack(xx),np.stack(yy),np.array(groups,int),np.array(indices,int),registry


@contextmanager
def guard(allowed):
    allowed={Path(p).resolve() for p in allowed};counts=dict(science_import_attempts=0,network_or_process_attempts=0,undeclared_reads=0,outside_writes=0)
    bad=('torch','mujoco','metaworld','gym','gymnasium','src.rollout')
    need(not any(n==p or n.startswith(p+'.') for n in sys.modules for p in bad),'no preloaded environment or policy')
    active=[True]
    def hook(event,args):
        if not active[0]:return
        if event=='import' and any(args[0]==p or args[0].startswith(p+'.') for p in bad):
            counts['science_import_attempts']+=1;raise RuntimeError('no robot/neural/policy imports')
        if event.startswith('socket.') or event in ('subprocess.Popen','os.system','os.exec','os.posix_spawn'):
            counts['network_or_process_attempts']+=1;raise RuntimeError('no process or network during learning')
        if event=='open' and isinstance(args[0],(str,bytes,os.PathLike)):
            p=Path(os.fsdecode(args[0])).resolve();mode,flags=args[1:3]
            writing=(isinstance(mode,str) and any(s in mode for s in 'wax+')) or (type(flags) is int and bool(flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC)))
            inside=p==OUT or OUT in p.parents
            if writing and not inside:counts['outside_writes']+=1;raise RuntimeError('no writes outside new run')
            if not writing and not inside and p not in allowed:counts['undeclared_reads']+=1;raise RuntimeError('undeclared data read')
    sys.addaudithook(hook)
    try:yield counts
    finally:active[0]=False


def admit():
    f=read(FREEZE);need(f['integrity']=='FROZEN_TRAIN_ONLY_LOW_RANK_RISK_PILOT_V1','software and population freeze')
    verify(f['source_sha256']);verify(f['input_sha256']);verify(f['scientific_source_sha256'])
    for n,h in f['source_sha256'].items():need(hashlib.sha256(git('show','HEAD:'+n)).hexdigest()==h,'committed tested code '+n)
    need(git('show','HEAD:'+FREEZE.relative_to(ROOT).as_posix())==FREEZE.read_bytes(),'committed freeze')
    need(not git('status','--porcelain','--untracked-files=no').strip(),'clean frozen source');return f


def persistent_base(path,base,models,pca,train_ids):
    pack={k:v for k,v in base.items() if isinstance(v,np.ndarray)}
    pack.update(kernel_grand=np.array([base['kernel_grand']]),pca_eigenvalues=pca[0],pca_basis=pca[1],training_unit_indices=train_ids)
    for name,(b,p) in models.items():
        if b is base:pack['projection_'+name]=p
    with path.open('xb') as stream:np.savez_compressed(stream,**pack)


def empirical_mean(pop,train_ids,test):
    rows=[pop[i] for i in train_ids]
    for mode in ('TASK_BOUNDARY','TASK','ALL'):
        r=[x for x in rows if mode=='ALL' or x['task']==test['task'] and (mode!='TASK_BOUNDARY' or x['boundary']==test['boundary'])]
        if r:
            means=[np.mean([x['losses'] for x in r if x['group']==g],axis=0) for g in sorted({x['group'] for x in r})]
            return np.mean(means,axis=0)/500,mode
    raise ValueError('empty empirical reference')


def summarize(records,pop,score_rows):
    result={}
    score_map={(r['unit_index'],r['model']):np.asarray(r['scores']) for r in score_rows}
    for name in [*core.NAMES,'TASK_BOUNDARY_MEAN',*('FIXED_'+str(i).zfill(2) for i in range(12))]:
        rs=[r for r in records if r['model']==name];need(len(rs)==54,'full selection denominator')
        group={str(g):sum(r['loss'] for r in rs if pop[r['unit_index']]['group']==g)/6 for g in range(9)}
        tasks={t:dict(cases=18,success=sum(r['success'] for r in rs if pop[r['unit_index']]['task']==t),
            mean_loss=sum(r['loss'] for r in rs if pop[r['unit_index']]['task']==t)/18) for t in core.TASKS}
        result[name]=dict(success=sum(r['success'] for r in rs),cases=54,mean_deadline_loss=sum(group.values())/9,
            group_means=group,tasks=tasks,selected_program_counts={str(i):sum(r['selected_index']==i for r in rs) for i in range(12)},
            no_decision=sum(r['selected_index'] is None for r in rs))
        if name in core.NAMES:
            mse={};contrast={};available={}
            for g in range(9):
                units=[u for u in pop if u['group']==g and u['pre_available']];available[str(g)]=len(units)
                values=[];differences=[]
                for u in units:
                    predicted=np.clip(score_map[(u['unit_index'],name)],0,1);actual=np.array(u['losses'])/500
                    values.append(float(np.mean((predicted-actual)**2)))
                    differences.append(float(np.mean(((predicted-predicted.mean())-(actual-actual.mean()))**2)))
                mse[str(g)]=sum(values)/len(values) if values else None
                contrast[str(g)]=sum(differences)/len(differences) if differences else None
            result[name]['factual_prediction']=dict(available=sum(available.values()),allocated=54,available_by_group=available,
                full_vector_normalized_MSE=sum(v for v in mse.values() if v is not None)/sum(v is not None for v in mse.values()),
                contrast_normalized_MSE=sum(v for v in contrast.values() if v is not None)/sum(v is not None for v in contrast.values()),
                group_full_MSE=mse,group_contrast_MSE=contrast,missing_not_filled_zero=True)
    main=result['RBF_RR2'];controls=('RBF_FULL','RBF_PCA2','RBF_RAW_RR3','FIXED_00','FIXED_01','FIXED_02','FIXED_03')
    differences={k:main['mean_deadline_loss']-result[k]['mean_deadline_loss'] for k in controls}
    return dict(programs=result,primary='RBF_RR2',primary_development_differences=differences,
        necessary_development_point_condition=all(x<0 for x in differences.values()),
        independent_task_qualification=False,algorithm_novelty_established=False,publication_goal_complete=False)


def worker():
    start=perf_counter_ns();f=admit();allowed=[ROOT/n for n in f['source_sha256']|f['input_sha256']|f['scientific_source_sha256']]
    ledger=dict(linear_solves=0,symmetric_eigendecompositions=0,projected_model_solutions=0,prediction_batches=0,predicted_rows=0)
    independent_ledger=dict(kernel_eigendecompositions=0,augmented_lstsq=0,augmented_QR=0,rank_SVD=0,PCA_SVD=0,reconstructed_model_solutions=0)
    with guard(allowed) as access:
        x,y,g,ids,pop=dataset(core.features);write(OUT/'population.json',pop)
        with (OUT/'public_training_arrays.npz').open('xb') as stream:np.savez_compressed(stream,features=x,normalized_losses=y,groups=g,unit_indices=ids)
        contexts={};model_records=[];predictions={};modeldir=OUT/'models';modeldir.mkdir()
        for fold in [*range(9),'ALL']:
            train=np.arange(len(x)) if fold=='ALL' else np.flatnonzero(g!=fold)
            test=np.arange(len(x)) if fold=='ALL' else np.flatnonzero(g==fold)
            need(set(g[train])==set(range(9)) if fold=='ALL' else set(g[train])==set(range(9))-{fold},'whole-group split')
            tag='ALL' if fold=='ALL' else 'LOO_'+str(fold);models,pca=core.fit_models(x[train],y[train],g[train],ledger)
            contexts[tag]=(train,test,models)
            for kind in core.KINDS:
                base=models[kind+'_FULL'][0];path=modeldir/(tag+'_'+kind+'.npz');persistent_base(path,base,models,pca,ids[train])
                model_records.append(dict(context=tag,kind=kind,training_units=ids[train].tolist(),training_groups=sorted(set(map(int,g[train]))),
                    heldout_group=None if fold=='ALL' else fold,path=path.relative_to(ROOT).as_posix(),sha256=sha(path),
                    active_features=len(base['active']),matrix_output_dimensions=12))
            for name,(b,p) in models.items():
                scores=core.predict(b,x[test],p);ledger['prediction_batches']+=1;ledger['predicted_rows']+=len(test)
                predictions[(tag,name)]=scores
        need(ledger['linear_solves']==20 and ledger['symmetric_eigendecompositions']==50 and ledger['projected_model_solutions']==180,'frozen fit budget')
        write(OUT/'model_manifest.json',dict(base_files=model_records,model_variants=list(core.NAMES),
            shared_base_solves_not_180_independent_solves=True,ledger=ledger))
        # Independent decoding and LS/SVD do not call any main learner function.
        def deny(*args,**kw):raise RuntimeError('main low-rank learner disabled')
        disabled={n:deny for n,v in vars(core).items() if callable(v) and getattr(v,'__module__',None)==core.__name__}
        largest=0.
        with mock.patch.multiple(core,**disabled):
            xx,yy,gg,ii,pp=dataset(audit.feature_vector)
            need(np.array_equal(xx,x) and np.array_equal(yy,y) and np.array_equal(gg,g) and np.array_equal(ii,ids) and pp==pop,'independent full extraction')
            for tag,(train,test,models) in contexts.items():
                for kind in ('LINEAR','RBF'):
                    other,projectors=audit.reconstruct(xx[train],yy[train],gg[train],kind,xx[test],independent_ledger)
                    for name,v in other.items():
                        delta=float(np.max(np.abs(v-predictions[(tag,name)])));largest=max(largest,delta)
                        need(delta<=1e-7 and np.max(abs(projectors[name]-models[name][1]))<=1e-7,'independent model predictions/projectors '+tag+'/'+name)
        # Full-rank baseline must reproduce the already frozen standard model.
        for kind in core.KINDS:
            base=contexts['ALL'][2][kind+'_FULL'][0]
            with np.load(OLD/'models'/('static_'+kind+'.npz'),allow_pickle=False) as old:
                intercept=base['target_mean']-(base['weights']/sum(base['weights']))@base['k']@base['alpha']
                need(np.array_equal(old['active'],base['active']) and np.max(abs(old['mean']-base['mean']))<=1e-10
                    and np.max(abs(old['scale']-base['scale']))<=1e-10 and np.max(abs(old['coefficients']-base['alpha']))<=1e-7
                    and np.max(abs(old['intercept']-intercept))<=1e-7,'full-rank frozen baseline equivalence')
        write(OUT/'model_audit.json',dict(integrity='PASSED_AUGMENTED_LS_QR_SVD_AND_FROZEN_BASELINE',
            main_functions_disabled=sorted(disabled),maximum_prediction_difference=largest,numerical_tolerance_only=1e-7,
            independent_ledger=independent_ledger,legacy_model_parameter_reads=2,legacy_inference_calls=0))
        # Save all scores before consulting the selected factual leaf for outcomes.
        score_rows=[]
        for fold in range(9):
            tag='LOO_'+str(fold);train,test,_=contexts[tag]
            for j,index in enumerate(test):
                for name in core.NAMES:score_rows.append(dict(unit_index=int(ids[index]),model=name,training_groups=sorted(set(map(int,g[train]))),scores=predictions[(tag,name)][j].tolist()))
        write(OUT/'heldout_predictions.json',score_rows)
        scores={(r['unit_index'],r['model']):r['scores'] for r in score_rows};selection=[]
        for unit in pop:
            i=unit['unit_index'];fold=unit['group'];train,_,_=contexts['LOO_'+str(fold)]
            for name in [*core.NAMES,'TASK_BOUNDARY_MEAN',*('FIXED_'+str(j).zfill(2) for j in range(12))]:
                if not unit['pre_available']:chosen=None
                elif name.startswith('FIXED_'):chosen=int(name[-2:])
                elif name=='TASK_BOUNDARY_MEAN':chosen=core.choice(empirical_mean(pop,ids[train],unit)[0])
                else:chosen=core.choice(np.asarray(scores[(i,name)]))
                leaf=0 if chosen is None else chosen
                selection.append(dict(unit_index=i,model=name,selected_index=chosen,loss=unit['losses'][leaf],success=unit['successes'][leaf],
                    source_case_key=unit['source_case_keys'][leaf],source_case_sha256=unit['source_case_sha256'][leaf],
                    offline_supported_branch_only=True,new_robot_execution=False))
        write(OUT/'selected_factual_outcomes.json',selection);result=summarize(selection,pop,score_rows);write(OUT/'statistics.json',result)
        with mock.patch.multiple(core,**disabled):checks=audit.audit_metrics(selection,pop,result,score_rows)
        write(OUT/'statistics_audit.json',dict(integrity='PASSED_COMPLETE_54_UNIT_31_PROGRAM_RECONSTRUCTION',selection_rows_checked=checks))
        report(result,pop,ledger,independent_ledger)
        verify(f['source_sha256']);verify(f['input_sha256']);verify(f['scientific_source_sha256'])
        total=sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file());need(total<=100*1024**2,'complete frozen output disk cap')
        need(not any(access.values()),'zero unexpected forbidden operations')
        write(OUT/'worker_complete.json',dict(integrity='PASSED_COMPLETE_TRAIN_ONLY_LOW_RANK_DEVELOPMENT',
            source_cases=648,source_units=54,independent_source_groups=9,available_PRE=len(x),
            source_graph_sha256=GRAPH_SHA,scientific_learning_ledger=ledger,independent_numerical_ledger=independent_ledger,
            counters=ZERO,guard=access,source_IO=shared.IO,wall_ns=perf_counter_ns()-start,output_bytes_before_receipt=total,
            old_CAL_TEST_QUAL_semantic_reads=0,learning_validation_is_post_hoc_development=True,publication_goal_complete=False))


def report(result,pop,ledger,other):
    rows=['# 低秩完整风险共享假设：TRAIN开发试验 v1','',
        '**事后描述性开发学习，不是新的机器人运行、独立任务资格或新算法。**',
        '旧A1 TRAIN的54单元／9组／648执行与12个真实完整程序；未使用CAL／TEST／QUAL。271条稀疏标签来自另一来源，本轮未混入。','',
        '|程序|成功/54|平均完整截止损失|','|---|---:|---:|']
    for name,v in result['programs'].items():rows.append(f'|{name}|{v["success"]}/54|{v["mean_deadline_loss"]:.6f}|')
    rows+=['','FULL是标准全秩核岭；RR1/2/4在去掉跨程序共同难度后约束可预测成本对比秩；共同难度保留全秩回归。PCA是同样对比空间的普通标签PCA参考；RAW_RR2/3直接降全成本，RAW_RR3与RR2对比加共同方向的总秩匹配。全部方法保留未惩罚列截距、相同公开特征／权重／核／正则／裁剪和同值规则。',
        '降秩、核扩展、共同成本不影响排序都是标准思想，不构成新机制。低输出秩不等于完整模型大小同倍压缩，核中心和标准化费用仍在。','',
        '各方法完整／对比向量预测MSE、实际可用／54和逐组缺失另列于statistics；只在实际PRE可用节点上评价预测，不以填零处理提前结束，不把MSE当任务收益。','',
        '|预定RBF_RR2−强参考|平均差步|','|---|---:|']
    for name,v in result['primary_development_differences'].items():rows.append(f'|{name}|{v:+.6f}|')
    rows+=['',f'预定必要开发点条件：{result["necessary_development_point_condition"]}。不选择另一个较好秩／核替代主候选。失败则封存本版共享假设，不加门控挽救；通过也只允许进一步独立机制设计，不能宣称新颖性或直接开始最终评价。',
        '九个留一组折高度重叠，不当作独立资格样本；无bootstrap／p值／最终CI。先轨迹完整损失、再组均值；提前结束保留全部54分母，没有伪造PRE。源图已验证同前缀/返回状态/时钟/随机数；每次只选一条真实完整来源叶，无拼接或反事实补值。',
        '全部9组、三任务点、所有31程序、固定12程序、早结束及失败见statistics/population/selected_factual_outcomes。若DIRECT_C8／积分等在本事实树无匹配前缀，保持缺失，不借用另一人口；最终必须真实补齐全部强对照。',
        f'科学解180个投影模型，20个共享线性求解、50个特征分解；独立20次增广LS、20 QR、20核特征分解、40秩SVD及20 PCA SVD。实测ledger为{ledger}／{other}，与构造测试开销分开。',
        '全秩基线参数与旧冻结STATIC_LINEAR/RBF逐项核对，未削弱参考；源旧8模型、回应模型及任务资格结论未修改。模型适用预测、数值合法与完整任务收益仍是不同判断。',
        '新环境／reset／帧／固定政策查询／响应模型／神经训练／种子／在线LLM全0；新增的是完整成本标准风险模型拟合及独立复算，不能谎称零拟合。数据、模型和预测实际占用字节、文件IO及墙钟单列。','']
    with (OUT/'report_zh.md').open('x',encoding='utf-8',newline='\n') as stream:stream.write('\n'.join(rows))


def analyze():
    started=perf_counter_ns();admit();need(__import__('shutil').disk_usage(ROOT).free>=256*1024**2,'read-only learning disk margin')
    OUT.mkdir(exist_ok=False);source=git('rev-parse','HEAD').decode().strip()
    write(OUT/'request.json',dict(source_commit=source,source_graph_sha256=GRAPH_SHA,hard_timeout_seconds=1800,one_attempt_only=True,counters=ZERO))
    try:
        with (OUT/'stdout.log').open('xb') as so,(OUT/'stderr.log').open('xb') as se:
            p=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'--worker'],cwd=ROOT,stdout=so,stderr=se,timeout=1800)
        need(p.returncode==0,'preserve single failed learning attempt; no automatic retry')
        done=read(OUT/'worker_complete.json')
        write(OUT/'complete.json',dict(integrity=done['integrity'],source_commit=source,freeze_sha256=sha(FREEZE),
            artifacts={p.relative_to(OUT).as_posix():dict(bytes=p.stat().st_size,sha256=sha(p)) for p in OUT.rglob('*') if p.is_file()},
            total_parent_wall_ns=perf_counter_ns()-started,parent_IO=shared.IO,counters=ZERO,
            no_new_robot_population=True,publication_goal_complete=False))
        print(json.dumps(dict(integrity=done['integrity'],risk_model_solutions=180)),flush=True)
    except Exception as e:
        write(OUT/'failure.json',dict(integrity='PRESERVED_LOW_RANK_PILOT_FAILURE',source_commit=source,reason=str(e),traceback=traceback.format_exc()));raise


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');p=argparse.ArgumentParser();p.add_argument('--worker',action='store_true');args=p.parse_args()
    worker() if args.worker else analyze()

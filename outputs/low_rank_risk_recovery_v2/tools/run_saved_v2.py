"""Read-only recovery of already generated models; never rerun their learner."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['OMP_NUM_THREADS']='1'
import encodings.cp437  # ZIP filename codec must be loaded before the file guard.
from pathlib import Path
from time import perf_counter_ns
from unittest import mock
import argparse
import json
import subprocess
import sys
import traceback
import numpy as np
import saved_audit_v2 as saved

ROOT=Path(__file__).resolve().parents[3];BASE=ROOT/'outputs/low_rank_risk_recovery_v2'
OUT=BASE/'analysis_v1';FREEZE=BASE/'freeze_v1/complete.json'
ORIGINAL=ROOT/'outputs/low_rank_risk_pilot_v1/development_v1'
INITIAL_COMMIT='f6a03dbdbd2ec45b0523d2c4ce90d6869360ac33'
FREEZE_PARENT='54c5071687fd4ca1759674446760b193b9640323'
DOC='docs/protocols/low_rank_risk_recovery_v2_zh.md'
sys.path.insert(0,str(ROOT/'outputs/low_rank_risk_pilot_v1/tools'))
import run_rank_v1 as r


def sources():return [*sorted((BASE/'tools').glob('*.py')),BASE/'.gitattributes',ROOT/DOC]


def admit():
    f=r.read(FREEZE)
    r.need(f['integrity']=='FROZEN_READ_ONLY_SAVED_MODEL_RECOVERY_V2','recovery frozen')
    for key in ('source_sha256','input_sha256','scientific_source_sha256'):r.verify(f[key])
    for name,h in f['source_sha256'].items():
        r.need(__import__('hashlib').sha256(r.git('show','HEAD:'+name)).hexdigest()==h,'committed tested recovery source')
    r.need(r.git('show','HEAD:'+FREEZE.relative_to(ROOT).as_posix())==FREEZE.read_bytes(),'committed recovery freeze')
    r.need(not r.git('status','--porcelain','--untracked-files=no').strip(),'clean committed recovery');return f


def worker():
    started=perf_counter_ns();f=admit();allowed=[ROOT/n for key in ('source_sha256','input_sha256','scientific_source_sha256') for n in f[key]]
    def deny(*args,**kwargs):raise RuntimeError('recovery never refits original models')
    blocked={n:deny for n in ('fit_models','fit_base','target_pca','canonical_eigenspace','normalize')}
    r.OUT=OUT
    ledger=dict(new_risk_fits=0,new_linear_solutions=0,new_spectral_decompositions=0,saved_base_files=0,
        ridge_certificates=0,spectral_certificates=0,projection_certificates=0,main_saved_prediction_batches=0,
        independent_saved_prediction_batches=0,main_saved_predicted_rows=0,independent_saved_predicted_rows=0,
        legacy_parameter_reads=0,legacy_inference=0)
    maximum=0.;certificates=[];scores=[]
    with r.guard(allowed) as access,saved.no_fit(),mock.patch.multiple(r.core,**blocked):
        x,y,g,ids,pop=r.dataset(r.audit.feature_vector)
        with np.load(ORIGINAL/'public_training_arrays.npz',allow_pickle=False) as z:
            r.need(all(np.array_equal(v,z[k]) for k,v in (('features',x),('normalized_losses',y),('groups',g),('unit_indices',ids))),'independent source/cache equality')
        r.need(pop==r.read(ORIGINAL/'population.json'),'complete original population retained')
        r.write(OUT/'population.json',pop)
        original_manifest=r.read(ORIGINAL/'model_manifest.json');entries=original_manifest['base_files']
        r.need(len(entries)==20 and original_manifest['model_variants']==list(r.core.NAMES),'all saved models')
        seen=set();train_for_fold={}
        for item in entries:
            tag=item['context'];kind=item['kind'];r.need((tag,kind) not in seen,'unique saved base');seen.add((tag,kind))
            fold=None if tag=='ALL' else int(tag.removeprefix('LOO_'))
            r.need(tag=='ALL' or tag=='LOO_'+str(fold) and fold in range(9),'fixed folds')
            train=np.arange(len(x)) if fold is None else np.flatnonzero(g!=fold)
            test=np.arange(len(x)) if fold is None else np.flatnonzero(g==fold)
            expected_groups=sorted(set(map(int,g[train])))
            r.need(item['training_units']==ids[train].tolist() and item['training_groups']==expected_groups,'saved provenance excludes test group')
            path=ROOT/item['path'];r.need(path==ORIGINAL/'models'/(tag+'_'+kind+'.npz') and r.sha(path)==item['sha256'],'saved model exact bytes')
            with np.load(path,allow_pickle=False) as archive:b={n:archive[n].copy() for n in archive.files}
            ledger['saved_base_files']+=1
            c=saved.certificate(b,x[train],y[train],g[train],kind,ids[train]);c.update(context=tag,kind=kind)
            certificates.append(c);ledger['ridge_certificates']+=1;ledger['spectral_certificates']+=3;ledger['projection_certificates']+=9
            for name in r.core.NAMES:
                if not name.startswith(kind+'_'):continue
                project=b['projection_'+name];main=dict(b,kind=kind,kernel_grand=float(b['kernel_grand'][0]))
                values=r.core.predict(main,x[test],project);other=saved.prediction(b,x[test],kind,project)
                maximum=max(maximum,saved.close(values,other,'independent saved inference'))
                ledger['main_saved_prediction_batches']+=1;ledger['independent_saved_prediction_batches']+=1
                ledger['main_saved_predicted_rows']+=len(test);ledger['independent_saved_predicted_rows']+=len(test)
                if fold is not None:
                    for j,index in enumerate(test):scores.append(dict(unit_index=int(ids[index]),model=name,training_groups=expected_groups,scores=values[j].tolist()))
            if fold is not None:train_for_fold[fold]=ids[train]
            else:
                with np.load(r.OLD/'models'/('static_'+kind+'.npz'),allow_pickle=False) as old:
                    r.need(np.array_equal(old['active'],b['active']),'legacy active coordinates')
                    for key in ('mean','scale'):saved.close(old[key],b[key],'legacy '+key,1e-10)
                    saved.close(old['coefficients'],b['alpha'],'legacy full-rank coefficients')
                    intercept=b['target_mean']-(b['weights']/sum(b['weights']))@b['k']@b['alpha']
                    saved.close(old['intercept'],intercept,'legacy unpenalized intercept')
                ledger['legacy_parameter_reads']+=1
        r.need(seen=={(tag,kind) for tag in [*('LOO_'+str(i) for i in range(9)),'ALL'] for kind in ('LINEAR','RBF')},'all ten contexts and two kernels')
        r.need(ledger['main_saved_prediction_batches']==180 and len(scores)==18*len(ids),'complete inference only')
        r.write(OUT/'model_audit.json',dict(audit_intercept_identity_corrected_from_v1=True,integrity='PASSED_SAVED_SOLUTION_ALGEBRA_AND_LEGACY_BASELINE',
            certificates=certificates,maximum_independent_prediction_difference=maximum,ledger=ledger,
            original_augmented_LS_receipt_not_persisted=True,original_attempt_remains_failed=True,
            no_fitting_or_decomposition_in_recovery=True))
        # Durably save predictions before selected source outcomes are extracted.
        r.write(OUT/'heldout_predictions.json',scores)
        by={(q['unit_index'],q['model']):q['scores'] for q in scores};selections=[]
        for unit in pop:
            i=unit['unit_index']
            for name in [*r.core.NAMES,'TASK_BOUNDARY_MEAN',*('FIXED_'+str(j).zfill(2) for j in range(12))]:
                if not unit['pre_available']:choice=None
                elif name.startswith('FIXED_'):choice=int(name[-2:])
                elif name=='TASK_BOUNDARY_MEAN':choice=r.core.choice(r.empirical_mean(pop,train_for_fold[unit['group']],unit)[0])
                else:choice=r.core.choice(np.asarray(by[(i,name)]))
                leaf=0 if choice is None else choice
                selections.append(dict(unit_index=i,model=name,selected_index=choice,loss=unit['losses'][leaf],success=unit['successes'][leaf],
                    source_case_key=unit['source_case_keys'][leaf],source_case_sha256=unit['source_case_sha256'][leaf],
                    offline_supported_branch_only=True,new_robot_execution=False))
        r.write(OUT/'selected_factual_outcomes.json',selections)
        result=r.summarize(selections,pop,scores);r.write(OUT/'statistics.json',result)
        disabled={n:deny for n,v in vars(r.core).items() if callable(v) and getattr(v,'__module__',None)==r.core.__name__}
        with mock.patch.multiple(r.core,**disabled):checks=r.audit.audit_metrics(selections,pop,result,scores)
        r.write(OUT/'statistics_audit.json',dict(integrity='PASSED_COMPLETE_54_UNIT_31_PROGRAM_RECONSTRUCTION',selection_rows_checked=checks))
        rows=['# 低秩完整风险开发试验：保存模型审计恢复 v2','',
            '**全部为旧TRAIN的事后描述性开发，不是独立任务验证或新算法。**','',
            '原唯一训练运行因ZIP编码模块被文件守卫误拦而失败；首个只读审计又因错误的带权截距断言失败。两个failure和全部部分工件原样保留。v2仅把错误的pᵀalpha=0改为正确的1ᵀalpha=0，带权合成反例在冻结前验证，容差不变。本入口不重训，通过保存模型的正规方程、完整谱基／投影证书和独立预测公式恢复统计。原增广LS／QR／SVD位于失败之前，但未持久化数值回执，不能冒称原worker成功。','',
            '|程序|成功/54|平均完整截止损失|','|---|---:|---:|']
        for name,v in result['programs'].items():rows.append(f'|{name}|{v["success"]}/54|{v["mean_deadline_loss"]:.6f}|')
        rows+=['','|预定RBF_RR2−参考|平均差步|','|---|---:|']
        for name,v in result['primary_development_differences'].items():rows.append(f'|{name}|{v:+.6f}|')
        rows+=['',f'必要开发点条件：**{result["necessary_development_point_condition"]}**。唯一主候选固定RBF_RR2，失败即封存本版，不改成次要较优核／秩、不加门控或样本。通过也不等于独立资格／新颖性。',
            '原TRAIN54单位／9组／648实际程序；48有PRE，6提前结束保留分母。18标准学习模型、任务边界均值及12固定程序共1674条来源支持选择，不能冒充新机器人执行。LOO训练集合重叠，没有最终CI或独立功效宣称。',
            'FULL为标准全秩核岭；RR1/2/4是保留共同难度方向的成本对比降秩；PCA是同样对比空间的标签方向；RAW_RR2/3降完整输出，RAW_RR3与RR2对比加共同方向的总秩匹配。核、特征、权重、截距、正则、裁剪和同值规则相同。',
            '数值合法、48/54节点的完整／对比MSE和完整54分母任务损失分别报告，MSE不能代替任务收益。全部组／三任务、早终止和失败保留。预测仅公开PRE；组只用于划分／权重，未来成本只作监督。',
            f'原180投影解／20求解／50特征分解及其独立LS等运算由工件与失败前控制流推断，未持久化原worker ledger。恢复实测ledger为{ledger}；没有新拟合或分解。独立保存参数预测最大差{maximum:.12g}。',
            '历史来源费用：648实际执行／77563控制步／33048全部重置／16911815物理帧；不计作本轮新交互，也不把历史数据当免费。新增环境／reset／帧／政策查询／响应拟合／神经训练／种子／在线LLM全0，恢复有360批模型预测和读取费用。','']
        with (OUT/'report_zh.md').open('x',encoding='utf-8',newline='\n') as stream:stream.write('\n'.join(rows))
        for key in ('source_sha256','input_sha256','scientific_source_sha256'):r.verify(f[key])
        total=sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file());r.need(total<=100*1024**2,'recovery output cap')
        r.need(not any(access.values()),'strict I/O guard')
        r.write(OUT/'worker_complete.json',dict(integrity='PASSED_READ_ONLY_SAVED_MODEL_RECOVERY',source_cases=648,source_units=54,independent_source_groups=9,
            available_PRE=len(x),source_graph_sha256=r.GRAPH_SHA,ledger=ledger,counters=r.ZERO,guard=access,source_IO=r.shared.IO,
            original_attempt_failed=True,original_numeric_operation_counts_inferred_not_persisted=True,
            wall_ns=perf_counter_ns()-started,output_bytes_before_receipt=total,old_CAL_TEST_QUAL_semantic_reads=0,publication_goal_complete=False))


def analyze():
    started=perf_counter_ns();admit();r.need(__import__('shutil').disk_usage(ROOT).free>=256*1024**2,'recovery-only space margin')
    OUT.mkdir(exist_ok=False);source=r.git('rev-parse','HEAD').decode().strip()
    r.write(OUT/'request.json',dict(source_commit=source,initial_training_commit=INITIAL_COMMIT,hard_timeout_seconds=1800,one_attempt_only=True,new_model_fits=0))
    try:
        with (OUT/'stdout.log').open('xb') as so,(OUT/'stderr.log').open('xb') as se:
            p=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'--worker'],cwd=ROOT,stdout=so,stderr=se,timeout=1800)
        r.need(p.returncode==0,'preserve failed recovery, no retry or refit')
        done=r.read(OUT/'worker_complete.json')
        r.write(OUT/'complete.json',dict(integrity=done['integrity'],source_commit=source,initial_training_commit=INITIAL_COMMIT,
            freeze_sha256=r.sha(FREEZE),artifacts={p.relative_to(OUT).as_posix():dict(bytes=p.stat().st_size,sha256=r.sha(p)) for p in OUT.rglob('*') if p.is_file()},
            total_parent_wall_ns=perf_counter_ns()-started,parent_IO=r.shared.IO,counters=r.ZERO,publication_goal_complete=False))
        print(json.dumps(dict(integrity=done['integrity'],new_fits=0)),flush=True)
    except Exception as error:
        r.write(OUT/'failure.json',dict(integrity='PRESERVED_SAVED_MODEL_RECOVERY_FAILURE',source_commit=source,reason=str(error),traceback=traceback.format_exc()));raise


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');args=argparse.ArgumentParser();args.add_argument('--worker',action='store_true');a=args.parse_args()
    worker() if a.worker else analyze()

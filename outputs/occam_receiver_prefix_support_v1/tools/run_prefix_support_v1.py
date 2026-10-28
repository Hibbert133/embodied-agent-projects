"""Versioned TRAIN-only prefix analysis. Nothing here can run an environment."""
from pathlib import Path
from time import perf_counter_ns
from contextlib import contextmanager,redirect_stdout,redirect_stderr
from unittest.mock import patch
import argparse,gzip,hashlib,io,json,os,sys,unittest
import numpy as np
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
import prefix_engine_v1 as e
import prefix_audit_v1 as a
from src.probe import occam_performance_core_v1 as pc
from src.probe import occam_training_program_v1 as tp
from src.probe.occam_qualification_provider_v1 import TrainedProvider

BASE=ROOT/'outputs/occam_receiver_prefix_support_v1';FREEZE=BASE/'freeze_v1/complete.json';OUT=BASE/'analysis_v1'
REPORT=ROOT/'reports/occam_receiver_prefix_support_v1_zh.md';DOC=ROOT/'docs/protocols/occam_receiver_prefix_support_v1_zh.md'
TRAIN=ROOT/'outputs/occam_reference_train_v3/development_v1/occam_reference_train_v3_20261028T071949Z_c92356173d9e'
QMANIFEST=ROOT/'outputs/occam_reference_qualification_v1/qualification_v1/occam_reference_qualification_v1_20261028T125131Z_7abaec83b085/manifest.json'
INPUTS={'manifest.json':'7416700122909b15ffeda1a3ca2925d325bebe92b1eab00cbe3dfea329e0a413',
    'train/audit.json':'a4d1a5d8ac1e2357c82ea129b454802e9c376f8777daeccf06a4dae07ee3e5db',
    'train/process_audit.json':'2b77793a50aeab8c008e9d3ffb11dc72261d9694033d2a369eef137546e5e745',
    'train/summary.json':'507d16e3b15d9c7e3e937e4a79c85c05ab3080c762ef484092215bc10b205040',
    'train/public_trajectories.jsonl.gz':'f4c5c0a774c6116308feffee18e69739c6f02696a78ed47d540cd103167727e3',
    'learning/META_FINAL_raw.json':'f09a294a09ef2883fb6a8b4f7ffdc07da4281a6be6ce238af9ff60809caaaa2d',
    'learning/MATCHED_ERM_FINAL_raw.json':'0f01c0e37e9a2795718040d96827670d2fec5a0c98ed2829e8b7ede05255a755'}
FIELDS=('cohort','group','task','seed','context','planned_boundary','acquisition_action','behavior')
THREADS=('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')
COMPONENTS=('src/probe/occam_performance_core_v1.py','src/probe/occam_public_history_v1.py',
    'src/probe/occam_training_program_v1.py','src/probe/occam_qualification_provider_v1.py',
    'src/analysis/occam_qualification_math_audit_v1.py','src/analysis/occam_performance_independent_v1.py',
    'src/probe/occam_qualification_program_v1.py')


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024**2),b''):h.update(b)
    return h.hexdigest()


def unique(pairs):
    result={}
    for k,v in pairs:e.require(k not in result,'duplicate JSON key');result[k]=v
    return result


def loads(text):return json.loads(text,object_pairs_hook=unique)
def read(path):return loads(Path(path).read_text(encoding='utf8'))


def write(path,value):
    with Path(path).open('x',encoding='utf8',newline='\n') as f:json.dump(value,f,indent=2,ensure_ascii=False,allow_nan=False);f.write('\n')


def rows(path):
    opener=gzip.open if str(path).endswith('.gz') else open
    with opener(path,'rt',encoding='utf8') as f:
        for line in f:yield loads(line)


def emit(stream,value):stream.write(json.dumps(value,separators=(',',':'),ensure_ascii=False,allow_nan=False)+'\n')
def verify(bindings):
    for n,h in bindings.items():e.require(sha(ROOT/n)==h,'frozen bytes changed '+n)


def zeros():
    return dict(environment_interactions=0,controlled_resets=0,all_resets=0,physical_frames=0,fixed_policy_queries=0,
        neural_training=0,batch_model_fits=0,new_episode_allocations=0,online_LLM_API_calls=0)


def bank_label(target):return 'META_FINAL' if target.startswith('META_') else 'MATCHED_ERM_FINAL'
def cell_key(spec):return tuple(spec[k] for k in ('task','context','planned_boundary','acquisition_action','behavior'))


@contextmanager
def arithmetic(counts,*,independent=False):
    solve,eig,lstsq=np.linalg.solve,np.linalg.eigvalsh,np.linalg.lstsq
    forward=tp.basis_forward;literal=a.literal_bases
    def solved(*args,**kwargs):counts['linear_solves']+=1;return solve(*args,**kwargs)
    def eigen(*args,**kwargs):counts['symmetric_eigendecompositions']+=1;return eig(*args,**kwargs)
    def forbidden(*args,**kwargs):counts['forbidden_batch_fit_attempts']+=1;raise RuntimeError('no batch fitting in prefix analysis')
    def basis(*args,**kwargs):counts['basis_batches']+=1;return (literal if independent else forward)(*args,**kwargs)
    with patch.object(np.linalg,'solve',solved),patch.object(np.linalg,'eigvalsh',eigen),patch.object(np.linalg,'lstsq',forbidden),\
         patch.object(a if independent else tp,'literal_bases' if independent else 'basis_forward',basis):
        yield


def new_counts():return dict(linear_solves=0,symmetric_eigendecompositions=0,forbidden_batch_fit_attempts=0,basis_batches=0)


def freeze():
    FREEZE.parent.mkdir(exist_ok=False);started=perf_counter_ns()
    e.require(all(os.environ.get(n)=='1' for n in THREADS),'single-thread analysis runtime')
    inputs={(TRAIN/n).relative_to(ROOT).as_posix():h for n,h in INPUTS.items()};verify(inputs)
    q=read(QMANIFEST);e.require(q['manifest_id']=='19347fbe7b039fabd536c411d74e87a823bd0925cd2bee9e5705329cdb77f78d','fixed qualification metadata only')
    components={n:q['source_sha256'][n] for n in COMPONENTS};verify(components)
    inputs[QMANIFEST.relative_to(ROOT).as_posix()]=sha(QMANIFEST)
    source={p.relative_to(ROOT).as_posix():sha(p) for p in sorted((BASE/'tools').glob('*.py'))+[BASE/'.gitattributes',DOC]}
    for n in source:
        if n.endswith('.py'):compile((ROOT/n).read_bytes(),n,'exec')
    stream=io.StringIO();counts=new_counts()
    with redirect_stdout(stream),redirect_stderr(stream),arithmetic(counts):
        suite=unittest.defaultTestLoader.discover(str(BASE/'tools'),pattern='test_prefix_support_v1.py')
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    (FREEZE.parent/'unit_tests.log').write_text(stream.getvalue(),encoding='utf8',newline='\n')
    e.require(result.wasSuccessful() and result.testsRun==20,'formal prefix/ordering/independent tests')
    old=read(TRAIN/'train/audit.json');summary=read(TRAIN/'train/summary.json');process=read(TRAIN/'train/process_audit.json')
    e.require(old['integrity']=='PASSED' and process['integrity']=='PASSED_ISOLATED_PROCESS_AND_BYTE_CONTINUITY_ONLY'
        and summary['executions']==summary['allocated_executions']==648 and summary['failure'] is None,'complete audited source')
    e.require(old['counts']['observed_window_labels']==3296 and old['public_trajectories_sha256']==INPUTS['train/public_trajectories.jsonl.gz'],'all source windows')
    verify(inputs);verify(components);verify(source)
    write(FREEZE,dict(integrity='FROZEN_TRAIN_ONLY_RECEIVER_PREFIX_DESCRIPTION',source_sha256=source,input_sha256=inputs,
        component_sha256=components,unit_tests=20,development_test_executions=20,formal_test_executions=20,
        synthetic_arithmetic=counts,unit_log_sha256=sha(FREEZE.parent/'unit_tests.log'),targets=list(e.TARGETS),
        source_executions=648,receiver_analyses=2592,actual_source_windows=3296,independent_groups=18,
        per_pass_caps=dict(model_declarations=13184,candidate_predictions=52736,analysis_posterior_updates=13184,linear_solves=13184),
        semantic_public_parses=2,additional_byte_hash_passes_disclosed=True,active_wall_seconds=1800,
        strict_in_sample_description=True,current_QUAL_outcomes_used=False,task_value_estimation=False,
        counters=zeros(),numpy_version=np.__version__,python_version=sys.version,
        thread_environment={n:os.environ[n] for n in THREADS},wall_ns=perf_counter_ns()-started,publication_goal_complete=False))
    return dict(integrity='FROZEN_TRAIN_ONLY_RECEIVER_PREFIX_DESCRIPTION',tests=20)


class Parts:
    def __init__(self):self.stream=None;self.size=0;self.count=0;self.parts=[];self.current=None
    def save(self,value):
        raw=(json.dumps(value,separators=(',',':'),ensure_ascii=False,allow_nan=False)+'\n').encode('utf8')
        e.require(len(raw)<=4*1024**2,'one bounded declaration row')
        if self.stream is None or self.size+len(raw)>4*1024**2:
            self.close();p=OUT/('decisions_%03d.jsonl'%(len(self.parts)+1));self.stream=p.open('xb');self.current=p;self.size=0;self.count=0
        self.stream.write(raw);self.size+=len(raw);self.count+=1
    def close(self):
        if self.stream is not None:
            self.stream.close();self.parts.append(dict(path=self.current.name,bytes=self.size,rows=self.count,sha256=sha(self.current)));self.stream=None


def source_meta():
    manifest=read(TRAIN/'manifest.json');audit=read(TRAIN/'train/audit.json');summary=read(TRAIN/'train/summary.json')
    return manifest['config']['populations']['TRAIN'],audit['panels'],summary['rows']


def analyze(plan,counts,started):
    specs,panels,compact=source_meta();stream=rows(TRAIN/'train/public_trajectories.jsonl.gz')
    banks={label:read(TRAIN/'learning'/(label+'_raw.json')) for label in ('META_FINAL','MATCHED_ERM_FINAL')}
    result=[];parts=Parts();sequence=0
    write(OUT/'case_registry.json',dict(source_cases=specs,targets=list(e.TARGETS),analyses_allocated=2592,model_or_task_results_not_imputed=True))
    try:
        with (OUT/'trajectories.jsonl').open('x',encoding='utf8',newline='\n') as output:
            for i,spec in enumerate(specs):
                e.require((perf_counter_ns()-started)/1e9<1800,'fixed analysis wall cap')
                raw=next(stream);e.require(set(raw)=={'sequence','value'} and raw['sequence']==i,'complete original row order')
                for key in FIELDS:e.require(panels[i][key]==compact[i][key]==spec[key],'same source case identity')
                value=raw['value'];e.require(len(value['windows'])==compact[i]['performance_windows'] and len(value['history'])==compact[i]['total_steps'],'all original windows/steps')
                for target in e.TARGETS:
                    provider=TrainedProvider(banks[bank_label(target)],adapt=target.endswith('_ADAPT')) if value['windows'] else None
                    row,records=e.replay(value,target,provider)
                    row.update(spec=spec,source_case_index=i,source_success=compact[i]['success'],source_deadline_loss=compact[i]['deadline_loss'],
                        no_window_reason=None if value['windows'] else 'BEFORE_INTERVENTION' if not compact[i]['boundary_applied'] else 'AFTER_ACQUISITION_NO_WINDOW')
                    emit(output,dict(sequence=len(result),value=row));result.append(row)
                    for record in records:
                        parts.save(dict(sequence=sequence,source_case_index=i,target=target,value=record));sequence+=1
    finally:parts.close()
    e.require(next(stream,None) is None and len(result)==2592,'no extra/omitted source or receiver')
    write(OUT/'decision_parts.json',dict(schema='BOUNDED_RECEIVER_DECLARATIONS_V1',parts=parts.parts,rows=sequence,max_part_bytes=4*1024**2))
    statistics=[];cells=[]
    for target in e.TARGETS:
        selected=[r for r in result if r['target']==target];e.require(len(selected)==648,'full per-target population')
        statistics.append(dict(target=target,summary=e.summarize(selected)))
        for key in sorted({cell_key(s) for s in specs}):
            subset=[r for r in selected if cell_key(r['spec'])==key];e.require(len(subset)==6,'full cell denominator')
            cells.append(dict(target=target,cell=list(key),summary=e.summarize(subset)))
    e.require(len(cells)==432,'all target/source strata')
    write(OUT/'statistics.json',dict(by_target=statistics,cells=cells,independent_source_groups=18,analyses_not_robot_executions=True))
    updates=sum(r['analysis_posterior_updates'] for r in result)
    e.require(counts['basis_batches']==sequence<=13184 and counts['linear_solves']==updates<=13184
        and counts['forbidden_batch_fit_attempts']==0,'actual source-bound inference/update budget')
    write(OUT/'analysis_complete.json',dict(integrity='COMPLETE_IN_SAMPLE_PREFIX_DESCRIPTION',source_cases=648,analyses=2592,
        declarations=sequence,candidate_predictions=4*sequence,analysis_posterior_updates=updates,arithmetic=counts,
        wall_ns=perf_counter_ns()-started,scientific_counters=zeros(),no_target_task_results_created=True))


def decision_rows():
    index=read(OUT/'decision_parts.json')
    e.require(index['schema']=='BOUNDED_RECEIVER_DECLARATIONS_V1','versioned bounded declarations')
    total=0
    for part in index['parts']:
        name=part['path'];e.require(type(name) is str and Path(name).name==name,'plain owned declaration part')
        path=OUT/name;e.require(path.stat().st_size==part['bytes']<=4*1024**2 and sha(path)==part['sha256'],'immutable declaration part')
        count=0
        for record in rows(path):count+=1;total+=1;yield record
        e.require(count==part['rows'],'all rows in part')
    e.require(total==index['rows'],'all declaration parts')


def audit(plan,counts,started):
    specs,panels,compact=source_meta();public=rows(TRAIN/'train/public_trajectories.jsonl.gz')
    saved=rows(OUT/'trajectories.jsonl');events=decision_rows();results=[];ordinal=0;updates=0
    banks={label:read(TRAIN/'learning'/(label+'_raw.json')) for label in ('META_FINAL','MATCHED_ERM_FINAL')}
    def denied(*args,**kwargs):raise RuntimeError('main replay/model/statistics disabled in independent audit')
    with patch.multiple(pc,forecast=denied,update=denied,choose=denied,basis_forward=denied),\
         patch.object(TrainedProvider,'declare',denied),patch.object(TrainedProvider,'feedback',denied),\
         patch.object(tp.OccamProvider,'declare',denied),patch.object(e,'replay',denied),patch.object(e,'summarize',denied):
        for i,spec in enumerate(specs):
            e.require((perf_counter_ns()-started)/1e9<1800,'fixed total analysis wall cap')
            source=next(public);a.require(source['sequence']==i,'independent source row order')
            value=source['value']
            for target in e.TARGETS:
                record=next(saved);a.require(record['sequence']==len(results),'all receiver result rows');row=record['value']
                a.require(row['target']==target and row['spec']==spec and row['source_case_index']==i,'receiver/source identity')
                a.require(row['source_success']==compact[i]['success'] and row['source_deadline_loss']==compact[i]['deadline_loss'],'source outcomes remain source only')
                reason=None if value['windows'] else 'BEFORE_INTERVENTION' if not compact[i]['boundary_applied'] else 'AFTER_ACQUISITION_NO_WINDOW'
                a.require(row['no_window_reason']==reason and 0<=row['declarations']<=len(value['windows']),'complete missingness')
                declarations=[]
                for j in range(row['declarations']):
                    event=next(events);a.require(event['sequence']==ordinal and event['source_case_index']==i and event['target']==target,'declaration owner/order')
                    declarations.append(event['value']);ordinal+=1
                reconstructed=a.verify_replay(value,target,row,declarations,banks[bank_label(target)])
                updates+=reconstructed['posterior_updates'];results.append(row)
        a.require(next(public,None) is None and next(saved,None) is None and next(events,None) is None,'nothing omitted or appended')
        stats=read(OUT/'statistics.json');a.require([x['target'] for x in stats['by_target']]==list(e.TARGETS),'all four targets')
        for item in stats['by_target']:a.verify_summary([r for r in results if r['target']==item['target']],item['summary'])
        expected=[(t,k) for t in e.TARGETS for k in sorted({cell_key(s) for s in specs})]
        a.require([(x['target'],tuple(x['cell'])) for x in stats['cells']]==expected,'all 432 preassigned cells')
        for item in stats['cells']:
            group=[r for r in results if r['target']==item['target'] and cell_key(r['spec'])==tuple(item['cell'])]
            a.require(len(group)==6,'full cell denominator');a.verify_summary(group,item['summary'])
    a.require(len(results)==2592 and counts['basis_batches']==ordinal<=13184 and counts['linear_solves']==0
        and not counts['forbidden_batch_fit_attempts'],'literal audit budget; no main solves')
    main=read(OUT/'analysis_complete.json')
    a.require(main['declarations']==ordinal and main['analysis_posterior_updates']==updates,'all computation rebuilt')
    write(OUT/'audit.json',dict(integrity='PASSED_INDEPENDENT_PREFIX_CHOICES_AND_SCALAR_POSTERIORS',source_cases=648,
        receiver_analyses=2592,declarations=ordinal,candidate_predictions=4*ordinal,analysis_posterior_updates=updates,
        arithmetic=counts,main_models_replay_and_statistics_disabled=True,shared_strict_features_disclosed=True,
        no_independent_physics_replay=True,counters=zeros(),wall_ns=perf_counter_ns()-started,
        independent_value_or_deployment_qualification=False))


class Guard:
    def __init__(self,allowed):
        self.allowed={str(Path(p).resolve()) for p in allowed};self.enabled=False
        self.counts=dict(file_reads_denied=0,file_writes_denied=0,network_or_process_attempts=0,scientific_import_attempts=0)
    def __call__(self,event,args):
        if not self.enabled:return
        if event in ('subprocess.Popen','os.system','os.exec','os.posix_spawn','socket.connect','socket.connect_ex','socket.bind','socket.getaddrinfo'):
            self.counts['network_or_process_attempts']+=1;raise RuntimeError('offline analysis, no process/network')
        if event=='import' and args[0].split('.')[0] in ('mujoco','metaworld','gym','gymnasium','torch'):
            self.counts['scientific_import_attempts']+=1;raise RuntimeError('no environment or training imports')
        if event!='open' or not isinstance(args[0],(str,bytes,os.PathLike)):return
        p=Path(os.fsdecode(args[0])).resolve();mode,flags=args[1],args[2]
        writing=(isinstance(mode,str) and any(x in mode for x in 'wax+')) or (isinstance(flags,int) and bool(flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT)))
        own=p==OUT or OUT in p.parents or p==REPORT
        runtime=any(Path(root).resolve() in p.parents for root in (sys.prefix,sys.base_prefix)) and p.suffix.lower() in ('.py','.pyc','.pyd','.dll')
        okay=own if writing else own or str(p) in self.allowed or runtime
        if not okay:
            self.counts['file_writes_denied' if writing else 'file_reads_denied']+=1;raise RuntimeError('undeclared file '+str(p))


def report(plan):
    stats=read(OUT/'statistics.json');main=read(OUT/'analysis_complete.json');audit_result=read(OUT/'audit.json')
    lines=['# 固定学习接收者的旧来源前缀支持（中文）','','**事后、训练来源内描述，不是独立部署或离策略价值估计。**','',
        '完整登记648来源轨迹、3296实际窗、18独立组；对四个既定接收者各检查一次，2592份分析不算机器人执行。每个接收者只在来源已分配的同一获取动作后检查增益选择，没有学习或选择获取动作。','',
        '|接收者|来源／非空|全部观测增益匹配|首次分歧|声明／匹配窗|分析后验更新|组等权匹配窗比例|','|---|---:|---:|---:|---:|---:|---:|']
    for item in stats['by_target']:
        s=item['summary'];lines.append(f"|{item['target']}|648／{s['source_nonempty']}|{s['all_observed_rate_choices_match']}|{s['first_rate_divergence']}|{s['declarations']}／{s['matching_windows']}|{s['analysis_posterior_updates']}|{s['equal_group_matching_fraction']:.6f}|")
    lines+=['','每种接收者保留106个无决定案例，分别标记边界前结束／获取后无任务窗；短窗按实际长度保留。全部432个分层和18组的轨迹内→组内→组等权统计见 statistics.json，逐来源／接收者见 trajectories.jsonl。没有将相关时间步当独立样本，也没有选择有利任务或匹配子集计算成功率。','',
        '每次声明只接收来源当时的严格公开 query。仅在增益相同的窗提交实际反馈，首次分歧后不再提交其标签或后续 query；没有为未执行的接收者尾段构造轨迹。声明、首次分歧、匹配反馈、四候选映射及模型版本按≤4MiB分片保存，query以来源行／窗和SHA精确引用原已归档公开流。','',
        '限制：bank本来就在该TRAIN上训练，包含训练来源复用；本表不是独立前瞻预测，不是实际部署，不证明低层命令或隐藏物理状态全程相同。所有接收者任务损失／成功字段均为缺失。原602成功／46失败只属于来源行为，不是四接收者的任务结果。全增益匹配也不成为独立成功率。','',
        '支持证据：独立reader重新计算全部四候选、选择、首个分歧、标量后验、缺失及分层权重，禁用主provider／前向／更新／回放／统计。严格公开特征抽取共享，未做独立物理重仿真。反证和不能区分之处：选择匹配计数不能补足条件概率、外生性、覆盖或模型偏差，也不能从分歧计数认定接收者任务优劣。','',
        '后续判断：旧随机／恒定增益轨迹不能直接作为改变选择及后验的接收者之完整后继风险标签。完整Q／DR仍需指定完整接收者、数据权限、行为概率／支持和停止处理，或另行冻结有效新数据设计；不能以本检查移除该强参考。统计覆盖不能从“有若干匹配”推出，也不能因有限样本未匹配就声称某路线理论不可用。','',
        '不改变当前独立QUAL，也不由本表选bank、阈值、主程序、获取动作或样本。无收益按原停止规则封存本版接收者，不在其上加门控。完整任务收益、A的新机制、同权限完整风险／普通重加权等强对照及消融仍未完成；本次不构成CCF A证据。','',
        '新增环境／全部重置／帧／固定策略查询／神经训练／批量拟合／seed／在线LLM均为0。模型运算单独计费：主计算'+json.dumps({k:main[k] for k in ('declarations','candidate_predictions','analysis_posterior_updates','arithmetic')},ensure_ascii=False)+'；独立复算'+json.dumps({k:audit_result[k] for k in ('declarations','candidate_predictions','analysis_posterior_updates','arithmetic')},ensure_ascii=False)+'。',
        f"全阶段耗时分别记录：主扫描 {main['wall_ns']/1e9:.3f} 秒，主扫描加独立审计 {audit_result['wall_ns']/1e9:.3f} 秒；20项新合成检查的运算与开发20次执行另记，不当作新的科学人口。",'',
        '来源费用保留：TRAIN648、80390控制步、33048全部reset、16925950帧；另有来源NATIVE36及5399控制步、1836全部reset、944995帧。一次训练9000 AdamW更新、三checkpoint及其审计／更早C8费用沿原交付清单单列，本阶段没有重做或抹去。','',
        '来源公开投影 SHA-256 '+INPUTS['train/public_trajectories.jsonl.gz']+'。冻结输入、代码、bank和合成运算回执见freeze_v1/complete.json；完整结果及独立核对哈希见analysis_v1/complete.json。','']
    text='\n'.join(lines)
    with (OUT/'report_zh.md').open('x',encoding='utf8',newline='\n') as f:f.write(text)
    with REPORT.open('x',encoding='utf8',newline='\n') as f:f.write(text)


def run():
    started=perf_counter_ns()
    plan=read(FREEZE);e.require(plan['integrity']=='FROZEN_TRAIN_ONLY_RECEIVER_PREFIX_DESCRIPTION','frozen analysis')
    e.require(all(os.environ.get(n)=='1' for n in THREADS),'frozen one-thread runtime')
    verify(plan['source_sha256']);verify(plan['input_sha256']);verify(plan['component_sha256'])
    q=read(QMANIFEST);verify(q['source_sha256'])
    e.require(not any(n.split('.')[0] in ('mujoco','metaworld','gym','gymnasium','torch') for n in sys.modules),'no scientific modules loaded')
    OUT.mkdir(exist_ok=False);main_counts=new_counts();audit_counts=new_counts()
    allowed=[ROOT/n for n in (*plan['source_sha256'],*plan['input_sha256'],*plan['component_sha256'])]+[FREEZE,FREEZE.parent/'unit_tests.log']
    guard=Guard(allowed);sys.addaudithook(guard);guard.enabled=True
    try:
        write(OUT/'intent.json',dict(freeze_sha256=sha(FREEZE),counters=zeros(),descriptive_in_sample_only=True))
        with arithmetic(main_counts):analyze(plan,main_counts,started)
        with arithmetic(audit_counts,independent=True):audit(plan,audit_counts,started)
        report(plan);verify(plan['source_sha256']);verify(plan['input_sha256']);verify(plan['component_sha256'])
        e.require(not any(guard.counts.values()),'zero forbidden file/process/network/environment attempts')
        write(OUT/'guard.json',dict(counts=guard.counts,no_other_scientific_data_inputs=True))
    except BaseException as error:
        write(OUT/'FAILED_ANALYSIS_RETAINED.json',dict(type=type(error).__name__,message=str(error),main_arithmetic=main_counts,
            independent_arithmetic=audit_counts,guard=guard.counts,counters=zeros(),no_science_allocation_retried=True))
        raise
    finally:guard.enabled=False
    verify(q['source_sha256'])
    artifacts=[p for p in OUT.iterdir() if p.is_file()]+[REPORT]
    write(OUT/'complete.json',dict(integrity='PASSED_COMPLETE_IN_SAMPLE_RECEIVER_PREFIX_AUDIT',source_cases=648,analyses=2592,
        source_independent_groups=18,cells=432,source_freeze_sha256=sha(FREEZE),
        artifact_sha256={p.relative_to(ROOT).as_posix():sha(p) for p in artifacts},
        active_scientific_source_files_verified_unchanged=len(q['source_sha256']),current_QUAL_outcomes_used=False,
        no_value_or_own_history_deployment_claim=True,counters=zeros(),wall_ns=perf_counter_ns()-started,publication_goal_complete=False))
    return dict(integrity='PASSED_COMPLETE_IN_SAMPLE_RECEIVER_PREFIX_AUDIT',source_cases=648,analyses=2592)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=('freeze','run'));args=parser.parse_args()
    print(json.dumps(freeze() if args.command=='freeze' else run(),ensure_ascii=False),flush=True)

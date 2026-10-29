"""One frozen stdlib-only saved TRAIN/NATIVE semantic audit; no science imports."""
from contextlib import contextmanager
from itertools import groupby
from pathlib import Path
from time import perf_counter_ns
from unittest import mock
import argparse
import gzip
import hashlib
import json
import os
import subprocess
import sys
import traceback
import contract_core_v1 as core
import contract_audit_v1 as audit

ROOT=Path(__file__).resolve().parents[3]
BASE=ROOT/'outputs/train_decision_contract_v1'
OUT=BASE/'analysis_v1'
FREEZE=BASE/'freeze_v1/complete.json'
RUN=ROOT/'outputs/occam_reference_train_v3/development_v1/occam_reference_train_v3_20261028T071949Z_c92356173d9e'
MID='5bc73a52c4cd6322d329876143892426c7e182aac24744d0a54fb99b871ac9a0'
PARENT='35f25bfa601e2e1e3ebdc2a5652eff88c8f82239'
DOCS=('docs/protocols/train_decision_contract_v1_zh.md',)
PRIOR=('outputs/occam_behavior_support_v1/analysis_v1/complete.json',
       'outputs/occam_receiver_prefix_support_v1/analysis_v1/complete.json')
IO=dict(SHA_file_passes=0,SHA_bytes=0,JSON_documents=0,JSON_bytes=0,gzip_stream_passes=0,gzip_rows=0,gzip_decoded_bytes=0)
ZERO=dict(environment_interactions=0,controlled_resets=0,all_resets=0,physical_frames=0,policy_queries=0,
          model_queries=0,model_fits=0,neural_training=0,filter_updates=0,new_episode_seeds=0,online_LLM_API_calls=0)


def need(v, msg):
    if not v: raise ValueError(msg)


def sha(path):
    size=0;h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for b in iter(lambda:stream.read(1024**2),b''):h.update(b);size+=len(b)
    IO['SHA_file_passes']+=1;IO['SHA_bytes']+=size
    return h.hexdigest()


def unique(pairs):
    d={}
    for k,v in pairs:
        need(k not in d,'duplicate JSON key');d[k]=v
    return d


def loads(s):return json.loads(s,object_pairs_hook=unique)


def read(path):
    b=Path(path).read_bytes();IO['JSON_documents']+=1;IO['JSON_bytes']+=len(b)
    return loads(b.decode('utf-8'))


def rows(path):
    IO['gzip_stream_passes']+=1
    with gzip.open(path,'rb') as stream:
        for b in stream:
            IO['gzip_rows']+=1;IO['gzip_decoded_bytes']+=len(b)
            yield loads(b.decode('utf-8'))


def write(path,value):
    with Path(path).open('x',encoding='utf-8',newline='\n') as f:
        json.dump(value,f,indent=2,ensure_ascii=False,allow_nan=False);f.write('\n')


def git(*args):return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT)


def verify(mapping):
    for name,digest in mapping.items():need(sha(ROOT/name)==digest,'immutable SHA '+name)


def source_paths():return [*sorted((BASE/'tools').glob('*.py')),BASE/'.gitattributes',*(ROOT/n for n in DOCS)]


def inputs():
    return [RUN/'manifest.json',*(RUN/c/n for c in ('native','train') for n in (
        'completion.json','summary.json','audit.json','process_audit.json','events.jsonl.gz','public_trajectories.jsonl.gz')),
        *(ROOT/n for n in PRIOR),ROOT/'outputs/occam_reference_qualification_v1/freeze_validation_v1/complete.json',
        ROOT/'outputs/occam_reference_qualification_v1/freeze_validation_v1/validation_receipt.json']


@contextmanager
def record_only(destination, allowed):
    target=Path(destination).resolve();allowed={Path(p).resolve() for p in allowed}
    counts=dict(forbidden_imports=0,network_or_process_attempts=0,outside_writes=0,undeclared_reads=0)
    bad=('numpy','torch','mujoco','metaworld','gym','gymnasium','src.probe','src.rollout')
    need(not any(n==p or n.startswith(p+'.') for n in sys.modules for p in bad),'no science libraries preloaded')
    enabled=[True]
    def hook(event,args):
        if not enabled[0]:return
        if event=='import' and any(args[0]==p or args[0].startswith(p+'.') for p in bad):
            counts['forbidden_imports']+=1;raise RuntimeError('no science/model imports')
        if event.startswith('socket.') or event in ('subprocess.Popen','os.system','os.exec','os.posix_spawn'):
            counts['network_or_process_attempts']+=1;raise RuntimeError('no network or child process')
        if event=='open' and isinstance(args[0],(str,bytes,os.PathLike)):
            p=Path(os.fsdecode(args[0])).resolve();mode,flags=args[1:3]
            writing=(isinstance(mode,str) and any(c in mode for c in 'wax+')) or (type(flags) is int and bool(flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC)))
            inside=p==target or target in p.parents
            if writing and not inside:counts['outside_writes']+=1;raise RuntimeError('no writes outside analysis')
            if not writing and not inside and p not in allowed:counts['undeclared_reads']+=1;raise RuntimeError('undeclared file read')
    sys.addaudithook(hook)
    try:yield counts
    finally:enabled[0]=False


def admit():
    f=read(FREEZE);need(f['integrity']=='FROZEN_TRAIN_DECISION_CONTRACT_V1','frozen software')
    verify(f['source_sha256']);verify(f['input_sha256']);verify(f['scientific_source_sha256'])
    for n,h in f['source_sha256'].items():need(hashlib.sha256(git('show','HEAD:'+n)).hexdigest()==h,'freeze source committed before semantic read')
    need(git('show','HEAD:'+FREEZE.relative_to(ROOT).as_posix())==FREEZE.read_bytes(),'committed freeze receipt')
    need(not git('status','--porcelain','--untracked-files=no').strip(),'clean frozen tracked state')
    return f


def cases(cohort,manifest):
    specs=manifest['config']['populations'][cohort.upper()]
    events=iter(groupby(rows(RUN/cohort/'events.jsonl.gz'),lambda e:tuple(e[k] for k in core.KEYS)))
    pub=iter(rows(RUN/cohort/'public_trajectories.jsonl.gz'))
    sequence=0
    for i,s in enumerate(specs):
        k,es=next(events);need(k==tuple(s[z] for z in core.KEYS),'exact frozen population order')
        es=list(es)
        for e in es:
            need(e['sequence']==sequence and e['manifest_id']==MID,'source sequence and manifest');sequence+=1
        wrapped=next(pub);need(wrapped['sequence']==i,'public case sequence')
        yield s,wrapped['value'],es
    need(next(events,None) is None and next(pub,None) is None,'no omitted or surplus source cases')


def report(result,checks):
    c=result['by_cohort'];alias=result['alias_summary']
    lines=['# TRAIN公开决策输入与完整后继标签审计 v1','',
        '**事后描述性数据准入审计，不是训练、OPE、任务收益或新颖性结论。**','',
        '|来源|全部|任务失败|移动前输入|返回后输入|返回后仍需决策|窗口|固定T可监督标签|常数随机实现|',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for k,v in c.items():lines.append('|'+k+'|'+'|'.join(str(v[z]) for z in ('cases','task_failures','before_views','after_views','live_after_views','windows','static_TRAIN_labels','constant_random'))+'|')
    lines+=['','NATIVE仅作验证，训练标签计数恒为零。提前结束没有伪造边界；返回后结束保留终局，但没有增益决策。',
        '固定T标签只来自实际BLOCK_FIXED完整后继且只对应实际T；标签是事实监督关联，不证明因果风险或新人口泛化。',
        'RANDOM_WINDOW完整终局属于实际后续程序。即使观测到全程相同T，也受未来停止／序列筛选影响，本协议不将其当作未加权固定T标签；适当序贯估计仍需单独假设与协议。',
        '完整损失为成功时实际控制步、失败时500；剩余损失减去已付前缀，获取不重复收费。实际交互步与未执行失败惩罚分开。','',
        '|比较字段|时点|相同|不同|缺失|','|---|---|---:|---:|---:|']
    for k,v in alias.items():
        a,p=k.split(':');lines.append(f'|{a}|{p}|{v.get("EQUAL",0)}|{v.get("DIFFERENT",0)}|{v.get("MISSING",0)}|')
    lines+=['','相同仅指已声明公开输入投影，不是充分统计量、普遍不可识别证明或纯信息收益。返回后的获取臂字段本身属于公开历史，跨臂差异可能仅来自这个字段；组件差异逐项保存，不删字段制造别名。',
        '移动前积分直接来自ACQUISITION_CHOICE.before_memory；返回状态来自TASK_MEMORY_RETURN，先于首次WINDOW_DECISION。保留初始观测、完整实际历史、过去原始策略动作、发送命令、阶段、积分、控制器、预算与公共边界。',
        'seed／group／cohort／context／未来分配臂／行为名／未来T／全调度哈希／最终结局只作来源或标签，禁止进入决策输入。当前和过去的成功标志是实际观测。',
        '原混合events日志由JSON解码器读取，确含私有字段；主读取器只白名单提取公开actor载荷，独立读取器另用实际交付的STEP_COMPLETE.after。真实扰动、噪声、执行器oracle动作、私有witness均未进入视图。不能声称未读取含私有字节的文件。',
        '独立重建时禁用主模块全部自定义函数；共享JSON/gzip/SHA基础设施。复用原物理、进程及字节连续性审计，没有重新调用策略、模型或模拟环境。',
        f'独立审计记录检查{checks}项；这是数据核对数量，不是独立样本数。完整36来源×任务×条件×边界表包含NATIVE无分配的B32/B64零案例格；组层和全部案例保留。',
        '原行为概率与四接收者首次分歧审计按来源哈希复用，未重算PRNG、权重、模型或反馈。没有QUAL输入，没有用旧结局训练或选择参数。',
        '后续建议须依据实际支持另行冻结：先定义可监督对象、独立组划分、同预算完整风险／序贯DR强参考及独立自身历史部署，不能把本审计当成新算法。',
        '新环境／reset／帧／策略／模型查询／拟合／训练／种子／在线LLM均0；文件IO、哈希通读与墙钟另记。历史完整费用沿用来源和资格成本附录。',
        '完整QUAL原始数据ZIP及三次恢复仍待磁盘空间；本小型审计不替代该交付。CCF A目标未完成。','']
    with (OUT/'report_zh.md').open('x',encoding='utf-8',newline='\n') as stream:stream.write('\n'.join(lines))


def worker():
    start=perf_counter_ns();f=admit();request=read(OUT/'request.json')
    need(request['source_commit']==git('rev-parse','HEAD').decode().strip(),'parent source')
    manifest=read(RUN/'manifest.json');all_rows=[];checks=0
    allowed=[ROOT/n for n in f['source_sha256']|f['input_sha256']|f['scientific_source_sha256']]
    with record_only(OUT,allowed) as guard:
        for cohort in ('native','train'):
            summary=read(RUN/cohort/'summary.json')
            for (s,p,es),old in zip(cases(cohort,manifest),summary['rows'],strict=True):
                r=core.extract(s,p,es)
                need(all(r[k]==old[k] for k in ('total_steps','success','deadline_loss')),'source summary unchanged')
                all_rows.append(r)
        result=core.summarize(all_rows)
        write(OUT/'case_contracts.json',all_rows);write(OUT/'statistics.json',result)
        # No compute function from the main module can service the second pass.
        def deny(*args,**kwargs):raise RuntimeError('main contract functions disabled in independent audit')
        functions={n:deny for n,v in vars(core).items() if callable(v) and getattr(v,'__module__',None)==core.__name__}
        with mock.patch.multiple(core,**functions):
            cursor=0
            for cohort in ('native','train'):
                for s,p,es in cases(cohort,manifest):
                    checks+=audit.rebuild(s,p,es,all_rows[cursor]);cursor+=1
            need(cursor==len(all_rows)==684,'all source cases independently read')
            checks+=audit.audit_summary(all_rows,result)
        write(OUT/'audit.json',dict(integrity='PASSED_INDEPENDENT_TEMPORAL_CONTRACT_RECONSTRUCTION',
            checks=checks,cases=684,main_functions_disabled=sorted(functions),shared_JSON_gzip_SHA=True,
            private_physics_audits_reused=True,new_physics_or_models=False))
        report(result,checks)
        verify(f['source_sha256']);verify(f['input_sha256']);verify(f['scientific_source_sha256'])
        need(not any(guard.values()),'zero unexpected forbidden operations')
        write(OUT/'worker_complete.json',dict(integrity='PASSED_COMPLETE_TRAIN_DECISION_CONTRACT_AUDIT',
            source_manifest_id=MID,counters=ZERO,source_cases=684,TRAIN_cases=648,NATIVE_cases=36,
            semantic_stream_passes_per_cohort=dict(events=2,public_projection=2),
            source_IO=IO,guard=guard,wall_ns=perf_counter_ns()-start,model_weights_read=False,
            current_QUAL_read=False,original_comparisons_changed=False,publication_goal_complete=False))


def analyze():
    start=perf_counter_ns();f=admit();OUT.mkdir(exist_ok=False);source=git('rev-parse','HEAD').decode().strip()
    write(OUT/'request.json',dict(source_commit=source,manifest_id=MID,hard_timeout_seconds=1800,one_attempt_only=True,counters=ZERO))
    try:
        with (OUT/'stdout.log').open('xb') as so,(OUT/'stderr.log').open('xb') as se:
            p=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'--worker'],cwd=ROOT,stdout=so,stderr=se,timeout=1800)
        need(p.returncode==0,'one worker failed; preserve without retry')
        done=read(OUT/'worker_complete.json')
        write(OUT/'complete.json',dict(integrity=done['integrity'],source_commit=source,source_manifest_id=MID,
            freeze_sha256=sha(FREEZE),worker_receipt_sha256=sha(OUT/'worker_complete.json'),
            artifact_sha256={p.name:sha(p) for p in OUT.iterdir() if p.is_file()},
            parent_IO=IO,total_parent_wall_ns=perf_counter_ns()-start,counters=ZERO,no_retry=True,
            full_QUAL_raw_delivery_complete=False,publication_goal_complete=False))
        print(json.dumps(dict(integrity=done['integrity'],source_cases=684,counters=ZERO)),flush=True)
    except Exception as e:
        write(OUT/'failure.json',dict(integrity='PRESERVED_CONTRACT_AUDIT_FAILURE',reason=str(e),
            traceback=traceback.format_exc(),source_commit=source,counters=ZERO));raise


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser();parser.add_argument('--worker',action='store_true');args=parser.parse_args()
    worker() if args.worker else analyze()

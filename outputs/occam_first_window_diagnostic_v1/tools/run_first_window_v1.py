"""Freeze now; analyze only after the complete immutable QUAL and all audits."""
from contextlib import contextmanager, ExitStack, redirect_stdout, redirect_stderr
from pathlib import Path
from time import perf_counter_ns
from unittest.mock import patch
import argparse
import gzip
import hashlib
import importlib.abc
import io
import json
import socket
import subprocess
import sys
import unittest

import first_window_engine_v1 as e
import first_window_audit_v1 as a

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT/'outputs/occam_first_window_diagnostic_v1'
DOC = ROOT/'docs/protocols/occam_first_window_diagnostic_v1_zh.md'
DESIGN = ROOT/'docs/research/occam_first_window_diagnostic_design_v1_zh.md'
RUN = ROOT/'outputs/occam_reference_qualification_v1/qualification_v1/occam_reference_qualification_v1_20261028T125131Z_7abaec83b085'
MID = '19347fbe7b039fabd536c411d74e87a823bd0925cd2bee9e5705329cdb77f78d'
SCIENCE = '7abaec83b0854f099d6f13f308cc8cd552f50e2b'
FREEZE = BASE/'freeze_v1/complete.json'
OUT = BASE/'analysis_v1'
GATES = ('qual/summary.json','qual/completion.json','qual/process_audit.json','qual/audit.json',
         'statistics_v1/statistics.json','statistics_v1/independent_audit.json','pipeline_v1/complete.json')
IO_COUNTS = dict(SHA256_file_passes=0,SHA256_bytes=0,JSON_document_reads=0,JSONL_rows_decoded=0,JSONL_UTF8_bytes=0)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for raw in iter(lambda:f.read(1024**2), b''): h.update(raw); IO_COUNTS['SHA256_bytes']+=len(raw)
    IO_COUNTS['SHA256_file_passes']+=1
    return h.hexdigest()


def unique(pairs):
    result = {}
    for key, value in pairs:
        e.require(key not in result, 'duplicate JSON key'); result[key] = value
    return result


def loads(raw):
    return json.loads(raw, object_pairs_hook=unique, parse_constant=lambda x: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def read(path):
    IO_COUNTS['JSON_document_reads']+=1
    return loads(Path(path).read_text(encoding='utf8'))


def write(path, value):
    with Path(path).open('x',encoding='utf8',newline='\n') as f:
        json.dump(value,f,indent=2,ensure_ascii=False,allow_nan=False); f.write('\n')


def rows(path):
    opener = gzip.open if str(path).endswith('.gz') else open
    with opener(path,'rt',encoding='utf8') as f:
        for line in f:
            IO_COUNTS['JSONL_rows_decoded']+=1; IO_COUNTS['JSONL_UTF8_bytes']+=len(line.encode('utf8'))
            yield loads(line)


def verify(bindings):
    for name, value in bindings.items(): e.require(sha(ROOT/name) == value, 'immutable source '+name)


def counters():
    return dict(environment_steps=0,controlled_resets=0,all_resets=0,physical_frames=0,policy_queries=0,
                network_forward_predictions=0,posterior_updates=0,model_fits=0,optimizer_updates=0,
                new_episode_allocations=0,online_LLM_API_calls=0)


@contextmanager
def record_only():
    class Block(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path, target=None):
            if fullname.split('.')[0] in ('src','metaworld','mujoco','gymnasium','torch','openai','requests','httpx'):
                raise RuntimeError('record-only reader forbids execution/model imports: '+fullname)
    def denied(*args, **kwargs): raise RuntimeError('record-only reader forbids network or process execution')
    block = Block(); sys.meta_path.insert(0,block)
    try:
        with patch.object(socket,'socket',denied), patch.object(socket,'create_connection',denied), patch.object(subprocess,'Popen',denied): yield
    finally: sys.meta_path.remove(block)


def admit(root, reader=read, checksum=sha):
    """All terminal markers must exist BEFORE any outcome-bearing metadata read."""
    root = Path(root)
    e.require(not (root/'CLOSED_TECHNICAL_FAILURE.json').exists(), 'technical allocation closed; no partial diagnosis')
    e.require(all((root/n).is_file() for n in GATES), 'full collection, both audits and original independent statistics required')
    pipe = reader(root/'pipeline_v1/complete.json')
    e.require(pipe['integrity'] == 'PASSED_COMPLETE_SEQUENCE' and pipe['failure'] is None and pipe['report_returncode'] == 0, 'terminal original pipeline')
    m = reader(root/'manifest.json'); e.require(m['manifest_id'] == MID == pipe['manifest_id'] and m['source_git_commit'] == SCIENCE, 'one fixed scientific run')
    e.require(e.digest({k:v for k,v in m.items() if k != 'manifest_id'}) == MID, 'complete manifest digest')
    s = reader(root/'qual/summary.json'); done = reader(root/'qual/completion.json')
    e.require(s['status'] == done['status'] == 'COLLECTED_FOR_INDEPENDENT_AUDIT'
              and s['executions'] == s['allocated_executions'] == 1566 and s['failure'] is None, 'all 1566 original executions')
    for name,h in done['artifact_sha256'].items():
        e.require(Path(name).name == name and checksum(root/'qual'/name) == h, 'immutable collected root artifact '+name)
    p = reader(root/'qual/process_audit.json'); audit = reader(root/'qual/audit.json')
    e.require(p['integrity'] == 'PASSED_ISOLATED_PROCESS_AND_BYTE_CONTINUITY_ONLY' and p['executions'] == 1566
              and audit['integrity'] == 'PASSED' and audit['counts']['executions'] == 1566
              and audit['manifest_id'] == MID, 'complete byte and dynamics audits')
    stats = reader(root/'statistics_v1/statistics.json'); independent = reader(root/'statistics_v1/independent_audit.json')
    e.require(stats['integrity'] == independent['integrity'] == 'PASSED' and stats['manifest_id'] == independent['manifest_id'] == MID
              and independent['all_executions'] == 1566 and independent['production_statistics_disabled'] is True, 'original independent statistics integrity')
    e.require(stats['source_audit_sha256'] == checksum(root/'qual/audit.json')
              and independent['source_statistics_sha256'] == checksum(root/'statistics_v1/statistics.json')
              and stats['bootstrap_indices_sha256'] == checksum(root/'statistics_v1/bootstrap_indices.json.gz')
              and audit['prequential_windows_sha256'] == checksum(root/'qual/prequential_windows.jsonl.gz'), 'immutable primary statistics chain')
    # Scientific gates may be FALSE. They are never replaced or used for selection.
    return m, audit, stats


class Parts:
    def __init__(self, directory): self.directory=Path(directory); self.stream=None; self.size=0; self.count=0; self.parts=[]; self.total=0
    def add(self,value):
        raw=(json.dumps(value,separators=(',',':'),allow_nan=False)+'\n').encode()
        e.require(len(raw) <= 4*1024**2, 'bounded capsule record')
        if self.stream is None or self.size+len(raw)>4*1024**2:
            self.close(); self.path=self.directory/('capsules_%03d.jsonl'%(len(self.parts)+1)); self.stream=self.path.open('xb'); self.size=self.count=0
        self.stream.write(raw); self.size+=len(raw); self.count+=1; self.total+=1
    def close(self):
        if self.stream is not None:
            self.stream.close(); self.parts.append(dict(path=self.path.name,bytes=self.size,rows=self.count,sha256=sha(self.path))); self.stream=None


def capsule_rows():
    index=read(OUT/'capsule_parts.json'); total=0
    for part in index['parts']:
        name=part['path']; e.require(Path(name).name==name, 'owned bounded part')
        path=OUT/name; e.require(path.stat().st_size==part['bytes']<=4*1024**2 and sha(path)==part['sha256'], 'capsule part bytes')
        count=0
        for row in rows(path): total+=1; count+=1; yield row
        e.require(count==part['rows'], 'part row count')
    e.require(total==index['rows']==1296, 'all same-prefix capsules')


def deadline(start): e.require(perf_counter_ns()-start <= 1800*10**9, 'fixed complete analysis plus audit wall cap')


def source_files(m):
    files = {n:sha(RUN/n) for n in (*GATES,'manifest.json','qual/cases.jsonl.gz','qual/events.jsonl.gz',
                'qual/witnesses.jsonl.gz','qual/prequential_windows.jsonl.gz','statistics_v1/bootstrap_indices.json.gz')}
    for i in range(1,1567):
        for name in ('case.json','events.jsonl.gz','witnesses.jsonl.gz'):
            n='qual/case_%04d/%s'%(i,name); files[n]=sha(RUN/n)
    return files


def run_main(m, source_audit, start):
    specs=m['config']['populations']['QUAL']; e.require(len(specs)==1566, 'fixed complete allocation')
    panels=source_audit['panels']; e.require(len(panels)==1566, 'all original audit panels')
    registry=[]; contexts=[]; pending=[]; parts=Parts(OUT)
    try:
        for i,(spec,panel) in enumerate(zip(specs,panels),1):
            deadline(start); folder=RUN/'qual'/('case_%04d'%i); case=read(folder/'case.json'); e.validate_case(case,spec)
            for key in ('success','deadline_loss','total_steps'): e.require(case[key]==panel[key], 'original audit bound case '+key)
            e.require(all(panel[k]==spec[k] for k in e.FIELDS), 'source panel allocation')
            same_prefix='__' in spec['program']
            registry.append(dict(case_index=i,spec=spec,success=case['success'],deadline_loss=case['deadline_loss'],
                total_steps=case['total_steps'],task_failure=not case['success'],
                first_window_diagnostic=same_prefix,exclusion_reason=None if same_prefix else 'DIFFERENT_CONTROL_PREFIX_RETAINED_IN_ORIGINAL_PRIMARY_RESULT'))
            if same_prefix:
                capsule=e.extract(case,spec,rows(folder/'events.jsonl.gz'),rows(folder/'witnesses.jsonl.gz'))
                parts.add(dict(case_index=i,value=capsule)); pending.append(capsule)
                if len(pending)==8:
                    contexts.append(e.context_diagnostics(pending,m['config']['prediction_constant'])); pending=[]
    finally: parts.close()
    e.require(not pending and len(contexts)==162 and len(registry)==1566, 'all registered contexts and failures')
    write(OUT/'case_registry.json',dict(QUAL_executions=1566,NATIVE_executions_separate=174,rows=registry))
    write(OUT/'capsule_parts.json',dict(parts=parts.parts,rows=parts.total,max_part_bytes=4*1024**2))
    with (OUT/'contexts.jsonl').open('x',encoding='utf8',newline='\n') as f:
        for row in contexts: f.write(json.dumps(row,separators=(',',':'),allow_nan=False)+'\n')
    write(OUT/'statistics.json',e.all_statistics(contexts))
    return contexts


def run_audit(m, contexts, start):
    registry=read(OUT/'case_registry.json')['rows']; saved=iter(capsule_rows()); capsules=[]; cursor=0; checked=0
    def denied(*args,**kwargs): raise RuntimeError('primary diagnostic reader/arithmetic forbidden in independent audit')
    with patch.multiple(e,extract=denied,context_diagnostics=denied,vector_metrics=denied,rank_errors=denied,summary=denied,all_statistics=denied):
        for i,spec in enumerate(m['config']['populations']['QUAL'],1):
            deadline(start); folder=RUN/'qual'/('case_%04d'%i); case=read(folder/'case.json'); r=registry[i-1]
            a.need(r['case_index']==i and r['spec']==spec and all(r[k]==case[k] for k in ('success','deadline_loss','total_steps'))
                   and r['task_failure']==(not case['success']), 'independent complete case registry')
            if '__' not in spec['program']: a.need(r['first_window_diagnostic'] is False, 'strong controls retained separately'); continue
            a.need(r['first_window_diagnostic'] is True and r['exclusion_reason'] is None, 'same-prefix registration')
            reconstructed=a.literal_extract(case,spec,rows(folder/'events.jsonl.gz'),rows(folder/'witnesses.jsonl.gz'))
            s=next(saved); a.need(s['case_index']==i and s['value']==reconstructed, 'independent raw source capsule'); checked+=1
            capsules.append(reconstructed)
            if len(capsules)==8:
                row=contexts[cursor]; base=capsules[0]['spec']
                a.need(row['context']=={k:base[k] for k in ('group','task','context','planned_boundary')}
                       and row['acquisition_action']==base['program'].split('__')[1]
                       and row['allocated_programs']==[c['spec']['program'] for c in capsules], 'independent context identity')
                a.verify_context(capsules,row,m['config']['prediction_constant']); cursor+=1; capsules=[]
        a.need(not capsules and next(saved,None) is None and checked==1296 and cursor==162, 'all independent context records')
        stats=read(OUT/'statistics.json')
        a.need(stats['contexts']==162 and stats['cells_count']==len(stats['cells'])==216, 'independent all cells')
        a.need(len(stats['by_target'])==4 and stats['post_hoc_descriptive_only'] is True
               and stats['new_scientific_gate'] is False and stats['task_value_estimated'] is False, 'independent scope and complete model summaries')
        for target,s in zip(e.TARGETS,stats['by_target']): a.verify_summary(contexts,target,s)
        seen=set()
        for cell in stats['cells']:
            key=(cell['target'],cell['task'],cell['context'],cell['boundary'],cell['arm']); a.need(key not in seen,'unique diagnostic cell'); seen.add(key)
            subset=[r for r in contexts if r['context']['task']==cell['task'] and r['context']['context']==cell['context']
                    and r['context']['planned_boundary']==cell['boundary'] and r['acquisition_action']==cell['arm']]
            a.need(len(subset)==3, 'three independent groups per complete cell'); a.verify_summary(subset,cell['target'],cell)
    return dict(integrity='PASSED_INDEPENDENT_RECORD_READER_AND_FRACTION_ARITHMETIC',registered_executions=1566,
                capsules=checked,contexts=cursor,cells=216,production_diagnostic_functions_disabled=True,
                shared_strict_JSON_codec_and_admission_disclosed=True,independent_physics_resimulation=False,counters=counters())


def freeze():
    FREEZE.parent.mkdir(exist_ok=False); start=perf_counter_ns()
    m=read(RUN/'manifest.json'); e.require(m['manifest_id']==MID and m['source_git_commit']==SCIENCE, 'frozen run metadata only')
    verify(m['source_sha256']); verify(m['input_sha256'])
    source={p.relative_to(ROOT).as_posix():sha(p) for p in sorted((BASE/'tools').glob('*.py'))+[BASE/'.gitattributes',DOC,DESIGN]}
    for name in source:
        if name.endswith('.py'): compile((ROOT/name).read_bytes(),name,'exec')
    stream=io.StringIO()
    with record_only(),redirect_stdout(stream),redirect_stderr(stream):
        suite=unittest.defaultTestLoader.discover(str(BASE/'tools'),pattern='test_first_window_v1.py')
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    (FREEZE.parent/'unit_tests.log').write_text(stream.getvalue(),encoding='utf8',newline='\n')
    e.require(result.wasSuccessful() and result.testsRun>=30, 'complete pure-array and constructed-record checks')
    verify(source); verify(m['source_sha256']); verify(m['input_sha256'])
    write(FREEZE,dict(integrity='FROZEN_RECORD_ONLY_FIRST_WINDOW_DIAGNOSTIC_SOFTWARE',source_sha256=source,
        run_manifest_sha256=sha(RUN/'manifest.json'),manifest_id=MID,scientific_source_commit=SCIENCE,
        tests=result.testsRun,test_log_sha256=sha(FREEZE.parent/'unit_tests.log'),
        full_scientific_source_files_unchanged=len(m['source_sha256']),QUAL_outcomes_read=False,full_diagnostic_started=False,
        original_primary_comparisons_unchanged=True,post_hoc_descriptive_only=True,
        analysis_caps=dict(QUAL_case_registrations=1566,same_prefix_capsules=1296,contexts=162,cells=216,
                           semantic_case_passes=2,first_window_event_prefix_passes=2,catalog_byte_hash_passes=2,total_wall_seconds=1800),
        zero_model_computation_including_posterior_updates=True,counters=counters(),wall_ns=perf_counter_ns()-start))
    return dict(integrity='FROZEN_RECORD_ONLY_FIRST_WINDOW_DIAGNOSTIC_SOFTWARE',tests=result.testsRun,analysis_started=False)


def analyze():
    # Fail before creating an output or reading QUAL results when allocation is live.
    e.require(all((RUN/n).is_file() for n in GATES) and not (RUN/'CLOSED_TECHNICAL_FAILURE.json').exists(), 'terminal original qualification required')
    f=read(FREEZE); verify(f['source_sha256']); e.require(sha(RUN/'manifest.json')==f['run_manifest_sha256'],'fixed manifest bytes')
    git=['git','-c','maintenance.auto=false','-c','gc.auto=0']
    e.require(not subprocess.check_output(git+['status','--porcelain','--untracked-files=no'],cwd=ROOT).strip(), 'committed diagnostic freeze')
    for name in (*f['source_sha256'],FREEZE.relative_to(ROOT).as_posix()):
        e.require(subprocess.check_output(git+['show','HEAD:'+name],cwd=ROOT)==(ROOT/name).read_bytes(), 'actual Git diagnostic freeze '+name)
    start=perf_counter_ns(); OUT.mkdir(exist_ok=False)
    for key in IO_COUNTS: IO_COUNTS[key]=0
    try:
        with record_only():
            m,source_audit,original_stats=admit(RUN); verify(m['source_sha256']); verify(m['input_sha256'])
            catalog=source_files(m); deadline(start); write(OUT/'source_catalog.json',catalog)
            write(OUT/'intent.json',dict(manifest_id=MID,scientific_source_commit=SCIENCE,
                diagnostic_freeze_sha256=sha(FREEZE),original_task_qualified=original_stats['task_qualified'],
                original_prediction_qualified=original_stats['prediction']['qualified'],post_hoc_descriptive_only=True))
            contexts=run_main(m,source_audit,start); main_ns=perf_counter_ns()-start
            audit=run_audit(m,contexts,start); write(OUT/'audit.json',audit)
            for name,h in catalog.items(): e.require(sha(RUN/name)==h,'source unchanged after diagnostic '+name)
            verify(m['source_sha256']); verify(m['input_sha256']); verify(f['source_sha256']); deadline(start)
            stats=read(OUT/'statistics.json')
            report=['# 首窗口全候选诊断 v1','', '**事后描述性分析**。原主比较和科学资格结论保持原样。', '',
                '完整登记1566次QUAL，Native174另列；1296条同前缀记录，162起点，216个完整分层格。',
                'ADAPT与FROZEN首窗同bank预测不作为独立样本。缺失不填零、短终止不删除。', '',
                '|接收者|四候选MSE（组等权）|首窗选择差|首窗排序错误|', '|---|---:|---:|---:|']
            for item in stats['by_target']:
                mean=item['equal_available_group_means']; report.append('|%s|%s|%s|%s|'%(item['target'],mean['MSE']['mean'],mean['first_window_choice_gap']['mean'],mean['rank_error']['mean']))
            report.extend(['','全部向量、原失败、缺失原因、组分母和216分层格见同目录记录。',
                '固定T完整结局仅属于其实际恒定程序，不能贴给之后会改变T的学习接收者。',
                '没有模拟未执行轨迹、选择门、置信界或因果失败归因；不能据此宣称任务收益或CCF A贡献。',
                '若当前接收者不具竞争力，保持封存；本诊断不授权在旧QUAL上调整它。',
                '新增环境、重置、物理帧、政策查询、模型前向、后验更新、拟合、训练、种子及在线LLM API均0。',
                '哈希及原始JSON编解码共享；独立记录／Fraction检查禁用主诊断函数，没有独立物理重仿真。'])
            (OUT/'report_zh.md').write_text('\n'.join(report)+'\n',encoding='utf8',newline='\n')
            write(OUT/'complete.json',dict(integrity='PASSED_COMPLETE_POST_HOC_DESCRIPTION',manifest_id=MID,
                source_files=len(catalog),registered_executions=1566,capsules=1296,contexts=162,cells=216,
                main_wall_ns=main_ns,total_wall_ns=perf_counter_ns()-start,counters=counters(),
                catalog_byte_hash_passes=2,additional_admission_and_code_hash_passes_disclosed=True,
                actual_IO_counts=dict(IO_COUNTS),semantic_case_passes=2,first_window_event_prefix_passes=2,
                original_statistics_sha256=sha(RUN/'statistics_v1/statistics.json'),
                original_primary_comparisons_unchanged=True,publication_goal_complete=False))
    except BaseException as error:
        if not (OUT/'failure.json').exists(): write(OUT/'failure.json',dict(type=type(error).__name__,message=str(error),wall_ns=perf_counter_ns()-start,no_retry_or_source_changes=True))
        raise
    return dict(integrity='PASSED_COMPLETE_POST_HOC_DESCRIPTION',wall_ns=perf_counter_ns()-start)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('command',choices=('freeze','analyze')); x=p.parse_args()
    print(freeze() if x.command=='freeze' else analyze(),flush=True)

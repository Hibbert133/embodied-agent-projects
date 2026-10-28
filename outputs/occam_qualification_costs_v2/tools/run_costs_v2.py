"""Freeze and run the accounting-compatible, record-only cost reader once."""
from contextlib import redirect_stdout,redirect_stderr
from pathlib import Path
from time import perf_counter_ns
from collections import Counter
from unittest.mock import patch
import argparse,csv,hashlib,io,json,subprocess,sys,unittest
ROOT=Path(__file__).resolve().parents[3];BASE=ROOT/'outputs/occam_qualification_costs_v2';OUT=BASE/'analysis_v1';FREEZE=BASE/'freeze_v1/complete.json'
sys.path.insert(0,str(ROOT/'outputs/occam_qualification_costs_v1/tools'))
import run_costs_v1 as old
import costs_engine_v1 as e
import costs_audit_v1 as old_audit
import accounting_reader_v2 as r
import accounting_audit_v2 as independent
gate=old.gate;RUN=old.RUN;DOC=ROOT/'docs/protocols/occam_qualification_costs_reader_v2_zh.md'
RAW_IO=dict(metadata_JSON_documents=0,metadata_bytes_read=0,catalog_in_memory_SHA256_evaluations=0,parent_artifact_byte_SHA256_checks=0)


def freeze():
    FREEZE.parent.mkdir(exist_ok=False);start=perf_counter_ns()
    m=gate.read(RUN/'manifest.json');gate.verify(m['source_sha256']);gate.verify(m['input_sha256'])
    previous=gate.read(old.FREEZE);gate.verify(previous['source_sha256'])
    guard=gate.read(gate.FREEZE)['source_sha256'];gate.verify(guard)
    sources={p.relative_to(ROOT).as_posix():gate.sha(p) for p in sorted((BASE/'tools').glob('*.py'))+[BASE/'.gitattributes',DOC,BASE/'development_v1/schema_census.json',BASE/'development_v1/v1_stderr.log',ROOT/'outputs/occam_qualification_costs_v1/analysis_v1/failure.json']}
    fixtures={}
    for phase,index in (('NATIVE',1),('NATIVE',28),('QUAL',1),('QUAL',28)):
        folder=RUN/phase.lower()/('case_%04d'%index)
        for name in ('case.json','accounting.json','result.json'):
            p=folder/name;fixtures[p.relative_to(ROOT).as_posix()]=gate.sha(p)
    stream=io.StringIO()
    with gate.record_only(),redirect_stdout(stream),redirect_stderr(stream):
        suite=unittest.defaultTestLoader.discover(str(BASE/'tools'),pattern='test_accounting_reader_v2.py')
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    (FREEZE.parent/'unit_tests.log').write_text(stream.getvalue(),encoding='utf8',newline='\n')
    e.require(result.wasSuccessful() and result.testsRun==15,'all accounting compatibility checks')
    for name in sources:
        if name.endswith('.py'):compile((ROOT/name).read_bytes(),name,'exec')
    for binding in (sources,fixtures,previous['source_sha256'],guard,m['source_sha256'],m['input_sha256']):gate.verify(binding)
    gate.write(FREEZE,dict(integrity='FROZEN_EXPLICIT_ACCOUNTING_COST_READER_V2',source_sha256=sources,saved_metadata_test_inputs_sha256=fixtures,
        reused_cost_source_sha256=previous['source_sha256'],reused_cost_freeze_sha256=gate.sha(old.FREEZE),reused_guard_source_sha256=guard,
        manifest_sha256=gate.sha(RUN/'manifest.json'),formal_test_log_sha256=gate.sha(FREEZE.parent/'unit_tests.log'),
        new_unique_tests=15,development_test_executions=15,formal_test_executions=15,
        original_cost_checks_source_bound_reused=25,actual_metadata_regression_cases=4,scientific_sources_unchanged=1393,
        prior_cost_failure_retained=True,complete_cost_reanalysis_started=False,new_environment_interactions=0,new_real_model_queries=0,
        new_fits=0,online_LLM_API_calls=0,wall_ns=perf_counter_ns()-start,publication_goal_complete=False))
    return dict(integrity='FROZEN_EXPLICIT_ACCOUNTING_COST_READER_V2',new_tests=15)


def raw_json(path):
    raw=path.read_bytes();RAW_IO['metadata_JSON_documents']+=1;RAW_IO['metadata_bytes_read']+=len(raw)
    return gate.loads(raw.decode('utf8')),raw


def records(m,phase):
    previous=dict(counts={},by_phase={})
    for index,spec in enumerate(m['config']['populations'][phase],1):
        folder=RUN/phase.lower()/('case_%04d'%index);values={};raws={}
        for name in ('case.json','accounting.json','result.json'):values[name],raws[name]=raw_json(folder/name)
        case=values['case.json'];e.require(case['ledger_before']==previous,'whole serial lifecycle');previous=case['ledger_after_close']
        yield index,spec,folder,case,values['accounting.json'],values['result.json'],raws


def deadline(start):e.require(perf_counter_ns()-start<1800*10**9,'full cost analysis and independent audit wall cap')


def analyze():
    start=perf_counter_ns()
    e.require(all((RUN/n).is_file() for n in (*gate.GATES,'report_v1/complete.json','report_v1/source_manifest.json')),'terminal original qualification first')
    for key in gate.IO_COUNTS:gate.IO_COUNTS[key]=0
    for key in RAW_IO:RAW_IO[key]=0
    f=gate.read(FREEZE)
    for key in ('source_sha256','saved_metadata_test_inputs_sha256','reused_cost_source_sha256','reused_guard_source_sha256'):gate.verify(f[key])
    e.require(gate.sha(RUN/'manifest.json')==f['manifest_sha256'] and gate.sha(old.FREEZE)==f['reused_cost_freeze_sha256'],'fixed manifest and original cost freeze')
    git=['git','-c','maintenance.auto=false','-c','gc.auto=0']
    e.require(not subprocess.check_output(git+['status','--porcelain','--untracked-files=no'],cwd=ROOT).strip(),'committed v2 reader first')
    names=set(f['source_sha256'])|set(f['reused_cost_source_sha256'])|{FREEZE.relative_to(ROOT).as_posix()}
    for name in sorted(names):e.require(subprocess.check_output(git+['show','HEAD:'+name],cwd=ROOT)==(ROOT/name).read_bytes(),'actual committed reader '+name)
    m=old.ready();OUT.mkdir(exist_ok=False);historical=gate.read(old.HIST);phases={};all_rows=[];catalog={}
    try:
        with gate.record_only():
            for phase in ('NATIVE','QUAL'):
                rows=[];sources=Counter()
                for index,spec,folder,case,accounting,parent,raws in records(m,phase):
                    deadline(start);RAW_IO['parent_artifact_byte_SHA256_checks']+=2
                    source=r.authenticate(case,spec,accounting,parent,index=index,case_bytes=raws['case.json'],accounting_bytes=raws['accounting.json'])
                    sources[source]+=1;rows.append(r.project(case,spec,accounting))
                    for name,raw in raws.items():
                        catalog[(folder/name).relative_to(ROOT).as_posix()]=hashlib.sha256(raw).hexdigest();RAW_IO['catalog_in_memory_SHA256_evaluations']+=1
                summary=gate.read(RUN/phase.lower()/'summary.json');audit=gate.read(RUN/phase.lower()/'audit.json')
                phases[phase]=dict(**e.check_phase(rows,summary,audit),programs=e.program_table(rows,historical),
                    API_cost_provenance=r.check_phase_api(summary,audit,rows,sources),
                    recorded_collection_wall_ns=summary['wall_ns'],recorded_full_audit_wall_ns=audit['wall_ns'])
                all_rows+=rows
            e.require(len(all_rows)==1740,'whole original population, no failure exclusion')
            gate.write(OUT/'cases.json',all_rows);gate.write(OUT/'costs.json',dict(phases=phases,historical_sources_original=historical,
                original_case_bytes_unchanged=True,missing_case_field_not_default_zero=True,source_training_subsets_not_added_to_whole_studies=True,
                standalone_source_views_not_actual_project_sum=True,old_unknown_costs_not_zero=True,primary_statistics_unchanged=True))
            saved=iter(gate.read(OUT/'cases.json'))
            with patch.object(r,'authenticate',None),patch.object(r,'project',None),patch.object(r,'check_phase_api',None),\
                patch.object(e,'case_cost',None),patch.object(e,'increment',None),patch.object(e,'program_table',None),patch.object(e,'check_phase',None):
                for phase in ('NATIVE','QUAL'):
                    subset=[];sources=[]
                    for index,spec,folder,case,accounting,parent,raws in records(m,phase):
                        deadline(start);row=next(saved);RAW_IO['parent_artifact_byte_SHA256_checks']+=2
                        sources.append(independent.verify(case,spec,accounting,parent,index,raws['case.json'],raws['accounting.json'],row))
                        old_audit.verify_case(case,spec,row);subset.append(row)
                    old_audit.verify_programs(subset,historical,phases[phase]['programs'])
                    summary=gate.read(RUN/phase.lower()/'summary.json');audit=gate.read(RUN/phase.lower()/'audit.json')
                    old_audit.verify_phase(subset,summary,audit,phases[phase]);independent.verify_phase(summary,audit,subset,sources,phases[phase]['API_cost_provenance'])
                independent.need(next(saved,None) is None,'all independent cases consumed')
            for name,h in catalog.items():e.require(gate.sha(ROOT/name)==h,'raw source unchanged after complete read '+name)
            gate.verify(m['source_sha256']);gate.verify(m['input_sha256'])
            for key in ('source_sha256','reused_cost_source_sha256','reused_guard_source_sha256'):gate.verify(f[key])
            old.ready();deadline(start);gate.write(OUT/'source_catalog.json',catalog)
            fields=('executions','control_steps','all_resets','physical_frames','fixed_policy_queries','trained_model_declarations','candidate_predictions','recorded_parameter_update_attempts','C4_C8_fit_attempts')
            lines=['# 完整资格成本附录 v2','','**事后资源记账，原科学资格与全部主比较不变。**','',
                '旧v1读取器因120条legacy case缺少API字段而失败，原失败和源码保留。本版核对每例accounting显式计数、网络守卫与原父回执哈希，未以缺字段默认0。','',
                '|阶段|执行|实际控制步|全部reset|物理帧|政策查询|NN声明|候选预测|参数更新|C4/C8拟合|','|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
            for phase,p in phases.items():lines.append('|%s|%s|'%(phase,'|'.join(str(p['totals'][k]) for k in fields)))
            lines+=['','完整58行逐阶段／程序费用见program_costs.csv；假设单独来源摊销只作资源视图，不替换原截止损失主标准。',
                '核心eig／收集solve是固定代码重建；原完整审计重放／独立batch／cold guard运算与阶段wall分别保留。case总wall不是隔离NN推断延迟。',
                '历史共同NN训练9000更新，不按程序数相乘；单bank假设5000更新。C8训练3072步包含在完整3840步来源内，旧未知费用不填0。',
                '当前资格API／tokens均0，平均API延迟null；不代表所有历史项目API费用为0。本分析新增物理交互、模型推断／拟合和API均0。',
                '独立复算禁用主成本投影和API适配器；JSON、SHA、路径布局及旧标量成本检查明确复用，不是物理重仿真或新算法。']
            (OUT/'report_zh.md').write_text('\n'.join(lines)+'\n',encoding='utf8',newline='\n')
            with (OUT/'program_costs.csv').open('x',encoding='utf8',newline='') as file:
                columns=['phase','program',*e.ADDITIVE,'source_controls','source_all_resets','source_frames','standalone_AdamW_updates','actual_online_control_mean_exact','standalone_source_plus_online_control_mean_exact']
                writer=csv.DictWriter(file,fieldnames=columns);writer.writeheader()
                for phase,p in phases.items():
                    for item in p['programs']:
                        source=item['hypothetical_standalone_source'];writer.writerow(dict(phase=phase,program=item['program'],**item['observed'],
                            **{k:source[k] for k in ('source_controls','source_all_resets','source_frames','standalone_AdamW_updates')},
                            actual_online_control_mean_exact=item['actual_online_control_mean_exact'],standalone_source_plus_online_control_mean_exact=item['standalone_source_plus_online_control_mean_exact']))
            deadline(start)
            gate.write(OUT/'complete.json',dict(integrity='PASSED_EXPLICIT_ACCOUNTING_COST_RECONSTRUCTION_V2',manifest_id=m['manifest_id'],executions=1740,
                semantic_record_passes=2,catalog_hash_passes=2,additional_parent_artifact_hashes_and_admission_source_hashes_disclosed=True,
                raw_metadata_IO=dict(RAW_IO),other_file_IO=dict(gate.IO_COUNTS),Git_reader_objects_checked=len(names),
                primary_statistics_unchanged=True,original_case_bytes_unchanged=True,new_environment_interactions=0,new_real_model_queries=0,
                new_fits=0,online_LLM_API_calls=0,wall_ns=perf_counter_ns()-start,publication_goal_complete=False))
    except BaseException as error:
        gate.write(OUT/'failure.json',dict(type=type(error).__name__,message=str(error),no_retry_or_overwrite=True));raise
    return dict(integrity='PASSED_EXPLICIT_ACCOUNTING_COST_RECONSTRUCTION_V2',executions=1740)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=('freeze','analyze'));x=parser.parse_args()
    print(json.dumps(freeze() if x.command=='freeze' else analyze()),flush=True)

"""Freeze a cost addendum; analyze only complete independently audited QUAL."""
from contextlib import redirect_stdout,redirect_stderr
from pathlib import Path
from time import perf_counter_ns
from unittest.mock import patch
import argparse,io,json,sys,unittest,subprocess

ROOT=Path(__file__).resolve().parents[3];BASE=ROOT/'outputs/occam_qualification_costs_v1';OUT=BASE/'analysis_v1';FREEZE=BASE/'freeze_v1/complete.json'
sys.path.insert(0,str(ROOT/'outputs/occam_first_window_diagnostic_v1/tools'))
import run_first_window_v1 as gate
import costs_engine_v1 as e
import costs_audit_v1 as a
RUN=gate.RUN;HIST=ROOT/'outputs/occam_reference_qualification_v1/freeze_validation_v1/historical_source_costs.json'
DOC=ROOT/'docs/protocols/occam_qualification_costs_v1_zh.md'
COMPONENTS=('src/probe/occam_performance_core_v1.py','src/probe/occam_training_program_v1.py',
    'src/probe/occam_qualification_provider_v1.py','src/probe/occam_qualification_program_v1.py',
    'src/analysis/occam_qualification_math_audit_v1.py','src/analysis/occam_performance_independent_v1.py')


def freeze():
    FREEZE.parent.mkdir(exist_ok=False);start=perf_counter_ns()
    source={p.relative_to(ROOT).as_posix():gate.sha(p) for p in sorted((BASE/'tools').glob('*.py'))+[BASE/'.gitattributes',DOC]}
    model=gate.read(RUN/'manifest.json')
    e.require(model['manifest_id']==gate.MID and model['source_git_commit']==gate.SCIENCE
              and gate.e.digest({k:v for k,v in model.items() if k!='manifest_id'})==gate.MID,'fixed original manifest')
    gate.verify(model['source_sha256']);gate.verify(model['input_sha256'])
    binding={n:model['source_sha256'][n] for n in COMPONENTS};binding[HIST.relative_to(ROOT).as_posix()]=gate.sha(HIST)
    guard=gate.read(gate.FREEZE)['source_sha256'];gate.verify(guard)
    stream=io.StringIO()
    with gate.record_only(),redirect_stdout(stream),redirect_stderr(stream):
        suite=unittest.defaultTestLoader.discover(str(BASE/'tools'),pattern='test_costs_v1.py');result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    (FREEZE.parent/'unit_tests.log').write_text(stream.getvalue(),encoding='utf8',newline='\n')
    e.require(result.wasSuccessful() and result.testsRun==25,'all synthetic cost-accounting checks')
    for name in source:
        if name.endswith('.py'):compile((ROOT/name).read_bytes(),name,'exec')
    gate.verify(source);gate.verify(binding);gate.verify(model['source_sha256']);gate.verify(model['input_sha256'])
    gate.write(FREEZE,dict(integrity='FROZEN_COMPLETE_QUAL_COST_ADDENDUM_SOFTWARE',source_sha256=source,component_sha256=binding,reused_guard_source_sha256=guard,
        manifest_sha256=gate.sha(RUN/'manifest.json'),new_unique_tests=25,development_test_executions=48,formal_test_executions=25,
        current_QUAL_outcomes_read=False,complete_cost_analysis_started=False,reconstructed_core_counts_not_direct_instrumentation=True,
        new_environment_interactions=0,new_real_model_queries=0,new_fits=0,online_LLM_API_calls=0,wall_ns=perf_counter_ns()-start,publication_goal_complete=False))
    return dict(integrity='FROZEN_COMPLETE_QUAL_COST_ADDENDUM_SOFTWARE',tests=25)


def ready():
    e.require(all((RUN/n).is_file() for n in (*gate.GATES,'report_v1/complete.json','report_v1/source_manifest.json')),'all original qualification, audits, statistics and report first')
    m,_,_=gate.admit(RUN);report=gate.read(RUN/'report_v1/complete.json');e.require(report['integrity']=='COMPLETE_REPORT' and report['unresolved']==0,'complete original report')
    for n,h in gate.read(RUN/'report_v1/source_manifest.json')['source_sha256'].items():e.require(gate.sha(ROOT/n)==h,'original report source binding '+n)
    return m


def cases(m,phase):
    previous=dict(counts={},by_phase={})
    for index,spec in enumerate(m['config']['populations'][phase],1):
        path=RUN/phase.lower()/('case_%04d'%index)/'case.json';case=gate.read(path)
        e.require(case['ledger_before']==previous,'complete serial cumulative ledger');previous=case['ledger_after_close']
        yield case,spec,path


def analyze():
    start=perf_counter_ns()
    # Existence check before outcome reads or output allocation.
    e.require(all((RUN/n).is_file() for n in (*gate.GATES,'report_v1/complete.json','report_v1/source_manifest.json')),'original complete experiment must finish first')
    f=gate.read(FREEZE)
    e.require(gate.sha(RUN/'manifest.json')==f['manifest_sha256'],'frozen original manifest bytes')
    for key in ('source_sha256','component_sha256','reused_guard_source_sha256'):gate.verify(f[key])
    git=['git','-c','maintenance.auto=false','-c','gc.auto=0']
    e.require(not subprocess.check_output(git+['status','--porcelain','--untracked-files=no'],cwd=ROOT).strip(),'committed addendum freeze')
    for n in (*f['source_sha256'],FREEZE.relative_to(ROOT).as_posix()):
        e.require(subprocess.check_output(git+['show','HEAD:'+n],cwd=ROOT)==(ROOT/n).read_bytes(),'actual committed reader '+n)
    m=ready();OUT.mkdir(exist_ok=False);historical=gate.read(HIST);all_rows=[];phases={};catalog={}
    try:
        with gate.record_only():
            for phase in ('NATIVE','QUAL'):
                rows=[]
                for case,spec,path in cases(m,phase):
                    e.require((perf_counter_ns()-start)<1800*10**9,'cost read/audit wall cap')
                    catalog[path.relative_to(ROOT).as_posix()]=gate.sha(path);rows.append(e.case_cost(case,spec))
                s=gate.read(RUN/phase.lower()/'summary.json');audit=gate.read(RUN/phase.lower()/'audit.json')
                phases[phase]=dict(**e.check_phase(rows,s,audit),programs=e.program_table(rows,historical),
                    recorded_collection_wall_ns=s['wall_ns'],recorded_full_audit_wall_ns=audit['wall_ns'])
                all_rows+=rows
            e.require(len(all_rows)==1740,'all complete executions, no failure exclusion')
            gate.write(OUT/'cases.json',all_rows);gate.write(OUT/'costs.json',dict(phases=phases,historical_sources_original=historical,
                source_training_subsets_not_added_to_whole_studies=True,standalone_counterfactual_costs_not_actual_project_sum=True,
                old_lifecycle_unknowns_not_zero=True,primary_statistics_unchanged=True))
            saved=iter(gate.read(OUT/'cases.json'))
            with patch.object(e,'case_cost',None),patch.object(e,'increment',None),patch.object(e,'program_table',None),patch.object(e,'check_phase',None):
                for phase in ('NATIVE','QUAL'):
                    subset=[]
                    for case,spec,path in cases(m,phase):
                        e.require((perf_counter_ns()-start)<1800*10**9,'complete cost read/audit wall cap')
                        row=next(saved);a.verify_case(case,spec,row);subset.append(row)
                    a.verify_programs(subset,historical,phases[phase]['programs'])
                    a.verify_phase(subset,gate.read(RUN/phase.lower()/'summary.json'),gate.read(RUN/phase.lower()/'audit.json'),phases[phase])
                a.need(next(saved,None) is None,'independent complete all-case consumption')
            for n,h in catalog.items():e.require(gate.sha(ROOT/n)==h,'case source unchanged '+n)
            gate.verify(m['source_sha256']);gate.verify(m['input_sha256'])
            for key in ('source_sha256','component_sha256','reused_guard_source_sha256'):gate.verify(f[key])
            ready();gate.write(OUT/'source_catalog.json',catalog)
            lines=['# 完整资格成本附录','', '**事后资源记账，原主比较与统计不变。**','',
                '生命周期用逐案例累计账本差分；失败惩罚不产生物理帧。模型核心eig与collection solve为代码重建，不是直接插桩。',
                '各程序单独训练来源摊销是假设单独部署的资源视图，不能乘程序数当作实际项目训练总额。', '',
                '|阶段|执行|实际控制步|全部reset|物理帧|政策查询|NN声明|候选预测|参数更新|C4/C8拟合|',
                '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
            for phase,p in phases.items():
                t=p['totals'];lines.append('|%s|%s|'%(phase,'|'.join(str(t[k]) for k in ('executions','control_steps','all_resets','physical_frames','fixed_policy_queries','trained_model_declarations','candidate_predictions','recorded_parameter_update_attempts','C4_C8_fit_attempts'))))
            lines+=['','完整逐程序在线／单独来源投影、独立重放／批量求解、inclusive case wall及历史训练费见costs.json。',
                '实际joint NN训练9000更新，与各单独方法5000更新不是可相加的同一口径；C8训练3072步包含在完整3840步研究中。',
                '当前资格LLM调用／tokens均0，平均API延迟不适用。旧历史未知账本不填0；没有把手写政策或既有工程成本宣称0。',
                '本附录不训练模型、不改变科学门，不构成任务收益、新颖性或CCF A贡献。']
            (OUT/'report_zh.md').write_text('\n'.join(lines)+'\n',encoding='utf8',newline='\n')
            e.require((perf_counter_ns()-start)<1800*10**9,'complete cost analysis and audit wall cap')
            gate.write(OUT/'complete.json',dict(integrity='PASSED_COMPLETE_COST_RECONSTRUCTION_AND_INDEPENDENT_RECORD_CHECK',manifest_id=m['manifest_id'],
                executions=1740,case_passes=2,case_catalog_hash_passes=2,additional_source_and_admission_hash_passes=True,
                file_IO_counts=dict(gate.IO_COUNTS),primary_statistics_unchanged=True,new_environment_interactions=0,
                new_real_model_queries=0,new_fits=0,online_LLM_API_calls=0,wall_ns=perf_counter_ns()-start,publication_goal_complete=False))
    except BaseException as error:
        gate.write(OUT/'failure.json',dict(type=type(error).__name__,message=str(error),no_retry_or_overwrite=True));raise
    return dict(integrity='PASSED_COMPLETE_COST_RECONSTRUCTION_AND_INDEPENDENT_RECORD_CHECK',executions=1740)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=('freeze','analyze'));x=p.parse_args();print(json.dumps(freeze() if x.command=='freeze' else analyze()))

"""Freeze the standard mathematical component; no real-data evaluation entry."""
from contextlib import redirect_stdout,redirect_stderr
from pathlib import Path
from time import perf_counter_ns
from unittest.mock import patch
import io,json,sys,unittest

ROOT=Path(__file__).resolve().parents[3];BASE=ROOT/'outputs/full_program_dr_software_v1';OUT=BASE/'freeze_v1'
sys.path.insert(0,str(ROOT/'outputs/occam_first_window_diagnostic_v1/tools'))
import run_first_window_v1 as guard
import sequential_dr_v1 as main
import sequential_dr_audit_v1 as audit
DOC=ROOT/'docs/protocols/full_program_dr_software_v1_zh.md'


def freeze():
    OUT.mkdir(exist_ok=False);start=perf_counter_ns()
    sources={p.relative_to(ROOT).as_posix():guard.sha(p) for p in sorted((BASE/'tools').glob('*.py'))+[BASE/'.gitattributes',DOC]}
    for n in sources:
        if n.endswith('.py'):compile((ROOT/n).read_bytes(),n,'exec')
    q=guard.read(guard.RUN/'manifest.json');guard.verify(q['source_sha256']);guard.verify(q['input_sha256'])
    binding=guard.read(guard.FREEZE)['source_sha256'];guard.verify(binding)
    counts=dict(estimate_attempts=0,estimate_returns=0,backward_audit_attempts=0,group_summary_calls=0)
    calculate=main.estimate;verify=audit.verify_episode;summarize=main.group_summary
    def counted(*args,**kwargs):
        counts['estimate_attempts']+=1;result=calculate(*args,**kwargs);counts['estimate_returns']+=1;return result
    def audited(*args,**kwargs):counts['backward_audit_attempts']+=1;return verify(*args,**kwargs)
    def grouped(*args,**kwargs):counts['group_summary_calls']+=1;return summarize(*args,**kwargs)
    stream=io.StringIO()
    with guard.record_only(),redirect_stdout(stream),redirect_stderr(stream),patch.object(main,'estimate',counted),\
         patch.object(audit,'verify_episode',audited),patch.object(main,'group_summary',grouped):
        suite=unittest.defaultTestLoader.discover(str(BASE/'tools'),pattern='test_sequential_dr_v1.py')
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    (OUT/'unit_tests.log').write_text(stream.getvalue(),encoding='utf8',newline='\n')
    main.require(result.wasSuccessful() and result.testsRun==34,'all standard mathematical and data-semantics checks')
    guard.verify(sources);guard.verify(binding);guard.verify(q['source_sha256']);guard.verify(q['input_sha256'])
    guard.write(OUT/'complete.json',dict(integrity='PASSED_STANDARD_SEQUENTIAL_DR_SOFTWARE_ONLY',source_sha256=sources,
        reused_guard_source_sha256=binding,manifest_sha256=guard.sha(guard.RUN/'manifest.json'),scientific_source_files_unchanged=len(q['source_sha256']),
        new_unique_tests=34,development_test_executions=34,formal_test_executions=34,synthetic_arithmetic=counts,
        unique_constructed_tree_leaves=16,constructed_tree_reused_across_settings=True,
        real_data_read_or_evaluated=False,Q_or_policy_models_fitted=0,real_model_queries=0,new_robot_interactions=0,
        episode_seeds_allocated=0,online_LLM_API_calls=0,standard_existing_estimator=True,source_data_admission_complete=False,
        full_Q_reference_deployment_complete=False,publication_goal_complete=False,wall_ns=perf_counter_ns()-start))
    return dict(integrity='PASSED_STANDARD_SEQUENTIAL_DR_SOFTWARE_ONLY',tests=result.testsRun,synthetic_arithmetic=counts)


if __name__=='__main__':print(json.dumps(freeze()),flush=True)

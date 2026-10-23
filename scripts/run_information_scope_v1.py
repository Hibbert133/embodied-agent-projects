"""One-shot guarded planning/evaluation of explicitly synthetic finite references."""
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
from time import perf_counter_ns
import argparse,sys,traceback
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis import information_scope_io_v1 as a
from scripts.run_latent_response_v1 import readonly_guard
io=a.io


def plan(path):
    from src.analysis import information_scope_reference_v1 as r
    start=perf_counter_ns();m=a.checked(path);out=path.parent/'planning';out.mkdir(exist_ok=False)
    cases=r.probability_cases();io.write(out/'probability_cases.json',cases)
    io.write(out/'probability_results.json',[r.probability_result(c) for c in cases])
    w=r.witness();io.write(out/'witness.json',dict(input=w,result=r.probability_result(w)))
    io.write(out/'noninformative_witness.json',r.noninformative_witness())
    problems=r.decision_problems();io.write(out/'decision_problems.json',problems)
    policies=[r.plan(p,method) for p in problems for method in r.METHODS];io.write(out/'policies.json',policies)
    unique=len({io.digest({k:c[k] for k in ('p','q','mapping')}) for c in cases})
    io.require(len(cases)==324 and unique==270 and len(problems)==216 and len(policies)==2592,'complete frozen constructed census')
    done=dict(integrity='PLANNED_SYNTHETIC_REFERENCE_REQUIRES_EVALUATION_AND_AUDIT',manifest_id=m['manifest_id'],
        constructed_probability_rows=324,unique_probability_laws_and_channels=unique,decision_problems=216,saved_policies=2592,
        classified_as_independent_robot_samples=False,artifact_sha256={p.name:io.sha(p) for p in out.iterdir() if p.is_file()},
        wall_ns=perf_counter_ns()-start,new_environment_steps=0,new_model_fits=0,online_LLM_API_calls=0)
    a.checked(path);io.write(out/'completion.json',done);return done


def evaluate(path):
    from src.analysis import information_scope_reference_v1 as r
    start=perf_counter_ns();m=a.checked(path);root=path.parent;done=io.read(root/'planning/completion.json')
    for name,h in done['artifact_sha256'].items():io.require(io.sha(root/'planning'/name)==h,'saved choices/inputs precede evaluation')
    problems=io.read(root/'planning/decision_problems.json');policies=io.read(root/'planning/policies.json')
    out=root/'evaluation';out.mkdir(exist_ok=False)
    values=[r.evaluate(problems[p['problem_id']],p) for p in policies];io.write(out/'results.json',values)
    summary=[]
    for method in r.METHODS:
        rows=[v for v in values if v['method']==method]
        summary.append(dict(method=method,constructed_problems=len(rows),
            means={k:sum(v[k] for v in rows)/len(rows) for k in ('cutoff_loss','success_probability','interaction_equivalent','acquisition_equivalent',
                'harmful_adoption_probability','beneficial_adoption_probability','keep_missing_benefit_probability')},
            chosen_arms={arm:sum(v['chosen_arm']==arm for v in rows) for arm in r.ARMS}))
    io.write(out/'summary.json',summary)
    done=dict(integrity='SAVED_POLICY_EXACT_EVALUATION_REQUIRES_INDEPENDENT_AUDIT',manifest_id=m['manifest_id'],
        source_planning_completion_sha256=io.sha(root/'planning/completion.json'),evaluated_saved_policies=len(values),
        true_synthetic_probabilities_only_no_random_outcomes=True,
        artifact_sha256={p.name:io.sha(p) for p in out.iterdir() if p.is_file()},wall_ns=perf_counter_ns()-start,
        new_environment_steps=0,new_model_fits=0,online_LLM_API_calls=0)
    a.checked(path);io.write(out/'completion.json',done);return done


def run(phase,path):
    if phase=='prepare':return str(a.prepare())
    a.checked(path);guard={}
    try:
        with readonly_guard(guard):
            if phase=='plan':return plan(path)
            if phase=='evaluate':return evaluate(path)
            if phase=='audit':
                from src.analysis import information_scope_reference_v1 as main
                from src.analysis.information_scope_audit_v1 import audit
                def denied(*args,**kwargs):raise RuntimeError('Main finite numerical and planning functions disabled during audit')
                with ExitStack() as stack:
                    for name in ('first_min','rational_joint','float_joint','coarsen','information','probability_cases','probability_result','witness',
                                 'noninformative_witness','decision_problems','arm_law','arm_parameters','terminal','inner_policy','expected_metrics','plan','evaluate'):
                        stack.enter_context(patch.object(main,name,denied))
                    return audit(path)
            if phase=='report':
                from scripts.report_information_scope_v1 import report
                return str(report(path))
            raise ValueError('registered finite-reference phase')
    finally:io.write(path.parent/(phase+'_guard.json'),guard)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=('prepare','plan','evaluate','audit','report'));p.add_argument('--manifest',type=Path);v=p.parse_args()
    start=perf_counter_ns();failure=None;result=None
    try:result=run(v.phase,v.manifest.resolve() if v.manifest else None)
    except BaseException as error:failure=dict(type=type(error).__name__,message=str(error),traceback=traceback.format_exc())
    receipt=dict(phase=v.phase,status='PASSED' if failure is None else 'FAILED_PARTIAL_RETAINED',wall_ns=perf_counter_ns()-start,
                 failure=failure,new_environment_steps=0,new_model_fits=0,online_LLM_API_calls=0)
    if v.manifest:
        io.write(v.manifest.parent/(v.phase+'_process_receipt.json'),receipt)
        if failure is not None:io.write(v.manifest.parent/(v.phase+'_failure_artifacts.json'),{p.relative_to(v.manifest.parent).as_posix():io.sha(p) for p in v.manifest.parent.rglob('*') if p.is_file()})
    print(result if v.phase=='prepare' and failure is None else receipt,flush=True)
    if failure is not None:raise SystemExit(1)

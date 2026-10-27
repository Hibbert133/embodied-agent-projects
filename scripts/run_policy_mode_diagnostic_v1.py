"""One source-bound TRAIN-only policy-function diagnostic, no simulator or fits."""
from pathlib import Path
from time import perf_counter_ns
from contextlib import ExitStack
from unittest.mock import patch
from collections import Counter,defaultdict
import gzip,json,struct,sys,inspect
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
from src.analysis import policy_mode_math_v1 as main
from src.analysis import policy_mode_independent_v1 as literal
from src.analysis import correction_effect_learning_v1 as source
from src.analysis import correction_effect_independent_v1 as old_independent
from src.analysis.release_learning_guard_v1 import read_only
BASE=ROOT/'outputs/policy_mode_diagnostic'
CONFIG=ROOT/'configs/movement_task/policy_mode_diagnostic_v1.json'
PROTOCOL=ROOT/'docs/protocols/policy_mode_diagnostic_v1_zh.md'
SOURCE=source.SOURCE
REGISTER=ROOT/'outputs/correction_scope/effect_learning_v1/run_20261027T064624Z_db04aa83cabc/pairs/pair_register.json'
HORIZONS=(1,2,4,8,16,32)
OWN=('src/analysis/policy_mode_math_v1.py','src/analysis/policy_mode_independent_v1.py','tests/test_policy_mode_diagnostic_v1.py',
    'scripts/run_policy_mode_diagnostic_v1.py','scripts/validate_policy_mode_diagnostic_freeze_v1.py')
DOCS=('docs/protocols/policy_mode_diagnostic_v1_zh.md','docs/research/policy_mode_diagnostic_decision_v1_zh.md','configs/movement_task/policy_mode_diagnostic_v1.json')
AXES=((),('group',),('task',),('context',),('boundary',),('acquisition_action',),('rates',),('task','context','boundary'),('task','context','boundary','acquisition_action','rates'))


def policies():
    from metaworld.policies import SawyerPushV3Policy,SawyerReachV3Policy,SawyerDoorOpenV3Policy
    from metaworld.policies import policy,action
    return {str(Path(inspect.getfile(x)).resolve().relative_to(ROOT).as_posix()):io.sha(Path(inspect.getfile(x)))
        for x in (SawyerPushV3Policy,SawyerReachV3Policy,SawyerDoorOpenV3Policy,policy,action)}


def contract():
    audit=io.read(SOURCE/'train/audit.json');io.require(audit['integrity']=='PASSED' and audit['executions']==648,'complete sourceTRAIN')
    paths=[SOURCE/'manifest.json',SOURCE/'train/audit.json',REGISTER]
    for n,h in audit['collection_sha256'].items():
        p=SOURCE/'train'/n;io.require(io.sha(p)==h,'unchanged source '+n);paths.append(p)
    return dict(source_sha256={p.relative_to(ROOT).as_posix():io.sha(p) for p in paths},installed_policy_sha256=policies(),
        source_split='TRAIN',source_manifest_id=audit['manifest_id'],historical_cost=dict(executions=648,control_steps=77563,all_resets=33048,physical_frames=16911815))


def config():
    return dict(protocol='POLICY_MODE_DIAGNOSTIC_V1',classification='POST_HOC_FUNCTIONAL_NOT_PHYSICAL_CAUSAL',source=contract(),
        source_cases=648,pairs=972,windows=5832,horizons=list(HORIZONS),primary_descriptive_horizon=2,
        main_leaf_cap=2000000,independent_leaf_cap=2000000,per_test_run_synthetic_policy_query_cap=18,
        retained_development_synthetic_policy_queries=18,formal_synthetic_policy_queries=18,total_synthetic_policy_query_cap=36,
        new_physics=0,new_fits=0,scientific_policy_queries=0,online_LLM_API_calls=0,new_seed_allocations=0,
        actual_future_input_is_not_entry_forecast=True,CAL_TEST_content_used=False)


def close(a,b):
    if isinstance(a,dict):
        io.require(type(b) is dict and set(a)==set(b),'independent mapping');[close(a[k],b[k]) for k in a]
    elif isinstance(a,(tuple,list)):
        io.require(isinstance(b,(tuple,list)) and len(a)==len(b),'independent vector');[close(x,y) for x,y in zip(a,b)]
    elif isinstance(a,float):io.require(abs(a-b)<=1e-12,'independent scalar')
    else:io.require(a==b,'independent literal field')


def panels(rows):
    result=[]
    for axes in AXES:
        cells=defaultdict(list)
        for r in rows:cells[(r['horizon'],*(tuple(r[k]) if k=='rates' else r[k] for k in axes))].append(r)
        for key,registered in sorted(cells.items(),key=lambda x:str(x[0])):
            actual=[r for r in registered if r['metrics'] is not None];metrics=None
            if actual:
                weights=source.weights(actual);iw=old_independent.weights(actual);close(weights.tolist(),list(map(float,iw)))
                metrics={k:sum(float(w)*r['metrics'][k] for w,r in zip(weights,actual)) for k in actual[0]['metrics']}
                close(metrics,{k:sum(float(w)*r['metrics'][k] for w,r in zip(iw,actual)) for k in actual[0]['metrics']})
            result.append(dict(horizon=key[0],axes=list(axes),values=list(key[1:]),registered=len(registered),available=len(actual),
                groups=len({r['group'] for r in actual}),statuses=dict(Counter(r['status'] for r in registered)),metrics=metrics))
    io.require(len(result)==2214,'complete2214 declared panels');return result


def execute():
    started=perf_counter_ns();freeze=io.read(BASE/'freeze_validation_v1/complete.json')
    io.require(freeze['integrity']=='PASSED' and not io.git('status','--porcelain','--untracked-files=no'),'clean complete freeze')
    for n,h in freeze['source_sha256'].items():io.require(io.sha(ROOT/n)==h and io.git('ls-files','--error-unmatch',n)==n,'committed source '+n)
    io.require(io.read(CONFIG)==config(),'immutable fixed policy diagnostic')
    out=BASE/'diagnostic_v1';out.mkdir(parents=True,exist_ok=False)
    manifest=dict(source_git_commit=io.git('rev-parse','HEAD'),config=io.read(CONFIG),source_sha256=freeze['source_sha256'],started_ns=started)
    manifest['manifest_id']=io.digest(manifest);io.write(out/'manifest.json',manifest)
    guard={};counts=Counter();windows=[];trajectories=[];seen=set();maximum_residual=0.;seen_steps=0
    def counted(obj,name,label):
        fn=getattr(obj,name)
        def f(*args,**kwargs):
            counts[label]+=1;io.require(counts[label]<=2000000,'fixed leaf count cap '+label);return fn(*args,**kwargs)
        return patch.object(obj,name,f)
    def save(stream,x):stream.write(json.dumps(x,separators=(',',':'),allow_nan=False)+'\n')
    try:
        with read_only(guard),ExitStack() as stack,gzip.open(out/'paired_step_factors.jsonl.gz','xt',encoding='utf8') as output:
            stack.enter_context(counted(main,'leaf','main_leaf_evaluations'));stack.enter_context(counted(literal,'action','independent_leaf_evaluations'))
            register={r['pair_id']:r for r in io.read(REGISTER)};io.require(len(register)==972,'all prior registered rate pairs')
            for family in source.source_nodes():
                for case,steps,_ in family:
                    entry=None if case['post_forecast'] is None else case['post_forecast']['at_calls'];modes=Counter();n=0
                    if entry is not None:
                        for j in range(entry,len(steps)):
                            s=case['initial'] if j==0 else steps[j-1]['after'];r=steps[j]
                            io.require(r['phase']=='TAIL_TASK','actual fixed-policy tail only')
                            mode=main.signature(case['task'],s['observation']);raw=main.leaf(case['task'],s['observation'],mode)
                            close(raw,r['raw_policy']);io.require(struct.pack('<4f',*raw)==struct.pack('<4f',*r['raw_policy']),'bit-exact recorded raw policy')
                            close(raw,literal.action(case['task'],s['observation'],literal.mode(case['task'],s['observation'])))
                            io.require([max(-1.,min(1.,v)) for v in raw[2:]]==r['command'][2:],'unchanged sent Z/gripper')
                            modes[str(mode)]+=1;n+=1
                    trajectories.append(dict(group=case['group'],task=case['task'],context=case['context'],boundary=case['planned_boundary'],
                        acquisition_action=case['acquisition_action'],rate=case['time_constant_s'],actual_tail_steps=n,
                        missing_reason='NO_ACTUAL_ADOPTION_TAIL' if entry is None else None,mode_counts=dict(modes),source_outcome={k:case[k] for k in ('success','deadline_loss','total_steps')}))
                for ia,ib in source.PAIRS:
                    ca,sa,_=family[ia];cb,sb,_=family[ib];pid=io.digest([source.node_key(ca),ia,ib]);p=register[pid];seen.add(pid)
                    io.require(p['source_case_sha256']==[io.digest(ca),io.digest(cb)],'unchanged actual source cases')
                    first=p['first_difference'];records=[]
                    # Independent literal byte alignment, without the old first_difference helper.
                    differing=[j for j in range(min(len(sa),len(sb))) if struct.pack('<4f',*sa[j]['command'])!=struct.pack('<4f',*sb[j]['command'])]
                    io.require(first==(differing[0] if differing else None),'literal first actual sent disagreement')
                    if first is not None:
                        io.require(sa[first-1]['after']==sb[first-1]['after'],'common actual pre-divergence observation')
                        for j in range(first,min(first+32,len(sa),len(sb))):
                            a=sa[j-1]['after']['observation'];b=sb[j-1]['after']['observation'];f=main.decompose(ca['task'],a,b)
                            with patch.object(main,'signature',side_effect=AssertionError('main disabled')),patch.object(main,'leaf',side_effect=AssertionError('main disabled')),patch.object(main,'decompose',side_effect=AssertionError('main disabled')):
                                independent=literal.factors(ca['task'],a,b)
                            close(f,independent)
                            if j==first:io.require(all(v==0 for stage in ('raw','sent') for v in f[stage]['delta_zg']) and not f['mode_changed'],'zero first policy effect at common state')
                            if ca['task']=='reach-v3':io.require(all(v==0 for stage in ('raw','sent') for v in f[stage]['mode_zg']),'reach negative control')
                            for stage in ('raw','sent'):
                                for k in (0,1):io.require(f[stage]['delta_zg'][k]==(sb[j]['raw_policy'][k+2]-sa[j]['raw_policy'][k+2] if stage=='raw' else sb[j]['command'][k+2]-sa[j]['command'][k+2]),'real Z/gripper delta')
                            records.append(f);save(output,dict(pair_id=pid,actual_at_calls=j,offset_from_first_difference=j-first,factors=f));seen_steps+=1
                    for h in HORIZONS:
                        status=p['status'] if first is None else 'COMPLETE_FACTUAL_WINDOW'
                        if first is not None and (first+h>len(sa) or first+h>len(sb)):
                            status='BOTH_SOURCES_SHORT' if first+h>len(sa) and first+h>len(sb) else 'SOURCE_A_SHORT' if first+h>len(sa) else 'SOURCE_B_SHORT'
                        metrics=None
                        if status=='COMPLETE_FACTUAL_WINDOW':
                            metrics=main.summarize(records[:h])
                            with patch.object(main,'summarize',side_effect=AssertionError('main summary disabled')):independent=literal.window_mean(records[:h])
                            close(metrics,independent)
                        windows.append({k:p[k] for k in ('pair_id','group','task','context','boundary','acquisition_action','rates')}|dict(horizon=h,status=status,metrics=metrics))
                if len(trajectories)%72==0:print(dict(source_cases=len(trajectories),registered_windows=len(windows)),flush=True)
            io.require(len(trajectories)==648 and len(windows)==5832 and len(seen)==972,'all fixed source cases pairs windows')
            io.write(out/'windows.json',windows);io.write(out/'panels.json',panels(windows));io.write(out/'trajectories.json',trajectories)
        for n,h in manifest['config']['source']['source_sha256'].items():io.require(io.sha(ROOT/n)==h,'unchanged history after analysis '+n)
        io.require(policies()==manifest['config']['source']['installed_policy_sha256'],'installed source unchanged')
        io.write(out/'independent_audit.json',dict(integrity='PASSED',cases=648,pairs=972,windows=5832,panels=2214,actual_pair_steps=seen_steps,
            main_leaf_decompose_summary_disabled_during_literal_checks=True,shared_previously_audited_source_parser_and_weight_reference_disclosed=True,
            exact_actual_policy_command_reconstruction=True,reach_negative_control_and_first_step_zero_verified=True,
            guard=guard,leaf_counts=dict(counts),wall_ns=perf_counter_ns()-started,new_physics=0,new_fits=0,online_LLM_API_calls=0))
        io.write(out/'complete.json',dict(integrity='PASSED',classification='POST_HOC_FUNCTIONAL_NOT_PHYSICAL_CAUSAL',manifest_id=manifest['manifest_id'],
            source_cases=648,pairs=972,windows=5832,panels=2214,actual_pair_steps=seen_steps,guard=guard,leaf_counts=dict(counts),
            scientific_installed_policy_queries=0,artifact_sha256={p.name:io.sha(p) for p in out.iterdir() if p.is_file()},
            wall_ns=perf_counter_ns()-started,new_physics=0,new_fits=0,online_LLM_API_calls=0,publication_goal_complete=False))
        print(dict(integrity='PASSED',windows=5832,paired_steps=seen_steps,leaf_counts=dict(counts)),flush=True)
    except BaseException as e:
        io.write(out/'failure.json',dict(type=type(e).__name__,message=str(e),processed_cases=len(trajectories),windows=len(windows),guard=guard,counts=dict(counts),wall_ns=perf_counter_ns()-started));raise


if __name__=='__main__':execute()

from pathlib import Path
from itertools import groupby
from time import perf_counter_ns
from unittest.mock import patch
import sys,numpy as np
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import correction_scope_io_v1 as a
from src.analysis import correction_scope_audit_v1 as audit
from src.analysis import correction_scope_independent_v1 as independent
from src.analysis.release_learning_guard_v1 import read_only
from src.probe.task_passive_pi_v1 import PIPlan
from src.probe import correction_scope_program_v1 as actor
folder=a.OUTPUT/'correction_scope_20261026T042133Z_d74cba1945e2/native'
out=a.BASE/'live_prefix_audit_v1';out.mkdir(exist_ok=False)
start=perf_counter_ns();guard={}
try:
    with read_only(guard),patch.object(actor,'run',side_effect=RuntimeError('main actor disabled')),patch.object(PIPlan,'numbers',side_effect=RuntimeError('main PI disabled')):
        case=next(a.io.rows(folder/'cases.jsonl.gz'));spec=a.population('NATIVE')[0]
        _,event_it=next(iter(groupby(a.io.rows(folder/'events.jsonl.gz'),a.case_key)));events=list(event_it)
        _,private_it=next(iter(groupby(a.io.rows(folder/'witnesses.jsonl.gz'),a.case_key)));private=list(private_it)
        ledger,steps,labels,public,examples=audit.reconstruct(spec,case,events[1:-1],private,dict(counts={},by_phase={}))
        history=[];before=case['initial']
        for r in steps:history.append(dict(at_calls=r['logical_step'],before=before,command=r['command'],after=r['after']));before=r['after']
        returned=next(e['public_payload']['memory'] for e in public if e['agent_event']=='TASK_MEMORY_RETURN')
        entry=examples[1]['view']['memory']['completed_steps'];expected=independent.target(history,entry,returned)
        for e in examples:a.io.require(np.allclose(e['target'],expected,atol=2e-12,rtol=2e-12),'literal real successor targets')
    result=dict(integrity='PASSED',source_git_commit=a.io.git('rev-parse','HEAD'),executions_checked=1,actual_saved_steps=len(steps),
        guard=guard,main_actor_and_PI_numbers_disabled=True,new_policy_queries=0,new_physics=0,new_fits=0,online_LLM_API_calls=0,
        wall_ns=perf_counter_ns()-start,not_full_native_population_gate=True)
except BaseException as e:
    import traceback
    result=dict(integrity='FAILED',error_type=type(e).__name__,message=str(e),traceback=traceback.format_exc(),guard=guard,wall_ns=perf_counter_ns()-start)
a.io.write(out/'receipt.json',result);print({k:v for k,v in result.items() if k in ('integrity','message','actual_saved_steps')})
if result['integrity']!='PASSED':raise SystemExit(1)

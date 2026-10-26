"""Additional read-only witness check; never changes a frozen scientific choice."""
from pathlib import Path
from itertools import groupby
from time import perf_counter_ns
import hashlib,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import correction_scope_io_v1 as a
from src.analysis.continuous_state_witness_v1 import compare_witnesses
from src.analysis.release_learning_guard_v1 import read_only
cohort=sys.argv[1];manifest=a.OUTPUT/'correction_scope_20261026T042133Z_d74cba1945e2/manifest.json'
m=a.checked(manifest);folder=manifest.parent/cohort.lower();audit=a.io.read(folder/'audit.json');a.io.require(audit['integrity']=='PASSED','completed main record audit')
out=a.BASE/'common_state_audit_v1';out.mkdir(exist_ok=True);start=perf_counter_ns();guard={};initial_pairs=return_pairs=memory_pairs=0;unit=None;initial=None;canonical={}
inputs={n:a.io.sha(folder/n) for n in ('events.jsonl.gz','witnesses.jsonl.gz','cases.jsonl.gz','audit.json')}
try:
    public=iter(groupby(a.io.rows(folder/'events.jsonl.gz'),a.case_key));private=iter(groupby(a.io.rows(folder/'witnesses.jsonl.gz'),a.case_key))
    with read_only(guard):
        for spec in a.population(cohort):
            key,it=next(public);pk,pit=next(private);a.io.require(key==pk==a.case_key(spec),'common-state allocation')
            returned=None
            for e in it:
                if e['event']=='AGENT_EVENT' and e['agent_event']=='TASK_MEMORY_RETURN':returned=e['public_payload']['memory']
            witnesses={p['label']:p['witness'] for p in pit};u=a.unit_key(spec)
            if u!=unit:unit=u;initial=witnesses['INITIAL'];canonical={}
            else:a.io.require(compare_witnesses(initial,witnesses['INITIAL'])['comparison_equal'],'initial private state differs');initial_pairs+=1
            action=spec['acquisition_action'];post=witnesses.get('POST_ACQUISITION')
            if action not in canonical:canonical[action]=(post,returned)
            else:
                old,old_memory=canonical[action];a.io.require((post is None)==(old is None),'return availability differs')
                if post is not None:
                    a.io.require(compare_witnesses(old,post)['comparison_equal'],'actual returned private state/RNG differs');return_pairs+=1
                    a.io.require(a.io.digest(returned)==a.io.digest(old_memory),'actual returned controller memory differs');memory_pairs+=1
        a.io.require(next(public,None) is None and next(private,None) is None,'extra common-state case')
    result=dict(integrity='PASSED',cohort=cohort,source_git_commit=m['source_git_commit'],manifest_id=m['manifest_id'],
        initial_private_pairs=initial_pairs,returned_private_pairs=return_pairs,returned_memory_pairs=memory_pairs,
        guard=guard,new_physics=0,new_fits=0,new_policy_queries=0,online_LLM_API_calls=0,post_hoc_additional_integrity_check=True,
        wall_ns=perf_counter_ns()-start,input_sha256=inputs,script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
except BaseException as e:
    import traceback
    result=dict(integrity='FAILED',cohort=cohort,error_type=type(e).__name__,message=str(e),traceback=traceback.format_exc(),guard=guard,input_sha256=inputs)
a.io.write(out/(cohort.lower()+'.json'),result);print({k:v for k,v in result.items() if k in ('integrity','cohort','message','returned_private_pairs','initial_private_pairs')})
if result['integrity']!='PASSED':raise SystemExit(1)

"""Supplementary read-only traversal of immutable preflight inputs."""
from pathlib import Path
from datetime import datetime,timezone
from time import perf_counter_ns
import json,re,hashlib,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
from src.analysis.release_learning_guard_v1 import read_only

def audit():
    start=perf_counter_ns();scope_path=ROOT/'outputs/history_response/freeze_validation_v1/seed_scope.json'
    scope=io.read(scope_path);found=[];ranges=[];checked=[];guard={};started=datetime.now(timezone.utc).isoformat()
    excluded=('noise','namespace','bootstrap','generator','generation','nonce','initialization','sampling')
    def interval(lo,hi,name,key):
        ranges.append(dict(source=name,key=key,range=[lo,hi]))
        if lo<=112999 and 112000<=hi:found.append(dict(source=name,key=key,range=[lo,hi]))
    def numeric(v,name,key):
        if type(v) is int:
            if 112000<=v<=112999:found.append(dict(source=name,key=key,value=v))
        elif type(v) is list:
            if len(v)==2 and all(type(x) is int for x in v) and v[0]<=v[1]:interval(*v,name,key)
            else:
                for i,item in enumerate(v):numeric(item,name,key+'['+str(i)+']')
        elif type(v) is dict:
            for lower,upper in (('start','end'),('low','high'),('min','max')):
                if type(v.get(lower)) is int and type(v.get(upper)) is int and v[lower]<=v[upper]:interval(v[lower],v[upper],name,key)
            for k,w in v.items():numeric(w,name,key+'.'+k)
        elif isinstance(v,str):
            for lo,hi in re.findall(r'\b(\d{4,6})\s*(?:--|–|\.\.|-)\s*(\d{4,6})\b',v):interval(int(lo),int(hi),name,key)
    def visit(v,name,key=''):
        if type(v) is dict:
            if type(v.get('seed_start')) is int:
                lo=v['seed_start'];hi=v.get('seed_end',lo+v.get('num_seeds',1)-1)
                if type(hi) is int:interval(lo,hi,name,key)
            for k,w in v.items():
                if 'seed' in k.lower() and not any(x in k.lower() for x in excluded):numeric(w,name,key+k)
                else:visit(w,name,key+k+'.')
        elif type(v) is list:
            for i,w in enumerate(v):visit(w,name,key+'['+str(i)+'].')
    with read_only(guard):
        for name,sha in scope['inputs_sha256'].items():
            p=ROOT/name;io.require(io.sha(p)==sha,'unchanged original preflight source')
            if p.suffix=='.json':visit(io.read(p),name);checked.append(name)
    result=dict(integrity='PASSED_NO_COLLISION' if not found else 'COLLISION',checked_json_sources=len(checked),range_occurrences_checked=len(ranges),collisions=found,
        original_preflight_sha256=io.sha(scope_path),source_sha256=io.sha(Path(__file__)),checked_sources=checked,range_catalog=ranges,
        started_utc=started,captured_after_collection_started=True,original_checker_gap='NESTED_INTEGER_RANGE_ARRAYS_NOT_CHECKED_BY_ORIGINAL_JSON_VISITOR',
        allocation_or_model_or_seed_changed=False,original_source_and_data_unchanged=True,guard=guard,wall_ns=perf_counter_ns()-start,
        new_environment_interactions=0,new_model_fits=0,online_LLM_API_calls=0)
    destination=ROOT/'outputs/history_response/development_v1/history_response_20261027T130543Z_b2f69d34b630/pipeline_control/nested_seed_scope_supplement.json'
    io.write(destination,result);io.require(not found,'supplementary seed inventory collision')
    print({k:result[k] for k in ('integrity','checked_json_sources','range_occurrences_checked','captured_after_collection_started')})

if __name__=='__main__':audit()

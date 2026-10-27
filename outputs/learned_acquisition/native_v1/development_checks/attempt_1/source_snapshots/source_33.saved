"""Fail-closed seed inventory retaining context through nested containers."""
from pathlib import Path
import re
from src.analysis import response_qualification_io_v1 as io

EXCLUDE=('noise','namespace','bootstrap','generator','generation','nonce','initialization','sampling','optimizer')


def overlaps(a,b,low,high):return a<=high and low<=b


def inspect(value,name,low,high,*,seed_context=False,range_context=False,path='root'):
    collisions=[]
    def pair(a,b,label):
        io.require(type(a) is int and type(b) is int and a<=b,'invalid registered seed interval '+name+label)
        if overlaps(a,b,low,high):collisions.append(dict(file=name,path=label,registered=[a,b]))
    if type(value) is dict:
        if type(value.get('seed_start')) is int:
            a=value['seed_start'];b=value.get('seed_end',a+value.get('num_seeds',1)-1)
            pair(a,b,path+'.seed_start/end')
        if seed_context and type(value.get('start')) is int and type(value.get('end')) is int:pair(value['start'],value['end'],path+'.start/end')
        for key,child in value.items():
            k=key.lower();episode='seed' in k and not any(t in k for t in EXCLUDE)
            context=(seed_context or episode) and not any(t in k for t in EXCLUDE)
            interval=context and (range_context or any(t in k for t in ('range','interval','reserved','future')))
            collisions+=inspect(child,name,low,high,seed_context=context,range_context=interval,path=path+'.'+key)
    elif type(value) is list:
        if range_context and len(value)==2 and all(type(v) is int for v in value):pair(value[0],value[1],path)
        else:
            for i,child in enumerate(value):collisions+=inspect(child,name,low,high,seed_context=seed_context,range_context=range_context,path=path+f'[{i}]')
    elif type(value) is int and seed_context:
        if low<=value<=high:collisions.append(dict(file=name,path=path,registered=value))
    elif type(value) is str and seed_context:
        for a,b in re.findall(r'\b(\d{3,7})\s*(?:--|–|\.\.|-)\s*(\d{3,7})\b',value):pair(int(a),int(b),path)
        if re.fullmatch(r'\d{3,7}',value) and low<=int(value)<=high:collisions.append(dict(file=name,path=path,registered=value))
    return collisions


def inventory(root,owned,low=73000,high=73999):
    root=Path(root);owned=set(owned);inputs={};collisions=[]
    files=set((root/'configs').rglob('*.json'))|set((root/'outputs').rglob('manifest.json'))|set((root/'docs/protocols').glob('*seed*.json'))
    for p in sorted(files):
        name=p.relative_to(root).as_posix()
        if name in owned:continue
        inputs[name]=io.sha(p);registry='seed' in p.name.lower()
        collisions+=inspect(io.read(p),name,low,high,seed_context=registry)
    for p in sorted(set((root/'docs').rglob('*.md'))|{root/'AGENTS.md',root/'RESEARCH_PLAN.md'}):
        name=p.relative_to(root).as_posix()
        if name in owned:continue
        inputs[name]=io.sha(p)
        for line in p.read_text(encoding='utf-8').splitlines():
            if not re.search('seed|种子|预留|保留',line,re.I):continue
            for a,b in re.findall(r'\b(\d{4,6})\s*(?:--|–|\.\.|-)\s*(\d{4,6})\b',line):
                if overlaps(int(a),int(b),low,high):collisions.append(dict(file=name,registered=[int(a),int(b)]))
    io.require(not collisions,'new used/reserved seed collision '+str(collisions[:4]))
    return dict(integrity='PASSED_NO_REGISTERED_COLLISION',proposed_range=[low,high],inputs_sha256=inputs,
        context_preserved_through_nested_lists=True,collisions=collisions)

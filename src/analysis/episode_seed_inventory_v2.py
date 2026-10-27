"""Conservative, source-bound episode-seed inventory. Never allocates a seed.

Legacy two-element reserved lists are inclusive ranges. Plain `seeds` lists
are explicit members. Algorithm RNG namespaces remain visible in the catalog.
"""
from pathlib import Path
import hashlib,json,re

RANGES=re.compile(r'(?<![A-Za-z0-9_.\-])([+-]?\d+)\s*(?:--|–|—|\.\.|~|至|-)\s*([+-]?\d+)(?![A-Za-z0-9_.\-])')
NON_EPISODE=('noise','bootstrap','namespace','nonce','operator_generation','perturbation','optimizer','network_init','model_init','monte_carlo','sampling_seed','rng_seed')
META=('sha256','fingerprint','hashes','source_hash','input_hash')
REFERENCES=('seed_registry','seed_registry_path','seed_registry_file')

def sha(data):return hashlib.sha256(data).hexdigest()
def pointer(path):return '/'+('/'.join(str(x).replace('~','~0').replace('/','~1') for x in path))
def namespace(path):
    names=[str(p).lower() for p in path if isinstance(p,str)];last=names[-1] if names else ''
    if any(x in last for x in NON_EPISODE):return 'NON_EPISODE_RNG'
    if any(x in last for x in ('episode_seed','environment_seed','task_seed')):return 'EPISODE'
    if any(x in '/'.join(names) for x in NON_EPISODE):return 'NON_EPISODE_RNG'
    return 'EPISODE'

def extract_json(value,source):
    records=[];issues=[];references=[]
    registry='seed' in Path(source).stem.lower()
    def issue(path,code):issues.append(dict(source=source,pointer=pointer(path),code=code,namespace=namespace(path)))
    def add(lo,hi,path,kind,space=None):
        if type(lo) is not int or type(hi) is not int or lo<0 or hi<lo:
            issue(path,'INVALID_DECLARED_SEED_BOUNDS');return
        records.append(dict(source=source,pointer=pointer(path),lower=lo,upper=hi,kind=kind,namespace=namespace(path) if space is None else space))
    def ranges(v,path):
        if isinstance(v,list):
            if len(v)==2 and all(type(x) is int for x in v):add(*v,path,'INCLUSIVE_RANGE')
            elif v:
                for i,item in enumerate(v):ranges(item,path+(i,))
            else:issue(path,'EMPTY_DECLARED_RANGE')
        elif isinstance(v,str):
            matches=list(RANGES.finditer(v))
            if not matches:issue(path,'UNPARSED_DECLARED_RANGE')
            for match in matches:add(int(match[1]),int(match[2]),path,'TEXT_RANGE')
        elif isinstance(v,dict):
            pairs=(('lower','upper'),('low','high'),('min','max'),('start','end'),('seed_start','seed_end'))
            matched=next(((l,h) for l,h in pairs if l in v and h in v),None)
            if matched:add(v[matched[0]],v[matched[1]],path,'NAMED_BOUNDS')
            elif 'start' in v and 'count' in v:
                if type(v['start']) is int and type(v['count']) is int and v['count']>0:add(v['start'],v['start']+v['count']-1,path,'START_COUNT')
                else:issue(path,'INVALID_DECLARED_SEED_COUNT')
            else:
                for k,w in v.items():ranges(w,path+(k,))
        else:issue(path,'UNPARSED_DECLARED_RANGE')
    def seeds(v,path,reserved=False):
        if type(v) is int:add(v,v,path,'SINGLE_SEED')
        elif isinstance(v,list):
            if reserved and len(v)==2 and all(type(x) is int for x in v):add(*v,path,'CONSERVATIVE_LEGACY_RESERVED_RANGE')
            else:
                for i,item in enumerate(v):
                    if isinstance(item,list):ranges(item,path+(i,))
                    else:seeds(item,path+(i,),reserved)
        elif isinstance(v,dict):walk(v,path,True)
        elif isinstance(v,str):
            if v.strip().isdigit():add(int(v),int(v),path,'DECIMAL_SEED_STRING')
            else:
                for match in RANGES.finditer(v):add(int(match[1]),int(match[2]),path,'TEXT_RANGE')
        elif type(v) is bool:issue(path,'BOOLEAN_IS_NOT_SEED')
        else:issue(path,'INVALID_SCALAR_SEED')
    def walk(v,path=(),seed_context=False):
        if isinstance(v,dict):
            if any(str(k).lower() in META or str(k).lower().endswith(('_hash','_hashes','_sha256')) for k in path):return
            start='seed_start' if 'seed_start' in v else 'start' if seed_context and 'start' in v else None
            if start is not None:
                end='seed_end' if 'seed_end' in v else 'end' if seed_context and 'end' in v else None
                count=next((k for k in ('num_seeds','n_seeds','seed_count','count') if k in v),None)
                if end is not None:add(v[start],v[end],path,'START_END')
                elif count is not None:
                    if type(v[start]) is int and type(v[count]) is int and v[count]>0:add(v[start],v[start]+v[count]-1,path,'START_COUNT')
                    else:issue(path,'INVALID_DECLARED_SEED_COUNT')
                elif any(isinstance(v.get(k),list) and len(v[k])==2 and all(type(x) is int for x in v[k])
                         and type(v[start]) is int and v[start]<=v[k][0]<=v[k][1]
                         for k in ('reserved_seeds','reserved_seed_range')):
                    end=max(v[k][1] for k in ('reserved_seeds','reserved_seed_range') if isinstance(v.get(k),list)
                            and len(v[k])==2 and all(type(x) is int for x in v[k]) and v[start]<=v[k][0]<=v[k][1])
                    add(v[start],end,path,'CONSERVATIVE_START_TO_RESERVED_END')
                else:issue(path,'UNPAIRED_SEED_START')
            for key,w in v.items():
                k=key.lower();p=path+(key,)
                if k in META or k.endswith(('_hash','_hashes','_sha256')):continue
                if k in ('num_seeds','n_seeds','seed_count','version','schema'):continue
                if k=='count' and start is not None:continue
                if k in REFERENCES:
                    targets=w if isinstance(w,list) else [w]
                    for i,target in enumerate(targets):
                        rp=p+(i,) if isinstance(w,list) else p
                        if isinstance(target,str) and target.lower().endswith(('.json','.md')):
                            references.append(dict(source=source,pointer=pointer(rp),target=target))
                        else:issue(rp,'UNPARSED_REGISTRY_REFERENCE')
                    continue
                is_seed='seed' in k
                if (is_seed or seed_context) and any(x in k for x in ('range','interval')):ranges(w,p)
                elif is_seed:
                    flag=k.startswith(('no_','zero_','forbid_','never_','shared_','same_','common_','preserve_','reuse_'))
                    declared=k in ('seed','seeds') or k.endswith(('_seed','_seeds','_seed_start','_seed_end'))
                    if type(w) is bool and (flag or not declared):continue
                    if w is None and not declared:continue
                    seeds(w,p,reserved='reserv' in k)
                elif seed_context and isinstance(w,(list,int)) and not isinstance(w,bool):seeds(w,p,reserved='reserv' in k or registry)
                elif registry and isinstance(w,list):seeds(w,p,reserved=True)
                else:walk(w,p,seed_context)
        elif isinstance(v,list):
            for i,w in enumerate(v):walk(w,path+(i,),seed_context)
    walk(value)
    return records,issues,references

def extract_markdown(text,source):
    records=[];issues=[]
    for number,line in enumerate(text.splitlines(),1):
        if not re.search(r'seed|种子|预留|保留',line,re.I):continue
        line=re.sub(r'(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)',lambda m:' '*len(m[0]),line)
        covered=[]
        for match in RANGES.finditer(line):
            covered.append(match.span())
            lo,hi=int(match[1]),int(match[2]);prefix=line[:match.start()].lower()
            space='NON_EPISODE_RNG' if any(x in prefix for x in NON_EPISODE) and not re.search(r'episode|environment|task.seed|环境|任务种子',prefix) else 'POSSIBLE_EPISODE_TEXT'
            if lo<0 or hi<lo:issues.append(dict(source=source,pointer='line:'+str(number),code='INVALID_TEXT_RANGE',namespace=space));continue
            records.append(dict(source=source,pointer='line:'+str(number),lower=lo,upper=hi,kind='TEXT_SEED_RANGE',namespace=space))
        for match in re.finditer(r'(?<![A-Za-z0-9_.\-])[+-]?\d+(?![A-Za-z0-9_.\-])',line):
            if any(a<=match.start()<b for a,b in covered):continue
            prefix=line[:match.start()].lower();n=int(match[0])
            space='NON_EPISODE_RNG' if any(x in prefix for x in NON_EPISODE) and not re.search(r'episode|environment|task.seed|环境|任务种子',prefix) else 'POSSIBLE_EPISODE_TEXT'
            if n<0:continue  # Signed command/loss prose is not a nonnegative seed declaration.
            records.append(dict(source=source,pointer='line:'+str(number),lower=n,upper=n,kind='POSSIBLE_TEXT_SINGLE_SEED',namespace=space))
    return records,issues,[]

def discover(root):
    root=Path(root).resolve()
    return sorted(set((root/'configs').rglob('*.json'))|set((root/'outputs').rglob('manifest.json'))|
        set((root/'docs/protocols').glob('*seed*.json'))|set((root/'docs').rglob('*.md'))|
        {p for p in (root/'AGENTS.md',root/'RESEARCH_PLAN.md') if p.is_file()})

def scan(root,lower,upper,paths=None):
    root=Path(root).resolve()
    if type(lower) is not int or type(upper) is not int or lower<0 or upper<lower:raise ValueError('Invalid query interval')
    mode='REPOSITORY_DISCOVERY' if paths is None else 'EXPLICIT_SOURCE_SET'
    queue=list(discover(root) if paths is None else paths);visited={};records=[];issues=[];references=[]
    while queue:
        candidate=Path(queue.pop(0));p=(root/candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
        try:name=p.relative_to(root).as_posix()
        except ValueError:
            issues.append(dict(source='OUTSIDE_ROOT',pointer='',code='OUTSIDE_ROOT_SOURCE',namespace='EPISODE'));continue
        if name in visited:continue
        if p.suffix.lower() not in ('.json','.md') or not p.is_file():
            issues.append(dict(source=name,pointer='',code='MISSING_OR_UNSUPPORTED_SOURCE',namespace='EPISODE'));continue
        raw=p.read_bytes();visited[name]=dict(sha256=sha(raw),bytes=len(raw))
        try:
            text=raw.decode('utf-8-sig')
            if p.suffix.lower()=='.json':rr,ee,refs=extract_json(json.loads(text),name)
            else:rr,ee,refs=extract_markdown(text,name)
        except (ValueError,TypeError,UnicodeError):
            issues.append(dict(source=name,pointer='',code='UNREADABLE_SOURCE_SCHEMA',namespace='EPISODE'));continue
        records+=rr;issues+=ee
        for ref in refs:
            target=Path(ref['target'].replace('\\','/'));target=(root/target).resolve() if not target.is_absolute() else target.resolve()
            try:relative=target.relative_to(root).as_posix()
            except ValueError:
                issues.append(dict(source=name,pointer=ref['pointer'],code='OUTSIDE_ROOT_REFERENCE',namespace='EPISODE'));continue
            references.append(dict(source=name,pointer=ref['pointer'],target=relative));queue.append(target)
    if not visited:issues.append(dict(source='',pointer='',code='EMPTY_SCOPE',namespace='EPISODE'))
    blockers=[r for r in records if r['namespace']!='NON_EPISODE_RNG' and r['lower']<=upper and lower<=r['upper']]
    fatal=[e for e in issues if e['namespace']!='NON_EPISODE_RNG' and e['code']!='EMPTY_DECLARED_RANGE']
    return dict(schema='EPISODE_SEED_INVENTORY_V2',status='INDETERMINATE' if fatal else 'REGISTERED_COLLISION' if blockers else 'NO_REGISTERED_COLLISION',
        query=dict(lower=lower,upper=upper),scope=mode,sources=visited,records=records,issues=issues,blocking_issues=fatal,blockers=blockers,references=references,
        allocation_created=False,new_environment_interactions=0,online_LLM_API_calls=0)

def verify_unchanged(root,result):
    root=Path(root).resolve()
    for name,entry in result['sources'].items():
        path=(root/name).resolve();path.relative_to(root)
        if not path.is_file() or sha(path.read_bytes())!=entry['sha256']:raise ValueError('Seed inventory input changed: '+name)
    return True

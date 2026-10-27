"""Independent source census and extraction coverage audit; no production parser.

This checks registered metadata, not undisclosed seed generation in arbitrary code.
JSON traversal is iterative; interval interiors, not only endpoints, are checked.
"""
from pathlib import Path
import hashlib,json,re

def audit(root,inventory):
    root=Path(root).resolve();checked=0;requirements=0;proofs=0
    ranges=re.compile(r'(?<![A-Za-z0-9_.\-])([+-]?\d+)\s*(?:--|–|—|\.\.|~|至|-)\s*([+-]?\d+)(?![A-Za-z0-9_.\-])')
    non=('noise','bootstrap','namespace','nonce','operator_generation','perturbation','optimizer','network_init','model_init','monte_carlo','sampling_seed','rng_seed')
    meta=('sha256','fingerprint','hashes','source_hash','input_hash')
    by_source={}
    def require(ok,message):
        if not ok:raise ValueError(message)
    if inventory['scope']=='REPOSITORY_DISCOVERY':
        expected=set()
        for folder,pattern in (('configs','*.json'),('outputs','manifest.json'),('docs','*.md')):
            expected.update(p.relative_to(root).as_posix() for p in (root/folder).rglob(pattern) if p.is_file())
        expected.update(p.relative_to(root).as_posix() for p in (root/'docs/protocols').glob('*seed*.json') if p.is_file())
        expected.update(name for name in ('AGENTS.md','RESEARCH_PLAN.md') if (root/name).is_file())
        require(expected<=set(inventory['sources']),'repository discovery source omitted')
    for ref in inventory['references']:require(ref['target'] in inventory['sources'] or any(e['source']==ref['target'] for e in inventory['issues']),'reference closure omitted')
    def ptr(path):return '/'+('/'.join(str(p).replace('~','~0').replace('/','~1') for p in path))
    def space(path):
        names=[str(p).lower() for p in path if isinstance(p,str)];last=names[-1] if names else ''
        if any(x in last for x in non):return 'NON_EPISODE_RNG'
        if any(x in last for x in ('episode_seed','environment_seed','task_seed')):return 'EPISODE'
        return 'NON_EPISODE_RNG' if any(x in '/'.join(names) for x in non) else 'EPISODE'
    for record in inventory['records']:
        require(record['source'] in inventory['sources'],'record with no bound source')
        require(type(record['lower']) is int and type(record['upper']) is int and 0<=record['lower']<=record['upper'],'invalid saved interval')
        by_source.setdefault(record['source'],[]).append(record)
    for name,entry in inventory['sources'].items():
        path=(root/name).resolve();path.relative_to(root);raw=path.read_bytes()
        require(hashlib.sha256(raw).hexdigest()==entry['sha256'] and len(raw)==entry['bytes'],'source changed '+name)
        checked+=1;local=by_source.get(name,[])
        def cover(lo,hi,p,expected_space):
            nonlocal requirements
            requirements+=1;label=ptr(p) if isinstance(p,tuple) else p
            require(any(r['lower']<=lo<=hi<=r['upper'] and r['namespace']==expected_space and
                        (r['pointer']==label or (label.startswith(r['pointer']+'/') if r['pointer']!='/' else True)) for r in local),
                    'missing registered interval interior '+name+label+':'+str((lo,hi)))
        try:text=raw.decode('utf-8-sig');value=json.loads(text) if path.suffix=='.json' else None
        except (ValueError,UnicodeError):
            require(any(e['source']==name and e['code']=='UNREADABLE_SOURCE_SCHEMA' for e in inventory['issues']),'unreported unreadable source');continue
        if path.suffix=='.md':
            lines=text.splitlines()
            for r in local:
                number=int(r['pointer'].split(':')[1]);line=lines[number-1]
                line=re.sub(r'(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)',lambda m:' '*len(m[0]),line)
                require(re.search(r'seed|种子|预留|保留',line,re.I) is not None,'non-seed text accepted')
                if r['kind']=='TEXT_SEED_RANGE':require(any(int(m[1])==r['lower'] and int(m[2])==r['upper'] for m in ranges.finditer(line)),'text interval proof')
                else:require(r['lower']==r['upper'] and any(int(m[0])==r['lower'] for m in re.finditer(r'(?<![A-Za-z0-9_.\-])[+-]?\d+(?![A-Za-z0-9_.\-])',line)),'text singleton proof '+name+r['pointer'])
                proofs+=1
            for number,line in enumerate(lines,1):
                if not re.search(r'seed|种子|预留|保留',line,re.I):continue
                line=re.sub(r'(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)',lambda m:' '*len(m[0]),line)
                covered=[]
                for match in ranges.finditer(line):
                    covered.append(match.span());lo,hi=int(match[1]),int(match[2]);prefix=line[:match.start()].lower()
                    ns='NON_EPISODE_RNG' if any(x in prefix for x in non) and not re.search(r'episode|environment|task.seed|环境|任务种子',prefix) else 'POSSIBLE_EPISODE_TEXT'
                    if 0<=lo<=hi:cover(lo,hi,'line:'+str(number),ns)
                for match in re.finditer(r'(?<![A-Za-z0-9_.\-])[+-]?\d+(?![A-Za-z0-9_.\-])',line):
                    if any(a<=match.start()<b for a,b in covered) or int(match[0])<0:continue
                    prefix=line[:match.start()].lower();ns='NON_EPISODE_RNG' if any(x in prefix for x in non) and not re.search(r'episode|environment|task.seed|环境|任务种子',prefix) else 'POSSIBLE_EPISODE_TEXT'
                    cover(int(match[0]),int(match[0]),'line:'+str(number),ns)
            continue
        registry='seed' in path.stem.lower();stack=[(value,(),False,False,False)]
        while stack:
            node,p,seeded,interval,nested=stack.pop();ns=space(p)
            if any(str(x).lower() in meta or str(x).lower().endswith(('_hash','_hashes','_sha256')) for x in p):continue
            if isinstance(node,dict):
                start='seed_start' if 'seed_start' in node else 'start' if seeded and 'start' in node else None
                if start:
                    end='seed_end' if 'seed_end' in node else 'end' if seeded and 'end' in node else None
                    count=next((k for k in ('num_seeds','n_seeds','seed_count','count') if k in node),None)
                    lo=node[start]
                    if end and type(lo) is int and type(node[end]) is int and 0<=lo<=node[end]:cover(lo,node[end],p,ns)
                    elif not end and count and type(lo) is int and type(node[count]) is int and lo>=0 and node[count]>0:cover(lo,lo+node[count]-1,p,ns)
                for key,child in node.items():
                    k=key.lower()
                    if k in ('num_seeds','n_seeds','seed_count','version','schema','seed_start','seed_end'):continue
                    if k=='count' and (start or interval):continue
                    is_seed='seed' in k
                    if k in ('seed_registry','seed_registry_path','seed_registry_file'):continue
                    use=seeded or is_seed
                    mode=interval or (use and any(x in k for x in ('range','interval')))
                    if isinstance(child,list) and ('reserv' in k or (registry and not is_seed)):mode=True
                    stack.append((child,p+(key,),use,mode,False))
            elif isinstance(node,list):
                if seeded or registry:
                    if len(node)==2 and all(type(x) is int for x in node) and (interval or nested):
                        if 0<=node[0]<=node[1]:cover(node[0],node[1],p,ns)
                        continue
                    for i,child in enumerate(node):stack.append((child,p+(i,),seeded,interval,isinstance(child,list)))
                else:
                    for i,child in enumerate(node):stack.append((child,p+(i,),False,False,False))
            elif type(node) is int and seeded:
                if node>=0:cover(node,node,p,ns)
            elif isinstance(node,str) and seeded:
                if node.strip().isdigit():cover(int(node),int(node),p,ns)
                else:
                    for match in ranges.finditer(node):
                        lo,hi=int(match[1]),int(match[2])
                        if 0<=lo<=hi:cover(lo,hi,p,ns)
        for r in local:
            tokens=[] if r['pointer']=='/' else r['pointer'][1:].split('/');node=value;pathparts=[]
            for token in tokens:
                token=token.replace('~1','/').replace('~0','~');part=int(token) if isinstance(node,list) else token
                pathparts.append(part);node=node[part]
            require(r['namespace']==space(pathparts),'namespace proof')
            kind=r['kind'];lo,hi=r['lower'],r['upper']
            if kind in ('SINGLE_SEED','DECIMAL_SEED_STRING'):require(int(node)==lo==hi,'singleton proof')
            elif kind in ('INCLUSIVE_RANGE','CONSERVATIVE_LEGACY_RESERVED_RANGE'):require(node==[lo,hi],'range proof')
            elif kind=='TEXT_RANGE':require(any(int(m[1])==lo and int(m[2])==hi for m in ranges.finditer(node)),'JSON text proof')
            elif kind=='CONSERVATIVE_START_TO_RESERVED_END':require(node.get('seed_start',node.get('start'))==lo and any(isinstance(node.get(k),list) and len(node[k])==2 and node[k][1]==hi and lo<=node[k][0]<=hi for k in ('reserved_seeds','reserved_seed_range')),'conservative hull proof')
            elif kind in ('NAMED_BOUNDS','START_END'):require(any(node.get(a)==lo and node.get(b)==hi for a,b in (('lower','upper'),('low','high'),('min','max'),('start','end'),('seed_start','seed_end'))),'bound proof')
            elif kind=='START_COUNT':require(node.get('seed_start',node.get('start'))==lo and any(node.get(k)==hi-lo+1 for k in ('num_seeds','n_seeds','seed_count','count')),'count proof')
            else:raise ValueError('unknown saved record kind '+kind)
            proofs+=1
    q=inventory['query'];blockers=[r for r in inventory['records'] if r['namespace']!='NON_EPISODE_RNG' and max(q['lower'],r['lower'])<=min(q['upper'],r['upper'])]
    fatal=[e for e in inventory['issues'] if e['namespace']!='NON_EPISODE_RNG' and e['code']!='EMPTY_DECLARED_RANGE']
    expected='INDETERMINATE' if fatal else 'REGISTERED_COLLISION' if blockers else 'NO_REGISTERED_COLLISION'
    require(blockers==inventory['blockers'] and fatal==inventory['blocking_issues'] and expected==inventory['status'],'independent status mismatch')
    require(inventory['allocation_created'] is False,'checker may not allocate')
    return dict(integrity='PASSED',sources_checked=checked,coverage_requirements=requirements,source_proofs=proofs,status=expected,
                production_parser_called=False,new_environment_interactions=0,new_model_fits=0,online_LLM_API_calls=0)

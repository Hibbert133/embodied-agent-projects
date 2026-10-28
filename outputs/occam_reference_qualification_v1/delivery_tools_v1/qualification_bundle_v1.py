"""Offline completed qualification-phase delivery; never a collector or simulator."""
from pathlib import Path
import gzip,hashlib,json,shutil,sys,zipfile
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from src.analysis import occam_qualification_case_io_v1 as c


def require(value,message):
    if not value:raise ValueError(message)


def safe_name(name):
    require(type(name) is str and bool(name),'literal artifact name');p=Path(name)
    require(not p.is_absolute() and '..' not in p.parts and '\\' not in name,'safe relative artifact name')
    return p



def metadata_gate(m,summary,completion,process,audit,phase='NATIVE'):
    require(phase in ('NATIVE','QUAL'),'registered delivery phase')
    n=len(m['config']['populations'][phase]);require(n=={'NATIVE':174,'QUAL':1566}[phase],'exact frozen phase allocation')
    require(summary['status']==completion['status']=='COLLECTED_FOR_INDEPENDENT_AUDIT','complete collection before export')
    require(summary['allocated_executions']==summary['executions']==len(summary['rows'])==len(summary['outcomes'])==n,'complete phase denominator')
    require(all(o['status']=='COMPLETE' for o in summary['outcomes']),'no partial or unstarted cases')
    require(process['integrity']=='PASSED_ISOLATED_PROCESS_AND_BYTE_CONTINUITY_ONLY' and process['executions']==n,'complete process audit')
    require(audit['integrity']=='PASSED' and audit['phase']==phase and audit['counts']['executions']==n,'complete full audit')
    require(completion['manifest_id']==summary['manifest_id']==audit['manifest_id']==m['manifest_id'],'same allocated data')
    require(process['ledger']==audit['ledger']==summary['lifecycle'] and process['control_steps']==audit['counts']['control_steps']==summary['control_steps'],'same complete costs')


def manifest_metadata(manifest):
    path=Path(manifest).resolve();require(path.name=='manifest.json' and path.parent.parent==c.OUTPUT.resolve(),'exact qualification run path')
    m=c.read(path);copy=dict(m);mid=copy.pop('manifest_id')
    require(c.digest(copy)==mid and m['config']==c.read(c.CONFIG) and m['config']['protocol']=='OCCAM_REFERENCE_QUALIFICATION_V1','immutable qualification manifest')
    f=c.read(c.FREEZE);require(f['integrity']=='PASSED','frozen source qualification')
    for name,h in m['source_sha256'].items():require(c.sha(ROOT/name)==h,'original frozen source '+name)
    for name,h in f['source_sha256'].items():require(m['source_sha256'][name]==h,'original tested source')
    # A later phase's CLOSED marker forbids recollection, not export of an already
    # complete audited phase. This function never resumes or launches anything.
    return m


def ready(manifest,phase='NATIVE'):
    manifest=Path(manifest).resolve();m=manifest_metadata(manifest)
    require(phase in ('NATIVE','QUAL'),'registered delivery phase');folder=manifest.parent/phase.lower()
    require((folder/'summary.json').is_file(),'phase still live or not collected; no export')
    s=c.read(folder/'summary.json');require(s['status']=='COLLECTED_FOR_INDEPENDENT_AUDIT','phase still live or partial; no export')
    comp=c.read(folder/'completion.json');p=c.read(folder/'process_audit.json');a=c.read(folder/'audit.json');metadata_gate(m,s,comp,p,a,phase)
    for name,h in comp['artifact_sha256'].items():require(c.sha(folder/safe_name(name))==h,'immutable phase artifact '+name)
    require(c.sha(folder/'prequential_windows.jsonl.gz')==a['prequential_windows_sha256'],'audited prequential projection')
    for i,outcome in enumerate(s['outcomes'],1):
        case=folder/('case_%04d'%i);require(outcome['case_index']==i and outcome['case']==m['config']['populations'][phase][i-1],'exact registered complete case')
        require(c.sha(case/'result.json')==outcome['process_result_sha256'],'immutable process result')
        result=c.read(case/'result.json');require(c.sha(case/'request.json')==result['request_sha256'],'immutable process request')
        for name,h in result['artifact_sha256'].items():require(c.sha(case/safe_name(name))==h,'immutable child artifact '+name)
        require({x.name for x in case.iterdir() if x.is_file()}==set(result['artifact_sha256'])|{'request.json','result.json'},'only audited child files')
    return m,s,p,a


def member_aliases(root,phase,index):
    root=Path(root).resolve();phase=Path(phase).resolve();result={}
    label=phase.name.upper();require(label in ('NATIVE','QUAL'),'phase directory name')
    require(index['schema']=='OCCAM_VERBATIM_GZIP_MEMBERS_V1' and index['phase']==label and len(index['members'])=={'NATIVE':174,'QUAL':1566}[label],'all registered gzip members')
    for i,entry in enumerate(index['members'],1):
        require(entry['case_index']==i and set(entry['files'])=={'events.jsonl.gz','witnesses.jsonl.gz'},'exact member owner')
        for name,slice_ in entry['files'].items():
            alias=(phase/('case_%04d'%i)/name).relative_to(root).as_posix();anchor=(phase/name).relative_to(root).as_posix()
            result[alias]=dict(anchor=anchor,offset=slice_['offset'],bytes=slice_['bytes'],sha256=slice_['sha256'])
    return result


def validate_ranges(files,aliases):
    grouped={}
    require(set(aliases)<=set(files),'aliases belong to original file inventory')
    for name,item in aliases.items():
        safe_name(name);anchor=item['anchor'];safe_name(anchor)
        require(anchor in files and anchor not in aliases and anchor.endswith('.gz'),'direct gzip anchor, no alias chains')
        require(type(item['offset']) is int and item['offset']>=0 and type(item['bytes']) is int and item['bytes']>0,'nonempty exact integer slice')
        require(item['sha256']==files[name]['sha256'] and item['bytes']==files[name]['bytes'],'alias original byte binding')
        grouped.setdefault(anchor,[]).append(item)
    for anchor,items in grouped.items():
        cursor=0
        for item in sorted(items,key=lambda x:x['offset']):require(item['offset']==cursor,'no member gap or overlap');cursor+=item['bytes']
        require(cursor==files[anchor]['bytes'],'members cover whole canonical stream')


def bundle(root,paths,aliases,target):
    root=Path(root).resolve();target=Path(target);original=[Path(p) for p in paths]
    require(all(p.is_file() and not p.is_symlink() for p in original),'ordinary source files')
    resolved=[p.resolve() for p in original];require(all(p.is_relative_to(root) for p in resolved),'owned resolved files')
    names={p.relative_to(root).as_posix():p for p in resolved};require(len(names)==len(original),'unique resolved source files')
    inventory={name:dict(bytes=p.stat().st_size,sha256=c.sha(p)) for name,p in sorted(names.items())};validate_ranges(inventory,aliases)
    with zipfile.ZipFile(target,'x',allowZip64=True) as archive:
        for name,p in sorted(names.items()):
            safe_name(name)
            if name in aliases:continue
            info=zipfile.ZipInfo(name,date_time=(2000,1,1,0,0,0));info.compress_type=zipfile.ZIP_STORED if name.endswith('.gz') else zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
            with p.open('rb') as source,archive.open(info,'w',force_zip64=True) as output:shutil.copyfileobj(source,output,1024**2)
    return dict(schema='OCCAM_QUALIFICATION_ZIP_ALIASES_V1',files=inventory,aliases=aliases,bundle_bytes=target.stat().st_size,bundle_sha256=c.sha(target),
        original_files_unchanged=True,aliases_are_exact_compressed_bytes_not_reencoded=True)


def recover(root,target,index,destination,*,scan):
    root=Path(root).resolve();destination=Path(destination).resolve();require(index['schema']=='OCCAM_QUALIFICATION_ZIP_ALIASES_V1','versioned qualification bundle')
    require(c.sha(target)==index['bundle_sha256'],'whole ZIP bytes')
    files=index['files'];aliases=index['aliases'];validate_ranges(files,aliases);destination.mkdir(parents=True,exist_ok=False);seen=set();lines=0
    def owned(name):
        path=(destination/safe_name(name)).resolve();require(path.is_relative_to(destination),'recovery remains in owned directory');path.parent.mkdir(parents=True,exist_ok=True);return path
    def check(path,name):require(path.stat().st_size==files[name]['bytes'] and c.sha(path)==files[name]['sha256']==c.sha(root/name),'every original file restored '+name)
    with zipfile.ZipFile(target,'r') as archive:
        for item in archive.infolist():
            name=item.filename;require(name in files and name not in aliases and name not in seen and not item.is_dir(),'exact canonical member set');seen.add(name);path=owned(name)
            with archive.open(item,'r') as source,path.open('xb') as output:shutil.copyfileobj(source,output,1024**2)
            check(path,name)
            if name.endswith('.gz'):
                with gzip.open(path,'rb') as source:
                    for line in source:scan(line,name);lines+=1
            else:scan(path.read_bytes(),name)
    require(seen==set(files)-set(aliases),'all canonical files present')
    for name,item in sorted(aliases.items()):
        path=owned(name);anchor=destination/safe_name(item['anchor'])
        with anchor.open('rb') as source,path.open('xb') as output:
            source.seek(item['offset']);left=item['bytes']
            while left:
                data=source.read(min(left,1024**2));require(bool(data),'complete raw gzip slice');output.write(data);left-=len(data)
        check(path,name)
    return dict(integrity='PASSED_LOSSLESS_QUALIFICATION_BUNDLE',files=len(files),canonical_files=len(seen),reconstructed_member_files=len(aliases),
        decoded_canonical_gzip_lines=lines,alias_decoded_scan_reuses_complete_canonical_stream_scan=True,all_files_byte_identical=True,
        new_physics=0,new_fits=0,online_LLM_API_calls=0)



def export(manifest,out,restore,phase='NATIVE'):
    m,s,p,a=ready(manifest,phase) # Reject live/incomplete phase before output allocation.
    out=Path(out).resolve();require(out==c.BASE/(phase.lower()+'_delivery_v1'),'owned completed-phase delivery path');out.mkdir(exist_ok=False)
    run=Path(manifest).resolve().parent;folder=run/phase.lower();paths={p for p in folder.rglob('*') if p.is_file()}
    paths|={run/name for name in ('manifest.json','seed_scope.json','seed_scope_audit.json')}
    for command in ('collect','process-audit','audit'):
        entry=run/'entry_attempts_v1'/(command+'_'+phase+'_attempt01');require(c.read(entry/'complete.json')['integrity']=='PASSED','successful one-shot phase entries')
        paths|={p for p in entry.iterdir() if p.is_file()}
    total=sum(p.stat().st_size for p in paths);require(shutil.disk_usage(out).free>=2*total+512*1024**2,'reserve bundle, restoration and parts space')
    aliases=member_aliases(ROOT,folder,c.read(folder/'member_index.json'));target=out/(phase.lower()+'_records.zip');index=bundle(ROOT,paths,aliases,target)
    index.update(phase=phase,manifest_id=m['manifest_id'],source_git_commit=m['source_git_commit'],executions=len(s['rows']),
        full_audit_sha256=c.sha(folder/'audit.json'),process_audit_sha256=c.sha(folder/'process_audit.json'),source_freeze_sha256=c.sha(c.FREEZE))
    parts=out/'bundle_parts';parts.mkdir();items=[]
    with target.open('rb') as source:
        while True:
            data=source.read(4*1024**2)
            if not data:break
            path=parts/('part_%03d.bin'%(len(items)+1));path.write_bytes(data);items.append(dict(path=path.relative_to(ROOT).as_posix(),bytes=len(data),sha256=c.sha(path)))
    index['parts']=items;c.write(out/'bundle_index.json',index)
    from scripts.check_tracked_secrets import find_secret_rule
    from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
    def scan(raw,name):
        text=raw.decode('utf8');require(find_secret_rule(text) is None and not any(rule.search(text) for rule in EXTRA.values()),'credential pattern '+name)
    result=recover(ROOT,target,index,restore,scan=scan);ready(manifest,phase);c.write(out/'local_restoration.json',result)
    c.write(out/'complete.json',dict(integrity='PASSED_COMPLETE_QUALIFICATION_PHASE_EXPORT_LOCAL_RESTORATION',phase=phase,manifest_id=m['manifest_id'],executions=len(s['rows']),
        bundle_index_sha256=c.sha(out/'bundle_index.json'),raw_files_and_zip_retained_local=True,aliases_deduplicate_storage_not_costs=True,
        new_physics_during_export=0,new_fits=0,online_LLM_API_calls=0,publication_goal_complete=False))
    return result


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--manifest',required=True);parser.add_argument('--phase',choices=('NATIVE','QUAL'),default='NATIVE');parser.add_argument('--restore');parser.add_argument('--check-only',action='store_true');args=parser.parse_args()
    if args.check_only:
        ready(args.manifest,args.phase);print(json.dumps(dict(integrity='PASSED_COMPLETE_PHASE_EXPORT_ADMISSION',phase=args.phase,new_physics=0,new_fits=0)))
    else:
        parser.error('--restore required for export') if args.restore is None else None
        print(json.dumps(export(args.manifest,c.BASE/(args.phase.lower()+'_delivery_v1'),args.restore,args.phase)))

"""Version offline export gates; retain the already checked archive/range algorithms."""
from pathlib import Path
import ast,hashlib,json,subprocess
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects')
OLD=ROOT/'outputs/occam_reference_train_v3/delivery_tools_v1';OUT=ROOT/'outputs/occam_reference_qualification_v1/delivery_tools_v1'
OUT.mkdir(exist_ok=False)
for p in (OLD/'train_bundle_v1.py',OLD/'test_train_bundle_v1.py'):
    original=subprocess.check_output(['git','show','HEAD:'+p.relative_to(ROOT).as_posix()],cwd=ROOT)
    assert original==p.read_bytes()
s=(OLD/'train_bundle_v1.py').read_text(encoding='utf8')
header=s[:s.index('def metadata_gate')].replace('Offline TRAIN delivery, lossless member aliases, never a data collector.',
    'Offline completed qualification-phase delivery; never a collector or simulator.').replace('occam_native_case_io_v1','occam_qualification_case_io_v1')
metadata=r'''
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


'''
generic=s[s.index('def validate_ranges'):s.index('def export')].replace('OCCAM_TRAIN_ZIP_ALIASES_V1','OCCAM_QUALIFICATION_ZIP_ALIASES_V1').replace('versioned TRAIN bundle','versioned qualification bundle').replace('PASSED_LOSSLESS_TRAIN_BUNDLE','PASSED_LOSSLESS_QUALIFICATION_BUNDLE')
export=r'''
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
'''
module=header+metadata+generic+export
compile(module,'qualification_bundle_v1.py','exec');(OUT/'qualification_bundle_v1.py').write_text(module,encoding='utf8',newline='\n')
old_tree=ast.parse(s);new_tree=ast.parse(module);unchanged={}
for name in ('safe_name','validate_ranges','bundle','recover'):
    x=next(n for n in old_tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
    normalized=module.replace('OCCAM_QUALIFICATION_ZIP_ALIASES_V1','OCCAM_TRAIN_ZIP_ALIASES_V1').replace('versioned qualification bundle','versioned TRAIN bundle').replace('PASSED_LOSSLESS_QUALIFICATION_BUNDLE','PASSED_LOSSLESS_TRAIN_BUNDLE')
    y=next(n for n in ast.parse(normalized).body if isinstance(n,ast.FunctionDef) and n.name==name)
    assert ast.dump(x)==ast.dump(y),name
    unchanged[name]=hashlib.sha256(ast.dump(x).encode()).hexdigest()
tests=(OLD/'test_train_bundle_v1.py').read_text(encoding='utf8')
tests=tests.replace('from outputs.occam_reference_train_v3.delivery_tools_v1 import train_bundle_v1 as b','from outputs.occam_reference_qualification_v1.delivery_tools_v1 import qualification_bundle_v1 as b')
tests=tests.replace('648','174').replace('647','173').replace("dict(TRAIN=[{}]*174)","dict(NATIVE=[{}]*174)").replace("manifest_id='array')\n    return", "manifest_id='array',phase='NATIVE')\n    return")
tests=tests.replace("phase=self.root/'train'","phase=self.root/'native'").replace("patch.object(b.c,'check_manifest'","patch.object(b,'manifest_metadata'").replace('OCCAM_TRAIN_ZIP_ALIASES_V1','OCCAM_QUALIFICATION_ZIP_ALIASES_V1')
tests+='''
    def test_wrong_phase_audit_rejected(self):
        v=metadata();v[4]['phase']='QUAL'
        with self.assertRaisesRegex(ValueError,'full audit'):b.metadata_gate(*v)
    def test_QUAL_requires_all1566_not_NATIVE(self):
        v=metadata();v[0]['config']['populations']['QUAL']=[{}]*1566
        with self.assertRaisesRegex(ValueError,'denominator'):b.metadata_gate(*v,phase='QUAL')
    def test_unknown_phase_rejected(self):
        with self.assertRaisesRegex(ValueError,'registered delivery phase'):b.metadata_gate(*metadata(),phase='TRAIN')
'''
compile(tests,'test_qualification_bundle_v1.py','exec');(OUT/'test_qualification_bundle_v1.py').write_text(tests,encoding='utf8',newline='\n')
proof=dict(integrity='PASSED_ARCHIVE_ALGORITHMS_AST_IDENTITY_ONLY',source_files={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (OLD/'train_bundle_v1.py',OLD/'test_train_bundle_v1.py')},
    unchanged_function_AST_sha256=unchanged,only_format_version_strings_normalized=True,metadata_gates_newly_versioned=True,new_environment_interactions=0,online_LLM_API_calls=0)
(OUT/'algorithm_reuse.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf8',newline='\n')
print(proof['integrity'])

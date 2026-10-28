"""Fast-forward a compact archival branch; retain original research history."""
from pathlib import Path
from datetime import datetime,timezone
from time import perf_counter_ns
import gzip,hashlib,json,os,subprocess,sys
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from scripts.check_tracked_secrets import find_secret_rule
from src.analysis import response_qualification_io_v1 as io
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
OUT=Path(__file__).parent
BRANCH='codex/archive-20261023-information-release-v2'
PARENT='7b9cd18ec23bcf204475c30fd2af30beb9a80125'
SOURCE='c55d0940384e645dc7aa98f95cc93a19ffa639dd'


def git(*args,data=None,env=None):
    return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT,input=data,env=env)


def scan(data,name):
    if (name.startswith(('outputs/controller_agreement/','outputs/policy_mode_diagnostic/','outputs/occam_performance_core/','outputs/occam_window_host/','outputs/occam_reference_train/','outputs/occam_reference_train_v2/')) and name.endswith('.gz')) or (name.startswith('outputs/episode_seed_inventory/') and name.endswith('inventory.json.gz')) or name in ('outputs/graybox_response/freeze_validation_v1/seed_scope.json.gz','outputs/graybox_qualification/freeze_validation_v2/ownership_scope.json.gz'):data=gzip.decompress(data)
    if b'\0' not in data:
        text=data.decode('utf-8',errors='replace')
        io.require(find_secret_rule(text) is None and not any(p.search(text) for p in EXTRA.values()),'publication credential pattern '+name)



def scan_all_record_parts():
    catalog_name='outputs/research_archive/occam_training_partial_failure_v2/catalog.json'
    baseline_bytes=git('show',PARENT+':'+catalog_name)
    io.require(baseline_bytes==(ROOT/catalog_name).read_bytes(),'exact remote-parent catalog')
    prior=json.loads(baseline_bytes);io.require(prior['integrity']=='PASSED' and prior['source_local_commit']=='3759e0e425ddb49e3d199abee1e2c95a494c91e0','prior actual Git recovery proof')
    old={r['path']:r for r in prior['files']};allowed=set();bindings={}
    def unchanged(name):
        oid=git('rev-parse',SOURCE+':'+name).decode().strip()
        io.require(oid==old[name]['oid']==git('rev-parse',PARENT+':'+name).decode().strip() and old[name]['published'],'unchanged published proof input')
        bindings[name]=oid
    for entry in prior['decoded_record_parts']['indices']:
        name=entry['index_path'];unchanged(name);raw=git('show',SOURCE+':'+name)
        io.require(hashlib.sha256(raw).hexdigest()==entry['index_sha256'],'index hash binding')
        for artifact in json.loads(raw)['artifacts']:
            unchanged((Path(artifact['original_path']).parent/'completion.json').as_posix())
            for part in artifact['parts']:
                unchanged(part['path']);allowed.add(part['path'])
    io.require(len(allowed)==28 and sum(len(x['artifacts']) for x in prior['decoded_record_parts']['indices'])==7,'complete unchanged recovery proof')
    return allowed,dict(strategy='reuse seven actual Git stream recoveries only after exact Git object identity for every index, part and collection completion',
        prior_archive_commit=PARENT,prior_catalog_sha256=hashlib.sha256(baseline_bytes).hexdigest(),unchanged_git_objects=bindings,
        indices=prior['decoded_record_parts']['indices'],new_recovery_or_physics=False)


def main():
    started=perf_counter_ns();io.require(git('rev-parse','HEAD').decode().strip()==SOURCE,'completed checkpoint only')
    state=git('status','--porcelain','--untracked-files=no');io.require(not state and not git('diff','--cached','--name-only').strip(),'clean tracked checkout/index')
    io.require(git('rev-parse','refs/heads/'+BRANCH).decode().strip()==PARENT,'unchanged verified archival parent')
    allowed_parts,record_parts_scan=scan_all_record_parts()
    baseline_path=ROOT/'outputs/research_archive/occam_training_partial_failure_v2/catalog.json'
    baseline=io.read(baseline_path);io.require(baseline['integrity']=='PASSED' and not baseline.get('credential_findings',[]),'audited prior catalog')
    old={r['path']:r for r in baseline['files']};cache={r['oid']:r for r in old.values()}
    scanned={r['oid'] for r in old.values() if r['published']};catalog=[];read_bytes=0;reused=0;new_scans=0
    proc=subprocess.Popen(['git','cat-file','--batch'],cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE)
    try:
        for raw in git('ls-tree','-r','-l','-z',SOURCE).split(b'\0'):
            if not raw:continue
            meta,path=raw.split(b'\t',1);mode,kind,oid,size=meta.decode().split();name=path.decode('utf-8');size=int(size)
            io.require(kind=='blob','plain source blobs only')
            allowed=size<=8*1024**2 and (not name.endswith(('.jsonl.gz','.bin')) or name in allowed_parts or (name.startswith(('outputs/controller_agreement/','outputs/policy_mode_diagnostic/','outputs/occam_performance_core/','outputs/occam_window_host/','outputs/occam_reference_train/','outputs/occam_reference_train_v2/')) and name.endswith('.jsonl.gz'))) and not any(p=='.env' or p.startswith('.env.') for p in Path(name).parts)
            published=allowed and (old[name]['published'] if name in old else True)
            known=cache.get(oid);need_read=known is None or (published and oid not in scanned)
            if need_read:
                proc.stdin.write((oid+'\n').encode());proc.stdin.flush();header=proc.stdout.readline().split()
                io.require(len(header)==3 and header[1]==b'blob' and int(header[2])==size,'source object size')
                digest=hashlib.sha256();remaining=size;parts=[]
                while remaining:
                    block=proc.stdout.read(min(1048576,remaining));io.require(bool(block),'complete blob bytes');remaining-=len(block);digest.update(block);read_bytes+=len(block)
                    if published:parts.append(block)
                io.require(proc.stdout.read(1)==b'\n','object boundary');h=digest.hexdigest()
                if known is not None:io.require(h==known['sha256'],'re-read content matches earlier hash')
                if published:scan(b''.join(parts),name);scanned.add(oid);new_scans+=1
                cache[oid]=dict(sha256=h,bytes=size)
            else:
                io.require(known['bytes']==size,'unchanged object size');h=known['sha256'];reused+=1
            catalog.append(dict(path=name,mode=mode,oid=oid,bytes=size,sha256=h,published=published))
        proc.stdin.close();io.require(proc.wait(timeout=60)==0,'source blob reader')
    finally:
        if proc.poll() is None:proc.kill();proc.wait()
    io.require(not any(r['published'] and r['bytes']>8*1024**2 for r in catalog),'bounded publication')
    cache_receipt=dict(integrity='PASSED',source_local_commit=SOURCE,previous_archive_commit=PARENT,
        prior_catalog_sha256=io.sha(baseline_path),decoded_record_parts=record_parts_scan,all_source_files=len(catalog),selected_files=sum(r['published'] for r in catalog),
        reused_content_hash_rows=reused,new_actual_git_bytes_hashed=read_bytes,newly_secret_scanned_blob_objects=new_scans,
        selection='retain prior per-path selection; publish bounded completed controller_agreement, policy_mode_diagnostic and occam_performance_core artifacts after decompressed scan; other raw jsonl.gz, binary .bin, environment and >8MiB remain omitted',
        selected_secret_scan='unchanged Git objects reuse earlier selected-byte scan; newly published objects scanned before publication',
        original_history_and_raw_data_preserved=True,files=catalog)
    io.write(OUT/'catalog.json',cache_receipt)
    build=Path(r'C:/Users/Administrator/Documents/ChatGPT/robotic agent/research_archive_build_research_log_v1_20261028_c55d0940384e');build.mkdir(exist_ok=False)
    entries={}
    # Keep the previous archival metadata as historical records, not a new source claim.
    for raw in git('ls-tree','-r','-z',PARENT).split(b'\0'):
        if not raw:continue
        meta,path=raw.split(b'\t',1);mode,kind,oid=meta.decode().split();name=path.decode()
        if name.startswith('ARCHIVE_'):entries[name]=(mode,oid)
    entries.update({r['path']:(r['mode'],r['oid']) for r in catalog if r['published']})
    note=f'''# 阶段研究日志已建立

来源{SOURCE}，父归档{PARENT}。根目录Research_Log.md采用北京时间，阶段完成、
检查并核对push后追加日期、任务、结果、来源及下一目标，保留历史条目。
初始三条由已核实的2026-10-28阶段归档回执补记，不冒充完整项目历史。
正在实现的资源软件资格代码未冻结，未纳入本快照。

上一轮失败结论、原始记录、全部分片和恢复副本保持原样。本次无新环境、
拟合、训练或在线LLM。原有7流/28分片实际Git恢复证明，仅在逐一核对全部
索引、分片及采集完成文件Git对象完全相同后复用；没有宣称重新恢复。
只做普通快进，不强推、合并或删除原始历史。CCF A研究目标仍未完成。

完整本地源树{len(catalog)}项，发布{sum(r["published"] for r in catalog)}项；完整省略目录保留。
'''
    extras={'ARCHIVE_LATEST.md':note.encode('utf-8'),
        'ARCHIVE_FILE_CATALOG_RESEARCH_LOG_V1_20261028.json':(json.dumps(cache_receipt,ensure_ascii=False,indent=2)+'\n').encode('utf-8'),
        (OUT/'archive_checkpoint.py').relative_to(ROOT).as_posix():(OUT/'archive_checkpoint.py').read_bytes(),
        (OUT/'catalog.json').relative_to(ROOT).as_posix():(OUT/'catalog.json').read_bytes()}
    extra_sha={}
    for name,data in extras.items():
        scan(data,name)
        if name.endswith('.py'):compile(data,name,'exec')
        entries[name]=('100644',git('hash-object','-w','--stdin',data=data).decode().strip());extra_sha[name]=hashlib.sha256(data).hexdigest()
    env=os.environ.copy();env['GIT_INDEX_FILE']=str(build/'snapshot.index');git('read-tree','--empty',env=env)
    git('update-index','-z','--index-info',data=b''.join((mode+' '+oid+'\t'+n).encode()+b'\0' for n,(mode,oid) in sorted(entries.items())),env=env)
    tree=git('write-tree',env=env).decode().strip()
    commit=git('commit-tree',tree,'-p',PARENT,data=b'Archive append-only Chinese research log and verified historical phase receipts\n').decode().strip()
    actual={}
    for raw in git('ls-tree','-r','-z',commit).split(b'\0'):
        if not raw:continue
        meta,path=raw.split(b'\t',1);mode,kind,oid=meta.decode().split();io.require(kind=='blob','archive blobs');actual[path.decode()]=(mode,oid)
    io.require(actual==entries and git('status','--porcelain','--untracked-files=no')==state and git('rev-parse','HEAD').decode().strip()==SOURCE,
        'exact snapshot and unchanged checkout')
    git('update-ref','refs/heads/'+BRANCH,commit,PARENT)
    io.write(OUT/'local_receipt.json',dict(integrity='PASSED',archive_branch=BRANCH,archive_commit=commit,archive_parent=PARENT,archive_tree=tree,
        source_local_commit=SOURCE,archive_files=len(entries),source_selected_files=sum(r['published'] for r in catalog),
        all_source_file_catalog_sha256=io.sha(OUT/'catalog.json'),extra_metadata_sha256=extra_sha,ordinary_head_worktree_index_unchanged=True,
        no_force_or_merge=True,push_performed=False,utc=datetime.now(timezone.utc).isoformat(),wall_ns=perf_counter_ns()-started))
    print(dict(integrity='PASSED',archive_commit=commit,archive_files=len(entries),new_git_bytes_hashed=read_bytes,new_secret_scanned_objects=new_scans),flush=True)


if __name__=='__main__':main()

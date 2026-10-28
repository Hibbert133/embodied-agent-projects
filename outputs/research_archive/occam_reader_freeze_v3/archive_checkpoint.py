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
PARENT='9579f995b81d1010f6e6f6894ef484af8219dad2'
SOURCE='be387b8f073beea835acc85e7b8f98a4b50aec7f'


def git(*args,data=None,env=None):
    return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT,input=data,env=env)


def scan(data,name):
    if (name.startswith(('outputs/controller_agreement/','outputs/policy_mode_diagnostic/','outputs/occam_performance_core/','outputs/occam_window_host/','outputs/occam_reference_train/','outputs/occam_reference_train_v2/')) and name.endswith('.gz')) or (name.startswith('outputs/episode_seed_inventory/') and name.endswith('inventory.json.gz')) or name in ('outputs/graybox_response/freeze_validation_v1/seed_scope.json.gz','outputs/graybox_qualification/freeze_validation_v2/ownership_scope.json.gz'):data=gzip.decompress(data)
    if b'\0' not in data:
        text=data.decode('utf-8',errors='replace')
        io.require(find_secret_rule(text) is None and not any(p.search(text) for p in EXTRA.values()),'publication credential pattern '+name)



def scan_record_parts():
    index_name='outputs/occam_window_host/delivery_v1/record_parts_index.json'
    raw=git('show',SOURCE+':'+index_name);index=json.loads(raw);io.require(index['integrity']=='PASSED','parts index')
    allowed=set();checks=[];seen=set()
    for artifact in index['artifacts']:
        original=artifact['original_path'];io.require(original.startswith('outputs/occam_window_host/native_v1/') and Path(original).name in ('cases.jsonl.gz','events.jsonl.gz','witnesses.jsonl.gz'),'owned original')
        io.require(original not in seen,'unique stream');seen.add(original)
        completion=json.loads(git('show',SOURCE+':'+str(Path(original).parent/'completion.json').replace('\\','/')))
        io.require(completion['artifact_sha256'][Path(original).name]==artifact['original_sha256'],'parts bind original collection completion')
        values=[]
        for part in artifact['parts']:
            name=part['path'];io.require(name.startswith('outputs/occam_window_host/delivery_v1/parts/') and name.endswith('.bin') and name not in allowed,'only owned unique bounded parts')
            data=git('show',SOURCE+':'+name);io.require(len(data)==part['bytes']<=4*1024**2 and hashlib.sha256(data).hexdigest()==part['sha256'],'actual Git part bytes')
            values.append(data);allowed.add(name)
        joined=b''.join(values);io.require(len(joined)==artifact['original_bytes'] and hashlib.sha256(joined).hexdigest()==artifact['original_sha256'],'actual complete gzip recovery')
        decoded=gzip.decompress(joined);io.require(len(decoded)==artifact['decoded_bytes'] and hashlib.sha256(decoded).hexdigest()==artifact['decoded_sha256'],'actual decoded stream hash')
        scan(decoded,original+'.decoded.json')
        checks.append(dict(original_path=original,original_sha256=artifact['original_sha256'],parts=len(values),decoded_bytes=len(decoded),decoded_sha256=artifact['decoded_sha256'],actual_git_recovery_and_full_decoded_scan=True))
    io.require(len(checks)==3 and len(allowed)==5,'all three streams and five parts')
    return allowed,dict(index_sha256=hashlib.sha256(raw).hexdigest(),artifacts=checks)


def scan_reader_parts():
    index_name='outputs/occam_reference_train_v2/audit_repair_v3/source_delivery_v1/record_parts_index.json'
    raw=git('show',SOURCE+':'+index_name);index=json.loads(raw);io.require(index['integrity']=='PASSED','reader source parts index')
    prefix='outputs/occam_reference_train_v2/development_v1/occam_reference_train_v2_20261027T233346Z_e695620a8a91/native/'
    completion=json.loads(git('show',SOURCE+':'+prefix+'completion.json'))
    manifest=json.loads(git('show',SOURCE+':'+prefix.removesuffix('native/')+'manifest.json'))
    io.require(completion['manifest_id']==manifest['manifest_id']=='5c3b6565eee628b32f1ca1eed1b15eb5dc6191b8f47b8293d25efb973a26f510','original native identity')
    allowed=set();checks=[];seen=set()
    for artifact in index['artifacts']:
        original=artifact['original_path'];name=Path(original).name
        io.require(original==prefix+name and name in ('events.jsonl.gz','witnesses.jsonl.gz') and name not in seen,'exact original native stream')
        seen.add(name);io.require(artifact['original_sha256']==artifact['completion_sha256']==completion['artifact_sha256'][name],'collection completion binding')
        values=[]
        for part in artifact['parts']:
            path=part['path'];io.require(path.startswith('outputs/occam_reference_train_v2/audit_repair_v3/source_delivery_v1/parts/') and path.endswith('.bin') and path not in allowed,'owned bounded reader part')
            data=git('show',SOURCE+':'+path)
            io.require(len(data)==part['bytes']<=4*1024**2 and hashlib.sha256(data).hexdigest()==part['sha256'],'actual Git reader part')
            values.append(data);allowed.add(path)
        joined=b''.join(values);decoded=gzip.decompress(joined)
        io.require(len(joined)==artifact['original_bytes'] and hashlib.sha256(joined).hexdigest()==artifact['original_sha256'],'actual full reader stream recovery')
        io.require(len(decoded)==artifact['decoded_bytes'] and hashlib.sha256(decoded).hexdigest()==artifact['decoded_sha256'],'actual decoded reader stream')
        scan(decoded,original+'.decoded.json')
        checks.append(dict(original_path=original,original_sha256=artifact['original_sha256'],parts=len(values),decoded_bytes=len(decoded),decoded_sha256=artifact['decoded_sha256'],actual_git_recovery_and_full_decoded_scan=True))
    io.require(len(checks)==2 and len(allowed)==4,'all native reader streams and four parts')
    return allowed,dict(index_sha256=hashlib.sha256(raw).hexdigest(),artifacts=checks)


def main():
    started=perf_counter_ns();io.require(git('rev-parse','HEAD').decode().strip()==SOURCE,'completed checkpoint only')
    state=git('status','--porcelain','--untracked-files=no');io.require(not state and not git('diff','--cached','--name-only').strip(),'clean tracked checkout/index')
    io.require(git('rev-parse','refs/heads/'+BRANCH).decode().strip()==PARENT,'unchanged verified archival parent')
    allowed_parts,record_parts_scan=scan_record_parts()
    native_parts,native_scan=scan_reader_parts();allowed_parts|=native_parts;record_parts_scan['native_reader_v3']=native_scan
    baseline_path=ROOT/'outputs/research_archive/occam_reference_training_freeze_v2/catalog.json'
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
    build=Path(r'C:/Users/Administrator/Documents/ChatGPT/robotic agent/research_archive_build_occam_reader_v3_20261028_be387b8f073b');build.mkdir(exist_ok=False)
    entries={}
    # Keep the previous archival metadata as historical records, not a new source claim.
    for raw in git('ls-tree','-r','-z',PARENT).split(b'\0'):
        if not raw:continue
        meta,path=raw.split(b'\t',1);mode,kind,oid=meta.decode().split();name=path.decode()
        if name.startswith('ARCHIVE_'):entries[name]=(mode,oid)
    entries.update({r['path']:(r['mode'],r['oid']) for r in catalog if r['published']})
    note=f'''# 最新归档：真实原生数据及只读读者修复v3冻结

本地来源{SOURCE}，父归档{PARENT}。原生36次实际执行、3111控制步、1836次
全部reset和933555物理帧已完成，原读者在旧命名空间常量断言处失败。
原错误日志、守卫、51字节部分公开导出与原FAILED_PARTIAL流水线全部保留。

修复版本只把噪声编号断言绑定既有冻结登记，并隔离新的NATIVE导出；完整噪声
哈希、逐步执行/成本/见证及全部人口要求保留。7新增与5重复路径回归分别计数，
2571项源码复用，共2578唯一。没有修复导致的新物理/拟合/优化/API。
首例保存记录与错误编号/哈希、噪声移位、未来历史均由数组测试覆盖。

大事件和私有见证以四个4MiB上限分片发布，归档器实际从Git取回并恢复两个
完整压缩流，核对原采集完成哈希并完整解压秘密扫描；原文件与恢复副本留本地。
当前源提交包含新读者与未启动TRAIN的受控续接冻结；源提交之后运行中的
原生重审、TRAIN及后续训练结果不在此快照，不把它写成科学资格已经完成。

见reports/occam_reference_train_reader_v3_freeze_zh.md。科学CAL/QUAL、新获取
机制、强对照完整任务收益、消融及CCF A目标尚未完成。全程零在线LLM；
保留全部旧失败/负结果、来源与省略目录。普通快进，无强推合并或历史删除。

完整本地源树{len(catalog)}项，发布{sum(r["published"] for r in catalog)}项；完整省略目录保留。
'''
    extras={'ARCHIVE_LATEST.md':note.encode('utf-8'),
        'ARCHIVE_FILE_CATALOG_OCCAM_READER_V3_20261028.json':(json.dumps(cache_receipt,ensure_ascii=False,indent=2)+'\n').encode('utf-8'),
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
    commit=git('commit-tree',tree,'-p',PARENT,data=b'Archive complete native records and independently frozen reader-only repair; scientific training and task qualification not complete\n').decode().strip()
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

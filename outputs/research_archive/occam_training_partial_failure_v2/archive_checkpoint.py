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
PARENT='ee1162c775c3e54f94b78c9d595ced211c2a5c91'
SOURCE='3759e0e425ddb49e3d199abee1e2c95a494c91e0'


def git(*args,data=None,env=None):
    return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT,input=data,env=env)


def scan(data,name):
    if (name.startswith(('outputs/controller_agreement/','outputs/policy_mode_diagnostic/','outputs/occam_performance_core/','outputs/occam_window_host/','outputs/occam_reference_train/','outputs/occam_reference_train_v2/')) and name.endswith('.gz')) or (name.startswith('outputs/episode_seed_inventory/') and name.endswith('inventory.json.gz')) or name in ('outputs/graybox_response/freeze_validation_v1/seed_scope.json.gz','outputs/graybox_qualification/freeze_validation_v2/ownership_scope.json.gz'):data=gzip.decompress(data)
    if b'\0' not in data:
        text=data.decode('utf-8',errors='replace')
        io.require(find_secret_rule(text) is None and not any(p.search(text) for p in EXTRA.values()),'publication credential pattern '+name)



def scan_all_record_parts():
    specs=(
        ('outputs/occam_window_host/delivery_v1/record_parts_index.json','outputs/occam_window_host/delivery_v1/parts/','outputs/occam_window_host/native_v1/',{'cases.jsonl.gz','events.jsonl.gz','witnesses.jsonl.gz'},3,5),
        ('outputs/occam_reference_train_v2/audit_repair_v3/source_delivery_v1/record_parts_index.json','outputs/occam_reference_train_v2/audit_repair_v3/source_delivery_v1/parts/','outputs/occam_reference_train_v2/development_v1/occam_reference_train_v2_20261027T233346Z_e695620a8a91/native/',{'events.jsonl.gz','witnesses.jsonl.gz'},2,4),
        ('outputs/occam_reference_train_v2/failure_delivery_v2/result_delivery_v1/record_parts_index.json','outputs/occam_reference_train_v2/failure_delivery_v2/result_delivery_v1/parts/','outputs/occam_reference_train_v2/development_v1/occam_reference_train_v2_20261027T233346Z_e695620a8a91/train/',{'events.jsonl.gz','witnesses.jsonl.gz'},2,19))
    restore=OUT/'actual_git_stream_restoration_v1';restore.mkdir(exist_ok=False);allowed=set();checks=[]
    for ordinal,(index_name,part_prefix,original_prefix,basenames,nstream,npart) in enumerate(specs):
        raw=git('show',SOURCE+':'+index_name);index=json.loads(raw);io.require(index['integrity']=='PASSED','parts index')
        local_allowed=set();local_checks=[];seen=set()
        for artifact in index['artifacts']:
            original=artifact['original_path'];name=Path(original).name
            io.require(original.startswith(original_prefix) and name in basenames and original not in seen,'exact owned original stream');seen.add(original)
            if ordinal:io.require(original==original_prefix+name,'new reference exact original')
            completion_path=(Path(original).parent/'completion.json').as_posix();completion=json.loads(git('show',SOURCE+':'+completion_path))
            io.require(completion['artifact_sha256'][name]==artifact['original_sha256'],'collection completion hash')
            if ordinal==2:io.require(completion['status']=='FAILED_PARTIAL' and completion['manifest_id']=='5c3b6565eee628b32f1ca1eed1b15eb5dc6191b8f47b8293d25efb973a26f510','closed incomplete TRAIN binding')
            recovered=restore/(str(ordinal)+'_'+name);full=hashlib.sha256();total=0
            with recovered.open('xb') as target:
                for part in artifact['parts']:
                    path=part['path'];io.require(path.startswith(part_prefix) and path.endswith('.bin') and path not in allowed and path not in local_allowed,'owned unique part')
                    data=git('show',SOURCE+':'+path);io.require(len(data)==part['bytes']<=4*1024**2 and hashlib.sha256(data).hexdigest()==part['sha256'],'actual Git part')
                    target.write(data);full.update(data);total+=len(data);local_allowed.add(path)
            io.require(total==artifact['original_bytes'] and full.hexdigest()==artifact['original_sha256'],'actual complete compressed stream recovery')
            decoded=hashlib.sha256();size=records=0
            with gzip.open(recovered,'rb') as stream:
                for line in stream:
                    decoded.update(line);size+=len(line);records+=1;scan(line,original+'.decoded.json')
            io.require(size==artifact['decoded_bytes'] and decoded.hexdigest()==artifact['decoded_sha256'],'all decoded bytes hash')
            if 'decoded_records' in artifact:io.require(records==artifact['decoded_records'],'decoded record count')
            local_checks.append(dict(original_path=original,original_sha256=artifact['original_sha256'],parts=len(artifact['parts']),decoded_bytes=size,decoded_records=records,decoded_sha256=decoded.hexdigest(),actual_git_recovery_and_every_decoded_row_scanned=True))
        io.require(len(local_checks)==nstream and len(local_allowed)==npart,'complete source index coverage')
        allowed|=local_allowed;checks.append(dict(index_path=index_name,index_sha256=hashlib.sha256(raw).hexdigest(),artifacts=local_checks))
    io.require(len(allowed)==28 and sum(len(q['artifacts']) for q in checks)==7,'all seven streams and28 parts')
    return allowed,dict(strategy='bounded actual Git part to disk; decoded row streaming; no full decoded allocation',indices=checks)


def main():
    started=perf_counter_ns();io.require(git('rev-parse','HEAD').decode().strip()==SOURCE,'completed checkpoint only')
    state=git('status','--porcelain','--untracked-files=no');io.require(not state and not git('diff','--cached','--name-only').strip(),'clean tracked checkout/index')
    io.require(git('rev-parse','refs/heads/'+BRANCH).decode().strip()==PARENT,'unchanged verified archival parent')
    allowed_parts,record_parts_scan=scan_all_record_parts()
    baseline_path=ROOT/'outputs/research_archive/occam_reader_freeze_v3/catalog.json'
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
    build=Path(r'C:/Users/Administrator/Documents/ChatGPT/robotic agent/research_archive_build_occam_train_failure_v2_20261028_3759e0e425dd');build.mkdir(exist_ok=False)
    entries={}
    # Keep the previous archival metadata as historical records, not a new source claim.
    for raw in git('ls-tree','-r','-z',PARENT).split(b'\0'):
        if not raw:continue
        meta,path=raw.split(b'\t',1);mode,kind,oid=meta.decode().split();name=path.decode()
        if name.startswith('ARCHIVE_'):entries[name]=(mode,oid)
    entries.update({r['path']:(r['mode'],r['oid']) for r in catalog if r['published']})
    note=f'''# 最新归档：TRAIN技术停止与零交互失败交付

本地来源{SOURCE}，父归档{PARENT}。NATIVE36完成且审计通过；TRAIN188项
完整，第189项首次见证边界bytes分配失败，459项未启动。所有原分配及预留
关闭，不续接、补齐或用188条绕过648项训练门，未启动任务指标保持null。

原分配实际27982控制步/11475全部reset/5877410物理帧，含失败例51reset/
25500帧/0任务控制步。Windows事件2004支持系统虚拟内存压力；没有内部
完整原生栈，不能指认唯一原因、分配大小或内存泄漏。原事件XML留本地，
去除计算机名/SID的观测与原哈希已保存。没有科学网络训练/在线LLM。

零交互诊断冻结eb0bffc后，逐行核对完整性、闭合、序号/身份/时间和整数
费用；它不是完整政策/PI/执行器重放或完整TRAIN审计，没有训练资格。
8新增检查与2578源码复用共2586唯一，原生/读者失败、全部19实际任务失败、
部分和未启动记录均保留；169/188仅作未平衡前缀的事后描述，无总体收益主张。

新增TRAIN事件/私有见证以19个4MiB上限分片发布。归档器对本轮及历史
共7条流/28分片逐块从实际Git恢复、绑定采集完成哈希，逐行扫描全部解压
字节并核对哈希，不将整条解压大流装入内存。原文件与恢复副本继续保留。

完整中文报告reports/occam_reference_training_partial_failure_v2_zh.md。
下一步先完成资源观测/完整栈/有界生命周期的软件资格；不以弱化见证、调旧
QUAL、复活ARX/SS或换小人口通过。A主线的新获取机制、独立自身历史完整
任务优势、强参考/消融及CCF A目标仍未完成。普通快进，无强推合并或历史删除。

完整本地源树{len(catalog)}项，发布{sum(r["published"] for r in catalog)}项；完整省略目录保留。
'''
    extras={'ARCHIVE_LATEST.md':note.encode('utf-8'),
        'ARCHIVE_FILE_CATALOG_OCCAM_TRAIN_FAILURE_V2_20261028.json':(json.dumps(cache_receipt,ensure_ascii=False,indent=2)+'\n').encode('utf-8'),
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
    commit=git('commit-tree',tree,'-p',PARENT,data=b'Archive closed incomplete training allocation and bounded-stream zero-interaction failure diagnosis\n').decode().strip()
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

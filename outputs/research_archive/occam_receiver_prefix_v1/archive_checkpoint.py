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
PARENT='e3b43c1ddaca52a4a9def9cea14f90856fea9ba2'
SOURCE='4fb646a93bac29fcf2b6422c60a562dad7bddf0d'


def git(*args,data=None,env=None):
    return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT,input=data,env=env)


def scan(data,name):
    if name.startswith('outputs/occam_reference_qualification_v1/') and name.endswith('.gz'):data=gzip.decompress(data)
    elif (name.startswith(('outputs/controller_agreement/','outputs/policy_mode_diagnostic/','outputs/occam_performance_core/','outputs/occam_window_host/','outputs/occam_reference_train/','outputs/occam_reference_train_v2/')) and name.endswith('.gz')) or (name.startswith('outputs/episode_seed_inventory/') and name.endswith('inventory.json.gz')) or name in ('outputs/graybox_response/freeze_validation_v1/seed_scope.json.gz','outputs/graybox_qualification/freeze_validation_v2/ownership_scope.json.gz'):data=gzip.decompress(data)
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
    native_index_name='outputs/occam_reference_train_v3/native_delivery_v1/bundle_index.json'
    native_proof_name='outputs/occam_reference_train_v3/native_delivery_v1/actual_git_recovery.json'
    native_raw=git('show',SOURCE+':'+native_index_name);native_index=json.loads(native_raw)
    native_proof_raw=git('show',SOURCE+':'+native_proof_name);native_proof=json.loads(native_proof_raw)
    io.require(native_raw==(ROOT/native_index_name).read_bytes() and native_proof_raw==(ROOT/native_proof_name).read_bytes(),'native immutable proof bytes')
    io.require(native_index['schema']=='OCCAM_NATIVE_ZIP_PARTS_V1' and native_proof['integrity']=='PASSED_ACTUAL_COMMIT_PARTS_AND_FILES_RESTORATION'
        and native_proof['index_sha256']==hashlib.sha256(native_raw).hexdigest() and native_proof['source_commit']=='d2dc35e56e174a1e26388068f617f82caf89df34'
        and native_proof['result']['files']==len(native_index['files'])==499 and native_proof['part_count']==len(native_index['parts'])==10,'complete native actual Git restoration')
    native_oids={}
    for part in native_index['parts']:
        name=part['path'];io.require(name.startswith('outputs/occam_reference_train_v3/native_delivery_v1/bundle_parts/') and name.endswith('.bin') and part['bytes']<=4*1024**2,'bounded native parts only')
        oid=git('rev-parse',SOURCE+':'+name).decode().strip()
        io.require(oid==native_proof['part_git_oids'][name]==git('rev-parse',native_proof['source_commit']+':'+name).decode().strip(),'same actually restored native object')
        data=git('show',SOURCE+':'+name);io.require(len(data)==part['bytes'] and hashlib.sha256(data).hexdigest()==part['sha256'],'native source part bytes')
        native_oids[name]=oid;allowed.add(name)
    records=dict(strategy='reuse historical actual recoveries after exact Git identity; native499-file ZIP has its own committed actual recovery and decoded credential scan',
        prior_archive_commit=PARENT,prior_catalog_sha256=hashlib.sha256(baseline_bytes).hexdigest(),unchanged_git_objects=bindings,
        indices=prior['decoded_record_parts']['indices'],new_recovery_or_physics=False,
        native_zip_bundle=dict(index_path=native_index_name,index_sha256=hashlib.sha256(native_raw).hexdigest(),proof_path=native_proof_name,
            proof_sha256=hashlib.sha256(native_proof_raw).hexdigest(),source_commit=native_proof['source_commit'],part_git_oids=native_oids,
            files=499,parts=10,decoded_gzip_lines=native_proof['result']['decoded_gzip_lines']))


    train_index_name='outputs/occam_reference_train_v3/train_delivery_v1/bundle_index.json'
    train_proof_name='outputs/occam_reference_train_v3/train_delivery_v1/actual_git_recovery.json'
    train_raw=git('show',SOURCE+':'+train_index_name);train=json.loads(train_raw)
    proof_raw=git('show',SOURCE+':'+train_proof_name);proof=json.loads(proof_raw)
    io.require(train_raw==(ROOT/train_index_name).read_bytes() and proof_raw==(ROOT/train_proof_name).read_bytes(),'TRAIN exact committed proof bytes')
    io.require(train['schema']=='OCCAM_TRAIN_ZIP_ALIASES_V1' and proof['integrity']=='PASSED_ACTUAL_COMMIT_TRAIN_PARTS_AND_FILES_RESTORATION'
        and proof['source_commit']=='634b3454fa0dd3aceb901ba565be2d80b854ec40'
        and proof['index_sha256']==hashlib.sha256(train_raw).hexdigest()
        and proof['result']['files']==len(train['files'])==8450 and proof['part_count']==len(train['parts'])==83
        and proof['result']['reconstructed_member_files']==len(train['aliases'])==1296
        and proof['result']['decoded_canonical_gzip_lines']==802542 and proof['result']['all_files_byte_identical'],'all648 original TRAIN files restored and decoded-scanned')
    io.require(git('rev-parse',SOURCE+':'+train_index_name)==git('rev-parse',proof['source_commit']+':'+train_index_name),'same actually recovered TRAIN index')
    train_oids={}
    for part in train['parts']:
        name=part['path'];io.require(name.startswith('outputs/occam_reference_train_v3/train_delivery_v1/bundle_parts/') and part['bytes']<=4*1024**2,'bounded owned TRAIN part')
        oid=git('rev-parse',SOURCE+':'+name).decode().strip()
        io.require(oid==proof['part_git_oids'][name]==git('rev-parse',proof['source_commit']+':'+name).decode().strip(),'TRAIN exact actually restored Git part')
        data=git('show',SOURCE+':'+name);io.require(len(data)==part['bytes'] and hashlib.sha256(data).hexdigest()==part['sha256'],'TRAIN source part bytes')
        train_oids[name]=oid;allowed.add(name)
    records['train_zip_bundle']=dict(index_path=train_index_name,index_sha256=hashlib.sha256(train_raw).hexdigest(),proof_path=train_proof_name,
        proof_sha256=hashlib.sha256(proof_raw).hexdigest(),source_commit=proof['source_commit'],part_git_oids=train_oids,
        original_files=8450,parts=83,exact_gzip_aliases=1296,decoded_canonical_gzip_lines=802542,
        aliases_reuse_complete_canonical_decoded_scan_disclosed=True,no_new_recovery_in_archive=True)

    qindex_name='outputs/occam_reference_qualification_v1/native_delivery_v1/bundle_index.json'
    qproof_name='outputs/occam_reference_qualification_v1/native_delivery_v1/actual_git_recovery.json'
    qraw=git('show',SOURCE+':'+qindex_name);qindex=json.loads(qraw)
    qproof_raw=git('show',SOURCE+':'+qproof_name);qproof=json.loads(qproof_raw)
    io.require(qraw==(ROOT/qindex_name).read_bytes() and qproof_raw==(ROOT/qproof_name).read_bytes(),'Native qualification exact committed receipts')
    io.require(qindex['schema']=='OCCAM_QUALIFICATION_ZIP_ALIASES_V1' and qindex['phase']=='NATIVE' and qindex['executions']==174
        and len(qindex['files'])==2288 and len(qindex['aliases'])==348,'complete Native qualification record scope')
    io.require(qproof['integrity']=='PASSED_ACTUAL_COMMIT_QUALIFICATION_NATIVE_PARTS_AND_FILES_RESTORATION'
        and qproof['source_commit']=='de7d3541b7af0f24226f141344b3cb4787ba0526'
        and qproof['index_sha256']==hashlib.sha256(qraw).hexdigest() and qproof['result']['files']==2288
        and qproof['result']['all_files_byte_identical'] and qproof['result']['decoded_canonical_gzip_lines']==158286
        and qproof['part_count']==len(qindex['parts'])==12,'Native actual original-byte Git restoration')
    qoids={}
    for part in qindex['parts']:
        name=part['path'];io.require(name.startswith('outputs/occam_reference_qualification_v1/native_delivery_v1/bundle_parts/')
            and name.endswith('.bin') and part['bytes']<=4*1024**2,'bounded Native qualification data shard')
        oid=git('rev-parse',SOURCE+':'+name).decode().strip()
        io.require(oid==qproof['part_git_oids'][name]==git('rev-parse',qproof['source_commit']+':'+name).decode().strip(),'same actually recovered Native shard object')
        data=git('show',SOURCE+':'+name);io.require(len(data)==part['bytes'] and hashlib.sha256(data).hexdigest()==part['sha256'],'Native shard exact bytes')
        qoids[name]=oid;allowed.add(name)
    portable_name='outputs/occam_reference_qualification_v1/native_delivery_v1/archive_only_restoration.json'
    portable_raw=git('show',SOURCE+':'+portable_name);portable=json.loads(portable_raw)
    io.require(portable_raw==(ROOT/portable_name).read_bytes() and portable['integrity']=='PASSED_ACTUAL_GIT_ARCHIVE_ONLY_NATIVE_RESTORATION'
        and portable['part_git_oids']==qoids and portable['result']['files']==2288
        and portable['result']['size_and_SHA_against_committed_index'] and not portable['result']['original_raw_files_required']
        and not portable['result']['original_raw_byte_comparison'] and not any(portable['guard'].values()),'Native archive-only actual restoration')
    validation_name='outputs/occam_reference_qualification_v1/delivery_tools_v1/archive_only_validation_v1/complete.json'
    validation_raw=git('show',SOURCE+':'+validation_name);validation=json.loads(validation_raw)
    io.require(validation['integrity']=='PASSED_ARCHIVE_ONLY_ENGINEERING_VALIDATION' and validation['unit_tests']==3,'portable engineering checks')
    for name,h in validation['source_sha256'].items():
        io.require(hashlib.sha256(git('show',SOURCE+':'+name)).hexdigest()==h,'tested portable recovery code unchanged')
    records['qualification_native_bundle']=dict(index_path=qindex_name,index_sha256=hashlib.sha256(qraw).hexdigest(),
        proof_path=qproof_name,proof_sha256=hashlib.sha256(qproof_raw).hexdigest(),data_commit=qproof['source_commit'],
        actual_part_git_oids=qoids,files=2288,parts=12,exact_gzip_aliases=348,decoded_canonical_gzip_lines=158286,
        portable_proof_path=portable_name,portable_proof_sha256=hashlib.sha256(portable_raw).hexdigest(),
        portable_source_raw_read_attempts=0,portable_original_comparison_not_claimed=True,
        no_new_science_or_recovery_during_archive=True)
    io.require(len(allowed)==133,'exact historical and Native bounded lossless part scope')

    return allowed,records


def main():
    started=perf_counter_ns();io.require(git('rev-parse','HEAD').decode().strip()==SOURCE,'completed checkpoint only')
    state=git('status','--porcelain','--untracked-files=no');io.require(not state and not git('diff','--cached','--name-only').strip(),'clean tracked checkout/index')
    io.require(git('rev-parse','refs/heads/'+BRANCH).decode().strip()==PARENT,'unchanged verified archival parent')
    allowed_parts,record_parts_scan=scan_all_record_parts()
    baseline_path=ROOT/'outputs/research_archive/occam_qualification_native_v1/catalog.json'
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
        selection='retain prior per-path selections; allow individually proved old, Native, complete TRAIN and qualification Native174 lossless parts plus bounded checked banks; omit other raw streams, binary parts, environment and >8MiB files',
        selected_secret_scan='unchanged Git objects reuse earlier selected-byte scan; newly published objects scanned before publication',
        original_history_and_raw_data_preserved=True,files=catalog)
    io.write(OUT/'catalog.json',cache_receipt)
    build=Path(r'C:/Users/Administrator/Documents/ChatGPT/robotic agent/research_archive_build_occam_receiver_prefix_v1_20261029_4fb646a93bac');build.mkdir(exist_ok=False)
    entries={}
    # Keep the previous archival metadata as historical records, not a new source claim.
    for raw in git('ls-tree','-r','-z',PARENT).split(b'\0'):
        if not raw:continue
        meta,path=raw.split(b'\t',1);mode,kind,oid=meta.decode().split();name=path.decode()
        if name.startswith('ARCHIVE_'):entries[name]=(mode,oid)
    entries.update({r['path']:(r['mode'],r['oid']) for r in catalog if r['published']})
    note=f'''# 四个冻结接收者的旧来源前缀：完整只读交付

来源{SOURCE}，父归档{PARENT}。先提交软件／输入／20合成检查冻结，再对
全部TRAIN648来源×四接收者＝2592份分析、432完整分层、18独立组复算。
首个不同增益后不再提交旧反馈或后续query，全部接收者任务结果字段缺失。

每方法542非空来源：META两程序各493条首次分歧／49条全部观测增益相同，
ERM各484／58；各106无决定。bank本来就由这些TRAIN训练，因此只是来源内
描述，不是独立前瞻误差、统计覆盖、离策略价值或自身部署。选择相同也
不自动证明所有低层命令／物理状态相同；原602／46仅为来源成功／失败。

独立dense／标量后验／记录／分层复算通过，主provider／前向／更新／回放／
统计函数在审计禁用。严格公开特征共享已披露。主3027声明／12108候选、
440分析端更新／求解、44148eig，独立同样声明／候选／标量更新、0求解。
全阶段1790.990秒<冻结1800秒。另两次合成输入冻结bank计时共2声明／8候选，
0更新，30eig按代码复算而非直接计数，含cProfile且与主墙钟重叠，单列。
新环境／reset／帧／固定策略查询／神经训练／批量拟合／seed／在线LLM0。

实际Git／索引／磁盘字节、秘密／补充秘密和差异检查通过；原数据、分片、
恢复副本和全部负结果不改。旧133个有实际恢复证明的记录分片按精确Git
身份核对复用，归档没有新采集或新复原。原科学源码／bank／主比较不变。
查新v7及补充只限定已知方法边界，不宣称创新；首窗口全候选诊断仍是
DESIGN_ONLY，待完整QUAL与统计完整性通过后另冻reader，当前无其结果。
仍运行的QUAL不在本归档。完整风险强参考、独立任务收益、新获取机制和
消融仍待完成；本次检查不完成CCF A目标。当前源树{len(catalog)}项，发布
{sum(r["published"] for r in catalog)}项；省略源有完整大小／SHA目录。
'''
    extras={'ARCHIVE_LATEST.md':note.encode('utf-8'),
        'ARCHIVE_FILE_CATALOG_OCCAM_RECEIVER_PREFIX_V1_20261029.json':(json.dumps(cache_receipt,ensure_ascii=False,indent=2)+'\n').encode('utf-8'),
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
    commit=git('commit-tree',tree,'-p',PARENT,data=b'Archive complete TRAIN receiver-prefix support with independent arithmetic, missing task outcomes and full costs\n').decode().strip()
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

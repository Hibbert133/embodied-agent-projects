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
PARENT='ff5610d3e44b44c92351d9fb7d2c0b280c4f9c56'
SOURCE='ff05ef4e5f10e5da683f14f8a6ffd9603c7825b9'


def git(*args,data=None,env=None):
    return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT,input=data,env=env)


def scan(data,name):
    if (name.startswith(('outputs/controller_agreement/','outputs/policy_mode_diagnostic/','outputs/occam_performance_core/','outputs/occam_window_host/')) and name.endswith('.gz')) or (name.startswith('outputs/episode_seed_inventory/') and name.endswith('inventory.json.gz')) or name in ('outputs/graybox_response/freeze_validation_v1/seed_scope.json.gz','outputs/graybox_qualification/freeze_validation_v2/ownership_scope.json.gz'):data=gzip.decompress(data)
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

def main():
    started=perf_counter_ns();io.require(git('rev-parse','HEAD').decode().strip()==SOURCE,'completed checkpoint only')
    state=git('status','--porcelain','--untracked-files=no');io.require(not state and not git('diff','--cached','--name-only').strip(),'clean tracked checkout/index')
    io.require(git('rev-parse','refs/heads/'+BRANCH).decode().strip()==PARENT,'unchanged verified archival parent')
    allowed_parts,record_parts_scan=scan_record_parts()
    baseline_path=ROOT/'outputs/research_archive/occam_performance_core_v1/catalog.json'
    baseline=io.read(baseline_path);io.require(baseline['integrity']=='PASSED' and not baseline.get('credential_findings',[]),'audited prior catalog')
    old={r['path']:r for r in baseline['files']};cache={r['oid']:r for r in old.values()}
    scanned={r['oid'] for r in old.values() if r['published']};catalog=[];read_bytes=0;reused=0;new_scans=0
    proc=subprocess.Popen(['git','cat-file','--batch'],cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE)
    try:
        for raw in git('ls-tree','-r','-l','-z',SOURCE).split(b'\0'):
            if not raw:continue
            meta,path=raw.split(b'\t',1);mode,kind,oid,size=meta.decode().split();name=path.decode('utf-8');size=int(size)
            io.require(kind=='blob','plain source blobs only')
            allowed=size<=8*1024**2 and (not name.endswith(('.jsonl.gz','.bin')) or name in allowed_parts or (name.startswith(('outputs/controller_agreement/','outputs/policy_mode_diagnostic/','outputs/occam_performance_core/','outputs/occam_window_host/')) and name.endswith('.jsonl.gz'))) and not any(p=='.env' or p.startswith('.env.') for p in Path(name).parts)
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
    build=Path(r'C:/Users/Administrator/Documents/ChatGPT/robotic agent/research_archive_build_occam_window_20261028_ff05ef4e5f10');build.mkdir(exist_ok=False)
    entries={}
    # Keep the previous archival metadata as historical records, not a new source claim.
    for raw in git('ls-tree','-r','-z',PARENT).split(b'\0'):
        if not raw:continue
        meta,path=raw.split(b'\t',1);mode,kind,oid=meta.decode().split();name=path.decode()
        if name.startswith('ARCHIVE_'):entries[name]=(mode,oid)
    entries.update({r['path']:(r['mode'],r['oid']) for r in catalog if r['published']})
    note=f'''# 最新归档：OCCAM相关连续表现窗口原生主机资格

本地来源 ff05ef4e5f10e5da683f14f8a6ffd9603c7825b9，冻结9087199，读者修复1d49623/b623f39，父归档ff5610d3e44b44c92351d9fb7d2c0b280c4f9c56。
完整36项构造模型人口仅采集一次：4203控制步、36受控重置、1836全部重置、
939015物理帧、3845次政策查询、142次在线滤波；33/36成功，全部3失败保留。
14对到达选择，首个实际命令全部不同；4对提前结束保留。世界/噪声/时钟、
保存决策消费、独立标量完整成本与联合高斯后验、完整人口/见证核对通过。

这是未训练构造模型的软件执行资格，不是完整OCCAM复现、科学任务优势或新算法。
31主机+4人口循环新增唯一检查，旧2487源码绑定复用，共2522。首次21项开发
未运行时计数的限制保留，后续守卫明确；无新科学离线训练/Adam/在线LLM。
标准势差只保证全段核账一致，不能保证短时贪心、预测或控制安全。

v1缺全局导入，v2配对覆盖流游标，两次失败和费用都保留；v3在4项完整人口
循环回归后另冻，只修导入/变量名，门槛/原始记录/科学源不变，零物理重跑。
先前滤波推算33漏计末段，更正34；实测/推得和缺失耗时分列，不能只报通过那次。
完整报告reports/occam_window_host_v1_zh.md，来源/成本/原始完整分母可追溯。

三原始gzip以五个<=4MiB分片完整保存。归档器从实际Git对象拼接每一组，
校验原采集completion SHA及完整解压字节后秘密扫描，才允许这些特定bin发布；
原始大文件/超限gzip副本留本地。旧省略目录维持，不把紧凑归档冒称全历史备份。
下一步仍需独立TRAIN/CAL/自身历史任务协议、强对照/消融与新机制验证；
独立任务优势和CCF A目标未完成。普通快进，无强推、合并或删除。

完整本地源树{len(catalog)}项，发布{sum(r["published"] for r in catalog)}项；完整省略目录保留。
'''
    extras={'ARCHIVE_LATEST.md':note.encode('utf-8'),
        'ARCHIVE_FILE_CATALOG_OCCAM_WINDOW_20261028.json':(json.dumps(cache_receipt,ensure_ascii=False,indent=2)+'\n').encode('utf-8'),
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
    commit=git('commit-tree',tree,'-p',PARENT,data=b'Archive continuous performance host contract and complete retained reader failures; no learned task gain\n').decode().strip()
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

"""Fast-forward a compact archival branch; retain original research history."""
from pathlib import Path
from datetime import datetime,timezone
from time import perf_counter_ns
import hashlib,json,os,subprocess,sys
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from scripts.check_tracked_secrets import find_secret_rule
from src.analysis import response_qualification_io_v1 as io
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
OUT=Path(__file__).parent
BRANCH='codex/archive-20261023-information-release-v2'
PARENT='aa95518b50f188d2969d2731b86e8740c0fd826a'
SOURCE='f26a138bf271da2e112b5642985166b18d1894dd'


def git(*args,data=None,env=None):
    return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT,input=data,env=env)


def scan(data,name):
    if b'\0' not in data:
        text=data.decode('utf-8',errors='replace')
        io.require(find_secret_rule(text) is None and not any(p.search(text) for p in EXTRA.values()),'publication credential pattern '+name)


def main():
    started=perf_counter_ns();io.require(git('rev-parse','HEAD').decode().strip()==SOURCE,'completed checkpoint only')
    state=git('status','--porcelain','--untracked-files=no');io.require(not state and not git('diff','--cached','--name-only').strip(),'clean tracked checkout/index')
    io.require(git('rev-parse','refs/heads/'+BRANCH).decode().strip()==PARENT,'unchanged verified archival parent')
    baseline_path=ROOT/'outputs/research_archive/transfer_learning_v1/catalog.json'
    baseline=io.read(baseline_path);io.require(baseline['integrity']=='PASSED' and not baseline.get('credential_findings',[]),'audited prior catalog')
    old={r['path']:r for r in baseline['files']};cache={r['oid']:r for r in old.values()}
    scanned={r['oid'] for r in old.values() if r['published']};catalog=[];read_bytes=0;reused=0;new_scans=0
    proc=subprocess.Popen(['git','cat-file','--batch'],cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE)
    try:
        for raw in git('ls-tree','-r','-l','-z',SOURCE).split(b'\0'):
            if not raw:continue
            meta,path=raw.split(b'\t',1);mode,kind,oid,size=meta.decode().split();name=path.decode('utf-8');size=int(size)
            io.require(kind=='blob','plain source blobs only')
            allowed=size<=8*1024**2 and not name.endswith(('.jsonl.gz','.bin')) and not any(p=='.env' or p.startswith('.env.') for p in Path(name).parts)
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
        prior_catalog_sha256=io.sha(baseline_path),all_source_files=len(catalog),selected_files=sum(r['published'] for r in catalog),
        reused_content_hash_rows=reused,new_actual_git_bytes_hashed=read_bytes,newly_secret_scanned_blob_objects=new_scans,
        selection='retain prior per-path selection; new files exclude raw jsonl.gz, binary .bin parts, environment files and >8MiB',
        selected_secret_scan='unchanged Git objects reuse earlier selected-byte scan; newly published objects scanned before publication',
        original_history_and_raw_data_preserved=True,files=catalog)
    io.write(OUT/'catalog.json',cache_receipt)
    build=Path(r'C:/Users/Administrator/Documents/ChatGPT/robotic agent/research_archive_build_transfer_ablation_20261026_f26a138');build.mkdir(exist_ok=False)
    entries={}
    # Keep the previous archival metadata as historical records, not a new source claim.
    for raw in git('ls-tree','-r','-z',PARENT).split(b'\0'):
        if not raw:continue
        meta,path=raw.split(b'\t',1);mode,kind,oid=meta.decode().split();name=path.decode()
        if name.startswith('ARCHIVE_'):entries[name]=(mode,oid)
    entries.update({r['path']:(r['mode'],r['oid']) for r in catalog if r['published']})
    note=f'''# 最新阶段存档：纠正后适用性的匹配辅助监督消融

来源已检查结果 {SOURCE}，父存档 {PARENT}；普通快进，无强推/合并。
本轮先在ccf7629提交实现/配置/数组测试及独立审计，再一次固定预算拟合。
旧TRAIN9组54单元，32原程序1728行原样复用，12新控制648次新离线支持选择，
总44程序2376行；不是新物理运行或最终独立评价人口，CAL/TEST未用于学习评价。

原候选/架构/初始化/完整成本/折分/预算固定，仅干预辅助监督：
FUTURE_MARGINAL_PRODUCT保留p/g/长度，用p*g替代j；FUTURE_RATE_MEAN平均
四个候选未来目标；HISTORY_RECONSTRUCT重建已有真实历史。派生标签不是新
物理轨迹，历史控制仍保留相同全局TRAIN误差尺度和完整成本监督。
每个前置critic只绑定自己的确切receiver；不跨接标签，不用事后最优成本。

主判断通过：源JOINT平均完整损失86.425926、成功54/54；三个简化控制依次
102.740741(52/54)、93.851852(54/54)、95.925926(52/54)。候选逐一更低，
但只显示该固定有限学习设置的监督区别；不能判定唯一物理机制或新颖性。
纠正平均控制也54/54，成功率本身不能证明纠正相关信息必要。原相对最小
固定程序均值仅低.425926步且来源组集中这一限制保持，不因消融自动消失。
普通辅助学习、SF、SPO、任务性能预测/获取已有研究；本轮不是CCF A成果。

新增科学9神经风险/辅助模型9000次SGD、9前置RBF；独立9神经9000SGD、9lstsq。
原候选及其他源模型未重训，源拟合/物理数据费用另列。独立核对3415296字段，
最大参数差6.619704784327496e-15、预定容差5e-8，实际选择完全一致；主标签/
网络/梯度/训练/特征/选择/统计禁用。共享NumPy，不称独立机构或框架审计。
原152224标签字段事件审计来源哈希复用，未当成新增独立证据重复计算。
19新数组测试加2139源码绑定旧回执=2158唯一检查，旧六组张量另列；重复
开发检查不增加唯一数。编译、依赖、全仓秘密、新实际索引秘密/字节、差异、
Git/disk字节核对通过。实际PNG已查看，图/全表/失败/缺失及792分格均保留。

新增环境/重置/控制步/物理帧、原策略查询、机器人种子、响应/逆模型、底层
策略训练、在线LLM API全部0。源TRAIN648次、77563步、33048全部重置、
16911815帧单列；不免费化物理来源，不删失败，不恢复世界撤销获取位移。
下一步仍需具体获取/采用机制区别、独立自身历史、完整强参考和成本资格。
中文报告reports/correction_transfer_ablation_v1_zh.md；原A1/FULL-MASK/ARX/
响应模型负结果和旧六项比较保持不变，完整CCF A目标未完成。

来源树{len(catalog)}文件、发布{sum(r['published'] for r in catalog)}个。
ARCHIVE_FILE_CATALOG_TRANSFER_ABLATION_20261026.json登记全部已提交路径的
大小、Git对象与SHA-256。新18模型、9派生TRAIN目标、全量选择/重放/结果均
发布；旧大型原始物理.jsonl.gz、二进制分片、实际恢复副本及普通完整Git
历史仍在本地，克隆此分支不包含它们。按类型/大小排除，不按成败。
新发布Git对象实际读取/扫描；相同对象复用已核验哈希和扫描；没有强推、
合并、删除/改写原始历史或数据，也不推送含超大blob的普通研究历史。
'''
    extras={'ARCHIVE_LATEST.md':note.encode('utf-8'),
        'ARCHIVE_FILE_CATALOG_TRANSFER_ABLATION_20261026.json':(json.dumps(cache_receipt,ensure_ascii=False,indent=2)+'\n').encode('utf-8'),
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
    commit=git('commit-tree',tree,'-p',PARENT,data=b'Archive matched auxiliary supervision ablations f26a138; no new physics or LLM\n').decode().strip()
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

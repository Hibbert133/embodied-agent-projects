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
PARENT='f478a2a73da035d69dd97164b2f1713e85bc4c8a'
SOURCE='2c50164b3a69a044133ef93e51ee280a2a2bf4a7'


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
    baseline_path=ROOT/'outputs/research_archive/transfer_ablation_v1/catalog.json'
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
    build=Path(r'C:/Users/Administrator/Documents/ChatGPT/robotic agent/research_archive_build_learned_native_20261027_2c50164');build.mkdir(exist_ok=False)
    entries={}
    # Keep the previous archival metadata as historical records, not a new source claim.
    for raw in git('ls-tree','-r','-z',PARENT).split(b'\0'):
        if not raw:continue
        meta,path=raw.split(b'\t',1);mode,kind,oid=meta.decode().split();name=path.decode()
        if name.startswith('ARCHIVE_'):entries[name]=(mode,oid)
    entries.update({r['path']:(r['mode'],r['oid']) for r in catalog if r['published']})
    note=f'''# 最新存档：原生接入负结果与公开信号诊断

来源结果提交 {SOURCE}；原冻结3c437c6；只读审计修复冻结33fcb95。
父存档{PARENT}，普通快进，无强推、合并或大blob研究历史推送。

结论：原生接入资格未成立。一次完成54例真实MetaWorld执行：5207控制步、
2754全部重置、1403035物理帧、4747实际固定策略查询；新拟合/训练/LLM
API均0。冻结bank0从当前公开历史发出14 PRE RBF+14 POST神经选择，
真实选择被保存并实际采用。模型12次VALIDATE8、2次CONTINUE、0次MOVE；
4例提前结束无选择。完整神经MOVE→测量→POST纠正→尾段链路0，不能
把强制参考MOVE或全体成功算作该验收通过；没有换折、调参、补样重采。

原冻结审计逐步重建54例后，汇总程序键的set不能JSON规范化，软件失败。
原源码/失败/查询全部保留；另提交只读v2冻结，只改键比较为排序列表，
输出到新目录，不追认原资格通过。补充核验54例、18强制整轨迹对、36
共同前缀对、9隐藏条件对（7活查询+2双方提前结束）通过；14非默认
模型程序、10真实命令差；v1/v2解压查询SHA一致。共享旧宏/NumPy，
不称独立物理重模拟或不同机构。信息/预算/连续性/权重违规均0。

三个程序均18/18成功。模型平均截止损失79.722222，旧/强制参考各
104.777778。净改善451步中的418步来自边界64组避开固定MOVE；参考
只是工程路径覆盖，不是强任务基线。完整配对：较差2、较好7、相同9，
不利严重度219步，改善670步；push变化+218、door变化+1均保留。
不据此宣布算法收益、模型适用性资格、安全保证、创新或CCF A完成。

源TRAIN只读648例、536实际未来窗口、134唯一过去、18443逐步行；
72例边界前结束、40例获取结束不补零。独立标量核对270860字段，
统计另核对9310字段。E=U+D-C中组均值E .354468、U .811668、D
.491179、C .948379；以命令能量U替代E的平均相对L2误差3.429837，
不支持简单命令能量解释，也不证明剩余误差有唯一物理来源。
完整任务×条件×边界×获取×率及9源组均保留；旧六项比较和TEST
统计SHA不变，旧ARX/响应模型/FULL-MASK等负结果不改。

新增23接入数组测试+2纯键回归，连同2158源码绑定旧检查=2183唯一；
重复开发运行不增数，旧六张量另列。编译、依赖、源码绑定全仓秘密、
新暂存字节基本/补充秘密、差异、Git/磁盘实际字节均检查。原始gzip
5文件12093579字节，7个≤4MiB分片已实际恢复/CRC/JSON核对，原件及
新恢复副本保留。准备错误、格式失败和原审计软件失败均留档。

本分支按既定类型/大小规则排除原始.jsonl.gz和.bin分片；克隆此紧凑
分支不含完整原始日志、普通完整研究历史或恢复副本。完整54例结果、
全部配对/分格、导出模型、图形、代码、来源及恢复索引均发布，不按
成功或失败排除。源TRAIN物理与源训练/独立复算费用另列，不免费化。

中文报告 reports/learned_acquisition_native_v1_zh.md。
潜在A主线仍须具体可证伪机制、廉价固定程序/重加权/完整成本风险等
强参考、独立自身时序历史及最终资格；GAUGE已有候选逆命令不确定性
惩罚，MDE/Residual RL/OCCAM/Poke等路线均需对照。本轮负结果封存，
不直接启动大批新采集，不把软件通过或改进弱参考当作论文贡献。

来源树{len(catalog)}文件、发布{sum(r['published'] for r in catalog)}个。
ARCHIVE_FILE_CATALOG_LEARNED_NATIVE_20261027.json登记来源Git对象、
字节和SHA。新发布实际字节扫描；相同对象复用已核验哈希与扫描。
'''
    extras={'ARCHIVE_LATEST.md':note.encode('utf-8'),
        'ARCHIVE_FILE_CATALOG_LEARNED_NATIVE_20261027.json':(json.dumps(cache_receipt,ensure_ascii=False,indent=2)+'\n').encode('utf-8'),
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
    commit=git('commit-tree',tree,'-p',PARENT,data=b'Archive native qualification negative result 2c50164; 54 actual runs, zero LLM\n').decode().strip()
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

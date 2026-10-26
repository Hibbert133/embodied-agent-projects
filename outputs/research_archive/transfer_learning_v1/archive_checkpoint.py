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
PARENT='c1339e2126d34f8e10953c1a8acb9bc33ca7edb4'
SOURCE='bb19bd7b2e9eabd668bda9266601e2c843bd1ca9'


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
    baseline_path=ROOT/'outputs/research_archive/state_coupled_design_v1/catalog.json'
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
    build=Path(r'C:/Users/Administrator/Documents/ChatGPT/robotic agent/research_archive_build_transfer_learning_20261026_bb19bd7');build.mkdir(exist_ok=False)
    entries={}
    # Keep the previous archival metadata as historical records, not a new source claim.
    for raw in git('ls-tree','-r','-z',PARENT).split(b'\0'):
        if not raw:continue
        meta,path=raw.split(b'\t',1);mode,kind,oid=meta.decode().split();name=path.decode()
        if name.startswith('ARCHIVE_'):entries[name]=(mode,oid)
    entries.update({r['path']:(r['mode'],r['oid']) for r in catalog if r['published']})
    note=f'''# 最新阶段存档：纠正后适用性辅助学习（旧TRAIN开发）

来源为已检查本地结果 {SOURCE}，父存档 {PARENT}；普通快进，无强推/合并。
科学实现/配置/测试/独立审计先在7a8c4c5提交，再执行一次固定预算拟合。
分类TRAIN_ONLY_POSTHOC_COMPONENT_DEVELOPMENT；旧TRAIN9组54单元，三折
训练集重叠，不是新独立人口、真实部署或最终资格。CAL/TEST未用于学习评价。

五个同权限学习版本：直接完整成本MSE、直接SPO+、经验误差重加权、
条件误差辅助SPO+及joint辅助SPO+；全公开因果历史旁路均保留。
全部12固定程序、20学习程序及1728次受支持事实重放选择完整保存。
15个风险/辅助神经拟合共15000次SGD、15个绑定固定receiver的前置RBF拟合；
独立实现再15个神经拟合15000次SGD及15个lstsq复算，完整预算分别计费。
新增环境/重置/控制步/物理帧、策略查询、机器人种子、响应/逆模型、底层
策略训练及在线LLM API均0。旧TRAIN来源648次、77563步、33048全部重置、
16911815帧另列，不将离线重放视作免费物理数据或新物理部署。

JOINT两阶段54/54成功，平均完整截止损失86.425926；直接SPO96.037037，
经验重加权96.092593，条件误差95.166667。最低固定均值86.851852。
严格全人口均值开发必要条件满足，但相对最低固定程序仅少23总步/
0.425926平均步；九组仅组4改善，四组变差、四组相同，收益高度集中。
这不证明独立任务收益、机制因果或算法新颖性，不授权大规模新采集。
不能仅用成功54/54作为研究目标完成；应先独立冻结匹配辅助正则等消融。

全部失败和不利选择、18分格/组统计、32控制、全部末步模型/训练记录及
预测缺失均保留。joint预测误差没有全面胜出，历史未覆盖质量约.765。
参数合法、当前预测及完整任务收益分别评价；没有安全或稳定保证。
独立复算5562160数值字段、152224标签字段通过，最大参数差约1.02e-14；
网络/训练/特征主入口禁用，另实现反向微分；仍共享NumPy，非独立机构审计。
24新数组测试加来源绑定2115旧测试=2139唯一检查，重复开发检查不重复计数。
依赖/编译/全仓秘密/新实际索引字节/差异/Git与磁盘字节检查通过。
首次图例拥挤的图和修复记录保留，最终PNG/SVG经实际查看。

中文报告reports/correction_transfer_learning_v1_zh.md，冻结协议及查新表包含
MDE、Residual RL、OCCAM、GAUGE、Poke and Strike、TOM、SF、VaGraM、SPO。
辅助未来特征及任务导向损失都有已有路线；未声称本轮论文创新，CCF A未完成。
原A1、FULL/MASK、ARX、响应模型及全部负结果/六项比较保持不变。

来源树共{len(catalog)}文件，发布{sum(r['published'] for r in catalog)}个。
ARCHIVE_FILE_CATALOG_TRANSFER_LEARNING_20261026.json列出所有已提交来源路径、
大小、Git对象和SHA-256。新学习记录/30末步模型/结果全量发布，旧大型原始
物理.jsonl.gz、二进制分片、恢复副本及完整普通历史仍在本地，克隆此分支
不包含它们；按类型/大小排除，不按成败。相同Git对象复用此前检查，新增
发布对象实际读取扫描。未推送超大普通历史，也未删除、改写或合并历史。
'''
    extras={'ARCHIVE_LATEST.md':note.encode('utf-8'),
        'ARCHIVE_FILE_CATALOG_TRANSFER_LEARNING_20261026.json':(json.dumps(cache_receipt,ensure_ascii=False,indent=2)+'\n').encode('utf-8'),
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
    commit=git('commit-tree',tree,'-p',PARENT,data=b'Archive TRAIN-only auxiliary correction-transfer learning bb19bd7; no new physics or LLM\n').decode().strip()
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

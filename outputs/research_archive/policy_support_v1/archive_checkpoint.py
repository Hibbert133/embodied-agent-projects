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
PARENT='ea8fe4e9e0601885238d607bf59c0b80ea4e3db0'
SOURCE='6fe16168807e9ae29b1a4fa44c77fadc64a162e4'


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
    baseline_path=ROOT/'outputs/research_archive/learned_native_v1/catalog.json'
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
    build=Path(r'C:/Users/Administrator/Documents/ChatGPT/robotic agent/research_archive_build_policy_support_20261027_6fe1616');build.mkdir(exist_ok=False)
    entries={}
    # Keep the previous archival metadata as historical records, not a new source claim.
    for raw in git('ls-tree','-r','-z',PARENT).split(b'\0'):
        if not raw:continue
        meta,path=raw.split(b'\t',1);mode,kind,oid=meta.decode().split();name=path.decode()
        if name.startswith('ARCHIVE_'):entries[name]=(mode,oid)
    entries.update({r['path']:(r['mode'],r['oid']) for r in catalog if r['published']})
    note=f'''# 最新存档：廉价固定程序的事实相容性与未知后缀界

来源结果{SOURCE}，冻结769ad2f；父存档{PARENT}，普通快进，无强推/合并。
上一轮原生资格失败保留：模型MOVE链0，原审计软件失败及其只读补充通过
均未改写。本轮全部是事后只读描述，不新增环境/重置/控制步/物理帧/
机器人种子、模型加载/NN或RBF推理/拟合/策略训练或在线LLM。

来源完整54轨迹、18单元、3组；12固定程序=3动作×4原率。主/独立各648
来源程序尝试，汇总216单元程序。逐条比较所有4维float32字节，完全相同
才释放该步已有响应；首差之后永不消费反馈，不拼接或伪造未执行状态。
同单元三来源初始native/Python/RNG witness相同，相容前缀/完整结果一致。
固定模拟器、相同外生扰动/噪声的确定性一致性是假设，不是实机普遍因果保证。

主参考固定VALIDATE8/.125有15/18完整事实相容支持、3未知。已支持损失973，
三未知均在组0、最长前缀24，分别保留[25,500]，完整总界[1048,2473]、
均界[58.222222,137.388889]，相对模型79.722222差界[-21.5,+57.666667]。
没有证明学习模型优于该廉价程序，也没有证明两者总体等价。边界32/64的
两组共12单元全部与固定主参考相容；15支持中包含4例决策前成功，不把
它们称主动适应或新增部署成功。两个CONT/.5和VAL8/.5程序物理等价，
不是两个独立算法。完整12程序的范围均跨越模型均值，未按结果选最佳。

648来源尝试198全匹配、450首差未知；不是198新成功/450实际失败。未知
后缀只给[k+1,500]，无结果补零或成功抄用。主旧固定actor与独立动态actor
强制固定选择、独立读取/struct字节比较/独立PI公式核验全部通过。共享
TaskMemory和MOVE宏已披露，不称独立物理重模拟或不同机构审计。
各26822次CPU固定政策查询，合计53644；主释放28348缓存响应，不是新物理
步。独立26822次PI公式核验。主90.695673秒、独立115.772913秒。

19新数组测试加2183源码绑定旧检查=2202唯一；旧六张量另列，重复开发不
增数。编译、依赖、全仓秘密与实际索引补充扫描、普通/暂存差异和Git/
磁盘字节通过。完整648尝试、216界、12程序/3组、未知案例、原始哈希、
源码、图形和独立复算全发布。新文件均<1MiB，无新大记录需分片。

中文报告reports/correction_policy_support_v1_zh.md。有限界不是置信区间，
不是新off-policy算法、部署资格、总体收益、新颖性或CCF A完成。MDE/TOM/
OCCAM/GAUGE/Residual RL/Poke等强参考继续保留；新读PRC、日志replay和
ICML2024无覆盖部分识别进一步限制贡献主张，未移植其保证或冒称复现。
下一步仍需可证伪机制、同权限强组合参考和独立自身时序历史，不能换折/
加样救旧bank0、重开ARX/F20或按旧结果调阈值。完整研究目标仍活跃。

来源树{len(catalog)}文件，发布{sum(r['published'] for r in catalog)}。按已定
类型/大小规则保留此前选择，旧原始.jsonl.gz和.bin分片/恢复副本不在
紧凑克隆中，留在本地；不按成败筛除。ARCHIVE_FILE_CATALOG_POLICY_SUPPORT_
20261027.json登记全部来源对象/大小/SHA，新发布对象实际读取/秘密扫描。
'''
    extras={'ARCHIVE_LATEST.md':note.encode('utf-8'),
        'ARCHIVE_FILE_CATALOG_POLICY_SUPPORT_20261027.json':(json.dumps(cache_receipt,ensure_ascii=False,indent=2)+'\n').encode('utf-8'),
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
    commit=git('commit-tree',tree,'-p',PARENT,data=b'Archive fixed-program support bounds 6fe1616; zero new physics or LLM\n').decode().strip()
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

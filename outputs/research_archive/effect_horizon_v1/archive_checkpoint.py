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
PARENT='2a0f4aea1f2271deaed124f1ff1987f01386f582'
SOURCE='39727830189cfb9ce63ac8aa167f3fb8d171f53a'


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
    baseline_path=ROOT/'outputs/research_archive/effect_learning_v1/catalog.json'
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
    build=Path(r'C:/Users/Administrator/Documents/ChatGPT/robotic agent/research_archive_build_effect_horizon_20261027_3972783');build.mkdir(exist_ok=False)
    entries={}
    # Keep the previous archival metadata as historical records, not a new source claim.
    for raw in git('ls-tree','-r','-z',PARENT).split(b'\0'):
        if not raw:continue
        meta,path=raw.split(b'\t',1);mode,kind,oid=meta.decode().split();name=path.decode()
        if name.startswith('ARCHIVE_'):entries[name]=(mode,oid)
    entries.update({r['path']:(r['mode'],r['oid']) for r in catalog if r['published']})
    note=f'''# 最新存档：纠正后真实连续窗口的时间尺度诊断

来源结果{SOURCE}，冻结e5a3c3c；父存档{PARENT}，普通快进，无强推/合并。
全部新增分析为事后描述性，不是入口多步预测、部署收益、模型资格或创新。
旧成对上下文负结果、原生FAILED/MOVE链0、ARX/F20/旧响应版本保持关闭。

仅旧A1 TRAIN648轨迹，9组/54单元/162获取节点，四率共972对；六个固定
窗口1/2/4/8/16/32登记5832行、2214面板、1944全任务条件时点获取率对窗格。
4373完整窗口，其余缺失有原因；不延长成功端点、不把短窗口补成长窗、不
补零。每H完整窗口803/803/772/755/680/560，各自全分母仍972；人口随H变。

从共同首分歧前状态，比较两个实际末端位置差与实际后续XY发送命令差之和。
三参考0、名义和、冻结留组全局矩阵。H1须匹配原803保存结果。H>1未来
命令仅评价端事后读取，接口拒绝ENTRY_FORECAST；不伪造未执行状态。
一步矩阵RMSE0.006971mm，32步16.869430mm；后者只有560对，不能当同人口
趋势或唯一延迟证据。H2仍803对，但Z/夹爪至少一处float32字节差的加权
比例61.626%；没有度量幅度或因果影响，不据此识别唯一错误原因。

主与独立各9冻结权重读取、4373矩阵评价、8746零/名义参考计算；主25.348秒、
独立24.397秒。主窗口/面板/来源组装/首差数学禁用后，独立struct首差、
标量累计、矩阵方向、完整行/面板/组权重核对通过；共享旧解析/容差已披露。
新环境/重置/控制步/帧/种子/固定政策查询/拟合/在线LLM均0。旧来源648次/
77563步/33048重置/16911815帧、旧36+36拟合只列历史费用。

12新增数组测试和2216源码绑定旧项合计2228唯一，旧六张量另列；两次开发
测试均0拟合/物理/API。编译、依赖、全仓秘密/索引补充扫描、普通/暂存
差异、实际Git/磁盘字节通过。中文报告reports/correction_effect_horizon_v1_zh.md。
全部5832行、2214面板、1944格、缺失与负结果、图形/复算/来源SHA保留。
首次图形标题间距版本保留；文字澄清曾触发exclusive回执FileExistsError，
首失败与修改前文件保留，v2只修复展示元数据，科学分析没有重跑。

此诊断禁止从局部一步误差直接跳到连续纠正资格，也禁止从事后实际输入
条件检查跳到入口预测。MIAC rho-POMDP、任务相关最优实验设计及原MDE/
Residual RL/OCCAM/GAUGE/Poke/TOM等限制新颖性，不能把状态影响/任务加权
改名为新方法。仍需具体机制、同权限强参考、独立自身历史完整成本优势
和消融；未解锁新采集，完整CCF A目标仍活跃。

来源树{len(catalog)}文件，发布{sum(r['published'] for r in catalog)}。保留既有
类型/大小选择，不按成败筛选；原始.jsonl.gz/.bin分片/恢复副本仍留本地。
新windows约5.005MB，全部新科学文件均小于8MiB并发布。完整来源对象/
SHA/大小/是否发布见ARCHIVE_FILE_CATALOG_EFFECT_HORIZON_20261027.json。
'''
    extras={'ARCHIVE_LATEST.md':note.encode('utf-8'),
        'ARCHIVE_FILE_CATALOG_EFFECT_HORIZON_20261027.json':(json.dumps(cache_receipt,ensure_ascii=False,indent=2)+'\n').encode('utf-8'),
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
    commit=git('commit-tree',tree,'-p',PARENT,data=b'Archive factual effect horizon diagnosis 3972783; zero new physics or LLM\n').decode().strip()
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

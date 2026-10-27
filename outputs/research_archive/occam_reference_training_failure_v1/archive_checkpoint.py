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
PARENT='05978abfa00e2e1d25a246005918269d7fc39b74'
SOURCE='62e17a50cee6c25c8b71f701eb7c993c5b4dcf22'


def git(*args,data=None,env=None):
    return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT,input=data,env=env)


def scan(data,name):
    if (name.startswith(('outputs/controller_agreement/','outputs/policy_mode_diagnostic/','outputs/occam_performance_core/','outputs/occam_window_host/','outputs/occam_reference_train/')) and name.endswith('.gz')) or (name.startswith('outputs/episode_seed_inventory/') and name.endswith('inventory.json.gz')) or name in ('outputs/graybox_response/freeze_validation_v1/seed_scope.json.gz','outputs/graybox_qualification/freeze_validation_v2/ownership_scope.json.gz'):data=gzip.decompress(data)
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
    baseline_path=ROOT/'outputs/research_archive/occam_reference_training_freeze_v1/catalog.json'
    baseline=io.read(baseline_path);io.require(baseline['integrity']=='PASSED' and not baseline.get('credential_findings',[]),'audited prior catalog')
    old={r['path']:r for r in baseline['files']};cache={r['oid']:r for r in old.values()}
    scanned={r['oid'] for r in old.values() if r['published']};catalog=[];read_bytes=0;reused=0;new_scans=0
    proc=subprocess.Popen(['git','cat-file','--batch'],cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE)
    try:
        for raw in git('ls-tree','-r','-l','-z',SOURCE).split(b'\0'):
            if not raw:continue
            meta,path=raw.split(b'\t',1);mode,kind,oid,size=meta.decode().split();name=path.decode('utf-8');size=int(size)
            io.require(kind=='blob','plain source blobs only')
            allowed=size<=8*1024**2 and (not name.endswith(('.jsonl.gz','.bin')) or name in allowed_parts or (name.startswith(('outputs/controller_agreement/','outputs/policy_mode_diagnostic/','outputs/occam_performance_core/','outputs/occam_window_host/','outputs/occam_reference_train/')) and name.endswith('.jsonl.gz'))) and not any(p=='.env' or p.startswith('.env.') for p in Path(name).parts)
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
    build=Path(r'C:/Users/Administrator/Documents/ChatGPT/robotic agent/research_archive_build_occam_train_failure_20261028_62e17a50cee6');build.mkdir(exist_ok=False)
    entries={}
    # Keep the previous archival metadata as historical records, not a new source claim.
    for raw in git('ls-tree','-r','-z',PARENT).split(b'\0'):
        if not raw:continue
        meta,path=raw.split(b'\t',1);mode,kind,oid=meta.decode().split();name=path.decode()
        if name.startswith('ARCHIVE_'):entries[name]=(mode,oid)
    entries.update({r['path']:(r['mode'],r['oid']) for r in catalog if r['published']})
    note=f'''# 最新归档：独立表现参考v1在原生接口失败，已关闭

本地来源62e17a50cee6c25c8b71f701eb7c993c5b4dcf22，父归档05978abfa00e2e1d25a246005918269d7fc39b74。科学采集/训练未完成，不得使用v1种子
重跑或把该记录说成OCCAM/元学习任务负结果。CCF A完整目标仍未完成。

adf4521冻结、f77e36b执行。第一NATIVE环境工厂的reset意图携带phase=
GOAL_GENERATION，与案例头phase=NATIVE冲突，归属保护在原重置委托前拒绝。
真实费用：1工厂尝试未返回、1生命周期reset尝试/0完成，0控制步/0物理帧，
0科学模型训练/在线滤波/在线LLM。只完成准备和一次失败子进程，非零工厂尝试
与耗时单列。TRAIN未开放，无成功率/截止损失/预测误差，未启动案例不填500。

部分日志、失败案例、清单、退出码和原源码全部保留，684个分配逐项登记。
只读抽取冻结归属函数+真实内存JsonJournal验证18个命名冲突，不执行环境。
示意cohort/phase分离可保存二者，外来seed/cohort仍拒绝；不是已部署新版本。
原32项检查没覆盖真正生命周期接口，4项新诊断明确弥补分析证据，共2558唯一。
新增科学训练/物理0，软件构造Adam仍2次；不把测试通过冒称机器人集成通过。

完整中文报告reports/occam_reference_training_failure_v1_zh.md。修复需保留归属
保护、补生命周期到收集器头的集成测试，另冻实现/审计/预算和全新未用未预留
人口。当前所有v1分配/预留关闭，不自动重采或开始TRAIN。科学CAL/独立自身
时序完整任务比较、强参考/消融与新获取决策机制均未完成。

普通快进、无强推合并或历史删除；旧大记录/恢复/失败保留，省略目录保持。

完整本地源树{len(catalog)}项，发布{sum(r["published"] for r in catalog)}项；完整省略目录保留。
'''
    extras={'ARCHIVE_LATEST.md':note.encode('utf-8'),
        'ARCHIVE_FILE_CATALOG_OCCAM_TRAIN_FAILURE_20261028.json':(json.dumps(cache_receipt,ensure_ascii=False,indent=2)+'\n').encode('utf-8'),
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
    commit=git('commit-tree',tree,'-p',PARENT,data=b'Archive closed technical native acquisition failure and zero-interaction namespace diagnosis; no trained model\n').decode().strip()
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

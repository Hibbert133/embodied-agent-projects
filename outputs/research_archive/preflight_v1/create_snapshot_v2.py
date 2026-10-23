"""Create a separate archival commit without changing the active checkout/index."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,subprocess,sys
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
from scripts.check_tracked_secrets import find_secret_rule
OUT=Path(__file__).parent
BRANCH='codex/archive-20261023-information-release-v2'


def git(*args,input=None,env=None):
    return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT,input=input,env=env)


def main():
    audit=json.loads((OUT/'snapshot_blob_catalog_v2.json').read_text(encoding='utf-8'));assert audit['integrity']=='PASSED' and not audit['credential_findings']
    assert not git('diff','--cached','--name-only').strip()
    original_head=git('rev-parse','HEAD').decode().strip();original_status=git('status','--porcelain','--untracked-files=no')
    source=audit['source_commit'];parent=git('rev-parse','origin/main').decode().strip();selected=[p for p in audit['all_source_file_catalog'] if p['published']]
    build=Path(r'C:/Users/Administrator/Documents/ChatGPT/robotic agent/research_archive_build_20261023_v2');build.mkdir(exist_ok=False)
    catalog=dict(source_local_commit=source,archive_scope='COMPLETED_AUDITED_SNAPSHOT_WITH_LARGE_DATA_CATALOG',
        original_history_not_rewritten=True,all_local_raw_data_retained=True,selection='source tree at the completed commit; exclude raw jsonl.gz, binary parts, env files and files above8MiB',
        files=audit['all_source_file_catalog'])
    commits=git('log','--format=%H%x09%P%x09%aI%x09%s',source,'--not','--remotes=origin').decode().splitlines()
    note=f'''# 已验证研究快照存档：2026-10-23

这是截至本地提交 `{source}` 的单独存档分支，不是主分支合并。
它保存完整代码、协议、报告、可容纳的模型/结果表/图片，以及全部源文件的哈希目录。
当前尚未冻结的信息释放学习代码不在这个已完成快照内。

原始本地历史有三个超过 GitHub 单文件限制的对象，不能直接推送。
因此本分支以已有远程 main `{parent}` 为父建立快照，未改写、删除或重置本地历史。
未包含的逐步大记录、二进制分片和超过8MiB的工件仍完整保存在原项目及恢复目录。
`ARCHIVE_FILE_CATALOG_20261023.json` 标明每个文件是否在此分支、字节数、Git对象ID与SHA-256。
这些大记录目前只在本地；不能声称克隆这个分支就获得了全部实验数据或原始本地提交对象。

已完成阶段包括全部历史失败与负结果的报告，以及最新信息释放软件原型。
最新原型冻结 eb01a32，交付2b91c1f；30项新测试、独立构造审计通过，旧1954项源码绑定测试复用。
它没有新机器人训练/任务收益，不能作为 CCF A 目标完成证据。请从 reports/ 下中文报告阅读完整限制。

发布选择针对文件种类和大小，不按研究结果好坏筛选。秘密扫描仅针对实际发布字节，
原大文件完整字节哈希已登记；此次并未声称扫描了未发布的全部历史文本。
'''
    extras={'ARCHIVE_SNAPSHOT_20261023.md':note.encode('utf-8'),
        'ARCHIVE_FILE_CATALOG_20261023.json':(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n').encode('utf-8'),
        'ARCHIVE_LOCAL_COMMITS_20261023.json':(json.dumps(dict(local_source_commit=source,commits=commits),ensure_ascii=False,indent=2)+'\n').encode('utf-8')}
    for name in ('scan_snapshot.py','create_snapshot_v2.py','outgoing_inventory.json','snapshot_selection.json','snapshot_blob_catalog_v2.json'):
        extras['outputs/research_archive/preflight_v1/'+name]=(OUT/name).read_bytes()
    expected_paths={r['path'] for r in json.loads((OUT/'snapshot_selection.json').read_text(encoding='utf-8'))['selected']}
    assert {r['path'] for r in selected}==expected_paths
    entries={r['path']:(r['mode'],r['oid']) for r in selected};extra_sha={}
    for name,data in extras.items():
        text=data.decode('utf-8');assert find_secret_rule(text) is None and not any(p.search(text) for p in EXTRA.values()),'new archive metadata scan'
        if name.endswith('.py'):compile(data,name,'exec')
        oid=git('hash-object','-w','--stdin',input=data).decode().strip();entries[name]=('100644',oid);extra_sha[name]=hashlib.sha256(data).hexdigest()
    archive_environment=os.environ.copy();archive_environment['GIT_INDEX_FILE']=str(build/'snapshot.index')
    git('read-tree','--empty',env=archive_environment)
    records=b''.join((mode+' '+oid+'\t'+name).encode('utf-8')+b'\0' for name,(mode,oid) in sorted(entries.items()))
    git('update-index','-z','--index-info',input=records,env=archive_environment)
    tree=git('write-tree',env=archive_environment).decode().strip()
    message='Archive audited research snapshot through 2b91c1f with full large-file catalog\n'
    commit=git('commit-tree',tree,'-p',parent,input=message.encode()).decode().strip()
    git('update-ref','refs/heads/'+BRANCH,commit,'0'*40)
    actual={}
    for item in git('ls-tree','-r','-z',commit).split(b'\0'):
        if not item:continue
        meta,path=item.split(b'\t',1);mode,kind,oid=meta.decode().split();assert kind=='blob';actual[path.decode('utf-8')]=(mode,oid)
    assert actual==entries and git('rev-parse','HEAD').decode().strip()==original_head and git('status','--porcelain','--untracked-files=no')==original_status
    assert not git('diff','--cached','--name-only').strip()
    receipt=dict(integrity='PASSED',archive_branch=BRANCH,archive_commit=commit,archive_tree=tree,archive_parent=parent,source_local_commit=source,
        source_selected_files=len(selected),snapshot_files=len(entries),selected_source_bytes=sum(r['bytes'] for r in selected),
        omitted_source_files=audit['omitted_files'],extra_metadata_sha256=extra_sha,ordinary_worktree_index_and_head_unchanged=True,
        original_history_and_raw_data_retained=True,push_performed=False,utc=datetime.now(timezone.utc).isoformat())
    with (OUT/'local_snapshot_receipt_v2.json').open('x',encoding='utf-8') as f:json.dump(receipt,f,ensure_ascii=False,indent=2)
    print({k:receipt[k] for k in ('integrity','archive_branch','archive_commit','snapshot_files','ordinary_worktree_index_and_head_unchanged')},flush=True)


if __name__=='__main__':main()

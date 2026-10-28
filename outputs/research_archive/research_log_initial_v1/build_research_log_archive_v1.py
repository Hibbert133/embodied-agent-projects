from pathlib import Path
import sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
source=io.git('rev-parse','HEAD');parent='7b9cd18ec23bcf204475c30fd2af30beb9a80125'
assert io.git('diff-tree','--no-commit-id','--name-only','-r',source).splitlines()==['Research_Log.md']
out=ROOT/'outputs/research_archive/research_log_initial_v1';out.mkdir(exist_ok=False)
template=ROOT/'outputs/research_archive/occam_training_partial_failure_v2'
s=(template/'archive_checkpoint.py').read_text(encoding='utf8')
for old,new in (("PARENT='ee1162c775c3e54f94b78c9d595ced211c2a5c91'","PARENT='"+parent+"'"),
    ("SOURCE='3759e0e425ddb49e3d199abee1e2c95a494c91e0'","SOURCE='"+source+"'"),
    ('outputs/research_archive/occam_reader_freeze_v3/catalog.json','outputs/research_archive/occam_training_partial_failure_v2/catalog.json'),
    ('research_archive_build_occam_train_failure_v2_20261028_3759e0e425dd','research_archive_build_research_log_v1_20261028_'+source[:12]),
    ('ARCHIVE_FILE_CATALOG_OCCAM_TRAIN_FAILURE_V2_20261028.json','ARCHIVE_FILE_CATALOG_RESEARCH_LOG_V1_20261028.json'),
    ('Archive closed incomplete training allocation and bounded-stream zero-interaction failure diagnosis','Archive append-only Chinese research log and verified historical phase receipts')):
    assert old in s,old;s=s.replace(old,new)
i=s.index('def scan_all_record_parts():');j=s.index('def main():',i)
s=s[:i]+'''def scan_all_record_parts():
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
    return allowed,dict(strategy='reuse seven actual Git stream recoveries only after exact Git object identity for every index, part and collection completion',
        prior_archive_commit=PARENT,prior_catalog_sha256=hashlib.sha256(baseline_bytes).hexdigest(),unchanged_git_objects=bindings,
        indices=prior['decoded_record_parts']['indices'],new_recovery_or_physics=False)


'''+s[j:]
i=s.index("    note=f'''");j=s.index('    extras={',i)
note='''# 阶段研究日志已建立

来源{SOURCE}，父归档{PARENT}。根目录Research_Log.md采用北京时间，阶段完成、
检查并核对push后追加日期、任务、结果、来源及下一目标，保留历史条目。
初始三条由已核实的2026-10-28阶段归档回执补记，不冒充完整项目历史。
正在实现的资源软件资格代码未冻结，未纳入本快照。

上一轮失败结论、原始记录、全部分片和恢复副本保持原样。本次无新环境、
拟合、训练或在线LLM。原有7流/28分片实际Git恢复证明，仅在逐一核对全部
索引、分片及采集完成文件Git对象完全相同后复用；没有宣称重新恢复。
只做普通快进，不强推、合并或删除原始历史。CCF A研究目标仍未完成。

完整本地源树{len(catalog)}项，发布{sum(r["published"] for r in catalog)}项；完整省略目录保留。
'''
s=s[:i]+"    note=f'''"+note+"'''\n"+s[j:]
compile(s,'archive_checkpoint.py','exec');(out/'archive_checkpoint.py').write_text(s,encoding='utf8',newline='\n')
p=(template/'push_archive.py').read_text(encoding='utf8').replace('outputs/research_archive/occam_training_partial_failure_v2','outputs/research_archive/research_log_initial_v1')
(out/'push_archive.py').write_text(p,encoding='utf8',newline='\n')
print(dict(source=source,parent=parent),flush=True)

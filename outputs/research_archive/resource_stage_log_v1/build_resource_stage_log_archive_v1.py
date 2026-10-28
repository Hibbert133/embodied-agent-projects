from pathlib import Path
import sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
source='b0f0e5586140852fd771c31700131af1e619dd3f';parent='a6e9fe67f20f480829e0fcf44e9269ff23364d8a'
assert io.git('rev-parse','HEAD')==source
names=io.git('diff-tree','--no-commit-id','--name-only','-r',source).splitlines()
assert len(names)==19 and 'Research_Log.md' in names and all(n=='Research_Log.md' or n.startswith('outputs/research_archive/occam_resource_software_failure_v2/') for n in names)
out=ROOT/'outputs/research_archive/resource_stage_log_v1';out.mkdir(exist_ok=False)
template=ROOT/'outputs/research_archive/occam_resource_software_failure_v2';s=(template/'archive_checkpoint.py').read_text(encoding='utf8')
for a,b in (("PARENT='a903d6dc98097c716673a7b23e5be17e99bbd3bd'","PARENT='"+parent+"'"),
    ("SOURCE='ada1bad9ef9255f9824280108923ba49e07d8c78'","SOURCE='"+source+"'"),
    ("baseline_path=ROOT/'outputs/research_archive/occam_resource_software_failure_v1/catalog.json'","baseline_path=ROOT/'outputs/research_archive/occam_resource_software_failure_v2/catalog.json'"),
    ('research_archive_build_occam_resource_failure_v2_20261028_ada1bad9ef92','research_archive_build_resource_stage_log_v1_20261028_'+source[:12]),
    ('ARCHIVE_FILE_CATALOG_RESOURCE_FAILURE_V2_20261028.json','ARCHIVE_FILE_CATALOG_RESOURCE_STAGE_LOG_V1_20261028.json'),
    ('Archive closed resource v2 Windows version query failure, exact records and stage log','Archive append-only dated stage log and verified resource v2 archival receipts')):
    assert a in s,a;s=s.replace(a,b)
i=s.index("    note=f'''");j=s.index('    extras={',i)
note='''# 阶段研究日志追加与归档回执

来源{SOURCE}，父归档{PARENT}。Research_Log.md现有按北京时间排序的历史
补记及两轮资源软件阶段，均在对应push核对后追加，记录日期、任务、结果、
来源和下一阶段目标；原条目保留。最新研究阶段为软件v2未通过：7启动、
1未启动，Windows可选ver子进程被禁止。完整负结果和原始stderr已发布。
本次仅发布阶段日志/回执，没有新实现、实验、机器人交互、拟合或在线LLM。
原TRAIN及预留仍关闭，完整软件/原生/研究资格均未冒充完成。

后继先独立冻结进程内系统版本回退并验证软件契约；之后才有原生collector
集成、连续性、新独立分配及科学训练。完整任务收益、强参考/消融、具体
获取机制区别及CCF A仍未完成。根目录日志持续追加，不覆盖旧阶段。

历史7流/28分片的实际恢复证明在全部相关Git对象相同时复用，不声称重跑。
原历史/记录/恢复副本保留，普通快进，无强推或合并。
完整本地源树{len(catalog)}项，发布{sum(r["published"] for r in catalog)}项；完整省略目录保留。
'''
s=s[:i]+"    note=f'''"+note+"'''\n"+s[j:]
compile(s,'archive_checkpoint.py','exec');(out/'archive_checkpoint.py').write_text(s,encoding='utf8',newline='\n')
p=(template/'push_archive.py').read_text(encoding='utf8').replace('outputs/research_archive/occam_resource_software_failure_v2','outputs/research_archive/resource_stage_log_v1')
(out/'push_archive.py').write_text(p,encoding='utf8',newline='\n');print(source,flush=True)

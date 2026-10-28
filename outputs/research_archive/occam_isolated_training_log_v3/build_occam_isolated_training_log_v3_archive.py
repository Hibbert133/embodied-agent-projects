from pathlib import Path
import sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
source='c92356173d9e99dada69da6a032f880a4f763259';parent='587128a167e0a4ea909072134693aa33efd5468f'
assert io.git('rev-parse','HEAD')==source
names=io.git('diff-tree','--no-commit-id','--name-only','-r',source).splitlines();assert len(names)==26 and 'Research_Log.md' in names
out=ROOT/'outputs/research_archive/occam_isolated_training_log_v3';out.mkdir(exist_ok=False)
template=ROOT/'outputs/research_archive/occam_isolated_training_freeze_v3';s=(template/'archive_checkpoint.py').read_text(encoding='utf8')
for before,after in (("PARENT='ad5570adb15507cba2e20e185a1ab76f4e798db7'","PARENT='"+parent+"'"),
    ("SOURCE='fbcc0fe9cd7577aa283a9cf334df22505852489b'","SOURCE='"+source+"'"),
    ("baseline_path=ROOT/'outputs/research_archive/resource_qualification_stage_log_v1/catalog.json'","baseline_path=ROOT/'outputs/research_archive/occam_isolated_training_freeze_v3/catalog.json'"),
    ('research_archive_build_occam_isolated_freeze_v3_20261028_fbcc0fe9cd75','research_archive_build_occam_isolated_log_v3_20261028_'+source[:12]),
    ('ARCHIVE_FILE_CATALOG_OCCAM_ISOLATED_FREEZE_V3_20261028.json','ARCHIVE_FILE_CATALOG_OCCAM_ISOLATED_LOG_V3_20261028.json')):
    assert before in s,before;s=s.replace(before,after)
i=s.index("    note=f'''");j=s.index('    extras={',i)
note='''# 隔离收集器v3阶段交付与日志

来源{SOURCE}，父归档{PARENT}。已核对冻结fbcc0fe的64项全部发布，再追加
根目录Research_Log并保留旧内容前缀字节。中文报告明确软件32新增/5回归
检查通过、累计2661来源绑定检查，不等于真实机器人或研究资格。源码／
协议／预算保持冻结；没有因日志或报告变化重跑仿真、拟合和优化器测试。

冻结后真实prepare一次因4GiB提交门拒绝，完整失败回执保存；未创建科学
manifest。一次最新只读观测提交余量约1.56GiB、磁盘约4.34GiB，仍不足。
未关闭其他应用、改分页文件或降低资源门。新增环境/控制步/物理帧/政策
查询/拟合/Adam/在线LLM均0。旧部分数据及分配保持关闭，不替代完整新TRAIN。
后续资源达门后才执行一次NATIVE36及双审计，再完整TRAIN648及双审计。
独立科学资格、自身时序历史完整任务收益、强对照/消融和CCF A仍未完成。

历史7流/28分片恢复证明只在全部相关Git对象一致后复用；原历史/原始大
记录/恢复副本保留，省略目录公开。普通快进，没有强推、合并或删除。
本地源树{len(catalog)}项，发布{sum(r["published"] for r in catalog)}项。
'''
s=s[:i]+"    note=f'''"+note+"'''\n"+s[j:]
s=s.replace('Archive frozen isolated native-case collector, full source bindings and zero-physics checks',
    'Archive isolated collector stage log, complete publication proof and rejected preflight')
compile(s,'archive_checkpoint.py','exec');(out/'archive_checkpoint.py').write_text(s,encoding='utf8',newline='\n')
push=(template/'push_archive.py').read_text(encoding='utf8').replace('outputs/research_archive/occam_isolated_training_freeze_v3','outputs/research_archive/occam_isolated_training_log_v3')
(out/'push_archive.py').write_text(push,encoding='utf8',newline='\n');print(source,flush=True)

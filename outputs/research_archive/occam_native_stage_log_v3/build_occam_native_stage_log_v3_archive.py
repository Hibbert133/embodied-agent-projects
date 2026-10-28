from pathlib import Path
import sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
source='cefff065163e79fbe81c4f26412999f139d6f8e5';parent='fe1bf36891de8f0b38d242fd77d81f966c7896da'
assert io.git('rev-parse','HEAD')==source
names=io.git('diff-tree','--no-commit-id','--name-only','-r',source).splitlines();assert len(names)==32 and 'Research_Log.md' in names
out=ROOT/'outputs/research_archive/occam_native_stage_log_v3';out.mkdir(exist_ok=False)
template=ROOT/'outputs/research_archive/occam_native_qualification_v3';s=(template/'archive_checkpoint.py').read_text(encoding='utf8')
for before,after in (("PARENT='e642553f55bf906e13b7fccf2e5163bc627f307a'","PARENT='"+parent+"'"),
    ("SOURCE='c49b4268eb4e739256fcd7e2d9b3a2fed976198f'","SOURCE='"+source+"'"),
    ("baseline_path=ROOT/'outputs/research_archive/occam_isolated_training_log_v3/catalog.json'","baseline_path=ROOT/'outputs/research_archive/occam_native_qualification_v3/catalog.json'"),
    ('research_archive_build_occam_native_v3_20261028_c49b4268eb4e','research_archive_build_occam_native_log_v3_20261028_'+source[:12]),
    ('ARCHIVE_FILE_CATALOG_OCCAM_NATIVE_V3_20261028.json','ARCHIVE_FILE_CATALOG_OCCAM_NATIVE_LOG_V3_20261028.json')):
    assert before in s,before;s=s.replace(before,after)
i=s.index("    note=f'''");j=s.index('    extras={',i)
note='''# 原生资格v3阶段日志与已核对归档

来源{SOURCE}，父归档{PARENT}。已核对Native25项阶段文件全部发布，再追加
根目录Research_Log，旧条目前缀字节不变。Native36全部完整及双审计通过，
35任务成功/1失败保留；18对共同获取后完整状态一致，295个实际窗口。
只有1组与边界16，不是独立预测/任务收益或CCF A证明。

原始499文件/10片实际Git恢复、91106行gzip扫描及原有负结果完整保存。
Native实际5399步/1836全部reset/944995帧，实际及审计政策查询各5083，
科学拟合/Adam/在线LLM均0。研究日志快照TRAIN140/648仅用于运维，完整
新TRAIN及双审计前不学习，不用旧188项填充或挑选有利子集。

本次仅整理报告/回执/日志，冻结科学代码/参数/种子不变；正在运行的
TRAIN没有纳入本次静态记录包。旧7流28片及Native10片证明均经Git对象
一致性绑定复用，不重复收费或冒称新恢复。下一步完整TRAIN后学习标准
参考，再制定并执行独立自身历史科学资格、完整强对照任务收益及消融。

源树{len(catalog)}项，发布{sum(r["published"] for r in catalog)}项，原始大文件
和恢复副本留本地，省略目录公开；普通快进，无强推合并。
'''
s=s[:i]+"    note=f'''"+note+"'''\n"+s[j:]
s=s.replace('Archive native qualification with full raw record bundle, all failures and actual Git recovery','Archive native stage Research_Log, verified full record publication and ongoing TRAIN checkpoint')
compile(s,'archive_checkpoint.py','exec');(out/'archive_checkpoint.py').write_text(s,encoding='utf8',newline='\n')
push=(template/'push_archive.py').read_text(encoding='utf8').replace('outputs/research_archive/occam_native_qualification_v3','outputs/research_archive/occam_native_stage_log_v3')
(out/'push_archive.py').write_text(push,encoding='utf8',newline='\n');print(source,flush=True)

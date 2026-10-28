from pathlib import Path
import sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
source='6d5919fc1764745bf6b9c69569c8959b9faab291';parent='ddc7a759f79e992fc229c47f1b095415f891932e'
assert io.git('rev-parse','HEAD')==source
names=io.git('diff-tree','--no-commit-id','--name-only','-r',source).splitlines()
assert len(names)==20 and 'Research_Log.md' in names and 'docs/research/correction_scope_contribution_review_v5_zh.md' in names
out=ROOT/'outputs/research_archive/resource_qualification_stage_log_v1';out.mkdir(exist_ok=False)
template=ROOT/'outputs/research_archive/occam_resource_qualification_v3';s=(template/'archive_checkpoint.py').read_text(encoding='utf8')
for a,b in (("PARENT='7e27e365896bbc4b3eda7333476fc8fdc5e2d9fb'","PARENT='"+parent+"'"),
    ("SOURCE='74d672beadc830e3cb8e4205bab30689d31c0beb'","SOURCE='"+source+"'"),
    ("baseline_path=ROOT/'outputs/research_archive/resource_stage_log_v1/catalog.json'","baseline_path=ROOT/'outputs/research_archive/occam_resource_qualification_v3/catalog.json'"),
    ('research_archive_build_resource_qualification_v3_20261028_74d672beadc8','research_archive_build_resource_qualification_log_v1_20261028_'+source[:12]),
    ('ARCHIVE_FILE_CATALOG_RESOURCE_QUALIFICATION_V3_20261028.json','ARCHIVE_FILE_CATALOG_RESOURCE_QUALIFICATION_LOG_V1_20261028.json'),
    ('Archive eight qualified resource v3 software contracts, exact records and independent audit','Archive dated resource qualification log, verified receipts and applicability contribution review v5')):
    assert a in s,a;s=s.replace(a,b)
i=s.index("    note=f'''");j=s.index('    extras={',i)
note='''# 资源资格阶段日志与A贡献复核v5

来源{SOURCE}，父归档{PARENT}。根目录Research_Log.md已在v3阶段push核对后
追加北京时间、任务/结果、完整费用、来源和下一目标，旧条目保留。软件8项
及独立审计通过，43模拟检查，累计2629唯一来源检查；v1/v2失败仍完整保存。
本次只补文档/回执，没有新机器人交互、拟合、训练或在线LLM。

docs/research/correction_scope_contribution_review_v5_zh.md新增CPC与递归选择
校准近邻及阅读边界，保留全部旧比较。政策风险/支持/历史分布条件未建立，
限幅和校准门本身不新；完整风险/DR、独立自身历史任务收益及消融仍必需。
科学门提交余量仍不足，原生collector/连续性及新科学分配另行冻结后资格。
旧TRAIN/预留仍关闭，没有把软件通过称为研究或CCF A目标完成。

历史7流/28分片的实际恢复证明仅在全部相关Git对象一致后复用，不声称
重新恢复。原历史、原始记录、失败及恢复副本保留，普通快进，无强推合并。
完整本地源树{len(catalog)}项，发布{sum(r["published"] for r in catalog)}项；完整省略目录保留。
'''
s=s[:i]+"    note=f'''"+note+"'''\n"+s[j:]
compile(s,'archive_checkpoint.py','exec');(out/'archive_checkpoint.py').write_text(s,encoding='utf8',newline='\n')
p=(template/'push_archive.py').read_text(encoding='utf8').replace('outputs/research_archive/occam_resource_qualification_v3','outputs/research_archive/resource_qualification_stage_log_v1')
(out/'push_archive.py').write_text(p,encoding='utf8',newline='\n');print(source,flush=True)

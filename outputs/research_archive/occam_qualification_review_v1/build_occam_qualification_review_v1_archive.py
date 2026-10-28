from pathlib import Path
import sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
source='d6b38a11d5ccc6c4f253feb4b0a85fd5f7f2683f';parent='16de5ce6fe97e25240ac34be6b3585d4fe71740e'
assert io.git('rev-parse','HEAD')==source and len(io.git('diff-tree','--no-commit-id','--name-only','-r',source).splitlines())==8
out=ROOT/'outputs/research_archive/occam_qualification_review_v1';out.mkdir(exist_ok=False)
template=ROOT/'outputs/research_archive/occam_native_stage_log_v3';s=(template/'archive_checkpoint.py').read_text(encoding='utf8')
for before,after in (("PARENT='fe1bf36891de8f0b38d242fd77d81f966c7896da'","PARENT='"+parent+"'"),
    ("SOURCE='cefff065163e79fbe81c4f26412999f139d6f8e5'","SOURCE='"+source+"'"),
    ("baseline_path=ROOT/'outputs/research_archive/occam_native_qualification_v3/catalog.json'","baseline_path=ROOT/'outputs/research_archive/occam_native_stage_log_v3/catalog.json'"),
    ('research_archive_build_occam_native_log_v3_20261028_cefff065163e','research_archive_build_occam_qual_review_v1_20261028_'+source[:12]),
    ('ARCHIVE_FILE_CATALOG_OCCAM_NATIVE_LOG_V3_20261028.json','ARCHIVE_FILE_CATALOG_OCCAM_QUAL_REVIEW_V1_20261028.json')):
    assert before in s,before;s=s.replace(before,after)
i=s.index("    note=f'''");j=s.index('    extras={',i)
note='''# 独立资格要求与来源核对

来源{SOURCE}，父归档{PARENT}。新增文献/源码义务清单，分开数值、完整训练、
数学导出、前瞻预测、完整自身历史任务收益和研究贡献。原文OCCAM与当前
受限参考的差异、离线支持集MSE及两种预测方差/创新方差的口径均明确。
共同协方差缩放是标准代数边界，不称新理论；既有训练损失不充当校准证明。

仅文档和只读来源检查，源码/配置/种子/参数/预算未变，未新增科学人口、
拟合、求解、优化或在线LLM。AST检查器首次键查找错误保留，修复检查器，
不增加单位测试计数。TRAIN同一原分配继续运行，前缀不作为完整训练或
模型选择证据；科学CAL/QUAL和完整任务收益仍未开放或证明，CCF A未完成。

全部旧失败及原始数据保留，旧7流/28片和Native499文件/10片的实际恢复
证明经原Git对象身份核对复用，未重做或重复收费。源树{len(catalog)}项，
发布{sum(r["published"] for r in catalog)}项；省略目录公开，普通快进，无强推合并。
'''
s=s[:i]+"    note=f'''"+note+"'''\n"+s[j:]
s=s.replace('Archive native stage Research_Log, verified full record publication and ongoing TRAIN checkpoint','Archive independent qualification obligations and source review without changing ongoing TRAIN')
compile(s,'archive_checkpoint.py','exec');(out/'archive_checkpoint.py').write_text(s,encoding='utf8',newline='\n')
push=(template/'push_archive.py').read_text(encoding='utf8').replace('outputs/research_archive/occam_native_stage_log_v3','outputs/research_archive/occam_qualification_review_v1')
(out/'push_archive.py').write_text(push,encoding='utf8',newline='\n');print(source,flush=True)

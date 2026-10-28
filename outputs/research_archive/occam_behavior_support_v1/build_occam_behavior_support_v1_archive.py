"""Archive the completed read-only support audit, not live QUAL records."""
from pathlib import Path
import sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis.response_qualification_io_v1 import git
source='d764e27f5a03edef5a5379455df567b298f87cea';parent='e41a358311a7d2d33e4be1bc25a60f2853ff6c4d'
assert git('rev-parse','HEAD')==source
out=ROOT/'outputs/research_archive/occam_behavior_support_v1';out.mkdir(exist_ok=False)
template=ROOT/'outputs/research_archive/occam_qualification_freeze_v1'
s=(template/'archive_checkpoint.py').read_text(encoding='utf8')
for before,after in (("PARENT='dbe64c7503e2a61c999932fd092f6699b9ae9a0f'","PARENT='"+parent+"'"),
    ("SOURCE='7abaec83b0854f099d6f13f308cc8cd552f50e2b'","SOURCE='"+source+"'"),
    ("baseline_path=ROOT/'outputs/research_archive/occam_complete_training_v3/catalog.json'","baseline_path=ROOT/'outputs/research_archive/occam_qualification_freeze_v1/catalog.json'"),
    ('research_archive_build_occam_qualification_freeze_v1_20261028_7abaec83b085','research_archive_build_occam_behavior_support_v1_20261028_'+source[:12]),
    ('ARCHIVE_FILE_CATALOG_OCCAM_QUALIFICATION_FREEZE_V1_20261028.json','ARCHIVE_FILE_CATALOG_OCCAM_BEHAVIOR_SUPPORT_V1_20261028.json')):
    assert before in s,before;s=s.replace(before,after)
i=s.index("    note=f'''");j=s.index('    extras={',i)
note='''# 完整 TRAIN 行为支持检查：零新增交互

来源{SOURCE}，父归档{PARENT}。旧TRAIN全部648轨迹、3296实际窗口、18组、
108完整分层；保留106空轨迹及457短窗口。24新合成检查、独立Fraction／
前缀比和组统计复算通过，主概率／统计函数在独立审计时禁用；首次测试
作用域错误、源码与日志全部保留。全部源字节、秘密、索引／磁盘核对通过。

RANDOM_WINDOW与BLOCK_FIXED在工作随机化模型下的动作核不能统一按每窗
1/4处理。212轨迹实际改变过增益；448非空轨迹的假想隐藏混合联合因子
与统一均匀因子不同。这是描述及条件代数，不是完整路径密度、合法OPE
权重、外生性、任务收益、安全或新颖性证据。原源费用保留，新环境／拟合／
模型预测／滤波更新／在线LLM全0。查新v6记录PRC／CDT理论条件及适用边界。

正在进行的独立自身历史QUAL不在本归档；其冻结输入／代码均核对不变，
不能用这份支持分析挑选接收者或更改科学门。原数据／分片／恢复副本与
全部负结果继续保留，旧实际Git恢复证明按精确对象身份核对复用。
当前源树{len(catalog)}项，发布{sum(r["published"] for r in catalog)}项；
省略源有完整大小／SHA目录。原生资格、任务优势、新获取机制和CCF A未完成。
'''
s=s[:i]+"    note=f'''"+note+"'''\n"+s[j:]
s=s.replace('Archive frozen own-history reference qualification with complete strong controls and dual audits','Archive complete TRAIN behavior-support audit without new interactions or off-policy value claims')
compile(s,'archive_checkpoint.py','exec');(out/'archive_checkpoint.py').write_text(s,encoding='utf8',newline='\n')
push=(template/'push_archive.py').read_text(encoding='utf8').replace('outputs/research_archive/occam_qualification_freeze_v1','outputs/research_archive/occam_behavior_support_v1')
(out/'push_archive.py').write_text(push,encoding='utf8',newline='\n')
print(source,flush=True)

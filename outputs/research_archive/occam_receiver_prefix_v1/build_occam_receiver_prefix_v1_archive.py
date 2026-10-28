"""Archive the complete TRAIN-only receiver-prefix audit, never live QUAL."""
from pathlib import Path
import sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis.response_qualification_io_v1 import git
source='4fb646a93bac29fcf2b6422c60a562dad7bddf0d';parent='e3b43c1ddaca52a4a9def9cea14f90856fea9ba2'
assert git('rev-parse','HEAD')==source
out=ROOT/'outputs/research_archive/occam_receiver_prefix_v1';out.mkdir(exist_ok=False)
template=ROOT/'outputs/research_archive/occam_qualification_native_v1';s=(template/'archive_checkpoint.py').read_text(encoding='utf8')
for before,after in (("PARENT='5359d3656dd16fecc27c839b8b378bb8f8cfa8eb'","PARENT='"+parent+"'"),
    ("SOURCE='1104977105f268baf28b2b53ed1a3f8436c50459'","SOURCE='"+source+"'"),
    ("baseline_path=ROOT/'outputs/research_archive/occam_behavior_support_v1/catalog.json'","baseline_path=ROOT/'outputs/research_archive/occam_qualification_native_v1/catalog.json'"),
    ('research_archive_build_occam_qualification_native_v1_20261028_1104977105f2','research_archive_build_occam_receiver_prefix_v1_20261029_'+source[:12]),
    ('ARCHIVE_FILE_CATALOG_OCCAM_QUALIFICATION_NATIVE_V1_20261028.json','ARCHIVE_FILE_CATALOG_OCCAM_RECEIVER_PREFIX_V1_20261029.json')):
    assert before in s,before;s=s.replace(before,after)
i=s.index("    note=f'''");j=s.index('    extras={',i)
note='''# 四个冻结接收者的旧来源前缀：完整只读交付

来源{SOURCE}，父归档{PARENT}。先提交软件／输入／20合成检查冻结，再对
全部TRAIN648来源×四接收者＝2592份分析、432完整分层、18独立组复算。
首个不同增益后不再提交旧反馈或后续query，全部接收者任务结果字段缺失。

每方法542非空来源：META两程序各493条首次分歧／49条全部观测增益相同，
ERM各484／58；各106无决定。bank本来就由这些TRAIN训练，因此只是来源内
描述，不是独立前瞻误差、统计覆盖、离策略价值或自身部署。选择相同也
不自动证明所有低层命令／物理状态相同；原602／46仅为来源成功／失败。

独立dense／标量后验／记录／分层复算通过，主provider／前向／更新／回放／
统计函数在审计禁用。严格公开特征共享已披露。主3027声明／12108候选、
440分析端更新／求解、44148eig，独立同样声明／候选／标量更新、0求解。
全阶段1790.990秒<冻结1800秒。另两次合成输入冻结bank计时共2声明／8候选，
0更新，30eig按代码复算而非直接计数，含cProfile且与主墙钟重叠，单列。
新环境／reset／帧／固定策略查询／神经训练／批量拟合／seed／在线LLM0。

实际Git／索引／磁盘字节、秘密／补充秘密和差异检查通过；原数据、分片、
恢复副本和全部负结果不改。旧133个有实际恢复证明的记录分片按精确Git
身份核对复用，归档没有新采集或新复原。原科学源码／bank／主比较不变。
查新v7及补充只限定已知方法边界，不宣称创新；首窗口全候选诊断仍是
DESIGN_ONLY，待完整QUAL与统计完整性通过后另冻reader，当前无其结果。
仍运行的QUAL不在本归档。完整风险强参考、独立任务收益、新获取机制和
消融仍待完成；本次检查不完成CCF A目标。当前源树{len(catalog)}项，发布
{sum(r["published"] for r in catalog)}项；省略源有完整大小／SHA目录。
'''
s=s[:i]+"    note=f'''"+note+"'''\n"+s[j:]
s=s.replace('Archive complete audited own-history Native174 records with actual Git and archive-only restorations','Archive complete TRAIN receiver-prefix support with independent arithmetic, missing task outcomes and full costs')
compile(s,'archive_checkpoint.py','exec');(out/'archive_checkpoint.py').write_text(s,encoding='utf8',newline='\n')
push=(template/'push_archive.py').read_text(encoding='utf8').replace('outputs/research_archive/occam_qualification_native_v1','outputs/research_archive/occam_receiver_prefix_v1')
(out/'push_archive.py').write_text(push,encoding='utf8',newline='\n');print(source,flush=True)

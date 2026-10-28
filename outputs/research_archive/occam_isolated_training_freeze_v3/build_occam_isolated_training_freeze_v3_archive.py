from pathlib import Path
import sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
source='fbcc0fe9cd7577aa283a9cf334df22505852489b';parent='ad5570adb15507cba2e20e185a1ab76f4e798db7'
assert io.git('rev-parse','HEAD')==source
names=io.git('diff-tree','--no-commit-id','--name-only','-r',source).splitlines();assert len(names)==64
out=ROOT/'outputs/research_archive/occam_isolated_training_freeze_v3';out.mkdir(exist_ok=False)
template=ROOT/'outputs/research_archive/resource_qualification_stage_log_v1';s=(template/'archive_checkpoint.py').read_text(encoding='utf8')
for before,after in (("PARENT='ddc7a759f79e992fc229c47f1b095415f891932e'","PARENT='"+parent+"'"),
    ("SOURCE='6d5919fc1764745bf6b9c69569c8959b9faab291'","SOURCE='"+source+"'"),
    ("baseline_path=ROOT/'outputs/research_archive/occam_resource_qualification_v3/catalog.json'","baseline_path=ROOT/'outputs/research_archive/resource_qualification_stage_log_v1/catalog.json'"),
    ('research_archive_build_resource_qualification_log_v1_20261028_6d5919fc1764','research_archive_build_occam_isolated_freeze_v3_20261028_'+source[:12]),
    ('ARCHIVE_FILE_CATALOG_RESOURCE_QUALIFICATION_LOG_V1_20261028.json','ARCHIVE_FILE_CATALOG_OCCAM_ISOLATED_FREEZE_V3_20261028.json')):
    assert before in s,before;s=s.replace(before,after)
i=s.index("    note=f'''");j=s.index('    extras={',i)
note='''# 隔离完整案例收集器v3软件冻结

本地来源{SOURCE}，父归档{PARENT}。实现一完整逻辑案例一进程，完整原生／
Python见证保留，任务内环境、RNG、噪声、时钟连续，费用／原始gzip字节／
进程回执独立审计。32新增数组与5读者回归全部通过，累计2661来源绑定检查。
首次失败日志、对应旧源码、预检与旧科学失败全部保留。编译、两个依赖环境、
秘密／差异和实际索引／磁盘／提交字节通过。没有真实native worker、环境
交互、政策查询、拟合、Adam或在线LLM；没有新科学manifest。

独立NATIVE36／TRAIN648、所有费用、故障闭合和公开训练边界已冻结，资源
提交门仍未达4GiB。软件契约不等于模型、任务或CCF A资格；旧部分188项不
用于训练，不重开旧分配。后续须NATIVE双审计、完整TRAIN双审计和另行资格。
研究A主线具体贡献、完整风险／DR等强对照及自身历史独立任务收益仍待建立。

历史7流/28分片实际恢复证明仅在所有相关Git对象完全一致后复用；原始大
记录及恢复副本保留本地，省略目录逐项公开。普通快进，无强推、合并或删除。
完整本地源树{len(catalog)}项，发布{sum(r["published"] for r in catalog)}项。
'''
s=s[:i]+"    note=f'''"+note+"'''\n"+s[j:]
s=s.replace('Archive dated resource qualification log, verified receipts and applicability contribution review v5',
    'Archive frozen isolated native-case collector, full source bindings and zero-physics checks')
compile(s,'archive_checkpoint.py','exec');(out/'archive_checkpoint.py').write_text(s,encoding='utf8',newline='\n')
push=(template/'push_archive.py').read_text(encoding='utf8').replace('outputs/research_archive/resource_qualification_stage_log_v1','outputs/research_archive/occam_isolated_training_freeze_v3')
(out/'push_archive.py').write_text(push,encoding='utf8',newline='\n')
print(source,flush=True)

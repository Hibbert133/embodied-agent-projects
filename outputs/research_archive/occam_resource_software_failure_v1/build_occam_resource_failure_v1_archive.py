from pathlib import Path
import sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
source='86294a578e8d94d2b410598f6a897b805e4f708b';parent='f735f259f6935a707cd95f41a9941b5abb417842'
assert io.git('rev-parse','HEAD')==source
out=ROOT/'outputs/research_archive/occam_resource_software_failure_v1';out.mkdir(exist_ok=False)
template=ROOT/'outputs/research_archive/research_log_initial_v1';s=(template/'archive_checkpoint.py').read_text(encoding='utf8')
for old,new in (("PARENT='7b9cd18ec23bcf204475c30fd2af30beb9a80125'","PARENT='"+parent+"'"),
    ("SOURCE='c55d0940384e645dc7aa98f95cc93a19ffa639dd'","SOURCE='"+source+"'"),
    ("baseline_path=ROOT/'outputs/research_archive/occam_training_partial_failure_v2/catalog.json'","baseline_path=ROOT/'outputs/research_archive/research_log_initial_v1/catalog.json'"),
    ('research_archive_build_research_log_v1_20261028_c55d0940384e','research_archive_build_occam_resource_failure_v1_20261028_'+source[:12]),
    ('ARCHIVE_FILE_CATALOG_RESEARCH_LOG_V1_20261028.json','ARCHIVE_FILE_CATALOG_RESOURCE_FAILURE_V1_20261028.json'),
    ('Archive append-only Chinese research log and verified historical phase receipts','Archive closed failed resource software qualification with all seven worker records and unstarted eighth')):
    assert old in s,old;s=s.replace(old,new)
i=s.index("    note=f'''");j=s.index('    extras={',i)
note='''# 资源软件资格v1失败交付

来源{SOURCE}，冻结196bcba0c88508c19b2fcae6b4fbf3f9e558df8a，父归档{PARENT}。
33项新增数组/假句柄检查通过；2586项来源绑定复用，共2619项。正式只运行
7个软件worker：前6项符合预期，第7项依赖导入被socket.gethostname误拦，
第8项未启动。全部负结果、回执/完整栈、资源及成本保存，已关闭不续接。
原始stderr按精确字节入Git；独立只读闭合审计不是完整软件资格通过。

无新环境、reset、控制步、物理帧、科学拟合、训练或在线LLM。一次科学
预检可提交余量2.10GiB低于4GiB，磁盘4.43GiB；科学采集未开放。
后继只可独立冻结修复版，不改旧数据、门槛或将未启动例贴为成功。
完整中文报告reports/occam_resource_qualification_v1_zh.md。

根目录Research_Log.md保留阶段历史；本阶段条目在核对本次push后追加。
未冻结的后继代码不发布。历史7流/28分片实际Git恢复证明在索引、完成及
所有分片Git对象逐一相同后复用，不宣称重新恢复；完整省略目录保留。
普通快进，无强推/合并/历史删除。工程资格不代表算法收益或CCF A贡献。

完整本地源树{len(catalog)}项，发布{sum(r["published"] for r in catalog)}项。
'''
s=s[:i]+"    note=f'''"+note+"'''\n"+s[j:]
compile(s,'archive_checkpoint.py','exec');(out/'archive_checkpoint.py').write_text(s,encoding='utf8',newline='\n')
p=(template/'push_archive.py').read_text(encoding='utf8').replace('outputs/research_archive/research_log_initial_v1','outputs/research_archive/occam_resource_software_failure_v1')
(out/'push_archive.py').write_text(p,encoding='utf8',newline='\n');print(source,flush=True)

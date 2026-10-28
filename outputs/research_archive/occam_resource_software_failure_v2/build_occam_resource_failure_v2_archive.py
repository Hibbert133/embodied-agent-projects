from pathlib import Path
import sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
source='ada1bad9ef9255f9824280108923ba49e07d8c78';parent='a903d6dc98097c716673a7b23e5be17e99bbd3bd'
assert io.git('rev-parse','HEAD')==source
out=ROOT/'outputs/research_archive/occam_resource_software_failure_v2';out.mkdir(exist_ok=False)
template=ROOT/'outputs/research_archive/occam_resource_software_failure_v1';s=(template/'archive_checkpoint.py').read_text(encoding='utf8')
for a,b in (("PARENT='f735f259f6935a707cd95f41a9941b5abb417842'","PARENT='"+parent+"'"),
    ("SOURCE='86294a578e8d94d2b410598f6a897b805e4f708b'","SOURCE='"+source+"'"),
    ("baseline_path=ROOT/'outputs/research_archive/research_log_initial_v1/catalog.json'","baseline_path=ROOT/'outputs/research_archive/occam_resource_software_failure_v1/catalog.json'"),
    ('research_archive_build_occam_resource_failure_v1_20261028_86294a578e8d','research_archive_build_occam_resource_failure_v2_20261028_'+source[:12]),
    ('ARCHIVE_FILE_CATALOG_RESOURCE_FAILURE_V1_20261028.json','ARCHIVE_FILE_CATALOG_RESOURCE_FAILURE_V2_20261028.json'),
    ('Archive closed failed resource software qualification with all seven worker records and unstarted eighth','Archive closed resource v2 Windows version query failure, exact records and stage log')):
    assert a in s,a;s=s.replace(a,b)
i=s.index("    note=f'''");j=s.index('    extras={',i)
note='''# 资源软件资格v2失败交付

来源{SOURCE}，冻结1b80c23e7abe8e150840323bd06393852b3c9ae7，父归档{PARENT}。
35项模拟检查（33重跑契约/2新增），累计2621唯一来源检查。v2正式7个软件
进程，前6项符合期望，第7项CPython可选ver版本查询试图创建后代而被
守卫阻止；第8项未启动。v2关闭不续接，不将失败改为通过。v1亦完整保留。
独立闭合审计、所有请求/回执/完整栈/原始stderr/PID/资源均保存；它不是
完整软件资格。两版累计14软件进程/约7.306秒主执行，无新机器人/拟合/API。

一次未来科学入口提交余量2.30GiB、磁盘4.43GiB，提交门仍未通过；科学
分配关闭。后继应先核对CPython本机版本回退并独立冻结，继续禁止后代
创建、连接及DNS。不弱化原见证/人口，不重开旧TRAIN，不将软件作CCF A贡献。
完整报告reports/occam_resource_qualification_v2_zh.md。

Research_Log.md已有历史及v1阶段；本阶段在核对此次push后追加。未冻结
后继代码未发布。历史7流/28分片实际恢复证明仅在全部索引/完成/分片Git
对象相同时复用，不声称新恢复。原历史/记录/恢复副本保留，普通快进。
完整本地源树{len(catalog)}项，发布{sum(r["published"] for r in catalog)}项。
'''
s=s[:i]+"    note=f'''"+note+"'''\n"+s[j:]
compile(s,'archive_checkpoint.py','exec');(out/'archive_checkpoint.py').write_text(s,encoding='utf8',newline='\n')
p=(template/'push_archive.py').read_text(encoding='utf8').replace('outputs/research_archive/occam_resource_software_failure_v1','outputs/research_archive/occam_resource_software_failure_v2')
(out/'push_archive.py').write_text(p,encoding='utf8',newline='\n');print(source,flush=True)

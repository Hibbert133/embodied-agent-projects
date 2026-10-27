"""Prepare compact completed engineering/research-review archive, no science run."""
from pathlib import Path
import sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
source=io.git('rev-parse','HEAD');parent='750b48e6f67f39f9dbb088dcb84af20cd3fce898'
assert io.read(ROOT/'outputs/episode_seed_inventory/delivery_validation_v2/complete.json')['integrity']=='PASSED'
out=ROOT/'outputs/research_archive/episode_seed_inventory_v2';out.mkdir(exist_ok=False)
s=(ROOT/'outputs/research_archive/history_response_v1/archive_checkpoint.py').read_text('utf8')
changes=(('import hashlib,json,os,subprocess,sys','import gzip,hashlib,json,os,subprocess,sys'),
    ("PARENT='2c1c246e97c6fdaa3b280727967c2777391bec44'","PARENT='"+parent+"'"),
    ("SOURCE='44cf501f479a17a04121dd21618dd540c51756c8'","SOURCE='"+source+"'"),
    ('outputs/research_archive/packet_structure_v1/catalog.json','outputs/research_archive/history_response_v1/catalog.json'),
    ('research_archive_build_history_response_20261027_44cf501f479a','research_archive_build_seed_inventory_20261027_'+source[:12]),
    ('ARCHIVE_FILE_CATALOG_HISTORY_RESPONSE_20261027.json','ARCHIVE_FILE_CATALOG_EPISODE_SEED_20261027.json'),
    ('Archive independent public-history response 44cf501f479a; zero online LLM','Archive seed inventory v2 and applicability review '+source[:12]+'; zero new physics or fits'),
    ('def scan(data,name):\n','def scan(data,name):\n    if name.startswith(\'outputs/episode_seed_inventory/\') and name.endswith(\'inventory.json.gz\'):data=gzip.decompress(data)\n'))
for old,new in changes:assert old in s,old;s=s.replace(old,new)
i=s.index("    note=f'''");j=s.index('    extras={',i)
note="""    note=f'''# 最新归档：环境种子登记修复与 A 主线机制复核

本地来源 {SOURCE}，父归档 {PARENT}。工程冻结8e3e8e4；本轮无新科学采集、
物理步／重置／帧、策略查询、模型拟合、机器人种子分配或在线LLM API。
修复嵌套区间内部／旧分区／保守包络／显式引用，独立迭代来源核验。
30项新增元数据测试通过，2318项源码绑定复用，总2348项唯一测试。
编译、依赖、秘密扫描与实际索引字节检查通过；四次开发失败记录保留。

正式只读两次查询604/605份输入、各34526条保守登记；未发现查询区间的
已登记冲突，但没有预留或授权新试验。原始JSON和实际恢复副本本地保留，
确定性gzip随本轮提交，并附恢复字节／SHA证明。仅保证声明的登记范围，
不能证明任意未登记代码未用种子；未来采集必须重新核验当时快照。

A“纠正后的适用性变化”是已选主线。查新加入GoBOED/AOPS/轨迹参数化
双重控制/策略相关模拟器/CPC等，淘汰普通加权、动作核、闭环展开或校准
幅度就算新贡献的说法。尚无通过审查的新学习机制，本轮不启动新采集。
旧HISTORY_KERNEL、FIR、A1、ARX/SS和全部其他失败/缺失结论保持；
独立完整任务优势、强参考、消融和CCF A目标都仍未完成。

中文报告 reports/episode_seed_inventory_v2_zh.md；机制复核
docs/research/correction_scope_mechanism_review_v2_zh.md。
本来源树{len(catalog)}项，发布{sum(r['published'] for r in catalog)}项；
沿用原逐路径选择，原始jsonl.gz、.bin和>8MiB文件不自动上传。
完整目录见 ARCHIVE_FILE_CATALOG_EPISODE_SEED_20261027.json；
不声称全部旧大数据已上传。普通快进，无强推、合并或删历史。
归档是留存，工程检查和查新均不计作机器人性能或论文贡献。
'''
"""
s=s[:i]+note+s[j:];compile(s,'archive_checkpoint.py','exec')
with (out/'archive_checkpoint.py').open('x',encoding='utf8',newline='\n') as f:f.write(s)
print(out/'archive_checkpoint.py')

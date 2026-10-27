"""Archive the completed freeze; the separate native process may keep running."""
from pathlib import Path
import sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
source='cf2712de2ed7f0eb6bba30cdc0d2cd363323a71c';parent='c4e126b3cea7873f0821b7721964fd9e0f80bd9a'
assert io.git('rev-parse','HEAD')==source and io.read(ROOT/'outputs/graybox_response/freeze_validation_v1/complete.json')['integrity']=='PASSED'
out=ROOT/'outputs/research_archive/graybox_freeze_v1';out.mkdir(exist_ok=False)
s=(ROOT/'outputs/research_archive/episode_seed_inventory_v2/archive_checkpoint.py').read_text('utf8')
for old,new in (("PARENT='750b48e6f67f39f9dbb088dcb84af20cd3fce898'","PARENT='"+parent+"'"),
    ("SOURCE='2bf53d0b9fa00fd211a6082dc94a26f124dfe467'","SOURCE='"+source+"'"),
    ('outputs/research_archive/history_response_v1/catalog.json','outputs/research_archive/episode_seed_inventory_v2/catalog.json'),
    ('research_archive_build_seed_inventory_20261027_2bf53d0b9fa0','research_archive_build_graybox_freeze_20261028_cf2712de2ed7'),
    ('ARCHIVE_FILE_CATALOG_EPISODE_SEED_20261027.json','ARCHIVE_FILE_CATALOG_GRAYBOX_FREEZE_20261028.json'),
    ('Archive seed inventory v2 and applicability review 2bf53d0b9fa0; zero new physics or fits','Archive frozen graybox reference collector cf2712de2ed7; no scientific outcome claim')):
    assert old in s,old;s=s.replace(old,new)
s=s.replace("if name.startswith('outputs/episode_seed_inventory/') and name.endswith('inventory.json.gz'):data=gzip.decompress(data)",
    "if (name.startswith('outputs/episode_seed_inventory/') and name.endswith('inventory.json.gz')) or name=='outputs/graybox_response/freeze_validation_v1/seed_scope.json.gz':data=gzip.decompress(data)")
i=s.index("    note=f'''");j=s.index('    extras={',i)
note="""    note=f'''# 最新归档：公开历史标准观测器收集协议冻结

来源本地 {SOURCE}，父归档 {PARENT}。本来源提交发生在新科学采集之前，
只包含数组观测器、独立数值实现及已验证的收集／训练／CAL／QUAL协议。
归档时另一个原生采集进程正在按此冻结运行；其未完成原始结果不在本快照。

32项新增／2376项源码哈希复用检查，总2408项唯一检查。编译、依赖、
完整已跟踪秘密扫描、实际索引BASIC/EXTRA扫描与逐字节核对通过。
开发中导入语法失败及审计集合类型错误均保留；构造测试费用单列。
数组组件28项检查和修正Y行先验方差的首轮记录也保留。

冻结新人口上限891次、82800控制步、45441全部重置、23134500物理帧。
新种子登记使用v2全面检查，三个确切自身注册文件例外及其哈希显式保存；
源census原始JSON本地保留，确定性gzip随本快照并验证实际解压字节。
零在线LLM API、无旧人口拟合、无任务尾部／逆控制／政策训练。

A“纠正后的适用性变化”保持。联合EKF、RLS/ARX、FIR均为标准强参考，
理想植物均值可写成ARX2；它们不是新获取算法。数值、预测与完整费用任务
收益分开验收，独立资格尚未结束，不宣称任何模型优势、安全或CCF A成果。
全部旧失败保留，不能用旧QUAL调参或事后换模型。

中文协议 docs/protocols/graybox_response_v1_zh.md；数组与ARX关系说明见
docs/research/graybox_observer_reference_v1_zh.md 和 graybox_arx_realization_v1_zh.md。
完整源树{len(catalog)}项，发布{sum(r['published'] for r in catalog)}项；
原始jsonl.gz、.bin和>8MiB沿已有规则留在本地，详见
ARCHIVE_FILE_CATALOG_GRAYBOX_FREEZE_20261028.json。未声称全部大记录在远端。
普通快进，无强推、合并或删历史；归档不计科学贡献。
'''
"""
s=s[:i]+note+s[j:];compile(s,'archive_checkpoint.py','exec');(out/'archive_checkpoint.py').write_bytes(s.encode('utf8'))
p=(ROOT/'outputs/research_archive/episode_seed_inventory_v2/push_seed_inventory_archive_v2.py').read_text('utf8').replace('outputs/research_archive/episode_seed_inventory_v2','outputs/research_archive/graybox_freeze_v1')
(out/'push_graybox_freeze_archive_v1.py').write_bytes(p.encode('utf8'));print(out/'archive_checkpoint.py')

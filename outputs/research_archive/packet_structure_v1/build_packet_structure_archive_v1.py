from pathlib import Path
import sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import packet_structure_sources_v1 as a
io=a.io;source=io.git('rev-parse','HEAD');parent='61e9865b6e0c1ee0f0c1ae360adb281cda41b1a4'
assert io.read(a.BASE/'result_validation_v1/complete.json')['integrity']=='PASSED'
out=ROOT/'outputs/research_archive/packet_structure_v1';out.mkdir(exist_ok=False)
s=(ROOT/'outputs/research_archive/paired_packet_v1/archive_checkpoint.py').read_text('utf8')
for old,new in (("PARENT='cc5926e7b5b24baa8d597905fbb458a6905a131a'","PARENT='"+parent+"'"),("SOURCE='5a24abfbb64528f9268fd17da68d4c983d7483c7'","SOURCE='"+source+"'"),
    ('outputs/research_archive/selective_coverage_v1/catalog.json','outputs/research_archive/paired_packet_v1/catalog.json'),
    ('research_archive_build_paired_packet_20261027_5a24abfbb645','research_archive_build_packet_structure_20261027_'+source[:12]),
    ('ARCHIVE_FILE_CATALOG_PAIRED_PACKET_20261027.json','ARCHIVE_FILE_CATALOG_PACKET_STRUCTURE_20261027.json'),
    ('Archive independent paired-packet response component 5a24abfbb645; zero online LLM','Archive exact packet structure diagnosis '+source[:12]+'; zero new physics or fits')):
    assert old in s,old;s=s.replace(old,new)
i=s.index("    note=f'''");j=s.index('    extras={',i)
note="""    note=f'''# 最新归档：三角色响应的事后结构诊断

来源本地结果 {SOURCE}，诊断冻结28744e2，父归档 {PARENT}。本轮零新增
环境创建/重置/控制步/帧/策略查询/模型拟合/模型预测/在线LLM API。
原864次包试验及FIR独立资格CLOSED_NEGATIVE保持，不救旧版本。

全部864案例/288家族，H1–16共4608槽位、23040保存模型槽位；3570次观测
分解、8950次数值保存预测分解。另一读者禁用主算式，用精确有理数核对
85830个量和29576个分组均值；非物理重仿真。两实现各再生224条旧确定性
噪声带、336000标量，各检查10721真实动作/原生更新，全部单列，不冒充
新独立样本。21项新/2265项源码复用检查，重复执行不另算新测试。

同入口线性命令类的偶响应表示下界，在QUAL完整三角色H16上约占保存FIR
MSE的0.706%，不能解释主要反对称残差。奇非线性仍可能存在，不能证明
只需线性状态条件或获得物理可识别性。QUAL完整H16的4个目标夹限家族均
在door，reach仍有大残差，不能把夹限当唯一原因。所有阶段/缺失保留。

这里是平方误差分解，不能替换原平均RMSE/1m缺失惩罚或推导完整任务收益。
固定刺激幅值的三次/一次特征共线是设计代数限制；共享动作无关反馈不改
同入口向量差，也不反驳已有反馈世界模型的绝对预测和控制收益。BLA/
非线性辨识、Feedback World Model以及MDE/OCCAM/GAUGE/TOM等已有研究，
本次数学与诊断不作算法创新或CCF A完成证据。新采集未解锁。

中文 reports/packet_structure_diagnosis_v1_zh.md。源成本864次/56801控制步/
44064全部重置/22316005帧及57+57求解仍是历史费用，未重复收费。原始
大表、8个4MiB内字节分片和真实恢复副本在本地保留。远端按原规则省略
gzip/二进制分片/>8MiB文件，原始大表也通过索引明确仅在本地，不声称
已全部上传。编译/依赖/实际索引秘密扫描/普通与暂存差异/提交后字节通过。

来源树 {len(catalog)}项，发布 {sum(r['published'] for r in catalog)}项，逐项
Git对象/SHA/大小/发布状态见ARCHIVE_FILE_CATALOG_PACKET_STRUCTURE_20261027.json。
普通快进，无强推/合并/删历史。归档为留存，不计科学贡献。
'''
"""
s=s[:i]+note+s[j:];compile(s,'archive_checkpoint.py','exec')
with (out/'archive_checkpoint.py').open('x',encoding='utf8',newline='\n') as f:f.write(s)
print(out/'archive_checkpoint.py')

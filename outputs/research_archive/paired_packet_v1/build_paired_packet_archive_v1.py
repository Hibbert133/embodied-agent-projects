"""Reuse the audited compact-tree engine, with new source/parent and honest scope."""
from pathlib import Path
import sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import paired_packet_io_v1 as a
io=a.io;source=io.git('rev-parse','HEAD');parent='cc5926e7b5b24baa8d597905fbb458a6905a131a'
assert io.read(a.BASE/'result_validation_v1/complete.json')['integrity']=='PASSED'
run=next(a.OUTPUT.glob('*/manifest.json')).parent;cost=io.read(run/'presentation/costs.json')['total'];decision=io.read(run/'presentation/research_decision.json')
out=ROOT/'outputs/research_archive/paired_packet_v1';out.mkdir(exist_ok=False)
s=(ROOT/'outputs/research_archive/selective_coverage_v1/archive_checkpoint.py').read_text('utf8')
for old,new in (("PARENT='736d54f16f44afe33886bbf1180ae364e9ede5f0'","PARENT='"+parent+"'"),("SOURCE='318e5ab0e93d4ed996435ee23eeebdd1d1fbceca'","SOURCE='"+source+"'"),
    ('outputs/research_archive/effect_horizon_v1/catalog.json','outputs/research_archive/selective_coverage_v1/catalog.json'),
    ('research_archive_build_selective_scope_20261027_318e5ab','research_archive_build_paired_packet_20261027_'+source[:12]),
    ('ARCHIVE_FILE_CATALOG_SELECTIVE_SCOPE_20261027.json','ARCHIVE_FILE_CATALOG_PAIRED_PACKET_20261027.json'),
    ('Archive exact selective coverage scope 318e5ab; zero new physics or LLM','Archive independent paired-packet response component '+source[:12]+'; zero online LLM')):
    assert old in s,old;s=s.replace(old,new)
i=s.index("    note=f'''");j=s.index('    extras={',i)
note="""    note=f'''# 最新归档：已知命令包响应差异组件

来源本地结果 {SOURCE}，科学冻结 bb74926，父紧凑归档 {PARENT}。
本次状态 @@STATUS@@。这是标准前向响应组件试验；绝对模型/逆控制/
完整任务收益和新颖获取机制仍未资格，CCF A目标保持未完成。

独立 SOFTWARE/TRAIN/CAL/QUAL 分配864次，上限80,640控制步、44,064全部
重置、22,435,200物理帧。实际执行 @@N@@ 次、@@STEPS@@ 步、@@RESETS@@
全部重置、@@FRAMES@@ 帧，工厂每次50次内部重置计费；失败/缺失保留。
科学主线性求解 @@SOLVES@@，独立增广最小二乘 @@LS@@。模型不参与控制，
在线LLM API=0。主预测在三角色任何包结果前保存，不用未知未来反馈动作。

三真实独立尝试同入口 ZERO/PLUS/MINUS，不捕获/恢复物理世界。仅已知
墙钟计时字段从配对Python语义哈希投影掉，完整原始哈希另存；在第一次
科学冻结提交/采集前发现修正，旧候选回执保留，37项新/2228项源码复用
检查。记录、数值拟合、统计各独立核对，未把补充共享调度重放当重仿真。

五项 ZERO/INSTANT/FIR/CENTERED_FIR/FREE_CAUSAL 全保留；中心化FIR是同数据
代数等价检查，非创新。CAL只选全局FIR或自由因果形式，权重不重训，先
锁定再QUAL。缺失端点罚1m，H8/H16完整人口为主，组bootstrap，三任务/
条件/获取/时间和全部失败见中文报告及机器表，不挑任务或补样。

报告 reports/paired_packet_response_v1_zh.md。配对输入响应/动态辨识已有
研究；该组件通过也不构成获取机制、纠正后适用性或任务改进证据。旧ARX/
GRU/SS/F20/A1/上下文与原生资格的负结果不重开。本地原始gzip、全部4MiB
分片及真实恢复副本保留；本远端按原规则省略gzip/二进制分片和>8MiB文件，
索引/来源大小/SHA说明它们仅在本地，不能宣称远端拥有全部原始数据。

来源树 {len(catalog)} 项，发布 {sum(r['published'] for r in catalog)} 项；
完整Git对象、SHA、大小与发布状态见 ARCHIVE_FILE_CATALOG_PAIRED_PACKET_20261027.json。
所有新增发布字节经秘密扫描，实际索引/磁盘及提交后对象核对。普通快进，
不强推、不合并、不删历史。归档是保存习惯，不计科学贡献。
'''
"""
for key,value in dict(STATUS=decision['status'],N=cost['executions'],STEPS=cost['control_steps'],RESETS=cost['all_resets'],FRAMES=cost['physical_frames'],SOLVES=cost['primary_scientific_ridge_solves'],LS=cost['independent_augmented_lstsq_solves']).items():note=note.replace('@@'+key+'@@',str(value))
s=s[:i]+note+s[j:];compile(s,'archive_checkpoint.py','exec')
with (out/'archive_checkpoint.py').open('x',encoding='utf8',newline='\n') as f:f.write(s)
print(out/'archive_checkpoint.py')

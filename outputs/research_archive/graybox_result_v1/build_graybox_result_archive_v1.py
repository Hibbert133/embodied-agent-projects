"""Publish the completed failed-run delivery and read-only numerical repair."""
from pathlib import Path
import sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
source=io.git('rev-parse','HEAD');assert source.startswith('e784794')
parent='1cae03ce34ec373675d02c1afb2d47c55697f6e3';out=ROOT/'outputs/research_archive/graybox_result_v1';out.mkdir(exist_ok=False)
s=(ROOT/'outputs/research_archive/graybox_freeze_v1/archive_checkpoint.py').read_text('utf8')
for old,new in (("PARENT='c4e126b3cea7873f0821b7721964fd9e0f80bd9a'","PARENT='"+parent+"'"),
    ("SOURCE='cf2712de2ed7f0eb6bba30cdc0d2cd363323a71c'","SOURCE='"+source+"'"),
    ('outputs/research_archive/episode_seed_inventory_v2/catalog.json','outputs/research_archive/graybox_freeze_v1/catalog.json'),
    ('research_archive_build_graybox_freeze_20261028_cf2712de2ed7','research_archive_build_graybox_result_20261028_'+source[:12]),
    ('ARCHIVE_FILE_CATALOG_GRAYBOX_FREEZE_20261028.json','ARCHIVE_FILE_CATALOG_GRAYBOX_RESULT_20261028.json'),
    ('Archive frozen graybox reference collector cf2712de2ed7; no scientific outcome claim','Archive graybox failed pre-qualification run and read-only audit repair; no model superiority claim')):
    assert old in s,old;s=s.replace(old,new)
i=s.index("    note=f'''");j=s.index('    extras={',i)
note="""    note=f'''# 最新归档：灰箱训练流水线失败交付与只读审计修复

来源本地 {SOURCE}，冻结cf2712d，失败交付5405cd4，父归档 {PARENT}。
实际459次执行、31017控制步、23409全部重置、11859585物理帧。
SOFTWARE、NOMINAL和TRAIN采集/记录审计通过；主训练9次求解、27次网格。
训练独立审计末尾在上下文退出前读取计数，触发KeyError，按冻结停止规则
终止原流程。CAL108与QUAL324均未开始，不能称为模型预测资格负结果。

修复v2写独立补充回执，未生成原流程的training/audit.json，不自动恢复采集。
两个完整生命周期回归测试通过（构造LS18次）。只读重建原27条名义和324条
训练执行及模型通过，追加独立LS9次、网格27次；连原失败审计共LS18/网格54。
模型SHA保持101030e545e92232b1855dc59eb77617025e56353786e4c10c2ae7922203927a。
补充数值重建不等于未知条件预测、完整任务收益、安全或算法创新。

32+2项新增、2376项旧源码绑定复用，共2410项唯一检查。编译、依赖、
源码绑定完整秘密扫描与新索引BASIC/EXTRA扫描、差异/字节核对通过。
原科学失败、开发失败以及交付日志CRLF归一化导致的一次字节检查失败保留；
传输属性修复后保持原始日志字节。全部13份原始数据/元数据已分片并实际
恢复，原件、分片和恢复副本均本地保留，没有重采、扩样、旧QUAL调参或API。

中文报告 reports/graybox_response_v1_zh.md；补充 reports/graybox_audit_repair_v2_zh.md。
A主线与CCF A目标保持；标准联合EKF/RLS/FIR不是新获取算法。后续须先独立
冻结尚未执行的资格入口及全部成本/失败处理，不能悄悄恢复原失败流程。

完整源树{len(catalog)}项，发布{sum(r['published'] for r in catalog)}项；
沿原规则省略原始jsonl.gz、.bin分片和>8MiB文件，逐项SHA、大小和发布状态
见 ARCHIVE_FILE_CATALOG_GRAYBOX_RESULT_20261028.json，不声称全部大记录在远端。
普通快进，无强推、合并或删历史；本轮零在线LLM API，归档不计科学贡献。
'''
"""
s=s[:i]+note+s[j:];compile(s,'archive_checkpoint.py','exec');(out/'archive_checkpoint.py').write_bytes(s.encode('utf8'))
p=(ROOT/'outputs/research_archive/graybox_freeze_v1/push_graybox_freeze_archive_v1.py').read_text('utf8').replace('outputs/research_archive/graybox_freeze_v1','outputs/research_archive/graybox_result_v1')
(out/'push_graybox_result_archive_v1.py').write_bytes(p.encode('utf8'));print(source)

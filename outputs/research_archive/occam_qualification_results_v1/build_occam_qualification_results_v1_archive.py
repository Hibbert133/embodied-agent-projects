"""Prepare a checked compact archive of completed qualification summaries."""
from pathlib import Path
import subprocess

ROOT = Path('C:/Users/Administrator/Desktop/embodied-agent-projects')
SOURCE = 'a2a4b921bf9a3127ffcf71505cfda24c98f63a0f'
PARENT = '4641010f67defc641b113c950a96aec275a2e83a'
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip() == SOURCE
out = ROOT / 'outputs/research_archive/occam_qualification_results_v1'
out.mkdir(exist_ok=False)
template = ROOT / 'outputs/research_archive/occam_costs_review_v1'
s = (template / 'archive_checkpoint.py').read_text(encoding='utf-8')
for before, after in [
    ("PARENT='89c1f0dfdfac50a85beb35533c0f141de336691f'", "PARENT='" + PARENT + "'"),
    ("SOURCE='017ba38e7c147cc88ac197218ef1bf69f391b3c6'", "SOURCE='" + SOURCE + "'"),
    ("baseline_path=ROOT/'outputs/research_archive/standard_dr_and_qual_delivery_tools_v1/catalog.json'", "baseline_path=ROOT/'outputs/research_archive/occam_costs_review_v1/catalog.json'"),
    ('research_archive_build_occam_costs_review_v1_20261029_017ba38e7c14', 'research_archive_build_occam_qualification_results_v1_20261029_' + SOURCE[:12]),
    ('ARCHIVE_FILE_CATALOG_OCCAM_COSTS_REVIEW_V1_20261029.json', 'ARCHIVE_FILE_CATALOG_OCCAM_QUALIFICATION_RESULTS_V1_20261029.json'),
    ('Archive complete qualification cost tools and conditional monitoring prior-art boundaries', 'Archive completed negative qualification, first-window diagnostics and full accounting summaries')
]:
    assert s.count(before) == 1, before
    s = s.replace(before, after)
i = s.index('def scan(data,name):')
j = s.index('def scan_all_record_parts():', i)
s = s[:i] + '''def scan(data,name):
    if name.endswith('.gz'):data=gzip.decompress(data)
    if b'\\0' not in data:
        text=data.decode('utf-8',errors='strict')
        io.require(find_secret_rule(text) is None and not any(p.search(text) for p in EXTRA.values()),'publication credential pattern '+name)


''' + s[j:]
marker = "SOURCE='" + SOURCE + "'"
summary = "\nQUAL_SUMMARY_GZIP={('outputs/occam_reference_qualification_v1/qualification_v1/occam_reference_qualification_v1_20261028T125131Z_7abaec83b085/'+phase+'/'+name) for phase in ('native','qual') for name in ('cases.jsonl.gz','prequential_windows.jsonl.gz')}"
s = s.replace(marker, marker + summary, 1)
before = "not name.endswith(('.jsonl.gz','.bin')) or name in allowed_parts or"
assert s.count(before) == 1
s = s.replace(before, "not name.endswith(('.jsonl.gz','.bin')) or name in allowed_parts or name in QUAL_SUMMARY_GZIP or")
i = s.index("    note=f'''")
j = s.index('    extras={', i)
note = '''# 独立资格负结果、首窗口诊断与完整成本：摘要归档

来源本地提交{SOURCE}，父归档{PARENT}。原一次性实验已经完成：
NATIVE174与QUAL1566，共1740次执行；99任务失败全部保留、未解决0。
数值／执行与预测资格通过，完整任务收益资格未通过。十项冻结主比较
七项满足、三项未满足；不挑选有利比较、改选主程序或追加样本。
主方法META_ADAPT__CONTINUE为51/54成功、86.500步损失；同前缀边界
后固定0.125秒为51/54、86.370。跨零区间不证明劣势，也不证明优越性。

主程序确有在线线性参数更新，神经特征权重和底层策略固定；在线LLM0。
完整费用为187405控制步、88740全部reset、45307025物理帧；历史NN
共同9000更新及全部来源费用单列。不能把窗口、FROZEN反馈、失败惩罚
或case总wall分别冒充神经预测、参数更新、物理步骤或隔离推断延迟。

首窗口事后描述登记全部1566，1296胶囊、162起点、216格；136可用、
26无首窗保留。META四候选MSE约0.000640，但组等权排序错误约0.361；
固定首窗与固定完整任务排序也有约0.337错误。不能唯一归因失败、
把固定程序结局贴给自适应后续，或据此训练／挑选旧QUAL后继机制。
独立诊断与显式accounting成本审计通过；旧v1读取失败及后续交付
大小／范围／换行检查失败、纠正说明均保留。所有事后分析新物理、
模型查询／拟合、episode种子及在线LLM0，当前接收者按负结果封存。

本次发布全部已提交统计、原报告CSV、两级审计、首窗口胶囊和成本
附录、来源／封存回执、精确种子元数据压缩副本及PNG／SVG，不是
完整QUAL原始轨迹归档。完整原始case事件／witness仍在源电脑本地，
不属于当前source Git树；元数据清单只有路径和字节，不能冒充原始
内容哈希或完整恢复证明。完整ZIP／数据分片／三种恢复尚待磁盘空间，
没有降低冻结空间门或删除旧记录／副本。case元数据和已执行预测窗
摘要不替代完整轨迹。旧133分片仅复用精确Git身份的历史恢复证明，
本次未重新恢复或采集。当前已提交源树{len(catalog)}项，发布
{sum(r["published"] for r in catalog)}项；对源树省略项记录完整大小与SHA。

源码1393及输入、原统计dccede3a…不变；测试／编译／依赖、秘密、
差异、实际索引／磁盘与提交字节证明保留。源码复用的测试不称新实验。
继续A方向仍需相对完整风险DR、重加权、同历史被动适应、MDE、OCCAM、
GAUGE、Poke和条件监测的可证伪机制差别及独立完整任务优势／消融。
目前没有合格新颖性或任务收益证据，CCF A目标未完成。
'''
s = s[:i] + "    note=f'''" + note + "'''\n" + s[j:]
compile(s, 'archive_checkpoint.py', 'exec')
(out / 'archive_checkpoint.py').write_text(s, encoding='utf-8', newline='\n')
push = (template / 'push_archive.py').read_text(encoding='utf-8')
before = 'outputs/research_archive/occam_costs_review_v1'
assert push.count(before) == 1
push = push.replace(before, 'outputs/research_archive/occam_qualification_results_v1')
compile(push, 'push_archive.py', 'exec')
(out / 'push_archive.py').write_text(push, encoding='utf-8', newline='\n')
print(dict(prepared_for_source=SOURCE, archive_parent=PARENT))

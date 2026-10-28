"""Archive two completed software-only phases; never the running QUAL prefix."""
from pathlib import Path
import subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects')
SOURCE=sys.argv[1];PARENT='517f41ce528d951963388e3d52530952253aa4a3'
assert len(SOURCE)==40 and all(c in '0123456789abcdef' for c in SOURCE)
assert subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0','rev-parse','HEAD'],cwd=ROOT).decode().strip()==SOURCE
out=ROOT/'outputs/research_archive/standard_dr_and_qual_delivery_tools_v1';out.mkdir(exist_ok=False)
template=ROOT/'outputs/research_archive/occam_first_window_freeze_v1'
s=(template/'archive_checkpoint.py').read_text(encoding='utf8')
for before,after in (
    ("PARENT='819afbe3252e8d7fd6a45b9d22699cfd6bed6170'","PARENT='"+PARENT+"'"),
    ("SOURCE='bb8fb0715b1b0719ea956051f808026b071a16ae'","SOURCE='"+SOURCE+"'"),
    ("baseline_path=ROOT/'outputs/research_archive/occam_receiver_prefix_v1/catalog.json'","baseline_path=ROOT/'outputs/research_archive/occam_first_window_freeze_v1/catalog.json'"),
    ('research_archive_build_occam_first_window_freeze_v1_20261029_bb8fb0715b1b','research_archive_build_standard_dr_and_qual_delivery_tools_v1_20261029_'+SOURCE[:12]),
    ('ARCHIVE_FILE_CATALOG_OCCAM_FIRST_WINDOW_FREEZE_V1_20261029.json','ARCHIVE_FILE_CATALOG_STANDARD_DR_QUAL_DELIVERY_TOOLS_V1_20261029.json')):
    assert before in s,before;s=s.replace(before,after)
i=s.index("    note=f'''");j=s.index('    extras={',i)
note='''# 完整结果交付工具与标准序贯DR：软件冻结归档

来源{SOURCE}，父归档{PARENT}。保存两个完成的软件准备阶段：
完整QUAL交付／实际Git恢复工具冻结737471225e796cc12018c32b97f87296abe486fd，
以及当前标准序贯DR纯数组组件。原实验继续一次性收集，活动QUAL原始
文件和中途结局未进入这份快照，科学1393来源／配置／bank不改变。

交付工具12构造／微型ZIP检查通过，开发及正式各12；只复用原bundle和
终态准入，不称实际1566案例已导出或完成Git恢复。新版本包含原报告、
全部失败／分配／29程序／522格、原独立统计及完整费用。仅归档模式
明确不与原始文件独立逐字节对比。首次新来源清单CRLF暂存失败及原
字节保留；只修该元数据换行，未改程序或科学数据。

DR是Jiang与Li2016标准估计式，不是新算法。34不同数组检查，开发／
正式各34。正式111估计尝试／99返回、99反向复算尝试／3组汇总调用；
故意非法／篡改拒绝包含其中。16构造叶节点跨设置重用，非机器人样本。
保留完整收费、首零权重停止、严格完整Q语义、支持缺失分母和独立组；
不裁权、归一化或从0–500任务上限取得估计风险保证。真实Q拟合、日志
支持／训练来源资格、有效精度和自身历史部署尚未完成，原失败设计不复活。

原文复核v8限定Poke／MDE／OCCAM／GAUGE已有机制，未确立新颖性；
Poke全文只读缓存留本地，归档只含来源SHA／阅读范围，未发布论文全文。
新环境／reset／帧／政策／真实模型查询／拟合／训练／seed／在线LLM0。
所有秘密／补充秘密、差异、索引／磁盘／实际提交字节已核对；旧原始
记录、失败、133记录分片及实际恢复副本保留，按精确Git身份复用原
证明，归档没有重新采集或恢复。当前源树{len(catalog)}项，发布
{sum(r["published"] for r in catalog)}项；省略源完整列大小／SHA。

原QUAL、独立统计与已冻结首窗诊断先按原协议完成；失败接收者不再加门。
A新机制、完整强对照、独立完整任务收益及消融尚缺证据，CCF A目标未完成。
'''
s=s[:i]+"    note=f'''"+note+"'''\n"+s[j:]
s=s.replace('Archive record-only four-candidate diagnostic software freeze before complete qualification results',
            'Archive complete-result delivery tools and standard sequential DR arithmetic without live-data evaluation')
compile(s,'archive_checkpoint.py','exec');(out/'archive_checkpoint.py').write_text(s,encoding='utf8',newline='\n')
push=(template/'push_archive.py').read_text(encoding='utf8').replace('outputs/research_archive/occam_first_window_freeze_v1','outputs/research_archive/standard_dr_and_qual_delivery_tools_v1')
(out/'push_archive.py').write_text(push,encoding='utf8',newline='\n')
print(dict(prepared_for_source=SOURCE,archive_parent=PARENT),flush=True)

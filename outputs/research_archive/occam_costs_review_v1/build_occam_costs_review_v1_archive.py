"""Prepare compact archival metadata for two completed source-bound phases."""
from pathlib import Path
import subprocess
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects')
SOURCE='017ba38e7c147cc88ac197218ef1bf69f391b3c6'
PARENT='89c1f0dfdfac50a85beb35533c0f141de336691f'
assert subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0','rev-parse','HEAD'],cwd=ROOT).decode().strip()==SOURCE
out=ROOT/'outputs/research_archive/occam_costs_review_v1';out.mkdir(exist_ok=False)
template=ROOT/'outputs/research_archive/standard_dr_and_qual_delivery_tools_v1'
s=(template/'archive_checkpoint.py').read_text(encoding='utf8')
for before,after in (
    ("PARENT='517f41ce528d951963388e3d52530952253aa4a3'","PARENT='"+PARENT+"'"),
    ("SOURCE='912799da8cf7be6eed12b2598956663ff7497cc3'","SOURCE='"+SOURCE+"'"),
    ("baseline_path=ROOT/'outputs/research_archive/occam_first_window_freeze_v1/catalog.json'","baseline_path=ROOT/'outputs/research_archive/standard_dr_and_qual_delivery_tools_v1/catalog.json'"),
    ('research_archive_build_standard_dr_and_qual_delivery_tools_v1_20261029_912799da8cf7','research_archive_build_occam_costs_review_v1_20261029_'+SOURCE[:12]),
    ('ARCHIVE_FILE_CATALOG_STANDARD_DR_QUAL_DELIVERY_TOOLS_V1_20261029.json','ARCHIVE_FILE_CATALOG_OCCAM_COSTS_REVIEW_V1_20261029.json')):
    assert s.count(before)==1,before;s=s.replace(before,after)
i=s.index("    note=f'''");j=s.index('    extras={',i)
note='''# 完整资格成本工具与A主线查新：已完成阶段归档

来源{SOURCE}，父归档{PARENT}。成本工具冻结0fd53ae7fb82673ae744f5bca1e7d01f04021cc3，
查新记录提交017ba38e7c147cc88ac197218ef1bf69f391b3c6。两阶段25项文件
已核对实际Git／磁盘字节；本次不是完整QUAL结果归档。原一次性资格
进程仍运行，1393个科学源码及配置／bank不变，活动QUAL文件未进入快照。

成本工具25不同纯构造测试，开发23+25、正式25；完整资格终态前实际
拒绝读取结局且没有创建analysis_v1。它只重建资源费用，不改变原主比较。
固定provider窗口不全部算作NN预测，FROZEN窗口不算参数更新。核心eig／
收集solve按固定代码重建，case总wall不是隔离NN延迟。历史NN训练9000
共同更新不按程序数相乘；C8训练3072步包含在完整3840步来源内，未知
旧费用不填0，零API时平均延迟null。完整实际成本分析尚未执行。

查新v9核对partially performative prediction、performative control与
干预影响下的条件性能监测的原始方法／假设段，保留明确阅读范围，没有
复现或移植证明。政策改变访问分布不等于改变物理转移矩阵；残差报警
也不自动识别真实故障。条件CUSUM、完整风险／DR与简单重加权继续作为
强参考，相关宽泛描述不构成新贡献。OpenReview验证页未绕过，改读作者
arXiv；中文补扫首次默认编码失败已保存原脚本／元数据哈希，只修UTF8
检查，未重跑科学实验或已通过的全量秘密扫描。

新环境／reset／帧／政策或真实模型查询／拟合／训练／seed／在线LLM0。
秘密、补充秘密、差异、索引及提交字节已通过；旧原始记录、全部失败、
133记录分片、来源费用和实际恢复副本保留。本次对旧分片仅按实际Git
身份复用原完整恢复证明，没有重复恢复或采集。当前源树{len(catalog)}项，
发布{sum(r["published"] for r in catalog)}项，省略源完整列大小和SHA。

原完整QUAL／双审计／独立统计及已冻结首窗口诊断先完成；没有根据
中途结果改bank、主比较或添加样本。A新机制、强参考完整部署、独立
完整任务优势和消融仍缺证据，CCF A目标保持未完成。
'''
s=s[:i]+"    note=f'''"+note+"'''\n"+s[j:]
old='Archive complete-result delivery tools and standard sequential DR arithmetic without live-data evaluation'
assert old in s;s=s.replace(old,'Archive complete qualification cost tools and conditional monitoring prior-art boundaries')
compile(s,'archive_checkpoint.py','exec');(out/'archive_checkpoint.py').write_text(s,encoding='utf8',newline='\n')
push=(template/'push_archive.py').read_text(encoding='utf8').replace('outputs/research_archive/standard_dr_and_qual_delivery_tools_v1','outputs/research_archive/occam_costs_review_v1')
compile(push,'push_archive.py','exec');(out/'push_archive.py').write_text(push,encoding='utf8',newline='\n')
print(dict(prepared_for_source=SOURCE,archive_parent=PARENT),flush=True)

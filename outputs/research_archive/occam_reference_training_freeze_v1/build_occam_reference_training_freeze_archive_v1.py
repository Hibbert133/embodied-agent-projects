from pathlib import Path
import sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
source=io.git('rev-parse','HEAD');parent='43a721b106c287bf2309f7070777c91e0997d15b'
assert source=='adf45217c95a75a067c77ac9c193120f15ff13e9' and io.read(ROOT/'outputs/occam_reference_train/freeze_validation_v1/complete.json')['integrity']=='PASSED'
out=ROOT/'outputs/research_archive/occam_reference_training_freeze_v1';out.mkdir(exist_ok=False)
s=(ROOT/'outputs/research_archive/occam_window_host_v1/archive_checkpoint.py').read_text('utf8')
for old,new in (("PARENT='ff5610d3e44b44c92351d9fb7d2c0b280c4f9c56'","PARENT='"+parent+"'"),
    ("SOURCE='ff05ef4e5f10e5da683f14f8a6ffd9603c7825b9'","SOURCE='"+source+"'"),
    ('outputs/research_archive/occam_performance_core_v1/catalog.json','outputs/research_archive/occam_window_host_v1/catalog.json'),
    ('research_archive_build_occam_window_20261028_ff05ef4e5f10','research_archive_build_occam_train_freeze_20261028_'+source[:12]),
    ('ARCHIVE_FILE_CATALOG_OCCAM_WINDOW_20261028.json','ARCHIVE_FILE_CATALOG_OCCAM_TRAIN_FREEZE_20261028.json'),
    ("'outputs/occam_window_host/')","'outputs/occam_window_host/','outputs/occam_reference_train/')"),
    ('Archive continuous performance host contract and complete retained reader failures; no learned task gain','Archive frozen independent performance-reference training protocol and verified software; no new robot data yet')):
    assert old in s,old;s=s.replace(old,new)
i=s.index("    note=f'''");j=s.index('    extras={',i)
note=f'''# 最新归档：独立表现参考采集与训练的冻结版本

本地来源{source}，父归档{parent}。本阶段软件/预算已冻结，尚未采集新机器人
数据、训练科学模型或开放CAL/QUAL。标准OCCAM相关参考不是新方法或CCF A贡献。

已实现保存实际随机/固定块行为、连续真实获取、完整流/执行器/积分审计、
严格公开标签投影、mask保持标准化、原单位JSON导出、可微两阶段学习及同案例
曝光/同更新尝试数普通ERM。输入排除注册/真扰动/实际噪声/未来结果；窗口MSE
不冒称完整任务收益。算法/平台/有限四T搜索不冒称原论文的完整复现。

25项主运行时+7项隔离检查通过，32新增唯一，旧2522源码绑定复用共2554；
开发/正式共64次检查、2次构造Adam，零新机器人/科学模型训练/在线LLM。
编译、两环境依赖、秘密、实际索引BASIC/EXTRA/解压与差异/字节通过。

未来一次NATIVE36+TRAIN648，最大342000控制步、34884全部重置、19152000帧。
训练最多9000实际共享Adam更新、1000000显式Torch求解、7200秒；META与普通
ERM匹配案例曝光/更新尝试，不声称同FLOPs或墙钟。所有失败/空/短窗保留，
预算/数值/读者失败停止，不重采/替换/挑checkpoint。学习数据只取新TRAIN。
旧主机资格4203步/939015帧等来源费用另列，不隐藏为免费数据。

完整报告reports/occam_reference_train_freeze_v1_zh.md及版本化协议。下一步
按冻结顺序真实收集/训练；科学CAL、最终自身时序完整损失比较和新获取机制
仍须独立协议、强参考及消融，CCF A完整目标未完成。
旧数据、分片、恢复和负结果保留，旧省略目录保持；普通快进，无强推或合并。
'''
tail='\n完整本地源树{len(catalog)}项，发布{sum(r["published"] for r in catalog)}项；省略目录保留。\n'
s=s[:i]+"    note=f'''"+note+tail+"'''\n"+s[j:];compile(s,'archive_checkpoint.py','exec');(out/'archive_checkpoint.py').write_bytes(s.encode('utf8'))
p=(ROOT/'outputs/research_archive/occam_window_host_v1/push_occam_window_archive_v1.py').read_text('utf8').replace('outputs/research_archive/occam_window_host_v1','outputs/research_archive/occam_reference_training_freeze_v1')
(out/'push_occam_reference_training_freeze_v1.py').write_bytes(p.encode('utf8'));print(source)

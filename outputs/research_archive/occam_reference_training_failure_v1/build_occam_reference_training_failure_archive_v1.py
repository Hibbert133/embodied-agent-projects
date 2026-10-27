from pathlib import Path
import sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
source=io.git('rev-parse','HEAD');parent='05978abfa00e2e1d25a246005918269d7fc39b74'
assert source=='62e17a50cee6c25c8b71f701eb7c993c5b4dcf22' and io.read(ROOT/'outputs/occam_reference_train/failure_delivery_v1/complete.json')['integrity']=='PASSED_FAILURE_DELIVERY_NOT_EXPERIMENT_QUALIFICATION'
out=ROOT/'outputs/research_archive/occam_reference_training_failure_v1';out.mkdir(exist_ok=False)
s=(ROOT/'outputs/research_archive/occam_reference_training_freeze_v1/archive_checkpoint.py').read_text('utf8')
for old,new in (("PARENT='43a721b106c287bf2309f7070777c91e0997d15b'","PARENT='"+parent+"'"),
    ("SOURCE='adf45217c95a75a067c77ac9c193120f15ff13e9'","SOURCE='"+source+"'"),
    ('outputs/research_archive/occam_window_host_v1/catalog.json','outputs/research_archive/occam_reference_training_freeze_v1/catalog.json'),
    ('research_archive_build_occam_train_freeze_20261028_adf45217c95a','research_archive_build_occam_train_failure_20261028_'+source[:12]),
    ('ARCHIVE_FILE_CATALOG_OCCAM_TRAIN_FREEZE_20261028.json','ARCHIVE_FILE_CATALOG_OCCAM_TRAIN_FAILURE_20261028.json'),
    ('Archive frozen independent performance-reference training protocol and verified software; no new robot data yet','Archive closed technical native acquisition failure and zero-interaction namespace diagnosis; no trained model')):
    assert old in s,old;s=s.replace(old,new)
i=s.index("    note=f'''");j=s.index('    extras={',i)
note=f'''# 最新归档：独立表现参考v1在原生接口失败，已关闭

本地来源{source}，父归档{parent}。科学采集/训练未完成，不得使用v1种子
重跑或把该记录说成OCCAM/元学习任务负结果。CCF A完整目标仍未完成。

adf4521冻结、f77e36b执行。第一NATIVE环境工厂的reset意图携带phase=
GOAL_GENERATION，与案例头phase=NATIVE冲突，归属保护在原重置委托前拒绝。
真实费用：1工厂尝试未返回、1生命周期reset尝试/0完成，0控制步/0物理帧，
0科学模型训练/在线滤波/在线LLM。只完成准备和一次失败子进程，非零工厂尝试
与耗时单列。TRAIN未开放，无成功率/截止损失/预测误差，未启动案例不填500。

部分日志、失败案例、清单、退出码和原源码全部保留，684个分配逐项登记。
只读抽取冻结归属函数+真实内存JsonJournal验证18个命名冲突，不执行环境。
示意cohort/phase分离可保存二者，外来seed/cohort仍拒绝；不是已部署新版本。
原32项检查没覆盖真正生命周期接口，4项新诊断明确弥补分析证据，共2558唯一。
新增科学训练/物理0，软件构造Adam仍2次；不把测试通过冒称机器人集成通过。

完整中文报告reports/occam_reference_training_failure_v1_zh.md。修复需保留归属
保护、补生命周期到收集器头的集成测试，另冻实现/审计/预算和全新未用未预留
人口。当前所有v1分配/预留关闭，不自动重采或开始TRAIN。科学CAL/独立自身
时序完整任务比较、强参考/消融与新获取决策机制均未完成。

普通快进、无强推合并或历史删除；旧大记录/恢复/失败保留，省略目录保持。
'''
tail='\n完整本地源树{len(catalog)}项，发布{sum(r["published"] for r in catalog)}项；完整省略目录保留。\n'
s=s[:i]+"    note=f'''"+note+tail+"'''\n"+s[j:];compile(s,'archive_checkpoint.py','exec');(out/'archive_checkpoint.py').write_bytes(s.encode('utf8'))
p=(ROOT/'outputs/research_archive/occam_reference_training_freeze_v1/push_occam_reference_training_freeze_v1.py').read_text('utf8').replace('outputs/research_archive/occam_reference_training_freeze_v1','outputs/research_archive/occam_reference_training_failure_v1')
(out/'push_occam_reference_training_failure_v1.py').write_bytes(p.encode('utf8'));print(source)

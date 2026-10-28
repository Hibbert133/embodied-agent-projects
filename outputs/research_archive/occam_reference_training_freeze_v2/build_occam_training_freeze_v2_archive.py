from pathlib import Path
import sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
source=io.git('rev-parse','HEAD');parent='f54d2dae7433e64dae6f97a67a3a499618d0fd20'
assert io.read(ROOT/'outputs/occam_reference_train_v2/freeze_validation_v1/complete.json')['integrity']=='PASSED'
assert io.git('branch','--show-current')=='codex/occam-training-collector-v2'
out=ROOT/'outputs/research_archive/occam_reference_training_freeze_v2';out.mkdir(exist_ok=False)
template=ROOT/'outputs/research_archive/occam_reference_training_failure_v1'
s=(template/'archive_checkpoint.py').read_text(encoding='utf8')
for old,new in (("PARENT='05978abfa00e2e1d25a246005918269d7fc39b74'","PARENT='"+parent+"'"),
    ("SOURCE='62e17a50cee6c25c8b71f701eb7c993c5b4dcf22'","SOURCE='"+source+"'"),
    ('outputs/research_archive/occam_reference_training_freeze_v1/catalog.json','outputs/research_archive/occam_reference_training_failure_v1/catalog.json'),
    ('research_archive_build_occam_train_failure_20261028_62e17a50cee6','research_archive_build_occam_train_freeze_v2_20261028_'+source[:12]),
    ('ARCHIVE_FILE_CATALOG_OCCAM_TRAIN_FAILURE_20261028.json','ARCHIVE_FILE_CATALOG_OCCAM_TRAIN_FREEZE_V2_20261028.json'),
    ('Archive closed technical native acquisition failure and zero-interaction namespace diagnosis; no trained model','Archive v2 repaired collector and frozen independent standard-reference training; no new physical collection yet'),
    ("'outputs/occam_reference_train/'","'outputs/occam_reference_train/','outputs/occam_reference_train_v2/'")):
    assert old in s,old;s=s.replace(old,new)
i=s.index("    note=f'''");j=s.index('    extras={',i)
note='''# 最新归档：采集接口v2及独立训练冻结

本地来源{SOURCE}，父归档{PARENT}。v1第一次工厂日志冲突的技术失败保持关闭，
不重采旧人口、不填未启动任务损失。v2案例cohort与事件phase分离，保留所有权
保护；真正collector/JsonJournal/Ledger数组回调、主机行为及全人口读者均有回归。

新协议36原生、648训练，科学CAL/最终自身历史任务资格尚未开放。所有科学算法、
控制器与学习参数/物理上限不变，仅隔离新数据与随机命名空间。13新增检查和
2558源复用检查，7项隔离数值复跑另外披露；2次构造Adam不算科学模型训练。
编译、依赖、源码/种子、实际恢复、秘密、索引与提交字节检查已通过。

本冻结仍无新增真实环境交互或在线LLM。完整费用上限342000控制步/34884全部
reset/19152000帧和共享9000次Adam已预登记，实际费用将在执行后另报。
保留全部旧失败与负结果；OCCAM相关表现学习为标准强参考，不是本项目创新。
新获取机制、强参考完整任务优势、消融、独立最终评价和CCF A目标仍未完成。

见reports/occam_reference_train_freeze_v2_zh.md。普通快进、无强推合并或历史删除，
完整省略目录和原始大记录保持，不把归档当科研结果。
'''
tail='\n完整本地源树{len(catalog)}项，发布{sum(r["published"] for r in catalog)}项；完整省略目录保留。\n'
s=s[:i]+"    note=f'''"+note+tail+"'''\n"+s[j:];compile(s,'archive_checkpoint.py','exec')
(out/'archive_checkpoint.py').write_text(s,encoding='utf8',newline='\n')
p=(template/'push_occam_reference_training_failure_v1.py').read_text(encoding='utf8').replace('outputs/research_archive/occam_reference_training_failure_v1','outputs/research_archive/occam_reference_training_freeze_v2')
(out/'push_archive.py').write_text(p,encoding='utf8',newline='\n');print(source)

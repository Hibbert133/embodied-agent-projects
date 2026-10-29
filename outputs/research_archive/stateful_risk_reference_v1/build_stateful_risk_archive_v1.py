"""Compact archive adapter for completed standard-reference evidence only."""
from pathlib import Path
import subprocess
import sys

ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');AUX=Path(__file__).parent
SOURCE=sys.argv[1];PARENT='f2c40f44ea60ed8849340e28989f73c06a5f864d'
assert len(SOURCE)==40 and subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip()==SOURCE
template=ROOT/'outputs/research_archive/train_decision_contract_v1'
out=ROOT/'outputs/research_archive/stateful_risk_reference_v1';out.mkdir(exist_ok=False)
s=(template/'archive_checkpoint.py').read_text(encoding='utf-8')
for before,after in [
    ("PARENT='03fa9655ad4a6bdee6ca2b15adf213167cd4984b'","PARENT='"+PARENT+"'"),
    ("SOURCE='b5cbf5d1aaf7c6069b0b185d3f96d44b6091e9f7'","SOURCE='"+SOURCE+"'"),
    ("baseline_path=ROOT/'outputs/research_archive/occam_opportunity_results_v1/catalog.json'","baseline_path=ROOT/'outputs/research_archive/train_decision_contract_v1/catalog.json'"),
    ('research_archive_build_train_decision_contract_v1_20261029_b5cbf5d1aaf7','research_archive_build_stateful_risk_reference_v1_20261029_'+SOURCE[:12]),
    ('ARCHIVE_FILE_CATALOG_TRAIN_DECISION_CONTRACT_V1_20261029.json','ARCHIVE_FILE_CATALOG_STATEFUL_RISK_REFERENCE_V1_20261029.json'),
    ('Archive frozen complete TRAIN public-decision and continuation-label support audit','Archive exact terminal-inclusive standard risk reference and contribution review v11')
]:
    assert s.count(before)==1,before;s=s.replace(before,after)
i=s.index("    note=f'''");j=s.index('    extras={',i)
note='''# A主线：标准完整风险参考核与查新v11

来源本地{SOURCE}，父归档{PARENT}。先冻结5503dbca90813531543933d09ceec542b36b0c54，
再运行一次五个预定抽象有限表。22项新构造测试、独立有理数展开、依赖、
源码与输入SHA、秘密、实际索引与磁盘字节及差异检查通过。旧2695科学
检查按1393源码绑定复用，没有新机器人／环境／reset／帧／政策或学习模型
查询／拟合／训练／种子／在线LLM。纯表评分不冒充机器人任务收益。

标准Bellman／DM／DR核保留真实获取后的状态和全部终止分支；成功时n'−n，
失败时500−n，其中获取已经计费一次。只有存活且实际完整固定后继才有T
标签；随机后续终局不贴给第一T。无日志支持的候选完整保留拒绝，未补
epsilon、剪权重或归一化造价值。回归或概率任一个正确时的精确恒等式，
及双失配／状态失配／丢终止分支的反例均保留。50是逐选项等式数，非
Python断言调用总数或独立统计样本数；这些都是标准性质，不是新方法。

事后只读原684案例审计输出：两种TRAIN行为各11个获取中结束，均成功。
271静态后继标签准入不变，不生成未执行T终局；这些终止成功应纳入未来
获取前完整风险目标。本报告不认定旧OCCAM或旧A1代码发生该遗漏或因此失败。
旧A1已经有8个训练完整风险模型及开发重放；本核只补当前稀疏日志的DR
语义检查，没有训练、部署或替换既有模型。原报告、所有失败与负结果不变。

查新v11核对TOPLE、AFAPE、COST-Q、NDE联合测试／处置的明示阅读范围；
一般POMDP／完整风险已能表达本问题，局部不变性、支持获取和有限资源
优势仍需具体新机制、直接强参考、独立自身历史任务收益和消融。新颖性
与CCF A未建立。首轮冻结前命名冲突被检查拒绝，旧文档恢复原字节，新
简报独立命名，工程失败回执保留；实际worker未因之重启。

当前源树{len(catalog)}个已提交文件，发布{sum(r["published"] for r in catalog)}项；
省略项有完整SHA／大小。原始QUAL仍本地保留，ZIP／分片／三次恢复待
磁盘空间，未冒称完整远程发布。旧133分片按精确Git身份复用历史实际
恢复证明，本次没有新恢复、合并或强推。完整A研究目标继续保留。
'''
s=s[:i]+"    note=f'''"+note+"'''\n"+s[j:];compile(s,'archive_checkpoint.py','exec')
(out/'archive_checkpoint.py').write_text(s,encoding='utf-8',newline='\n')
push=(template/'push_archive.py').read_text(encoding='utf-8')
assert push.count('outputs/research_archive/train_decision_contract_v1')==1
(out/'push_archive.py').write_text(push.replace('outputs/research_archive/train_decision_contract_v1','outputs/research_archive/stateful_risk_reference_v1'),encoding='utf-8',newline='\n')
pre=(AUX/'verify_train_contract_prepublication_v1.py').read_text(encoding='utf-8')
for before,after in [('train_decision_contract_v1','stateful_risk_reference_v1'),
    ("SOURCE = 'b5cbf5d1aaf7c6069b0b185d3f96d44b6091e9f7'","SOURCE = '"+SOURCE+"'"),
    ("BASE_SOURCE = '8d8bdadf610c08ffba5c61e4314f78b8e872b0e5'","BASE_SOURCE = 'b5cbf5d1aaf7c6069b0b185d3f96d44b6091e9f7'")]:
    assert pre.count(before)==1,before;pre=pre.replace(before,after)
(AUX/'verify_stateful_risk_prepublication_v1.py').write_text(pre,encoding='utf-8',newline='\n')
print(dict(prepared_source=SOURCE,archive_parent=PARENT),flush=True)

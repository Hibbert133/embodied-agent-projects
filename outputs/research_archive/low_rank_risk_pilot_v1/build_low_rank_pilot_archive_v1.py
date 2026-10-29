"""Bounded archive adapter for the frozen low-rank pilot and preserved failure."""
from pathlib import Path
import json
import subprocess
import sys

ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');AUX=Path(__file__).parent
SOURCE=sys.argv[1];PARENT='343554dcbdc516b1211eb2bdd26074c4b8ff836b'
assert len(SOURCE)==40 and subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip()==SOURCE
template=ROOT/'outputs/research_archive/stateful_risk_reference_v1'
out=ROOT/'outputs/research_archive/low_rank_risk_pilot_v1';out.mkdir(exist_ok=False)
text=(template/'archive_checkpoint.py').read_text(encoding='utf-8')
changes=[
    ("PARENT='f2c40f44ea60ed8849340e28989f73c06a5f864d'","PARENT='"+PARENT+"'"),
    ("SOURCE='068277fbb0090f9b3e81facd0dd875958316b661'","SOURCE='"+SOURCE+"'"),
    ("baseline_path=ROOT/'outputs/research_archive/train_decision_contract_v1/catalog.json'","baseline_path=ROOT/'outputs/research_archive/stateful_risk_reference_v1/catalog.json'"),
    ('research_archive_build_stateful_risk_reference_v1_20261029_068277fbb009','research_archive_build_low_rank_risk_pilot_v1_20261029_'+SOURCE[:12]),
    ('ARCHIVE_FILE_CATALOG_STATEFUL_RISK_REFERENCE_V1_20261029.json','ARCHIVE_FILE_CATALOG_LOW_RANK_RISK_PILOT_V1_20261029.json'),
    ('Archive exact terminal-inclusive standard risk reference and contribution review v11','Archive low-rank TRAIN risk pilot with preserved failure and saved-model certificate recovery')
]
for before,after in changes:
    assert text.count(before)==1,before;text=text.replace(before,after)
decision=json.loads((ROOT/'outputs/low_rank_risk_recovery_v2/presentation_v1/research_decision.json').read_text(encoding='utf-8'))
statistics=json.loads((ROOT/'outputs/low_rank_risk_recovery_v2/analysis_v1/statistics.json').read_text(encoding='utf-8'))
presentation=json.loads((ROOT/'outputs/low_rank_risk_recovery_v2/presentation_v1/presentation_validation.json').read_text(encoding='utf-8'))
primary=statistics['programs']['RBF_RR2'];full=statistics['programs']['RBF_FULL']
note='''# A主线：低秩完整风险TRAIN开发试验

来源本地{SOURCE}，父归档{PARENT}。原实现先冻结f6a03dbdbd2ec45b0523d2c4ce90d6869360ac33，
仅一次TRAIN模型拟合。原worker读取旧NPZ时被编码模块守卫误拦，失败、日志、
20个共享保存文件完整保留，没有重跑拟合。另行冻结只读恢复入口，禁止solve／
LS／eig／SVD／QR等，核对正规方程、完整谱基和固定投影，独立双公式预测及旧
STATIC全秩参数一致后才消费事实叶。第一只读审计错用pᵀalpha=0，失败亦保留；
v2以带权零核合成反例修正为1ᵀalpha=0，模型与容差不变。原增广LS循环未持久化
数值回执，不冒称原worker成功；180投影模型、20主求解、50主特征分解按工件与
控制流推断并披露。

旧A1 TRAIN54单位／9组／648真实完整执行，48有效PRE、6提前结束保留分母。
18学习模型、任务边界均值和12固定程序共31×54来源支持选择。全部任务／条件／
边界、组、SOURCE_FAILURES来源任务失败、配对不利情况与MSE另列；不是新增1674次机器人执行。
RBF_RR2成功PRIMARY_SUCCESS/54，平均完整损失PRIMARY_LOSS；RBF_FULL为FULL_LOSS。
预定七项必要点条件PRIMARY_PASS，决定DECISION_STATUS。不改选次要核或秩救活主方法。
标准核降秩岭、PCA、共同成本分离和排序已有研究，不构成本文创新；本次只是
TRAIN事后开发，不是独立自己的时序历史、期望有害更新因果识别或最终任务资格。

原22项、首恢复11项、v2额外1项，共34项独特构造检查；v2正式执行12项。
依赖复用、1393科学源码SHA与2695原检查绑定、秘密、
数值容器、实际索引／磁盘与差异检查通过。新风险拟合按原工件单列，恢复新增
拟合／谱分解0；环境／reset／帧／固定政策查询／响应训练／机器人种子／在线LLM0。
历史648执行成本另列，源CAL／TEST／QUAL未进入本轮训练或开发统计。

当前源树{len(catalog)}个已提交文件，发布{sum(r["published"] for r in catalog)}项，
省略项有SHA／大小。旧133分片按精确Git身份复用实际恢复证明。完整原始QUAL仍
在本地，ZIP／分片／三次恢复待空间，本次未冒称完整远程交付。没有强推或合并。
完整A与CCF A目标继续，仍需具体新机制、强参考、独立验证与消融。
'''
for key,value in [('PRIMARY_SUCCESS',str(primary['success'])),('PRIMARY_LOSS',format(primary['mean_deadline_loss'],'.6f')),
                  ('FULL_LOSS',format(full['mean_deadline_loss'],'.6f')),('PRIMARY_PASS',str(decision['necessary_development_point_condition'])),
                  ('DECISION_STATUS',decision['status']),('SOURCE_FAILURES',str(presentation['source_failures']))]:note=note.replace(key,value)
i=text.index("    note=f'''");j=text.index('    extras={',i)
text=text[:i]+"    note=f'''"+note+"'''\n"+text[j:];compile(text,'archive_checkpoint.py','exec')
(out/'archive_checkpoint.py').write_text(text,encoding='utf-8',newline='\n')
push=(template/'push_archive.py').read_text(encoding='utf-8')
assert push.count('outputs/research_archive/stateful_risk_reference_v1')==1
(out/'push_archive.py').write_text(push.replace('outputs/research_archive/stateful_risk_reference_v1','outputs/research_archive/low_rank_risk_pilot_v1'),encoding='utf-8',newline='\n')
pre=(AUX/'verify_stateful_risk_prepublication_v1.py').read_text(encoding='utf-8')
for before,after in [('stateful_risk_reference_v1','low_rank_risk_pilot_v1'),
    ("SOURCE = '068277fbb0090f9b3e81facd0dd875958316b661'","SOURCE = '"+SOURCE+"'"),
    ("BASE_SOURCE = 'b5cbf5d1aaf7c6069b0b185d3f96d44b6091e9f7'","BASE_SOURCE = '068277fbb0090f9b3e81facd0dd875958316b661'")]:
    assert pre.count(before)==1,before;pre=pre.replace(before,after)
(AUX/'verify_low_rank_pilot_prepublication_v1.py').write_text(pre,encoding='utf-8',newline='\n')
print(dict(prepared_source=SOURCE,archive_parent=PARENT),flush=True)

"""Prepare ordinary compact archive of completed frozen/read-only delivery only."""
from pathlib import Path
import subprocess

ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects')
AUX=Path(__file__).parent
SOURCE='b5cbf5d1aaf7c6069b0b185d3f96d44b6091e9f7'
PARENT='03fa9655ad4a6bdee6ca2b15adf213167cd4984b'
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip()==SOURCE
out=ROOT/'outputs/research_archive/train_decision_contract_v1';out.mkdir(exist_ok=False)
template=ROOT/'outputs/research_archive/occam_opportunity_results_v1'
s=(template/'archive_checkpoint.py').read_text(encoding='utf-8')
for before,after in [
    ("PARENT='46493049dcb4592aff27ed89df4e0cf6794715f2'","PARENT='"+PARENT+"'"),
    ("SOURCE='8d8bdadf610c08ffba5c61e4314f78b8e872b0e5'","SOURCE='"+SOURCE+"'"),
    ("baseline_path=ROOT/'outputs/research_archive/occam_qualification_results_v1/catalog.json'","baseline_path=ROOT/'outputs/research_archive/occam_opportunity_results_v1/catalog.json'"),
    ('research_archive_build_occam_opportunity_results_v1_20261029_8d8bdadf610c','research_archive_build_train_decision_contract_v1_20261029_'+SOURCE[:12]),
    ('ARCHIVE_FILE_CATALOG_OCCAM_OPPORTUNITY_RESULTS_V1_20261029.json','ARCHIVE_FILE_CATALOG_TRAIN_DECISION_CONTRACT_V1_20261029.json'),
    ('Archive complete post-hoc opportunity census and correction-applicability contribution review','Archive frozen complete TRAIN public-decision and continuation-label support audit')
]:
    assert s.count(before)==1,before;s=s.replace(before,after)
i=s.index("    note=f'''");j=s.index('    extras={',i)
note='''# A主线：TRAIN公开决策输入与完整后继标签审计

来源本地{SOURCE}，父归档{PARENT}。先冻结28403b6a106e1c482f5547880489c0987ac5e5f5，
再一次只读审计，结果b5cbf5d1aaf7c6069b0b185d3f96d44b6091e9f7。22项新合成
测试、依赖、来源绑定的原2695科学检查、编译、秘密扫描、索引和差异通过。
原1393科学源码、输入、统计及封存接收者不变。本次新环境／reset／帧／
策略或模型查询／拟合／训练／episode种子／在线LLM均0。

完整TRAIN648、18独立组及NATIVE36验证，全部47任务失败、84边界前结束、
22获取中结束保留。TRAIN有564前后公开投影、542返回后存活、3296窗口；
271条实际BLOCK固定T标签只对应所执行T，不补其他三个反事实。59条RANDOM
观察到全程固定仍受未来序列／停止筛选影响，不准入未加权固定T标签。
NATIVE不训练。36来源任务条件边界格、19来源组和216静态标签覆盖格完整。

移动前积分取实际ACQUISITION_CHOICE.before_memory，返回取TASK_MEMORY_RETURN，
先于未来增益选择。seed／条件／未来行为和完整调度哈希不进入公开输入。
独立读取器只按已完成命令和公开STEP_COMPLETE.after构建历史；主模块全部
自定义函数禁用。原混合journal确含私有字节，经JSON解码后白名单选取，
没有把实际噪声／oracle动作／witness用于特征。旧物理和支持审计按SHA复用。

工作进程186.4123833秒，共8个gzip流读取、1216692行、5865095092解码字节，
仅流式读取，非新增磁盘副本。回执121240是冻结公式的核对记账单位，并非
实际assert调用次数、标量字段总数或独立样本；精确分解与完整说明保留。
普通8步任务延续和移动测量都会造成条件间公开输入差异，不直接证明
纯信息收益、移动优越性或一般不可识别。被动适应、完整风险／序贯DR、
固定PI／积分等强参考保留，未来训练／自身历史部署须另行冻结。

当前源树{len(catalog)}个已提交文件，发布{sum(r["published"] for r in catalog)}项；
省略源文件均保留SHA／大小。原始完整QUAL仍本地保留；ZIP／分片／三次
恢复待空间，不假称它已远程发布。旧133个分片按精确Git身份复用实际
恢复证明，没有新恢复、合并或强推。数据准入不等于新机制、独立任务
提升或CCF A目标完成。A主线和完整研究目标继续保留。
'''
s=s[:i]+"    note=f'''"+note+"'''\n"+s[j:];compile(s,'archive_checkpoint.py','exec')
(out/'archive_checkpoint.py').write_text(s,encoding='utf-8',newline='\n')
push=(template/'push_archive.py').read_text(encoding='utf-8')
assert push.count('outputs/research_archive/occam_opportunity_results_v1')==1
push=push.replace('outputs/research_archive/occam_opportunity_results_v1','outputs/research_archive/train_decision_contract_v1')
(out/'push_archive.py').write_text(push,encoding='utf-8',newline='\n')
pre=(AUX/'verify_occam_opportunity_results_prepublication_v1.py').read_text(encoding='utf-8')
for before,after in [('occam_opportunity_results_v1','train_decision_contract_v1'),
    ("SOURCE = '8d8bdadf610c08ffba5c61e4314f78b8e872b0e5'","SOURCE = '"+SOURCE+"'"),
    ("BASE_SOURCE = 'a2a4b921bf9a3127ffcf71505cfda24c98f63a0f'","BASE_SOURCE = '8d8bdadf610c08ffba5c61e4314f78b8e872b0e5'")]:
    assert pre.count(before)==1,before;pre=pre.replace(before,after)
(AUX/'verify_train_contract_prepublication_v1.py').write_text(pre,encoding='utf-8',newline='\n')
print(dict(prepared_source=SOURCE,archive_parent=PARENT),flush=True)

from pathlib import Path
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');out=ROOT/'outputs/research_archive/effect_horizon_v1';out.mkdir(exist_ok=False)
s=(ROOT/'outputs/research_archive/effect_learning_v1/archive_checkpoint.py').read_text('utf8')
s=s.replace("PARENT='400beb24944a0387fc7a50078b43afb9a0b4e6d7'","PARENT='2a0f4aea1f2271deaed124f1ff1987f01386f582'")
s=s.replace("SOURCE='692efbe448776ee37debeff2d9ce9ea066ec223d'","SOURCE='39727830189cfb9ce63ac8aa167f3fb8d171f53a'")
s=s.replace('outputs/research_archive/policy_support_v1/catalog.json','outputs/research_archive/effect_learning_v1/catalog.json')
s=s.replace('research_archive_build_effect_learning_20261027_692efbe','research_archive_build_effect_horizon_20261027_3972783')
i=s.index("    note=f'''");j=s.index('    extras={',i)
note="""    note=f'''# 最新存档：纠正后真实连续窗口的时间尺度诊断

来源结果{SOURCE}，冻结e5a3c3c；父存档{PARENT}，普通快进，无强推/合并。
全部新增分析为事后描述性，不是入口多步预测、部署收益、模型资格或创新。
旧成对上下文负结果、原生FAILED/MOVE链0、ARX/F20/旧响应版本保持关闭。

仅旧A1 TRAIN648轨迹，9组/54单元/162获取节点，四率共972对；六个固定
窗口1/2/4/8/16/32登记5832行、2214面板、1944全任务条件时点获取率对窗格。
4373完整窗口，其余缺失有原因；不延长成功端点、不把短窗口补成长窗、不
补零。每H完整窗口803/803/772/755/680/560，各自全分母仍972；人口随H变。

从共同首分歧前状态，比较两个实际末端位置差与实际后续XY发送命令差之和。
三参考0、名义和、冻结留组全局矩阵。H1须匹配原803保存结果。H>1未来
命令仅评价端事后读取，接口拒绝ENTRY_FORECAST；不伪造未执行状态。
一步矩阵RMSE0.006971mm，32步16.869430mm；后者只有560对，不能当同人口
趋势或唯一延迟证据。H2仍803对，但Z/夹爪至少一处float32字节差的加权
比例61.626%；没有度量幅度或因果影响，不据此识别唯一错误原因。

主与独立各9冻结权重读取、4373矩阵评价、8746零/名义参考计算；主25.348秒、
独立24.397秒。主窗口/面板/来源组装/首差数学禁用后，独立struct首差、
标量累计、矩阵方向、完整行/面板/组权重核对通过；共享旧解析/容差已披露。
新环境/重置/控制步/帧/种子/固定政策查询/拟合/在线LLM均0。旧来源648次/
77563步/33048重置/16911815帧、旧36+36拟合只列历史费用。

12新增数组测试和2216源码绑定旧项合计2228唯一，旧六张量另列；两次开发
测试均0拟合/物理/API。编译、依赖、全仓秘密/索引补充扫描、普通/暂存
差异、实际Git/磁盘字节通过。中文报告reports/correction_effect_horizon_v1_zh.md。
全部5832行、2214面板、1944格、缺失与负结果、图形/复算/来源SHA保留。
首次图形标题间距版本保留；文字澄清曾触发exclusive回执FileExistsError，
首失败与修改前文件保留，v2只修复展示元数据，科学分析没有重跑。

此诊断禁止从局部一步误差直接跳到连续纠正资格，也禁止从事后实际输入
条件检查跳到入口预测。MIAC rho-POMDP、任务相关最优实验设计及原MDE/
Residual RL/OCCAM/GAUGE/Poke/TOM等限制新颖性，不能把状态影响/任务加权
改名为新方法。仍需具体机制、同权限强参考、独立自身历史完整成本优势
和消融；未解锁新采集，完整CCF A目标仍活跃。

来源树{len(catalog)}文件，发布{sum(r['published'] for r in catalog)}。保留既有
类型/大小选择，不按成败筛选；原始.jsonl.gz/.bin分片/恢复副本仍留本地。
新windows约5.005MB，全部新科学文件均小于8MiB并发布。完整来源对象/
SHA/大小/是否发布见ARCHIVE_FILE_CATALOG_EFFECT_HORIZON_20261027.json。
'''
"""
s=s[:i]+note+s[j:]
s=s.replace('ARCHIVE_FILE_CATALOG_EFFECT_LEARNING_20261027.json','ARCHIVE_FILE_CATALOG_EFFECT_HORIZON_20261027.json')
s=s.replace('Archive paired effect negative result 692efbe; zero new physics or LLM','Archive factual effect horizon diagnosis 3972783; zero new physics or LLM')
compile(s,'archive_checkpoint.py','exec')
with (out/'archive_checkpoint.py').open('x',encoding='utf8',newline='\n') as f:f.write(s)
print(str(out/'archive_checkpoint.py'))

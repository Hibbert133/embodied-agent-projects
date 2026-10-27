from pathlib import Path
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');out=ROOT/'outputs/research_archive/effect_learning_v1';out.mkdir(exist_ok=False)
s=(ROOT/'outputs/research_archive/policy_support_v1/archive_checkpoint.py').read_text('utf8')
s=s.replace("PARENT='ea8fe4e9e0601885238d607bf59c0b80ea4e3db0'","PARENT='400beb24944a0387fc7a50078b43afb9a0b4e6d7'")
s=s.replace("SOURCE='6fe16168807e9ae29b1a4fa44c77fadc64a162e4'","SOURCE='692efbe448776ee37debeff2d9ce9ea066ec223d'")
s=s.replace('outputs/research_archive/learned_native_v1/catalog.json','outputs/research_archive/policy_support_v1/catalog.json')
s=s.replace('research_archive_build_policy_support_20261027_6fe1616','research_archive_build_effect_learning_20261027_692efbe')
i=s.index("    note=f'''");j=s.index('    extras={',i)
note="""    note=f'''# 最新存档：真实命令响应差的标准构件负结果

来源结果{SOURCE}，冻结db04aa8；父存档{PARENT}。普通快进，无强推/合并。
本轮仅旧A1 TRAIN648实际轨迹、9组、54任务/条件、162获取节点。
原1296/CAL/TEST/旧QUAL/最新54原生未用于拟合。旧负结果和恢复副本保留。

全部四率两两登记972对，803对有真实首分歧，108决策前结束、60获取结束、
1始终无命令分歧。无定义目标不补零。核对初始native/Python/RNG、扰动/
噪声承诺、全部相同发送命令及响应前缀、首分歧物理时钟、同策略原始动作/
Z/夹爪。只用两个实际发生的下一观测；不造未执行后缀。实际噪声和施加
动作只作分离的评估诊断，不进入拟合输入/标签；目标不是物理无噪声误差。

固定公开16上下文、ridge.01、9个整组LOO。36科学ridge、36独立增强lstsq，
双方各4818留组预测；0神经更新。零效应/名义差/全局标量/全局矩阵/绝对
上下文/成对上下文六参考完整保留。独立提取、特征、拟合、预测和统计通过；
共享旧执行器公式/NumPy/来源工具已披露，不称独立机构或物理重模拟。

主成对上下文MSE4.933269857e-7，全局矩阵4.859859321e-7，点比较+1.511%。
主门槛NO_DEV_PREDICTIVE_ADVANTAGE，整体、push、reach未超过全局矩阵。
不凭胜过名义映射就宣布成功，不选door子集，不调ridge/特征/样本救版本。
成对上下文版本封存，不晋升独立响应资格、控制接入或任务收益。全局矩阵
也只是小幅首分歧条件人口上的标准参考，不是全域绝对植物/可反演增益。

新环境/重置/控制步/物理帧/机器人种子/在线LLM均0。原648次/77563控制步/
33048全部重置/16911815帧另列历史费用。3次开发测试各1合成solve+1lstsq
另列，14新唯一+2202源码绑定旧项=2216；旧六张量组另列。完整972对、
324笛卡尔分层单元、36模型、4818预测、缺失与负结果、图形/中文报告/
来源SHA和复算代码全发布。新记录最大约3.11MB，无新大文件需分片。

编译、依赖、全仓秘密及实际索引补充扫描、普通/暂存差异、实际Git/磁盘
字节全部通过。中文报告reports/correction_effect_learning_v1_zh.md。
旧原生资格仍FAILED_RETAINED，模型MOVE链0；不改旧六项比较，不重开ARX/
F20评分/旧响应版本。新颖性和独立自身时序任务收益未证明，CCF A目标
仍活跃。MDE/Residual RL/OCCAM/GAUGE/Poke/TOM等强参考和独立验证仍必需。

来源树{len(catalog)}文件，发布{sum(r['published'] for r in catalog)}。保留旧
逐路径类型/大小选择，新文件按同规则；旧原始.jsonl.gz/.bin分片和恢复
副本留在本地，不按成败筛除。ARCHIVE_FILE_CATALOG_EFFECT_LEARNING_
20261027.json登记所有来源对象/大小/SHA，新发布对象实际读取/秘密扫描。
'''
"""
s=s[:i]+note+s[j:]
s=s.replace('ARCHIVE_FILE_CATALOG_POLICY_SUPPORT_20261027.json','ARCHIVE_FILE_CATALOG_EFFECT_LEARNING_20261027.json')
s=s.replace('Archive fixed-program support bounds 6fe1616; zero new physics or LLM','Archive paired effect negative result 692efbe; zero new physics or LLM')
compile(s,'archive_checkpoint.py','exec')
with (out/'archive_checkpoint.py').open('x',encoding='utf8',newline='\n') as f:f.write(s)
print(str(out/'archive_checkpoint.py'))

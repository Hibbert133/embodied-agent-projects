from pathlib import Path
import json,subprocess
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects')
def git(*args):return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT).decode().strip()
source=git('rev-parse','HEAD');assert source=='f26a138bf271da2e112b5642985166b18d1894dd'
assert json.loads((ROOT/'outputs/correction_scope/transfer_ablation_v1/result_validation/complete.json').read_text(encoding='utf8'))['integrity']=='PASSED'
out=ROOT/'outputs/research_archive/transfer_ablation_v1';out.mkdir(exist_ok=False)
text=(ROOT/'outputs/research_archive/transfer_learning_v1/archive_checkpoint.py').read_text(encoding='utf8')
pairs=[("PARENT='c1339e2126d34f8e10953c1a8acb9bc33ca7edb4'","PARENT='aa95518b50f188d2969d2731b86e8740c0fd826a'"),
    ("SOURCE='bb19bd7b2e9eabd668bda9266601e2c843bd1ca9'",f"SOURCE='{source}'"),
    ('outputs/research_archive/state_coupled_design_v1/catalog.json','outputs/research_archive/transfer_learning_v1/catalog.json'),
    ('research_archive_build_transfer_learning_20261026_bb19bd7','research_archive_build_transfer_ablation_20261026_'+source[:7]),
    ('ARCHIVE_FILE_CATALOG_TRANSFER_LEARNING_20261026.json','ARCHIVE_FILE_CATALOG_TRANSFER_ABLATION_20261026.json'),
    ('Archive TRAIN-only auxiliary correction-transfer learning bb19bd7; no new physics or LLM','Archive matched auxiliary supervision ablations '+source[:7]+'; no new physics or LLM')]
for a,b in pairs:assert a in text;text=text.replace(a,b)
start=text.index("    note=f'''");end=text.index('    extras=',start)
text=text[:start]+"""    note=f'''# 最新阶段存档：纠正后适用性的匹配辅助监督消融

来源已检查结果 {SOURCE}，父存档 {PARENT}；普通快进，无强推/合并。
本轮先在ccf7629提交实现/配置/数组测试及独立审计，再一次固定预算拟合。
旧TRAIN9组54单元，32原程序1728行原样复用，12新控制648次新离线支持选择，
总44程序2376行；不是新物理运行或最终独立评价人口，CAL/TEST未用于学习评价。

原候选/架构/初始化/完整成本/折分/预算固定，仅干预辅助监督：
FUTURE_MARGINAL_PRODUCT保留p/g/长度，用p*g替代j；FUTURE_RATE_MEAN平均
四个候选未来目标；HISTORY_RECONSTRUCT重建已有真实历史。派生标签不是新
物理轨迹，历史控制仍保留相同全局TRAIN误差尺度和完整成本监督。
每个前置critic只绑定自己的确切receiver；不跨接标签，不用事后最优成本。

主判断通过：源JOINT平均完整损失86.425926、成功54/54；三个简化控制依次
102.740741(52/54)、93.851852(54/54)、95.925926(52/54)。候选逐一更低，
但只显示该固定有限学习设置的监督区别；不能判定唯一物理机制或新颖性。
纠正平均控制也54/54，成功率本身不能证明纠正相关信息必要。原相对最小
固定程序均值仅低.425926步且来源组集中这一限制保持，不因消融自动消失。
普通辅助学习、SF、SPO、任务性能预测/获取已有研究；本轮不是CCF A成果。

新增科学9神经风险/辅助模型9000次SGD、9前置RBF；独立9神经9000SGD、9lstsq。
原候选及其他源模型未重训，源拟合/物理数据费用另列。独立核对3415296字段，
最大参数差6.619704784327496e-15、预定容差5e-8，实际选择完全一致；主标签/
网络/梯度/训练/特征/选择/统计禁用。共享NumPy，不称独立机构或框架审计。
原152224标签字段事件审计来源哈希复用，未当成新增独立证据重复计算。
19新数组测试加2139源码绑定旧回执=2158唯一检查，旧六组张量另列；重复
开发检查不增加唯一数。编译、依赖、全仓秘密、新实际索引秘密/字节、差异、
Git/disk字节核对通过。实际PNG已查看，图/全表/失败/缺失及792分格均保留。

新增环境/重置/控制步/物理帧、原策略查询、机器人种子、响应/逆模型、底层
策略训练、在线LLM API全部0。源TRAIN648次、77563步、33048全部重置、
16911815帧单列；不免费化物理来源，不删失败，不恢复世界撤销获取位移。
下一步仍需具体获取/采用机制区别、独立自身历史、完整强参考和成本资格。
中文报告reports/correction_transfer_ablation_v1_zh.md；原A1/FULL-MASK/ARX/
响应模型负结果和旧六项比较保持不变，完整CCF A目标未完成。

来源树{len(catalog)}文件、发布{sum(r['published'] for r in catalog)}个。
ARCHIVE_FILE_CATALOG_TRANSFER_ABLATION_20261026.json登记全部已提交路径的
大小、Git对象与SHA-256。新18模型、9派生TRAIN目标、全量选择/重放/结果均
发布；旧大型原始物理.jsonl.gz、二进制分片、实际恢复副本及普通完整Git
历史仍在本地，克隆此分支不包含它们。按类型/大小排除，不按成败。
新发布Git对象实际读取/扫描；相同对象复用已核验哈希和扫描；没有强推、
合并、删除/改写原始历史或数据，也不推送含超大blob的普通研究历史。
'''
"""+text[end:]
compile(text,str(out/'archive_checkpoint.py'),'exec');(out/'archive_checkpoint.py').write_text(text,encoding='utf8',newline='\n');print(out/'archive_checkpoint.py')

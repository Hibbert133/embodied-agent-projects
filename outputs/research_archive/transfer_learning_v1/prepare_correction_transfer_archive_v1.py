from pathlib import Path
import json,subprocess
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects')
def git(*args):return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT).decode().strip()
source=git('rev-parse','HEAD');assert source=='bb19bd7b2e9eabd668bda9266601e2c843bd1ca9'
assert json.loads((ROOT/'outputs/correction_scope/transfer_learning_v1/result_validation/complete.json').read_text(encoding='utf8'))['integrity']=='PASSED'
out=ROOT/'outputs/research_archive/transfer_learning_v1';out.mkdir(exist_ok=False)
text=(ROOT/'outputs/research_archive/state_coupled_design_v1/archive_checkpoint.py').read_text(encoding='utf8')
replacements={
    "PARENT='d56b3c63a648cf50b647b24e4928518bdd719bbd'":"PARENT='c1339e2126d34f8e10953c1a8acb9bc33ca7edb4'",
    "SOURCE='aff4e55acbac551597cef72307089b7898b84eb4'":f"SOURCE='{source}'",
    'outputs/research_archive/program_support_v1/catalog.json':'outputs/research_archive/state_coupled_design_v1/catalog.json',
    'research_archive_build_state_coupled_design_20261026_aff4e55':'research_archive_build_transfer_learning_20261026_'+source[:7],
    'ARCHIVE_FILE_CATALOG_STATE_COUPLED_DESIGN_20261026.json':'ARCHIVE_FILE_CATALOG_TRANSFER_LEARNING_20261026.json',
    'Archive constructed state-coupled actuation design aff4e55; no robot allocation':
        'Archive TRAIN-only auxiliary correction-transfer learning '+source[:7]+'; no new physics or LLM'
}
for a,b in replacements.items():assert a in text;text=text.replace(a,b)
start=text.index("    note=f'''");end=text.index('    extras=',start)
note="""    note=f'''# 最新阶段存档：纠正后适用性辅助学习（旧TRAIN开发）

来源为已检查本地结果 {SOURCE}，父存档 {PARENT}；普通快进，无强推/合并。
科学实现/配置/测试/独立审计先在7a8c4c5提交，再执行一次固定预算拟合。
分类TRAIN_ONLY_POSTHOC_COMPONENT_DEVELOPMENT；旧TRAIN9组54单元，三折
训练集重叠，不是新独立人口、真实部署或最终资格。CAL/TEST未用于学习评价。

五个同权限学习版本：直接完整成本MSE、直接SPO+、经验误差重加权、
条件误差辅助SPO+及joint辅助SPO+；全公开因果历史旁路均保留。
全部12固定程序、20学习程序及1728次受支持事实重放选择完整保存。
15个风险/辅助神经拟合共15000次SGD、15个绑定固定receiver的前置RBF拟合；
独立实现再15个神经拟合15000次SGD及15个lstsq复算，完整预算分别计费。
新增环境/重置/控制步/物理帧、策略查询、机器人种子、响应/逆模型、底层
策略训练及在线LLM API均0。旧TRAIN来源648次、77563步、33048全部重置、
16911815帧另列，不将离线重放视作免费物理数据或新物理部署。

JOINT两阶段54/54成功，平均完整截止损失86.425926；直接SPO96.037037，
经验重加权96.092593，条件误差95.166667。最低固定均值86.851852。
严格全人口均值开发必要条件满足，但相对最低固定程序仅少23总步/
0.425926平均步；九组仅组4改善，四组变差、四组相同，收益高度集中。
这不证明独立任务收益、机制因果或算法新颖性，不授权大规模新采集。
不能仅用成功54/54作为研究目标完成；应先独立冻结匹配辅助正则等消融。

全部失败和不利选择、18分格/组统计、32控制、全部末步模型/训练记录及
预测缺失均保留。joint预测误差没有全面胜出，历史未覆盖质量约.765。
参数合法、当前预测及完整任务收益分别评价；没有安全或稳定保证。
独立复算5562160数值字段、152224标签字段通过，最大参数差约1.02e-14；
网络/训练/特征主入口禁用，另实现反向微分；仍共享NumPy，非独立机构审计。
24新数组测试加来源绑定2115旧测试=2139唯一检查，重复开发检查不重复计数。
依赖/编译/全仓秘密/新实际索引字节/差异/Git与磁盘字节检查通过。
首次图例拥挤的图和修复记录保留，最终PNG/SVG经实际查看。

中文报告reports/correction_transfer_learning_v1_zh.md，冻结协议及查新表包含
MDE、Residual RL、OCCAM、GAUGE、Poke and Strike、TOM、SF、VaGraM、SPO。
辅助未来特征及任务导向损失都有已有路线；未声称本轮论文创新，CCF A未完成。
原A1、FULL/MASK、ARX、响应模型及全部负结果/六项比较保持不变。

来源树共{len(catalog)}文件，发布{sum(r['published'] for r in catalog)}个。
ARCHIVE_FILE_CATALOG_TRANSFER_LEARNING_20261026.json列出所有已提交来源路径、
大小、Git对象和SHA-256。新学习记录/30末步模型/结果全量发布，旧大型原始
物理.jsonl.gz、二进制分片、恢复副本及完整普通历史仍在本地，克隆此分支
不包含它们；按类型/大小排除，不按成败。相同Git对象复用此前检查，新增
发布对象实际读取扫描。未推送超大普通历史，也未删除、改写或合并历史。
'''
"""
text=text[:start]+note+text[end:];compile(text,str(out/'archive_checkpoint.py'),'exec')
(out/'archive_checkpoint.py').write_text(text,encoding='utf8',newline='\n');print(out/'archive_checkpoint.py')

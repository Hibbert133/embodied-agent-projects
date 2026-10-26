from pathlib import Path
import json,subprocess
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects')
def git(*args):return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT).decode().strip()
source=git('rev-parse','HEAD');assert source=='aff4e55acbac551597cef72307089b7898b84eb4'
assert json.loads((ROOT/'outputs/correction_scope/state_coupled_design_v1/result_validation/complete.json').read_text(encoding='utf8'))['integrity']=='PASSED'
out=ROOT/'outputs/research_archive/state_coupled_design_v1';out.mkdir(exist_ok=False)
text=(ROOT/'outputs/research_archive/program_support_v1/archive_checkpoint.py').read_text(encoding='utf8')
replacements={
    "PARENT='8840aed22cf94967ea1478b36aefd9f4cba9db76'":"PARENT='d56b3c63a648cf50b647b24e4928518bdd719bbd'",
    "SOURCE='f61b539f5f6a0617120811eebb6f378f835b4a54'":f"SOURCE='{source}'",
    'outputs/research_archive/trace_value_v1/catalog.json':'outputs/research_archive/program_support_v1/catalog.json',
    'research_archive_build_program_support_20261026_f61b539':'research_archive_build_state_coupled_design_20261026_'+source[:7],
    'ARCHIVE_FILE_CATALOG_PROGRAM_SUPPORT_20261026.json':'ARCHIVE_FILE_CATALOG_STATE_COUPLED_DESIGN_20261026.json',
    'Archive complete factual acquisition support f61b539; no new physics or fits':
        'Archive constructed state-coupled actuation design '+source[:7]+'; no robot allocation'
}
for a,b in replacements.items():assert a in text;text=text.replace(a,b)
start=text.index("    note=f'''");end=text.index('    extras=',start)
note="""    note=f'''# 最新阶段存档：A线状态相关算子与短试机制审查（仅构造设计）

来源为已检查本地结果 {SOURCE}，父存档 {PARENT}；普通快进，无强推/合并。
本轮实现/配置/数组检查/独立审计先在657297c提交，再执行一次固定构造网格。
DESIGN_ONLY_NO_ROBOT_ALLOCATION：没有机器人采集/种子/TRAIN/CAL/最终评价分配。
collection_allocation明确拒绝；不将构造数据冒作MetaWorld轨迹或新算法资格。

新增环境创建/重置/控制步/物理帧、原政策查询、机器人种子、模型拟合、在线
LLM API均为零。不解析旧机器人记录或CAL/TEST；旧全部结果和失败保持不变。
新增状态相关仿射评价算子及两个平坦端点对照。它是抽象归一化数值实例，
不是从硬件测得的摩擦/回差；评价端真参数/混合权不能进入Agent或学习标签。

完整4320行构造网格与116640标量字段独立复算通过，主9个函数禁用。
独立最大绝对算术差2.220446049250313e-16，预定容差5e-7仅是数值实现容差。
两个平坦对照2880行与旧float32链逐字节一致；完整构造JSONL在此快照发布。
它们不是独立机器人样本/新测试，也不证明物理连续性、预测或任务收益。

明示无量纲运动学反例展示：同初态小/大命令第一步模型误差均0；大命令
改变后继位置，下一步固定左模型约-.24动作误差，小命令仍0。不是米或任务
损失，也不证明动力学不可逆。数值参数合法/预测有效/完整任务收益分别评价。

查新使“短试后接受/拒绝本身新颖”的主张被拒绝：连续切换、两阶段Q、
MDE/OCCAM等均是直接近邻；不将状态相关设置本身当算法贡献。各来源仅按
实际部分阅读披露，网页验证未绕过，缺失原全文不冒称读过或复现。

12项新数组检查通过，2103项源码绑定复用，合计2115项独特检查，旧六组张量另列。
编译、依赖、秘密、普通/暂存差异、实际Git对象和磁盘字节核对通过。
中文报告：reports/state_coupled_actuation_design_v1_zh.md。
下一机制仍须具体可训练区别、同权限强组合参考、独立自身时序任务优势和消融；
真实采集必须先有完整协议/预算。本轮未完成论文贡献或完整CCF A目标。

来源树共{len(catalog)}文件，发布{sum(r['published'] for r in catalog)}个。
ARCHIVE_FILE_CATALOG_STATE_COUPLED_DESIGN_20261026.json列出所有已提交来源路径、
大小、Git对象和SHA-256。旧大型原始物理记录、二进制分片、恢复副本及完整
历史仍在本地，克隆此分支不包含它们；按类型/大小排除，不按成败。
相同Git对象复用先前哈希/秘密检查，新增发布对象实际读取扫描。
没有推送超大普通研究历史，也没有删除、改写或合并本地/远端历史。
'''
"""
text=text[:start]+note+text[end:];compile(text,str(out/'archive_checkpoint.py'),'exec')
(out/'archive_checkpoint.py').write_text(text,encoding='utf8',newline='\n');print(out/'archive_checkpoint.py')

from pathlib import Path
import json,subprocess
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects')

def git(*args):return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT).decode().strip()
source=git('rev-parse','HEAD');assert source=='34ac29d2298fbcabcdf69720bfd6ad13334c547a'
assert json.loads((ROOT/'outputs/correction_scope/trace_value_v1/result_validation/complete.json').read_text(encoding='utf8'))['integrity']=='PASSED'
out=ROOT/'outputs/research_archive/trace_value_v1';out.mkdir(exist_ok=False)
text=(ROOT/'outputs/research_archive/risk_reference_v1/archive_checkpoint.py').read_text(encoding='utf8')
replacements={
    "PARENT='9757621b73598322064684f7e200cd8efc6205ba'":"PARENT='993bb1d78c9b1948c591be36eaaa90d9a12ced54'",
    "SOURCE='89667f78bfc253527ffc3e81c19b8b5b4770b6a5'":f"SOURCE='{source}'",
    'outputs/research_archive/correction_scope_result_v1/catalog.json':'outputs/research_archive/risk_reference_v1/catalog.json',
    'research_archive_build_risk_reference_20261026_89667f7':'research_archive_build_trace_value_20261026_'+source[:7],
    'ARCHIVE_FILE_CATALOG_RISK_REFERENCE_20261026.json':'ARCHIVE_FILE_CATALOG_TRACE_VALUE_20261026.json',
    'Archive audited standard risk references 89667f7; no new physics or final deployment claim':
        'Archive audited fixed-receiver trace ablation '+source[:7]+'; negative result, no new physics'
}
for before,after in replacements.items():
    assert before in text;text=text.replace(before,after)
start=text.index("    note=f'''");end=text.index('    extras=',start)
note="""    note=f'''# 最新阶段存档：获取额外轨迹的固定接收者对照（负结果）

来源为已检查的本地结果提交 {SOURCE}，父存档 {PARENT}，普通快进，无强推/合并。
实现、配置、信息接口和预算先在3875955冻结，再复用既有TRAIN数据。
新增物理交互、重置、仿真帧、底层政策查询、机器人种子、在线LLM API均为零。
复用TRAIN648次来源执行/77563控制步/33048全部重置/16911815物理帧；未再次发生。
完整A1总1620次及其他历史费用、失败和原13项比较继续保留且结论不变。

本轮6个统计风险拟合、6次独立最小二乘复算，9个TRAIN组54单元、10参考共540
离线事实分支重放。三个交叉折训练集重叠，只作开发描述，不给名义显著性。
CAL/TEST未用于本轮训练、评价、调参或模型选择；并非新方法的独立自身历史部署。

同一模型、同一获取返回状态/积分/花费时钟/完整免费前缀，只屏蔽MOVE额外轨迹。
FULL减MASK平均完整截止损失：线性+12.851852步，核岭+25.537037步；成功50/54
分别对51/54与53/54。核岭FULL预测MSE更低，实际任务成本却更高。
全部10参考、9组、三任务×两条件×三时点、39个来源失败和24个离线失败行保留。
其中离线失败行可能引用同一来源叶，不是新增独立失败。全部108配对补充诊断保留。
这是否定该固定接收者的当前收益，不证明额外轨迹没有信息或所有接收者都失败。

20项新数组检查+2073项源码绑定复用检查=2093项独特检查；旧六组张量另列。
5099016个独立参数字段和8604个重放字段核对不计作新测试。编译、依赖、秘密、
普通/暂存差异、实际Git对象与磁盘字节检查通过。大日志实际恢复并核对CRC/行数/
字节哈希，原件、压缩记录与恢复副本保留。补充读表格式失败和修改前源码也保留。

中文报告：reports/correction_trace_value_v1_zh.md。
封存这一版接收者负结果，不叠加旧人口门控或以MSE作为新采集资格。
新机制仍缺具体可证伪区别、同权限决策/完整免费历史强对照及独立自身历史部署。
本轮不是新算法、物理安全保证或CCF A目标完成；原ARX/SS等负结果仍封存。

来源树共{len(catalog)}文件，发布{sum(r['published'] for r in catalog)}个。
ARCHIVE_FILE_CATALOG_TRACE_VALUE_20261026.json列出全部已提交来源路径、大小、
Git对象和SHA-256。原始大记录、二进制分片、恢复副本及完整本地历史仍在本地；
克隆本分支不包含全部原始记录。排除按类型/大小，不按成败；本地有恢复索引。
相同Git对象复用先前哈希/秘密检查；新增发布对象实际读取并扫描。
没有推送包含超大历史对象的普通研究分支，也没有删除或改写本地历史。
'''
"""
text=text[:start]+note+text[end:]
compile(text,str(out/'archive_checkpoint.py'),'exec')
(out/'archive_checkpoint.py').write_text(text,encoding='utf8',newline='\n')
print(out/'archive_checkpoint.py')

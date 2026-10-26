from pathlib import Path
import subprocess,json
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects')
def git(*args):return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT).decode().strip()
source=git('rev-parse','HEAD');assert source=='89667f78bfc253527ffc3e81c19b8b5b4770b6a5'
assert json.loads((ROOT/'outputs/correction_scope/risk_reference_v1/result_validation/complete.json').read_text(encoding='utf8'))['integrity']=='PASSED'
out=ROOT/'outputs/research_archive/risk_reference_v1';out.mkdir(exist_ok=False)
text=(ROOT/'outputs/research_archive/correction_scope_result_v1/archive_checkpoint.py').read_text(encoding='utf8')
text=text.replace("PARENT='980c2b3660efd4589bb61db56b64ec5cc76b5cb9'","PARENT='9757621b73598322064684f7e200cd8efc6205ba'")
text=text.replace("SOURCE='9dbfece19324cf96cf08576f210ab08b9fbb7a78'",f"SOURCE='{source}'")
text=text.replace('outputs/research_archive/correction_scope_freeze_v1/catalog.json','outputs/research_archive/correction_scope_result_v1/catalog.json')
text=text.replace('research_archive_build_correction_scope_result_20261026_9dbfece','research_archive_build_risk_reference_20261026_'+source[:7])
start=text.index("    note=f'''");end=text.index('    extras=',start)
note="""    note=f'''# 最新阶段存档：A方向标准完整风险参考与事实分支开发重放

来源为已检查的本地结果提交 {SOURCE}，父存档 {PARENT}，普通快进，无强推/合并。
本版先于读取真实训练数值在82a3873冻结实现、配置、信息接口和费用。
新增物理交互、重置、仿真帧、底层政策查询、机器人种子、在线LLM API均为零。
复用现有TRAIN648/CAL216来源执行，原始A1总1620次/222322步及其费用另保留。

完成8个标准完整风险模型与8次独立增广最小二乘复算；3个CAL开发组、18单元、
12个预定选择器共216次离线事实分支重放，不是216次新机器人执行或独立部署。
原A1的FULL_RBF仍为NOT_QUALIFIED，13项主比较与所有原始记录不变。

开发均值：继续0.5为67.6667步；零新增观测的CONTINUE_POST_RBF为61.3333；
两阶段参考均65.2222，未胜过该免费历史参考，组三组差−17.8333/+10.5/0。
全部12参考、45个来源任务失败及2个可重复引用同叶的离线失败行均保留。
不据CAL挑选主方法或宣称稳定收益；核岭、任务风险与两阶段Q不是新算法。

28项新数组/构造记录检查加2045项源码绑定复用检查，合计2073项独特检查。
编译、依赖、秘密、普通/暂存差异、真实Git对象与磁盘字节检查通过。
3个记录文件实际恢复、压缩完整性/行数/哈希核对通过；原件和恢复副本保留。
失败的合成测试夹具、失败日志及源码快照保留；无真实数据重采或结果调参。

中文报告：reports/correction_scope_risk_reference_v1_zh.md。
下一机制仍须具体区别、同权限完整强对照、独立自身历史部署和消融。
本轮不证明算法创新、物理安全或CCF A目标完成；原ARX/SS等负结果仍封存。

来源树共{len(catalog)}文件，发布{sum(r['published'] for r in catalog)}个。
ARCHIVE_FILE_CATALOG_RISK_REFERENCE_20261026.json列出所有已提交来源路径、大小、
Git对象和SHA-256。原始大记录、二进制分片、恢复副本及完整历史仍在本地；
克隆本分支不包含全部原始数据或本地历史，重放大日志另有本地恢复索引。
选择按类型/大小，不按成败。相同Git对象复用先前哈希/秘密检查；新增发布
对象实际读取并扫描。没有推送包含超大历史对象的普通研究分支。
'''
"""
text=text[:start]+note+text[end:]
text=text.replace('ARCHIVE_FILE_CATALOG_CORRECTION_SCOPE_RESULT_20261026.json','ARCHIVE_FILE_CATALOG_RISK_REFERENCE_20261026.json')
text=text.replace('Archive audited correction-scope A1 negative result 9dbfece; full local records retained',f'Archive audited standard risk references {source[:7]}; no new physics or final deployment claim')
compile(text,str(out/'archive_checkpoint.py'),'exec');(out/'archive_checkpoint.py').write_text(text,encoding='utf8',newline='\n')
print(out/'archive_checkpoint.py')

from pathlib import Path
import json,subprocess

ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects')
def git(*args):
    return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT).decode().strip()
source=git('rev-parse','HEAD')
assert git('rev-parse','HEAD^')=='d74cba1945e283a6c9c2c92b43d400813a8df404'
validation=json.loads((ROOT/'outputs/correction_scope/result_validation_v1/complete.json').read_text(encoding='utf8'))
assert validation['integrity']=='PASSED' and not git('diff','--cached','--name-only')
out=ROOT/'outputs/research_archive/correction_scope_result_v1'
out.mkdir(exist_ok=False)
text=(ROOT/'outputs/research_archive/correction_scope_freeze_v1/archive_checkpoint.py').read_text(encoding='utf8')
assert "SOURCE='d74cba1945e283a6c9c2c92b43d400813a8df404'" in text
text=text.replace("PARENT='94121351259669fc2a7702cdbec1de5b4ee7ee80'","PARENT='980c2b3660efd4589bb61db56b64ec5cc76b5cb9'")
text=text.replace("SOURCE='d74cba1945e283a6c9c2c92b43d400813a8df404'",f"SOURCE='{source}'")
text=text.replace('outputs/research_archive/passive_support_v1/catalog.json','outputs/research_archive/correction_scope_freeze_v1/catalog.json')
text=text.replace('research_archive_build_correction_scope_freeze_20261026_d74cba1','research_archive_build_correction_scope_result_20261026_'+source[:7])
start=text.index("    note=f'''")
end=text.index('    extras=',start)
note="""    note=f'''# 最新阶段存档：A方向预测基础独立试验负结果

来源是已检查的本地结果提交 {SOURCE}，父存档 {PARENT}，普通快进，无强推/合并。
冻结提交d74cba1945e2先于全部新采集。实现、配置、预测与实际轨迹均保留；
先108次原生验证，再TRAIN648/CAL216/TEST648，总1620次执行、222322控制步、
82620全部仿真重置及42421610物理仿真帧。在线LLM API调用及tokens均为零。

FULL_RBF没有通过冻结A1组件门：13项PRE32主要比较中3项区间支持更低MSE、
7项支持更高MSE、3项跨零。全部任务/条件/时点有目标，不能把失败归咎于空层。
本轮没有让学习器选择实际控制；12种固定程序及147个任务失败完整披露。
标准预测器失败不等于A方向不可行；不按TEST换模型/速率、追加样本或叠加门控。
旧ARX/SS、记忆清零负结果、闭合DR草案及原始历史保持原样。

记录、独立模型/预测/组统计、共同状态/控制记忆和无操作等价审计均通过。
23项新数组/保存记录检查与2022项源码绑定复用检查合计2045项独特检查；
编译、依赖、秘密、普通/暂存差异及实际索引/磁盘核对通过。没有重复老仿真。
8次预测拟合、8次独立重拟合分别计账；不是新物理响应模型或逆控制器资格。
16个原始gz已实际恢复并核对字节/CRC/行数，56个8MiB上限分片保留本地提交。

中文报告：reports/correction_scope_development_v1_zh.md。
本结果不证明完整任务收益、算法新颖性、物理安全或CCF A目标完成。
TOM、模型适用范围、OCCAM、GAUGE及任务相关获取/停止等近邻继续约束贡献。

来源树共{len(catalog)}文件，发布{sum(r['published'] for r in catalog)}个。
ARCHIVE_FILE_CATALOG_CORRECTION_SCOPE_RESULT_20261026.json列出全部来源路径、
大小、Git对象和SHA-256。原始大记录、二进制分片、恢复副本及完整历史仍在本地；
克隆本分支不含全部原始记录或本地历史。选择按类型/大小，不按成败。
相同Git对象复用先前哈希/秘密检查；新增发布对象实际读取并扫描。
'''
"""
text=text[:start]+note+text[end:]
text=text.replace('ARCHIVE_FILE_CATALOG_CORRECTION_SCOPE_FREEZE_20261026.json','ARCHIVE_FILE_CATALOG_CORRECTION_SCOPE_RESULT_20261026.json')
text=text.replace('Archive checked correction-scope A1 freeze d74cba1; collection results separate',f'Archive audited correction-scope A1 negative result {source[:7]}; full local records retained')
compile(text,str(out/'archive_checkpoint.py'),'exec')
(out/'archive_checkpoint.py').write_text(text,encoding='utf8',newline='\n')
print(out/'archive_checkpoint.py')

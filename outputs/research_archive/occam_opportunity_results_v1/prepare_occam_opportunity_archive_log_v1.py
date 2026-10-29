"""Prepare the append-only log adapter from the previously verified archive log."""
from pathlib import Path

AUX = Path(__file__).parent
s = (AUX / 'log_occam_qualification_results_v1.py').read_text(encoding='utf-8')
s = s.replace('occam_qualification_results_v1', 'occam_opportunity_results_v1')
for before, after in [
    ('a2a4b921bf9a3127ffcf71505cfda24c98f63a0f', '8d8bdadf610c08ffba5c61e4314f78b8e872b0e5'),
    ('46493049dcb4592aff27ed89df4e0cf6794715f2', '03fa9655ad4a6bdee6ca2b15adf213167cd4984b'),
    ("('33eb50dd25610763e3f24eaf59dd9d3f94384d52', 'previous_archive_metadata_committed_bytes')", "('bb120f1c554e27937c4ce1bad76d77423a07ce5e', 'previous_archive_metadata_committed_bytes')"),
    ("('d6f1bad4bff34a31d210ae2ec94045bd517b6af9', 'accounting_v2_freeze_committed_bytes')", "('dbae170a956f8cef3ee38376bb9c1f7253de98af', 'opportunity_freeze_committed_bytes')"),
    ('qualification_summary_committed_bytes', 'opportunity_result_committed_bytes'),
    ('== 226', '== 75'), ('27400913', '6334561'), ('phase_published=226', 'phase_published=75'),
    ('PASSED_RESULT_SUMMARY_ARCHIVE_APPEND_ONLY_LOG', 'PASSED_OPPORTUNITY_CENSUS_ARCHIVE_APPEND_ONLY_LOG')
]:
    assert before in s, before
    s = s.replace(before, after)
marker = "    log = ROOT / 'Research_Log.md'"
assert s.count(marker) == 1
s = s.replace(marker, "    assert sha(ROOT / 'outputs/occam_opportunity_census_v1/analysis_v1/statistics.json') == '0214bd46cb101b982de982ca93e75b228cf218d09bad97abf28b490b660c960a'\n" + marker)
i = s.index("    addition = f'''")
j = s.index("    with log.open('ab')", i)
body = '''

## {stamp}（北京时间）｜A主线完整固定程序机会普查与查新v10归档

- 先本地冻结dbae170a956f8cef3ee38376bb9c1f7253de98af：25文件257561字节，
  16项纯构造测试开发／正式各16执行，不算32个不同测试。旧2695科学
  检查与编译按1393源码及输入复用，未重跑仿真；冻结前禁止语义解析
  实际CSV。源码／输入、依赖、239.3527003秒秘密、补扫、差异与索引通过。
- 一次实际只读普查工作进程0.7313194秒、父过程1.4558944秒；独立
  CSV／标量／Fraction核对18224项，主模块全部10个函数禁用。共享
  CSV／JSON／SHA工具，不称物理重仿真。全部1740分配、QUAL1566与99
  失败登记，29程序、261组程序行、522格完整复算。实际CSV6读、7163行、
  668450字节，JSON、哈希、父准入和绘图费用另记。
- 同前缀12个固定程序的54单元、9独立组中，获取严格记录差额7/54，
  无差额47/54；提前成功8例不删除。固定PI_0125继续86.370步，四个
  CONTINUE逐单元事后最低C86.185，12菜单事后最低R64.556；增益选择
  记录差额0.185、获取记录差额21.630。它们使用未来结局及每程序一次
  噪声实现，不能作可部署损失、可学习性、期望收益上界或纯信息收益。
- 全部精确获取差额频数：0步47、1步2、3／47／359／360／397步各1。
  补充事后描述中，三个所有固定CONTINUE均失败单元贡献1116/1168步，
  来自两个独立组；不认定唯一原因，不据此缩人口。固定T在移动分支
  也可恢复，状态／等待／记忆／反馈影响未与新增信息分离。
- 结果提交`{SOURCE}`：31文件1450131字节与实际Git／磁盘一致；完整
  原图54单元、全部频数、18格及原失败保留。197.4013789秒秘密扫描、
  索引基本／EXTRA、依赖、编译与两差异通过，16项源绑定检查不重复。
  原十项统计dccede3a…、执行／预测通过而任务资格失败及封存决定不变；
  新统计0214bd46…已绑定。新增环境／reset／帧／政策或模型查询／拟合／
  训练／episode种子／在线LLM均0；guard有意拒绝测试不称实际网络／环境。
- v10原文检索与两技能问题优先／失败边界／简单参考筛选登记12候选。
  D-World、内生漂移conformal、动作条件风险、ASID／SPI-Active与上下文
  行为探索的已读范围、条件与未核实403线索均披露。测量修订、闭环
  展开、门控、信息矩阵、普通重加权和多头风险不自动成为新贡献。
- 下一件是独立冻结的TRAIN公开历史／完整后继标签支持审计，不立即
  训练或采集。TRAIN648来自三获取×两行为×18组，不是四T完整反事实
  表；随机后续的终局不贴给保持首T的程序，QUAL不回填TRAIN。实际
  时序支持、角色及原行为概率须先核对，标准完整风险／DR仍是强参考。
- 75个阶段文件6334561字节在推送前逐项比对实际归档对象／磁盘；
  本次10704归档文件、65个新源对象秘密扫描、6334441新Git字节哈希。
  普通快进并再次核对远端`{ARCHIVE}`，无合并／强推；旧133分片按精确
  Git身份复用历史恢复证明，没有新恢复。完整原始QUAL仍本地保留、
  ZIP／分片／三种恢复待空间，元数据清单不冒充内容恢复。本条远端
  核对后追加，本地元数据提交不递归推送。
- [中文机会普查](reports/occam_opportunity_census_v1_zh.md)。当前没有
  合格新算法、独立自身历史任务优势或消融；A方向和CCF A目标完整保留、
  继续未完成，不以标准菜单差额、测试或存档代替贡献。
'''
s = s[:i] + "    addition = f'''" + body + "'''\n" + s[j:]
compile(s, 'log_occam_opportunity_results_v1.py', 'exec')
target = AUX / 'log_occam_opportunity_results_v1.py'
assert not target.exists()
target.write_text(s, encoding='utf-8', newline='\n')
print('prepared append-only opportunity archive log')

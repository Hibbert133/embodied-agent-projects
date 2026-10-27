from pathlib import Path
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');out=ROOT/'outputs/research_archive/selective_coverage_v1';out.mkdir(exist_ok=False)
s=(ROOT/'outputs/research_archive/effect_horizon_v1/archive_checkpoint.py').read_text('utf8')
s=s.replace("PARENT='2a0f4aea1f2271deaed124f1ff1987f01386f582'","PARENT='736d54f16f44afe33886bbf1180ae364e9ede5f0'")
s=s.replace("SOURCE='39727830189cfb9ce63ac8aa167f3fb8d171f53a'","SOURCE='318e5ab0e93d4ed996435ee23eeebdd1d1fbceca'")
s=s.replace('outputs/research_archive/effect_learning_v1/catalog.json','outputs/research_archive/effect_horizon_v1/catalog.json')
s=s.replace('research_archive_build_effect_horizon_20261027_3972783','research_archive_build_selective_scope_20261027_318e5ab')
i=s.index("    note=f'''");j=s.index('    extras={',i)
note="""    note=f'''# 最新存档：长期覆盖不能直接推出选择采用的证据

来源结果{SOURCE}，数学冻结208a2bf，只读明文读取修复冻结7ce69b3。
父存档{PARENT}，普通快进，无强推或合并。全部是已知公式的精确构造，
不是机器人试验、SI-OCP复现/定理反驳、新算法、统计发现或论文成果。

固定延迟P1/2/4/8/16，每线程400预测，alpha1/20、eta1、q0=0；每20轮
首个分数1其余0，分数只在P个构造时间单位后揭晓。阈值用已保存预测
比较后递推。每线程热身20轮后才按当前q=0选择，不偷看当前/未来标签。

全部12400预测的覆盖恰为19/20，热身后589个被选预测覆盖恰为0。
选择数19/38/76/152/304，首被选标签到期21/42/84/168/336。阈值非负、
无舍入/筛样/负阈值/缺失标签，尾端等候全部pending标签揭晓。不同
线程/轮数不当独立机器人样本，未把分数未覆盖冒称任务不利更新。

主12400次有理数阈值校准更新、独立12400次整数更新分别计费，37210个
有序事件和全部12400CSV行发布。模型/任务/政策拟合、随机采样、机器人
创建/重置/控制步/帧/任务种子、固定政策查询、在线LLM均0。新unittest
计数0；旧2228仅源码绑定复用，数学由完整第二实现核验，不虚增测试数。

原独立读者在首条记录前误用gzip读取明文JSONL而失败，首失败和源码保留。
独立v2先冻结，只改读取与输出位置，主生成器禁用，整数数学逐字相同，
原记录SHA完全不变，主构造没有重跑。v2完整事件/时序/公式/分母/覆盖/
终端阈值独立核验通过，不把原pipeline失败改为成功。

中文报告reports/staggered_selective_scope_v1_zh.md。关闭的是以长期边际覆盖
直接支持选后采用可靠性的推论，保留正确的经验不确定性参考。SI-OCP/
CPC/online multivalid/MVP等已有研究，当前反例不是创新；源物理/观测/
Lipschitz/可行性假设没有被本项目满足，不移植任何安全保证。原A1/ARX/
F20/成对上下文/原生等旧负结果保持，未采集新机器人或复活旧资格。

编译、依赖、全仓秘密与新增索引补充扫描、普通/暂存差异、实际Git/磁盘
字节通过。新颖机制、同权限强对照、独立自身时序完整任务收益和消融仍
未建立，完整CCF A目标活跃。归档是保存习惯，不计科学贡献。

来源树{len(catalog)}文件，发布{sum(r['published'] for r in catalog)}。保留既有
逐路径类型/大小规则，不按成败筛除。旧原始.jsonl.gz/.bin分片/恢复仍在
本地；本轮全部新明文数学事件和失败记录均<8MiB并发布。完整来源对象/
SHA/大小/发布状态见ARCHIVE_FILE_CATALOG_SELECTIVE_SCOPE_20261027.json。
'''
"""
s=s[:i]+note+s[j:]
s=s.replace('ARCHIVE_FILE_CATALOG_EFFECT_HORIZON_20261027.json','ARCHIVE_FILE_CATALOG_SELECTIVE_SCOPE_20261027.json')
s=s.replace('Archive factual effect horizon diagnosis 3972783; zero new physics or LLM','Archive exact selective coverage scope 318e5ab; zero new physics or LLM')
compile(s,'archive_checkpoint.py','exec')
with (out/'archive_checkpoint.py').open('x',encoding='utf8',newline='\n') as f:f.write(s)
print(str(out/'archive_checkpoint.py'))

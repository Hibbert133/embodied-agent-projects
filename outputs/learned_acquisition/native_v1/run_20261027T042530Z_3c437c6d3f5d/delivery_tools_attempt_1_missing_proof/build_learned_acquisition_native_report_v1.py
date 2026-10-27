"""Chinese report: original qualification failure, supplementary audit and full costs."""
from pathlib import Path
from datetime import datetime,timezone
import sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import learned_acquisition_native_io_v1 as a
io=a.io;path=Path(sys.argv[1]).resolve();m=a.checked(path);run=path.parent;out=run/'result_delivery'
r=io.read(out/'results.json');sa=io.read(run/'training_signal/audit.json');na=io.read(run/'native_audit_repair_v2/audit.json')
report=ROOT/'reports/learned_acquisition_native_v1_zh.md';rows=[]
def add(text=''):rows.append(text)
def table(headers,values):
    add('| '+' | '.join(headers)+' |');add('| '+' | '.join('---' for _ in headers)+' |')
    for values_row in values:add('| '+' | '.join(str(x) for x in values_row)+' |')
    add()
def f(x):return '缺失' if x is None else f'{x:.6f}'

add('# 冻结模型原生接入与公开信号诊断：中文完整报告')
add()
add('**结论：本轮原生接入资格未成立。** 54例已实际采集，零在线LLM、零新拟合。原冻结审计在54例逐步重建后发生集合序列化软件错误；保留原失败，另行提交只读v2修复后完成补充核验。模型实际选择并执行了VALIDATE8或CONTINUE及不同PI时间常数，但从未选择MOVE_MEASURE，预定完整神经移动链为0。不能用强制参考的移动、全体任务成功或较低均值替代这个验收条件。')
add()
add('以下全部新增统计均为**事后描述性分析或软件接入核验**。它们不是新算法独立任务收益资格、物理响应模型资格、安全保证或CCF A贡献证据。旧人口、原六项比较、ARX/响应模型/FULL-MASK等既有负结果保持原样。')
add()
add('## 范围、冻结与程序含义')
add()
add(f"运行 `{m['experiment_run_id']}`；原冻结 `{m['source_git_commit']}`；只读审计修复冻结 `{na['repair_source_git_commit']}`。使用新种子90000–90008，90009–90999预留，3组×3任务×2条件×3程序=54次；同单元程序共用初始状态和噪声，单次500步上限。源bank固定首个fold0，不选最佳折、不重训。")
add()
table(['名字','通俗解释','真实执行'],[
('LEGACY_REFERENCE','旧程序参考','16步边界继续PI.5；32步验证8步后PI.125；64步移动测量后PI.5'),
('DYNAMIC_FORCED_REFERENCE','强制新接口采用相同选择','核对新接口没有改变旧程序物理行为；不是学习结果'),
('LEARNED_JOINT_BANK0','冻结风险选择模型','前置RBF选获取程序，返回后神经模型选PI时间常数；不是在线LLM或已资格化物理逆模型')])
add('JOINT表示源训练中同时预测纠正后未来查询分布与误差联合量来辅助完整任务风险打分；SPO表示面向选择排序的训练目标。原始分数不是校准成功概率，SPO分数也不宜直接解释为精确绝对成本。PI时间常数是积分适应速度：.125较快，.5为原设置，2/8较慢；保留已有积分，不是重置或旧ARX限幅混合。')
add()
add('PRE输入先保存，模型分数/选择随后保存，执行器消费保存选择。返回真实当前节点后先做POST选择，再采用时间常数。模型只看当前公开观测/已发生历史和任务记忆；不接触种子、条件、真实扰动、噪声、witness或未来结果。这里“实时”指当前实际观测，未声称硬件实时期限；推理期间模拟时钟不推进。')
add()
add('## 新采集结果：完整分母')
add()
table(['程序','成功/全部','平均截止损失↓','总损失','实际控制步','移动步','登记验证/测量步'],[(p,f"{s['success']}/{s['n']}",f(s['mean_deadline_loss']),s['total_deadline_loss'],s['actual_steps'],s['movement_steps'],s['measurement_steps']) for p,s in r['programs'].items()])
add('三个程序各18例全部成功，无自然任务失败（`all_native_failures.json`为空数组）；软件审计失败单独保留。成功提前结束的4个模型案例不发起决定，不能计作主动适应成功。模型实际14次PRE和14次POST：VALIDATE8 12次、CONTINUE 2次、MOVE 0次；率.125 13次、8.0 1次，另4例无率。')
add()
add('VALIDATE8是在原PI.5下继续原任务8步，然后才改变率，全部沿用反馈与物理状态；不能冒充独立诊断探测。模型96个“验证步”已经包含在1435个总控制步和1435次实际策略查询内，不能再收费一次。参考登记测量56步中32步也属原任务验证，另24步为真实测量；其206移动步和24宏测量步已经包含在1886总步中。')
add()
table(['新组/边界','旧参考均值','新强制参考均值','模型均值','模型−参考'],[(f"{g['group']}/{g['boundary']}",*[f(g['programs'][p]['mean_deadline_loss']) for p in a.PROGRAMS],f(g['programs']['LEARNED_JOINT_BANK0']['mean_deadline_loss']-g['programs']['LEGACY_REFERENCE']['mean_deadline_loss'])) for g in r['groups']])
q=r['paired_descriptive']
add(f"18个实际配对差：模型较差{q['worse']}、较好{q['better']}、相同{q['tie']}；总不利严重度{q['total_harm']}步、总改善{q['total_help']}步，净差{q['total_difference']}步、平均{f(q['mean_difference'])}。成功转失败及反向均0。独立统计单位仅3组，未把54程序执行、28模型调用或逐时间步当独立样本，也不提供功效充足的推断或挑子集CI。")
add()
add('净改善451步中的418步来自边界64组避开参考的固定移动过程；该组参考本就为覆盖接口路径而固定MOVE。这不能证明模型优于廉价固定程序。没有在本人口同时比较DIRECT_C8、积分、固定CONTINUE/.125、固定VALIDATE8/.125及标准获取/重加权强参考，因此不进入独立任务收益阶段。')
add()
table(['全部不利配对案例','参考','模型','差值','模型选择'],[(str(x['unit']),x['reference_loss'],x['learned_loss'],x['loss_difference'],f"{x['learned_action']}/{x['learned_rate']}") for x in io.read(out/'all_paired_differences.json') if x['loss_difference']>0])
add('push变化例的+218步不能唯一归因于率8.0：获取动作/采用时点也改变，只观察各程序自己的事实轨迹，没有同一返回状态下未执行率的反事实任务结局。全部18对差和54条结果另存JSON，下表无挑选。')
add()
add('## 审计与预定行为链：未通过项保持未通过')
add()
table(['项目','实际','解释'],[
('原冻结v1审计','失败','同一单元程序键被转为set后传入不支持set的JSON规范化；原错误/源码/查询保留'),
('只读v2补充核验','通过','排序列表比较，缺失/额外键仍拒绝；不追认v1冻结资格'),
('全部54例逐步记录','核对完成','独立推理数学、PI/命令、float32变换→实际噪声→最终裁剪、时钟/成本/witness'),
('强制新/旧程序整轨迹','18/18相同','物理轨迹、最终原生和Python/RNG状态相同'),
('三程序共同前缀','36/36相同','未在决策边界前偷偷改动作'),
('隐藏条件PRE','9对一致','7对有实际PRE决定，2对双方在边界前结束；不能称9对真实查询'),
('非默认真实模型程序','14例','消费保存动作/率；10例实际发送命令与参考不同'),
('神经MOVE→实测→保存POST纠正→真实尾段','0条','预定行为链未建立，不能补样、换折或把参考MOVE算进来'),
('预算/衔接/泄漏/权重变化','补充核验均0违规','没有恢复世界、重新播种噪声、时钟倒退或在线拟合')])
add(f"补充核验禁用新actor/主模型推理，按独立数学重建真实选择；规范重放仅在记录反馈上复算固定策略命令，共{na['audit_fixed_policy_queries']}次策略查询，不推进物理。原v1在失败前已完成同样54例重放，按失败位置与代码推算另{na['audit_fixed_policy_queries']}次（原失败回执未单独保存该计数，明确标为推算）；合计9494，不超过原27000审核查询预算。二者使用共享旧宏原语和NumPy，不是独立物理重模拟、不同框架或独立机构。v1/v2导出的查询与决定解压后SHA完全相同。")
add()
add('## 旧TRAIN信号：事后描述性分解')
add()
add('648例全部登记；536个真实未来窗口、134个唯一实际过去窗口。过去按单元×获取动作仅固定率.5的一份计数，并核对其他率的历史相同。72例边界前已结束，40例获取时结束，不填零。过去有18个16步、18个24步及98个32步窗口；未来383个满32步、153个短窗口。从真实初始观测顺序重建，不伪造最早位移。')
add()
add('仅使用公开发送命令u和相邻观测d=ΔXY/.01，逐步计算 E=||d−u||²、U=||u||²、D=||d||²、C=2d·u。恒等式E=U+D−C的最大数值差为'+f"{r['signal']['maximum_identity_gap']:.3e}"+'。实际噪声、扰动和私有witness值不进入本信号；完整来源按字节校验。')
add()
table(['量','先轨迹内、再独立组平均'],[(k,f(v)) for k,v in r['signal']['overall']['equal_group_means'].items()])
add(f"仅用命令能量U替代观测误差E的轨迹相对L2误差，再按9组等权平均为{r['signal']['overall']['equal_group_command_only_relative_l2']:.6f}；各组从1.147231至7.200044。D和C量级不可忽略且可抵消，因此‘这个误差就是命令能量’的简化解释不获完整人口支持。反过来，这也不证明JOINT学到了唯一物理机制、可提前预测这些量或能改善获取决策。")
add()
table(['任务','条件','登记/可用','E','U','D','C','U替代E的相对L2'],[(c['values'][0],c['values'][1],f"{c['registered']}/{c['available']}",*[f(c['equal_group_means'][k]) for k in ('error','command_energy','motion_energy','alignment')],f(c['equal_group_command_only_relative_l2'])) for c in io.read(out/'source_future_cells.json') if c['axes']==['task','context']])
add('`source_future_cells.json`还保存全部任务×条件×边界×获取动作×率及各独立组的分母/缺失/均值；逐步CSV共18443行，规范过去不被四份率重复加权。未来四率访问不同真实状态与动作，只作事实描述；不能由相关性或代数恒等式断言接触、反馈噪声或模型失配的唯一因果来源。原工作模型未资格化，E不是物理无噪声误差，命令能量也不是任务收益。')
add()
add(f"独立标量复算禁用主分解入口，核对{sa['independent_signal_fields']}个字段；完整描述统计另独立核对9310字段。新增环境/拟合/策略实采查询/API均0。旧统计SHA仍为`d567b1a827b11edb1237b20f59d554fc1cf1a91733adc58b8b614e370c7826a4`，原六项比较未重算或更改。")
add()
add('## 全部成本、准备错误及数据保存')
add()
table(['项目','本轮实际','上限/来源'],[
('新物理执行','54','54，一次分配无重采'),('控制步','5207','27000'),('受控初始重置','54','54'),('全部重置','2754','2754，含2700次工厂goal-generation'),
('物理帧','1403035','1512000，其中控制26035、重置1377000'),('实际固定策略查询','4747','27000，宏移动/测量无原策略查询'),
('真实模型决定','28','36；14 PRE +14 POST，RBF及神经调用各14'),('新增训练/拟合','0','源权重直接字节导出'),('在线LLM/API','0','网络传输尝试0'),
('两个原生审计的策略重放','9494','4747已记录+4747由原失败位置推算；不产生物理步'),('采集墙钟','341.499465秒','包含工厂/记录，调用包装347.381868秒'),
('查询保存到选择保存间隔',f"均值{r['live_interval_mean_ms']:.3f}ms、最大{r['live_interval_max_ms']:.3f}ms",'含主机/序列化，不是隔离纯推理延迟或硬件实时保证')])
add('“模型决定28”是本地学习模型计算，并非在线LLM；其中只有POST14次为神经网络。早期进度中的“模型决策”统指RBF和神经两阶段，不把28误报为28次神经推理。源TRAIN物理648次/77563步/33048全部重置/16911815帧另列，不免费化；源学习15神经模型15000SGD及15前置RBF、后续消融9神经9000SGD及9RBF，独立复算各同量，均不是本轮新增。')
add()
add('准备阶段保留：首次导出缺少assets父目录；首次冻结检查发现活跃源码末尾空行与历史快照格式问题；图形首版字体缺少下标2。全部发生在对应阶段交付前，未增采或重训。原快照/失败/首图保留，修复当前源码格式与局部精确字节规则。原生v1审计失败另有单独冻结修复提交，不与这些准备错误混同。')
add()
pack=io.read(run/'record_archives/index.json')
add(f"原始gzip全部留本地；5个日志文件共{sum(x['bytes'] for x in pack['files'])}压缩字节，提交{sum(len(x['parts']) for x in pack['files'])}个≤4MiB分片及索引。已在新的独立目录实际拼接，核对原字节SHA、完整gzip CRC和UTF-8 JSON；恢复副本继续保留。紧凑远端存档按既定类型/大小规则排除原始.jsonl.gz和.bin分片，完整原始记录并非从该分支直接克隆可得；发布完整54例结果、全部配对、分格、模型和哈希索引。")
add()
add('新增23项数组接入测试和2项集合回归测试，加2158项源码绑定旧检查，共2183唯一检查；重复开发运行不增加唯一数。旧六组张量检查另列。编译/依赖、已通过全仓秘密回执与未变旧源码绑定、新暂存基本及补充秘密扫描、普通/暂存差异、索引与磁盘、实际提交对象字节核对分阶段完成。')
add()
add('## 查新与A主线的下一判断')
add()
table(['已有路线','本轮如何约束贡献主张'],[
('[模型适用范围/MDE](https://arxiv.org/html/2401.04007v2)','状态/动作相关的模型适用性已有研究，不能以门控本身称新颖'),
('[Residual RL](https://arxiv.org/abs/1812.03201)','基础控制加修正的路线已有；选择PI率不是新控制理论'),
('[OCCAM](https://arxiv.org/html/2406.17620v1)','性能预测驱动适应已有，单独风险打分器不构成新贡献'),
('[GAUGE](https://arxiv.org/html/2609.32154v1)','候选实际逆命令处的不确定性惩罚已写入目标；其稳态/固定控制条件与动态状态适用性须逐项对照，不能声称“逆控制考虑不确定性”是新区别'),
('[Poke and Strike](https://proceedings.mlr.press/v305/aoyama25a.html)','任务敏感的探索与停止已有，短验证或预算停止不是新颖点')])
add('本轮复核GAUGE官方摘要和部分HTML公式/讨论、Poke and Strike官方摘要；后者PDF工具读取失败，未宣称完整复现。其他路线沿用已保存查新记录，后续仍须补齐同预算实现、源码核对和消融。')
add()
add('**当前决定：封存本轮原生接入负结果，不将bank0晋升最终评价，不追加同人口或换折补救。** A主线保留为研究问题：纠正改变后续状态与动作后，已有模型/探测是否仍适用。本轮没有模型主动移动，因此不能回答其中“获取动作改变物理状态后如何决定”的关键部分。')
add()
add('后续应先建立具体、可证伪的机制区别及新独立开发协议：把简单重加权、固定廉价CONTINUE/.125和VALIDATE8/.125、完整任务成本风险/DR、标准检测/历史辨识以及任务相关获取作为强参考；训练、校准和最终自身时序历史分开。不要把未来误差拟合质量当任务收益，也不能把改写Q或普通辅助学习当新机制。原ARX和已关闭资格不重启；不直接启动新的大批采集。CCF A研究目标仍未完成。')
add()
add('## 图与完整结果索引')
add()
figure=(out/'figures/native_and_signal.png').as_posix();add('!['+'全部原生结果与信号分解'+']('+figure+')');add()
add('原版和补充审计、来源清单、全部分片与恢复证明位于运行目录。主要复算入口与表：')
add()
for name in ('results.json','all_native_cases.json','all_native_failures.json','all_paired_differences.json','native_group_task_context_cells.json','source_future_cells.json','all_live_decision_wall_intervals.json','independent_descriptive_audit.json'):
    add(f"- [{name}]({(out/name).as_posix()})")
add()
table(['组','任务','条件','程序','成功','截止损失','选择'],[(x['group'],x['task'],x['context'],x['program'],int(x['success']),x['deadline_loss'],f"{x['selected_action']}/{x['selected_rate']}") for x in io.read(out/'all_native_cases.json')])
with report.open('x',encoding='utf8',newline='\n') as stream:stream.write('\n'.join(rows)+'\n')
io.write(out/'report_receipt.json',dict(report_sha256=io.sha(report),source_manifest_sha256=io.sha(path),
    source_results_sha256=io.sha(out/'results.json'),original_frozen_qualification='FAILED_RETAINED',new_physics=0,new_fits=0,online_LLM_API_calls=0,
    utc=datetime.now(timezone.utc).isoformat()))
print(str(report))

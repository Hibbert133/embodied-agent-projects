"""Documentation/ownership finalization after passed numerical tests; no reruns."""
from pathlib import Path
import gzip,shutil,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import occam_reference_train_io_v1 as a
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
io=a.io;out=a.VALIDATION;q=io.read(out/'complete.json');assert q['integrity']=='PASSED'
for n,h in q['source_sha256'].items():assert io.sha(ROOT/n)==h,n
io.write(out/'formal_before_text_clarification.json',q)
text=a.PROTOCOL.read_text('utf8');needle='共享预训练只支付一次，总尝试9000、Adam更新<=9000；空batch不更新、不重抽。'
assert text.count(needle)==1;text=text.replace(needle,needle+'\n匹配的是更新尝试数与案例曝光，不声称FLOPs或墙钟相等；META的额外滤波/\n反传费用必须单列。');a.PROTOCOL.write_text(text,encoding='utf8',newline='\n')
decision=ROOT/'docs/research/occam_reference_training_decision_v1_zh.md';text=decision.read_text('utf8').replace('同案例曝光、同预算ERM长分支','同案例曝光、同更新尝试数ERM长分支（不称同FLOPs）');decision.write_text(text,encoding='utf8',newline='\n')
report=ROOT/'reports/occam_reference_train_freeze_v1_zh.md'
report.write_text('''# OCCAM相关参考训练：冻结交付

已实现行为采集、完整记录审计、公开训练投影、mask保持标准化、原单位JSON
导出、两阶段可微训练及预算/案例曝光匹配的普通ERM。该软件阶段未进行新的
机器人采集或科学模型训练，未开放CAL/QUAL，不代表任务收益、新机制或CCF A。

新增25项主运行时与7项隔离训练检查全部通过，32唯一项；原2522项按源码哈希
复用，共2554。开发/正式共64次测试执行，合计2次合成Adam更新，不能叫零训练。
NumPy每次6次求解，Torch每次8次求解/24次协方差谱；环境创建、重置、推进与
联网均0。没有读旧人口拟合、挑模型或选阈值。编译与两环境依赖、秘密、实际
索引BASIC/EXTRA/解压及差异检查通过；原大种子清单留本地，gzip实际恢复一致。

已固定NATIVE36项及TRAIN648项，三任务、两条件、三获取、随机/固定块两行为。
新物理上限342000控制步、684受控初始重置、34884全部重置、19152000物理帧。
所有提前结束、无窗口、失败均保留，不补采；同一次执行环境/噪声/时钟连续。
预训练1000尝试后分叉META4000与普通ERM4000，共享部分只执行一次，最大9000
Adam更新、1000000显式Torch求解、7200秒。空batch无更新、不重抽；不选最佳
checkpoint。匹配更新尝试和数据曝光，不声称相同FLOPs或墙钟；额外滤波单列。

训练仅从自身已审计TRAIN公开历史/实际窗口标签读取。终止短窗参与评分而不
进入支持集；无窗口登记缺失。meta支持覆盖最长实际完整非终端前缀，不因
长失败难学删掉这些历史。标准化只拟合TRAIN，填充保持零；导出以固定零方差
常数基恢复目标均值并缩放测量协方差，数值递归与Torch/NumPy检查通过。

原主机资格36执行/4203步/939015帧、旧核心1次合成Adam作为历史费用另列，
不隐藏为免费来源。采集与训练失败停止并保存，不重跑/补样或换checkpoint。
未来CAL/自身时序资格仍需单独冻结完整比较，保留DIRECT_C8、积分、廉价四T/
同历史被动适应及所有强参考/消融，以完整截止损失评价，不能用窗口MSE替代。

来源：[冻结协议](../docs/protocols/occam_reference_train_v1_zh.md)、
[决定记录](../docs/research/occam_reference_training_decision_v1_zh.md)、
[正式回执](../outputs/occam_reference_train/freeze_validation_v1/complete.json)。
''',encoding='utf8',newline='\n')
helper=out/Path(__file__).name;shutil.copyfile(__file__,helper);compile(helper.read_bytes(),str(helper),'exec')
source=dict(q['source_sha256'])
for p in (a.PROTOCOL,decision,report,helper):source[p.relative_to(ROOT).as_posix()]=io.sha(p)
changed=[n for n,h in q['source_sha256'].items() if io.sha(ROOT/n)!=h];assert set(changed)=={a.PROTOCOL.relative_to(ROOT).as_posix(),decision.relative_to(ROOT).as_posix()}
q.update(source_sha256=source,numerical_sources_and_tests_unchanged_after_formal=True,only_text_budget_clarification_after_formal=True)
io.write(out/'complete.json',q,exclusive=False);io.write(out/'text_clarification.json',dict(integrity='PASSED',changed_non_executable_sources=changed,new_physics=0,tests_or_optimizers_not_repeated=True))
names={n.decode() for n in (out/'owned_final.nul').read_bytes().split(b'\0') if n}|set(source)
names|={p.relative_to(ROOT).as_posix() for p in out.rglob('*') if p.is_file()}
path=out/'owned_final_delivery.nul';names.add(path.relative_to(ROOT).as_posix());path.write_bytes(b'\0'.join(n.encode() for n in sorted(names))+b'\0')
io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+path.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
actual=index_bytes(names)
for n in actual:
    data=(ROOT/n).read_bytes()
    if n.endswith('.gz'):data=gzip.decompress(data)
    if b'\0' in data:continue
    text=data.decode('utf8',errors='replace');assert find_secret_rule(text) is None and not any(p.search(text) for p in EXTRA.values()),n
assert not io.git('diff','--check') and not io.git('diff','--cached','--check')
io.write(out/'final_index_proof.json',dict(integrity='PASSED',actual_index_basic_extra_decoded_scan=True,object_sha256=actual))
io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--',(out/'final_index_proof.json').relative_to(ROOT).as_posix());index_bytes(names|{(out/'final_index_proof.json').relative_to(ROOT).as_posix()})
print(dict(integrity='PASSED',objects=len(names)+1,unique_tests=2554,new_physics=0),flush=True)

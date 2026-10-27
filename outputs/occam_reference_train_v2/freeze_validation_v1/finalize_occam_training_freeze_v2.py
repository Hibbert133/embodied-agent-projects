from pathlib import Path
from time import perf_counter_ns
import gzip,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import occam_reference_train_io_v2 as a
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
from outputs.information_release.validation_v1.validate_freeze import index_bytes
io=a.io;out=a.VALIDATION;start=perf_counter_ns();complete=io.read(out/'complete.json')
assert complete['integrity']=='PASSED'
for n,h in complete['source_sha256'].items():assert io.sha(ROOT/n)==h,n
old=a.PROTOCOL.read_text(encoding='utf8')
old_phrase='源码绑定复用原2522项，新增检查独立计数；'
assert old_phrase in old
before=io.sha(a.PROTOCOL)
a.PROTOCOL.write_text(old.replace(old_phrase,'源码绑定复用原2558项，新增13项；隔离7项数值复跑不重复增数；'),encoding='utf8',newline='\n')
complete['source_sha256'][a.PROTOCOL.relative_to(ROOT).as_posix()]=io.sha(a.PROTOCOL)
io.write(out/'final_document_source.json',dict(integrity='PASSED',only_changed_frozen_file=a.PROTOCOL.relative_to(ROOT).as_posix(),
    before_sha256=before,after_sha256=io.sha(a.PROTOCOL),reason='correct the inherited prior test count; no executable, allocation, model, cost or threshold changes',
    original_tested_document_preserved_in_snapshot=True,code_tests_repeated=False))
complete['final_document_source_sha256']=io.sha(out/'final_document_source.json');io.write(out/'complete.json',complete,exclusive=False)
report=ROOT/'reports/occam_reference_train_freeze_v2_zh.md'
text='''# 独立表现参考采集与训练v2：冻结交付

本阶段修复真实收集器案例cohort与事件phase的命名冲突，并建立独立新人口；
尚未新增物理数据或科学模型训练。v1技术失败保持关闭，全部记录、种子及预留
保留。目标仍是A主线：纠正改变实际状态/动作后，模型与获取是否适用。

学习器逐字比较仅有分配模块导入不同，学习配置、控制器、全部物理上限保持
原协议。新NATIVE36项必须先通过完整独立记录审计，才开放TRAIN648及一次
离线标准表现网络训练。校准与最终自身历史任务资格未开放。

正式根运行时12项检查通过，覆盖真实collector+JsonJournal+LifecycleLedger
的数组delegate、私有事件、异常不重试、所有权拒绝，以及36/648完整人口流。
数组callback的合成reset/frame计数不是实际环境交互。隔离8项执行通过，
其中7项重跑同一数学算法，1项新增拒绝v1数据路径；源绑定复用2558项，新增
13项，共2571项。工程检查不能替代原生数据或论文贡献。

本v2开发与正式隔离共2次构造Adam、16次Torch求解、48次谱分解，无科学数据
拟合、环境创建、真实reset、物理推进或在线LLM。全部数组fixture明确保留在
array_integration_fixtures_v1，不能用于原生或科学训练。编译、两环境依赖、
旧源哈希、实际恢复的双解析器种子清单、秘密扫描、索引/磁盘及差异检查通过。
临冻结仅更正协议继承的旧测试计数；保留原测试快照和独立文档变更回执。

新物理上限684次执行、342000控制步、34884次全部reset及19152000物理帧；
每次最多500步，环境/随机数/时钟连续，全部失败保留。共享训练最多9000次
Adam、1000000次显式Torch求解和7200秒；真实费用另外记录，不能以预算冒充
已经花费。历史来源和v1失败工厂尝试另列。零在线LLM。

下一步按冻结协议一次执行NATIVE→审计→TRAIN→审计→训练→独立数学审计；
失败停止、不补样本、不重启训练。数学合法性、当前预测力及含获取成本的
任务收益分别评价。OCCAM相关性能回归、元学习和势差成本均为已有强参考；
新获取机制、强对照完整任务优势、消融和CCF A目标仍未完成。
'''
with report.open('x',encoding='utf8',newline='\n') as f:f.write(text)
copy=out/Path(__file__).name;copy.write_bytes(Path(__file__).read_bytes())
names=set(io.git('diff','--cached','--name-only').splitlines())|{report.relative_to(ROOT).as_posix()}
def stage(label):
    global names
    names|={p.relative_to(ROOT).as_posix() for p in out.rglob('*') if p.is_file()}
    q=out/(label+'.nul');names.add(q.relative_to(ROOT).as_posix());q.write_bytes(b'\0'.join(n.encode() for n in sorted(names))+b'\0')
    io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+q.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
def check():
    actual=index_bytes(names)
    for n in actual:
        data=(ROOT/n).read_bytes()
        if n.endswith('.gz'):data=gzip.decompress(data)
        if b'\0' in data:continue
        text=data.decode('utf8',errors='replace');assert find_secret_rule(text) is None and not any(p.search(text) for p in EXTRA.values()),n
    assert not io.git('diff','--check') and not io.git('diff','--cached','--check');return actual
stage('final_documents_initial');proof=check()
for n,h in complete['source_sha256'].items():assert io.sha(ROOT/n)==h,n
io.write(out/'final_documents_proof.json',dict(integrity='PASSED',objects=len(proof),object_sha256=proof,actual_index_basic_extra_decoded_scan=True,
    all_executable_tested_sources_unchanged=True,new_physics=0,online_LLM_API_calls=0,wall_ns=perf_counter_ns()-start))
stage('final_documents_owned');check();print(dict(integrity='PASSED',objects=len(names),new_physics=0),flush=True)

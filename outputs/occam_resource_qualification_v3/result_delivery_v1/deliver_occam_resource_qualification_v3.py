from pathlib import Path
from time import perf_counter_ns
import shutil,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import occam_resource_qualification_v3 as q
from src.analysis import occam_resource_process_v3 as p
from src.analysis import response_qualification_io_v1 as io
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
from outputs.information_release.validation_v1.validate_freeze import index_bytes
started=perf_counter_ns();q.verify_freeze();out=p.OUTPUT/'result_delivery_v1';out.mkdir(exist_ok=False)
audit=p.read(q.RUN/'audit.json');complete=p.read(q.RUN/'complete.json');frozen=p.read(q.FREEZE)
assert audit['integrity']=='PASSED_SOFTWARE_CONTRACT_ONLY' and complete['launches']==8 and complete['unresolved_attempts']==[]
assert audit['source_local_commit']=='8d201a40f99d19042a61811004008541d3c924df' and audit['complete_sha256']==p.sha(q.RUN/'complete.json')
sources=frozen['source_sha256'];inputs=frozen['input_sha256']
for n,h in {**sources,**inputs}.items():assert p.sha(ROOT/n)==h,n
records={n.relative_to(ROOT).as_posix():p.sha(n) for n in q.RUN.rglob('*') if n.is_file()}
receipt=p.read(q.RUN/'job07/receipt.json');assert receipt['payload']['platform_query']['optional_command_calls_suppressed']==1
assert receipt['payload']['guard']['online_LLM_API_calls']==0 and not any(receipt['payload']['guard']['operation_counts'].values())
prior=[p.read(ROOT/('outputs/occam_resource_qualification_v%d/qualification_v1/complete.json'%v)) for v in (1,2)]
all_workers=sum(x['launches'] for x in prior)+complete['launches'];all_ns=sum(x['wall_ns'] for x in prior)+complete['wall_ns']
assert all_workers==22
shutil.copyfile(Path(__file__),out/Path(__file__).name)
proof=Path(__file__).parent/'occam_core_postcommit_8d201a40f99d.json';assert p.read(proof)['integrity']=='PASSED';shutil.copyfile(proof,out/'freeze_committed_bytes.json')
report=ROOT/'reports/occam_resource_qualification_v3_zh.md'
with report.open('x',encoding='utf8',newline='\n') as f:
    f.write('''# 资源观测与进程软件资格v3：通过软件契约

2026-10-28。**8项正式软件契约符合预期，独立只读审计通过。** 这只完成
资源／启动／回执／进程生命周期的软件前提，真实原生collector、连续性、
模型训练、任务收益及研究新颖性均未因此合格，CCF A目标仍未完成。

## 冻结、来源和检查

冻结8d201a40f99d19042a61811004008541d3c924df。先执行43项纯字典／假句柄
检查，再本地提交冻结，之后一次实际8进程资格，没有重试或追加。
43项包括35项原契约回归与8项新增平台回退／恢复／来源拒绝检查；旧2621项
源码绑定复用，唯一累计2629。编译和两个依赖环境检查均通过。
秘密扫描沿用c55d094已通过的完整tracked基线；之后变更对象逐次实际暂存
补扫基础／扩展规则并核对字节，不把历史未重跑检查冒称本次实际执行。
原v1／v2源文件、失败和未启动记录，以及关闭的科学TRAIN来源哈希不变。

v3在受限导入上下文令CPython可选ver命令不可用，使用原win32_ver已有的
本机API回退。标准库文件精确哈希绑定freeze／请求／start／receipt。
第7项实际抑制1次可选命令，本机API版本[10,0,20348]，退出后恢复原函数。
没有编造版本、架构、主机名或uname缓存；连接、DNS及Python后代创建继续
拒绝。此固定可信软件契约不是通用系统沙箱或安全保证。
依据：[锁定CPython源码](https://github.com/python/cpython/blob/v3.10.11/Lib/platform.py)、
[本机版本API文档](https://docs.python.org/3.10/library/sys.html#sys.getwindowsversion)。

## 全部正式项目

| 项目 | 实际结果 | 独立审计含义 |
| --- | --- | --- |
| 1 RETURN4096 | RETURNED | 真实小bytes长度／哈希正确 |
| 2 RETURN8192 | RETURNED | 真实小bytes长度／哈希正确 |
| 3 构造嵌套异常 | WORKER_EXCEPTION | 完整因果异常栈；是期望软件负例 |
| 4 无回执exit17 | UNRECEIPTED_EXIT | 保留缺失回执和退出17，无备用成功 |
| 5 1秒挂起 | TIMEOUT_TERMINATED | 只终止本次拥有句柄，退出已确认 |
| 6 nonce篡改 | INVALID_RECEIPT | 保存并拒绝篡改，不改为合法回执 |
| 7 运行时导入／原依赖核对 | RETURNED | 平台回退及完整只读守卫回执通过 |
| 8 RETURN65536 | RETURNED | 实际完成，无未启动或补样 |

期望错误属于契约检查，不能说成8次成功机器人任务。第7项守卫的环境创建、
reset、simulation、solve、lstsq、cold-fit及联网尝试全部0。
本轮政策查询、科学拟合／优化及在线LLM API同为0。
主执行46.0227961秒；冻结检查12.8738138秒、独立审计约0.092秒另列。
进程峰值私有提交最高553144320 bytes（约527.5MiB），来自第7项导入；
其余约9.3–9.5MiB。它们不代表原生模型峰值或原OOM失败分配大小。
运行时导入期间父观察器最小可用提交约1.505GiB，仍高于软件512MiB门。

独立审计关闭主runner／分类／规格、资源读取／解码／门和Popen，逐字节
核对全部原始stdio与回执哈希、PID／nonce／源码／平台绑定和时间顺序，
复算系统页／字节、提交余量、期望错误与预算。没有重启worker或仿真。

## 所有失败和完整费用边界

| 软件版本 | 真实启动 | 正式结论 | 主执行秒 |
| --- | ---: | --- | ---: |
| v1 | 7／8 | 主机名事件误拦，已关闭，第8项未启动 | 3.885 |
| v2 | 7／8 | 可选ver后代被拒绝，已关闭，第8项未启动 | 3.421 |
| v3 | 8／8 | 软件契约通过 | 46.023 |
| 合计 | 22 | 不是22个科学样本 | 53.329 |

原失败没有被v3替换或追认通过。两次第8项指标null，开发夹具／换行差异
等记录亦保留。主执行和不含源码扫描／开发／归档耗时，其他回执各自保留。
新增机器人环境／全部reset／控制步／物理帧／科学模型训练／在线API均0。
历史科学NATIVE+不完整TRAIN另列27982控制步／11475全部reset／5877410帧，
188完整／1部分／459未启动与所有预留仍关闭，不用前缀绕过648项训练门。

## 资源预检与下一研究步骤

一次科学入口观测：可提交余量2255056896 bytes（约2.10GiB），
磁盘4745199616 bytes（约4.42GiB）。4GiB提交门未通过；本阶段无论是否
过门都没有开放物理采集。观测易变，门槛不预留资源或保证未来分配。
物理可用内存、地址空间、工作集与提交余量不能互相替代。

下一步实现原生collector的有界进程生命周期，并单独冻结新分配／全部
费用与独立资格。任务内世界／随机数／时钟保持连续，工厂50次与受控1次
reset都计费；不恢复已发生位移，不减弱完整原生见证，不重开旧TRAIN。
真实环境峰值、完整异常路径及跨进程日志连续性仍需实际资格，不能由本次
无环境导入取代。资源不足时只继续无交互实现／测试，不降低冻结门槛。

A主线研究的是纠正改变后续状态／动作后的模型和获取适用性。当前软件
不是新机制，也未填补标准完整任务风险／DR强参考的缺口。独立自身历史
任务收益、完整费用、强对照／消融与具体既有路线区别仍须分别验证。
''')
names={n.relative_to(ROOT).as_posix() for n in q.RUN.rglob('*') if n.is_file()}|{report.relative_to(ROOT).as_posix()}
def stage(label):
    global names
    names|={n.relative_to(ROOT).as_posix() for n in out.iterdir() if n.is_file()}
    file=out/(label+'.nul');names.add(file.relative_to(ROOT).as_posix());file.write_bytes(b'\0'.join(n.encode() for n in sorted(names))+b'\0')
    io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+file.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
def check():
    actual=index_bytes(names)
    for n in actual:
        data=(ROOT/n).read_bytes()
        if b'\0' in data:continue
        text=data.decode('utf8',errors='replace');assert find_secret_rule(text) is None and not any(x.search(text) for x in EXTRA.values()),n
    assert not io.git('diff','--check') and not io.git('diff','--cached','--check');return actual
stage('owned_checked');proof=check();p.write(out/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=proof,actual_index_basic_extra_scan=True))
for n,h in {**sources,**inputs,**records}.items():assert p.sha(ROOT/n)==h,n
p.write(out/'complete.json',dict(integrity='PASSED_SOFTWARE_QUALIFICATION_DELIVERY_ONLY',source_sha256=sources,input_sha256=inputs,
    record_sha256=records,qualified_software_jobs=8,cumulative_software_launches=all_workers,cumulative_main_execution_ns=all_ns,
    new_environment_operations=0,new_fits=0,online_LLM_API_calls=0,science_collection_opened=False,native_continuity_not_qualified=True,
    scientific_training_and_task_benefit_not_qualified=True,publication_goal_complete=False,wall_ns=perf_counter_ns()-started))
stage('owned_final');check();print(dict(integrity='PASSED_SOFTWARE_QUALIFICATION_DELIVERY_ONLY',owned_files=len(names),software_jobs=8),flush=True)

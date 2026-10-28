from pathlib import Path
from time import perf_counter_ns
from unittest.mock import patch
from contextlib import ExitStack
import shutil,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import occam_resource_process_v2 as p
from src.analysis import occam_resource_qualification_v2 as q
from src.analysis import occam_resource_observation_v1 as r
from src.analysis import response_qualification_io_v1 as io
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
from outputs.information_release.validation_v1.validate_freeze import index_bytes
start=perf_counter_ns();run=q.RUN;out=p.OUTPUT/'failure_delivery_v1';out.mkdir(exist_ok=False)
assert io.git('rev-parse','HEAD')=='1b80c23e7abe8e150840323bd06393852b3c9ae7'
q.verify_freeze();frozen=p.read(q.FREEZE);manifest=p.read(run/'manifest.json');complete=p.read(run/'complete.json')
assert manifest['source_local_commit']=='1b80c23e7abe8e150840323bd06393852b3c9ae7' and manifest['freeze_sha256']==p.sha(q.FREEZE)
assert complete['integrity']=='UNEXPECTED_FAILURE' and complete['launches']==7 and complete['unresolved_attempts']==[]
assert len(complete['outcomes'])==8 and complete['outcomes'][-1]==dict(job_id=8,state='NOT_STARTED',task_metrics=None)
assert not (run/'job08').exists()
hashes={n.relative_to(ROOT).as_posix():p.sha(n) for n in run.rglob('*') if n.is_file()};rows=[]
def denied(*args,**kwargs):raise RuntimeError('main execution, telemetry and child creation disabled in closure audit')
with ExitStack() as stack:
    for obj,names in ((p,('attempt','classify','spec','validate_spec')),(r,('snapshot','decode','gate')),(q.subprocess,('Popen',))):
        for name in names:stack.enter_context(patch.object(obj,name,denied))
    for j,row in enumerate(complete['outcomes'][:7],1):
        folder=run/('job%02d'%j);request=p.read(folder/'spec.json');result=p.read(folder/'result.json');begin=p.read(folder/'start.json')
        receipt=p.read(folder/'receipt.json') if (folder/'receipt.json').exists() else None
        actual={n:p.sha(folder/n) for n in ('start.json','receipt.json','stdout.log','stderr.log') if (folder/n).exists()}
        assert row['job_id']==j and row['result_sha256']==p.sha(folder/'result.json') and result['artifact_sha256']==actual
        assert request['source_sha256']==p.source_hashes() and request['runtime_lock_sha256']==frozen['input_sha256'][p.RUNTIME_LOCK.relative_to(ROOT).as_posix()]
        if j<7:
            rows.append(q.audit_job(request,result,begin,receipt,request_hash=p.sha(folder/'spec.json'),artifact_hashes=actual));continue
        assert result['status']=='WORKER_EXCEPTION' and result['expected_status']=='RETURNED' and not result['expected_contract_observed']
        assert result['launches']==1 and result['returncode']==1 and result['termination'] is None and result['parent_error'] is None
        identity=dict(pid=result['pid'],ppid=result['parent_pid'],nonce=request['nonce'],job_id=7,kind='IMPORT_RUNTIME',spec_sha256=p.sha(folder/'spec.json'),
            source_sha256=request['source_sha256'],runtime_lock_sha256=request['runtime_lock_sha256'],direct_executable_sha256=request['direct_executable_sha256'])
        assert all(begin[k]==receipt[k]==v for k,v in identity.items())
        assert request['created_ns']<=result['started_ns']<=begin['started_ns']<=receipt['completed_ns']<=result['completed_ns']
        assert receipt['state']=='ERROR' and receipt['error']['type']=='RuntimeError' and not receipt['error']['constructed_fixture']
        trace=receipt['error']['traceback'];assert all(x in trace for x in ('_syscmd_ver','subprocess.Popen','_worker_audit','platform.py','numpy','scipy','network or descendant creation forbidden'))
        assert (folder/'stderr.log').read_text(encoding='utf8').strip()==trace.strip()
        assert all(result[k]==0 for k in ('new_environment_operations','new_fits','online_LLM_API_calls'))
        peaks=[begin['resource']['process_peak_private_commit_bytes'],receipt['resource_at_finish']['process_peak_private_commit_bytes']]
        for item in result['samples']:
            q.audit_sample(item['sample'],observer=result['parent_pid'],measured=result['parent_pid'] if item['phase']=='PREFLIGHT' else result['pid'])
            if item['phase']=='OWNED_CHILD':peaks.append(item['sample']['process_peak_private_commit_bytes'])
        q.audit_sample(begin['resource'],observer=result['pid'],measured=result['pid']);q.audit_sample(receipt['resource_at_finish'],observer=result['pid'],measured=result['pid'])
        rows.append(dict(job_id=7,status='UNEXPECTED_IMPORT_GUARD_EXCEPTION',peak_private_commit_bytes=max(peaks),
            complete_traceback_verified=True,guard_not_entered=True,not_a_success_or_native_qualification=True))
    s=complete['science_preflight']['sample'];available=q.audit_sample(s)
    assert available==2470645760 and s['disk_free_bytes']==4751642624
    assert complete['science_preflight']['decision']['reasons']==['AVAILABLE_COMMIT_BELOW_FLOOR'] and not complete['science_collection_opened']
p.write(run/'CLOSED_UNEXPECTED_IMPORT_FAILURE.json',dict(status='CLOSED_NO_RESUME_NO_EIGHTH_WORKER',source_local_commit=manifest['source_local_commit'],
    complete_sha256=p.sha(run/'complete.json'),actual_software_launches=7,not_started_jobs=[8],new_environment_operations=0,new_fits=0,online_LLM_API_calls=0))
p.write(out/'audit.json',dict(integrity='PASSED_FAILURE_CLOSURE_ONLY_NOT_SOFTWARE_QUALIFICATION',source_local_commit=manifest['source_local_commit'],
    planned_jobs=8,launched_jobs=7,expected_prefix_contracts=6,unexpected_failures=1,not_started=1,rows=rows,
    original_artifact_sha256=hashes,disabled_during_audit=['runner/spec/classify','snapshot/decode/gate','Popen'],
    new_environment_operations=0,new_fits=0,online_LLM_API_calls=0,science_collection_opened=False,
    available_commit_bytes=available,disk_free_bytes=s['disk_free_bytes'],native_peak_or_state_continuity_not_qualified=True,
    original_OOM_unique_cause_not_identified=True,publication_goal_complete=False,wall_ns=perf_counter_ns()-start))
shutil.copyfile(Path(__file__),out/Path(__file__).name)
proof=Path(__file__).parent/'occam_core_postcommit_1b80c23e7abe.json';assert p.read(proof)['integrity']=='PASSED'
shutil.copyfile(proof,out/'freeze_committed_bytes.json')
report=ROOT/'reports/occam_resource_qualification_v2_zh.md'
with report.open('x',encoding='utf8',newline='\n') as f:
    f.write('''# 资源观测与进程软件资格v2：失败交付

2026-10-28。**资格仍未通过，v2已关闭，不续接或重跑。** 本阶段只是工程
前提，不是机器人／模型实验，也不证明新获取机制或CCF A贡献。

冻结1b80c23e7abe8e150840323bd06393852b3c9ae7。35项纯字典／假进程检查通过：
33项原契约回归重新执行（不重复记新增），2项本机事件窄放行与DNS拒绝新增；
旧2619项来源绑定检查累计2621项。编译、两个依赖环境、秘密／实际暂存补扫、
普通和暂存差异及字节核对通过。v1原始代码、失败和未启动全部保留。

## 一次实际v2资格

| 项目 | 实际结果 | 判定 |
| --- | --- | --- |
| 1 RETURN4096 | RETURNED | 符合期望 |
| 2 RETURN8192 | RETURNED | 符合期望 |
| 3 构造嵌套异常 | WORKER_EXCEPTION | 符合期望，完整栈；不是旧OOM复现 |
| 4 无回执exit17 | UNRECEIPTED_EXIT | 符合期望，无备用成功回执 |
| 5 短挂起 | TIMEOUT_TERMINATED | 符合期望，仅终止自己的句柄 |
| 6 篡改nonce | INVALID_RECEIPT | 符合期望 |
| 7 只读运行时导入 | WORKER_EXCEPTION | 非预期失败，退出1 |
| 8 RETURN65536 | NOT_STARTED | 指标null，不启动、不重试 |

本次7个真实软件进程；主执行约3.421秒。v1另有7个／约3.885秒，累计14个
软件进程／约7.306秒（主执行和，不含开发、扫描或归档）。两次第8项均
未启动。两次环境创建／重置／控制步／物理帧／政策查询／科学拟合／优化／
在线LLM API均0；软件构造异常不算科学负任务或科学样本。

## 错误栈与可区分的原因

v2允许无参数本机主机名事件后，导入进入下一个链路：
SciPy→NumPy→platform.machine→win32_ver→_syscmd_ver→subprocess.Popen。
Python3.10的Windows版本辅助查询尝试启动ver，审计事件在创建后代前被
守卫拒绝。它发生在read_only上下文进入的依赖导入阶段，正式守卫未进入，
不能伪造运行时依赖核对通过或完整物理守卫回执。完整stderr与receipt栈
一致，峰值私有提交501653504 bytes（约478.4MiB），不是原生工厂峰值。

这次新栈说明v1的局部修复不足；不说明原科学TRAIN的bytes分配失败已经
定位。标准库源码显示win32_ver在可选命令解析不可用时，已有基于
sys.getwindowsversion().platform_version的进程内回退。后继应先明确并
测试这个路径，保持禁止后代进程，而不是逐个允许外部命令。
本地核对源码：.python310/Lib/platform.py，win32_ver与_syscmd_ver。

独立闭合审计禁用主执行／分类／规格、资源读取／计算／门与Popen；前六项
按字典复算，非预期项核对所有身份、来源、原字节哈希、时间、完整栈和退出；
第8项没有目录或启动，保留null。它只证明失败闭合，不是完整八项软件资格。

## 资源、边界与下一步

一次科学入口观测：提交余量2470645760 bytes（2.30GiB），磁盘4751642624
bytes（4.43GiB）。4GiB提交门未通过；科学采集仍关闭。可用物理内存、
地址空间、工作集不能代替提交余量。观测易变，门槛不是资源预留或安全保证。

下一步先冻结独立软件v3：在受限导入期间禁止可选ver命令，使原CPython
使用其已有的系统版本回退；绑定标准库源码哈希，记录回退次数和系统版本，
不伪造运行时或放开连接／DNS／后代进程。原八类契约、资源门槛和停止规则
不变。成功仍只说明软件契约，真实原生collector、峰值、世界／随机数／时钟
连续性及新独立科学分配仍需分别资格和预算。

原TRAIN188完整／1部分／459未启动及全部预留继续关闭；没有训练新模型，
不削弱科学见证，不用前缀绕过完整训练门。A方向的获取机制区别、强参考
上的独立自身历史完整任务收益、消融与前瞻验证仍未建立。
''')
names={n.relative_to(ROOT).as_posix() for n in run.rglob('*') if n.is_file()}|{report.relative_to(ROOT).as_posix()}
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
stage('owned_checked');proof=check();p.write(out/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=proof,actual_staged_basic_extra_scan=True))
p.write(out/'complete.json',dict(integrity='PASSED_FAILURE_DELIVERY_NOT_QUALIFICATION',launched=7,expected_prefix=6,unexpected=1,not_started=1,
    source_sha256=frozen['source_sha256'],original_qualification_artifacts_sha256=hashes,new_environment_operations=0,new_fits=0,online_LLM_API_calls=0,
    science_collection_opened=False,publication_goal_complete=False,wall_ns=perf_counter_ns()-start))
stage('owned_final');check();print(dict(integrity='PASSED_FAILURE_DELIVERY_NOT_QUALIFICATION',owned_files=len(names),launched=7,not_started=1),flush=True)

from pathlib import Path
from time import perf_counter_ns
from unittest.mock import patch
from contextlib import ExitStack
import shutil,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import occam_resource_process_v1 as p
from src.analysis import occam_resource_qualification_v1 as q
from src.analysis import occam_resource_observation_v1 as r
from src.analysis import response_qualification_io_v1 as io
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
from outputs.information_release.validation_v1.validate_freeze import index_bytes
start=perf_counter_ns();run=q.RUN;out=p.OUTPUT/'failure_delivery_v1';out.mkdir(exist_ok=False)
assert io.git('rev-parse','HEAD')=='196bcba0c88508c19b2fcae6b4fbf3f9e558df8a'
q.verify_freeze();frozen=p.read(q.FREEZE);manifest=p.read(run/'manifest.json');complete=p.read(run/'complete.json')
assert manifest['source_local_commit']=='196bcba0c88508c19b2fcae6b4fbf3f9e558df8a' and manifest['freeze_sha256']==p.sha(q.FREEZE)
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
        trace=receipt['error']['traceback'];assert all(x in trace for x in ('socket.gethostname()','_worker_audit','platform.py','numpy','scipy','network or descendant creation forbidden'))
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
    assert available==2257076224 and s['disk_free_bytes']==4757286912
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
proof=Path(__file__).parent/'occam_core_postcommit_196bcba0c885.json';assert p.read(proof)['integrity']=='PASSED'
shutil.copyfile(proof,out/'freeze_committed_bytes.json')
report=ROOT/'reports/occam_resource_qualification_v1_zh.md'
with report.open('x',encoding='utf8',newline='\n') as f:
    f.write('''# 资源观测与进程软件资格v1：失败交付

2026-10-28。结论：**资格未通过，已关闭，不续接或重跑**。不是机器人实验，
不提供模型、任务收益或CCF A贡献证据。

冻结提交196bcba0c88508c19b2fcae6b4fbf3f9e558df8a；33项新增纯数组／假进程
检查通过，2586项源码绑定复用，共2619项。编译、两个依赖环境检查通过。
开发夹具默认值错误、冻结前JSON换行差异均保留；没有因此启动真实worker。
完整tracked秘密扫描在c55d094基线已通过，原对象不变；新暂存内容逐字节
核对并补扫基础／扩展模式，没有将未重跑的历史检查冒充新执行。

## 一次实际执行

| 项目 | 实际结果 | 解释 |
| --- | --- | --- |
| 1／2 小bytes | RETURNED | 两项完成，4096／8192 bytes |
| 3 嵌套构造异常 | WORKER_EXCEPTION | 符合期望；完整因果异常栈，不是旧OOM复现 |
| 4 无回执退出 | UNRECEIPTED_EXIT | exit17，不借用备用成功回执 |
| 5 短挂起 | TIMEOUT_TERMINATED | 约1.023秒由父进程终止自己的句柄 |
| 6 篡改nonce | INVALID_RECEIPT | 拒绝被篡改回执 |
| 7 运行时导入 | WORKER_EXCEPTION | 非预期失败，退出1 |
| 8 65536 bytes | NOT_STARTED | 指标null，没有启动或重试 |

共7个真实软件进程，6项符合预期、1项非预期、1项未启动。预期异常是软件
契约检查，不是成功机器人案例。主执行约3.885秒；环境创建／reset／step／
物理帧、政策查询、科学拟合／优化及在线LLM API均为0。

第7项栈显示SciPy→NumPy→platform.machine→socket.gethostname→本守卫。
v1对全部socket审计事件拒绝，误将本机名称读取当网络活动；它在原只读
物理／拟合守卫进入前失败，不能捏造其未产生的运行时核对通过回执。
其进程峰值私有提交503414784 bytes，其余软件项约9.3MiB；均非原生机器人
或失败分配峰值。完整stderr与receipt栈一致。
Python文档说明gethostname读取本机名称：[官方定义](https://docs.python.org/3.10/library/socket.html#socket.gethostname)。

独立只读闭合审计在禁用主runner、分类、规格、资源计算／门及Popen后，
逐字节验证全部已生成回执和原文件哈希，前六项按冻结的字典审计复算；
第7项核对错误栈／身份／退出／来源，第8项核对无目录、null与停止关系。
该审计只证明失败保存和前缀契约，不替代缺失的完整八项资格。

## 资源与下一步

一次科学入口观测：磁盘4757286912 bytes（4.43GiB）；可提交余量
2257076224 bytes（2.10GiB），低于预设4GiB，因此科学采集仍关闭。
地址空间、物理可用内存、工作集及提交余量分别记录，不能互相替代。
观测有时效，门槛不预留资源，也不保证未来分配成功。

后继先独立冻结软件v2：只明确允许无参数本机主机名事件，继续阻断socket
创建、连接、DNS、外部进程及在线LLM；不改变门槛、样本计划或科学模型。
再用独立输出运行一次原八类软件契约，旧v1不改写、不把第7项重贴成功。
真实原生收集器集成、世界／随机数／时钟连续性及完整费用仍需另行资格。
原TRAIN188完整／1部分／459未启动与所有预留继续关闭，未训练新模型。
完整科学收益、获取机制区别、强参考、消融及独立自身历史验证仍待建立。
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

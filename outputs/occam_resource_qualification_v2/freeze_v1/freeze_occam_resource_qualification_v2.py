from pathlib import Path
from time import perf_counter_ns
from unittest.mock import patch
import hashlib,shutil,subprocess,sys,unittest
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import occam_resource_qualification_v2 as q
from src.analysis import occam_resource_process_v2 as p
from src.analysis import response_qualification_io_v1 as io
from src.analysis.release_learning_guard_v1 import read_only
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
from outputs.information_release.validation_v1.validate_freeze import index_bytes
start=perf_counter_ns();out=q.FREEZE.parent;out.mkdir(parents=True,exist_ok=False)
source_parent='86294a578e8d94d2b410598f6a897b805e4f708b';assert io.git('rev-parse','HEAD')==source_parent
assert not io.git('status','--porcelain','--untracked-files=no')
old_folder=ROOT/'outputs/occam_resource_qualification_v1/freeze_v1';old=p.read(old_folder/'complete.json');reuse=p.read(old_folder/'source_reuse.json')
assert old['integrity']=='PASSED_SOFTWARE_IMPLEMENTATION_ONLY' and old['unique_test_total']==2619 and p.sha(old_folder/'source_reuse.json')==old['source_reuse_sha256']
prior={**reuse['source_sha256'],**old['source_sha256']}
for n,h in prior.items():assert p.sha(ROOT/n)==h,n
source={n:p.sha(ROOT/n) for n in q.OWN};p.write(out/'source_before_tests.json',source)
guard={}
with (out/'tests.log').open('x',encoding='utf8',newline='\n') as log,read_only(guard),patch('subprocess.Popen',side_effect=AssertionError('real process forbidden in software tests')):
    result=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromName('tests.test_occam_resources_v2'))
p.write(out/'tests.json',dict(success=result.wasSuccessful(),tests=result.testsRun,regression_reexecutions=33,new_unique_tests=2,real_workers=0,guard=guard))
assert result.wasSuccessful() and result.testsRun==35
def run(name,args):
    t=perf_counter_ns();v=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,encoding='utf8',errors='replace')
    p.write(out/name,dict(args=args,returncode=v.returncode,stdout=v.stdout,stderr=v.stderr,wall_ns=perf_counter_ns()-t));assert v.returncode==0,name
run('compile.json',[sys.executable,'-m','compileall','-q','src','scripts','tests'])
run('main_dependencies.json',[sys.executable,'-m','pip','check'])
run('training_dependencies.json',[r'C:/Users/Administrator/Documents/ChatGPT/robotic agent/.venv-history-training-cpu22/Scripts/python.exe','-m','pip','check'])
p.write(out/'source_reuse.json',dict(integrity='PASSED',source_sha256=prior,reused_unique_tests=2619,new_unique_tests=2,unique_tests=2621,
    source_receipt=(old_folder/'complete.json').relative_to(ROOT).as_posix(),source_receipt_sha256=p.sha(old_folder/'complete.json'),
    separately_reexecuted_software_contract_tests=33,old_scientific_or_optimizer_checks_repeated=False))
inputs=dict(old['input_sha256'])
for name in ('outputs/occam_resource_qualification_v1/freeze_v1/complete.json','outputs/occam_resource_qualification_v1/freeze_v1/source_reuse.json',
    'outputs/occam_resource_qualification_v1/qualification_v1/complete.json','outputs/occam_resource_qualification_v1/qualification_v1/CLOSED_UNEXPECTED_IMPORT_FAILURE.json',
    'outputs/occam_resource_qualification_v1/failure_delivery_v1/complete.json'):
    inputs[name]=p.sha(ROOT/name)
p.write(out/'input_sha256.json',inputs)
archive=ROOT/'outputs/research_archive/occam_resource_software_failure_v1';remote=p.read(archive/'remote_receipt.json');catalog=p.read(archive/'catalog.json')
assert remote['remote_after']=='a903d6dc98097c716673a7b23e5be17e99bbd3bd' and remote['integrity']=='PASSED'
changed=io.git('diff','--name-only','c55d0940384e645dc7aa98f95cc93a19ffa639dd',source_parent).splitlines()
rows=[x for x in catalog['files'] if x['path'] in changed];assert len(rows)==len(changed)==93 and all(x['published'] for x in rows)
for name in ('build_occam_resource_failure_v1_archive.py','verify_occam_core_commit_v1.py'):
    shutil.copyfile(Path(__file__).parent/name,archive/name)
for head,label in (('196bcba0c88508c19b2fcae6b4fbf3f9e558df8a','freeze_committed_bytes.json'),(source_parent,'result_committed_bytes.json')):
    proof=Path(__file__).parent/('occam_core_postcommit_'+head[:12]+'.json');assert p.read(proof)['integrity']=='PASSED';shutil.copyfile(proof,archive/label)
p.write(archive/'phase_selection.json',dict(integrity='PASSED',source_local_commit=source_parent,published=93,omitted=0,files=rows,remote_archive_commit=remote['remote_after']))
p.write(archive/'complete.json',dict(integrity='PASSED_ARCHIVAL_OF_FAILED_SOFTWARE_QUALIFICATION',source_local_commit=source_parent,remote_archive_commit=remote['remote_after'],
    phase_files=93,phase_published=93,original_worker_records_and_failure_preserved=True,new_environment_operations=0,new_fits=0,online_LLM_API_calls=0))
log=ROOT/'Research_Log.md';before=log.read_bytes();assert hashlib.sha256(before).hexdigest()=='ab958bd8bb7ab9505a7dd60440985f8c253de02e8658c0b562ea49eb05251d7b'
with log.open('a',encoding='utf8',newline='\n') as f:
    f.write('''
## 2026-10-28｜资源软件资格v1失败闭合与归档

- 已完成：资源观测、固定真实解释器worker及独立字典审计实现，33项新增
  模拟检查通过，2586项来源绑定复用，共2619项；编译和两个依赖环境通过。
- 一次实际资格：7个软件进程，前6项符合预期，第7项依赖导入被
  socket.gethostname守卫误拦，第8项未启动。v1已关闭，未重试或续接。
  全部原始请求／响应／完整异常栈／退出／资源保存，stderr按精确字节入Git。
  独立闭合审计通过只表示失败保存完整，**软件资格未通过**。
- 费用：约3.885秒主执行，0环境／重置／控制步／帧／政策查询／拟合／在线
  LLM API。科学入口一次可提交余量2.10GiB、磁盘4.43GiB，4GiB提交门未通过。
- 来源：冻结 `196bcba0c88508c19b2fcae6b4fbf3f9e558df8a`，本地失败交付
  `86294a578e8d94d2b410598f6a897b805e4f708b`；核对远端
  `a903d6dc98097c716673a7b23e5be17e99bbd3bd`（同一归档分支），本阶段93项全部发布。
- 报告：[资源软件资格v1失败交付](reports/occam_resource_qualification_v1_zh.md)。
- 下一阶段目标：独立冻结v2，仅允许无参数本机主机名查询，继续禁止连接、
  DNS和后代进程；重做一次八类软件资格，不修改旧失败、门槛或科学分配。
  原生连续性资格、新独立训练和A主线的研究收益仍待完成。
''')
assert log.read_bytes().startswith(before)
p.write(out/'tracked_secret_scan_chain.json',dict(integrity='PASSED',full_tracked_scan_at='c55d0940384e645dc7aa98f95cc93a19ffa639dd',
    intervening_all_new_or_changed_index_objects_scanned_at=['196bcba0c88508c19b2fcae6b4fbf3f9e558df8a',source_parent],
    this_stage_actual_staged_basic_and_extra_scan=True,unchanged_large_objects_not_allocated_again=True))
for name in ('create_occam_resource_qualification_v2.py','freeze_occam_resource_qualification_v2.py'):
    shutil.copyfile(Path(__file__).parent/name,out/name)
names={n for n in q.OWN if n not in prior}|{'Research_Log.md'}
names|={n.relative_to(ROOT).as_posix() for n in archive.iterdir() if n.is_file()}
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
for n,h in {**source,**inputs,**prior}.items():assert p.sha(ROOT/n)==h,n
p.write(out/'complete.json',dict(integrity='PASSED_SOFTWARE_IMPLEMENTATION_ONLY',source_sha256=source,input_sha256=inputs,
    source_reuse_sha256=p.sha(out/'source_reuse.json'),unique_test_total=2621,new_unique_tests=2,reused_unique_tests=2619,
    actual_test_executions=35,reexecuted_software_contract_tests=33,guard=guard,real_workers=0,new_environment_operations=0,new_fits=0,
    online_LLM_API_calls=0,science_collection_opened=False,publication_goal_complete=False,wall_ns=perf_counter_ns()-start))
stage('owned_final');check();print(dict(integrity='PASSED_SOFTWARE_IMPLEMENTATION_ONLY',owned_files=len(names),unique_tests=2621,actual_tests=35),flush=True)

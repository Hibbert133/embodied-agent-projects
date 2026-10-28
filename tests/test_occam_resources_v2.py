"""No subprocesses, physics, fits or APIs: saved dictionaries and fake handles."""
import copy,ctypes,hashlib,os,subprocess,tempfile,traceback,unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
from src.analysis import occam_resource_observation_v1 as r
from src.analysis import occam_resource_process_v2 as p
from src.analysis import occam_resource_qualification_v2 as q


def sample(pid=None,observer=None,stamp=0):
    pid=os.getpid() if pid is None else pid;observer=os.getpid() if observer is None else observer
    m=NS(ullAvailPageFile=8*1024**3,ullTotalPhys=16*1024**3,ullAvailPhys=4*1024**3,ullAvailVirtual=2**45)
    g=NS(PageSize=4096,CommitTotal=1024,CommitLimit=4*1024**2,CommitPeak=2048)
    x=NS(PrivateUsage=4*1024**2,PeakPagefileUsage=8*1024**2,WorkingSetSize=2*1024**2,PeakWorkingSetSize=3*1024**2)
    return dict(schema='OCCAM_RESOURCE_SAMPLE_V1',timestamp_UTC='2026-10-28T00:00:00+00:00',
        sample_started_ns=stamp,sample_completed_ns=stamp,observer_pid=observer,measured_process_pid=pid,pointer_bits=64,
        disk_free_bytes=8*1024**3,**r.decode(m,g,x))


class Clock:
    def __init__(self):self.n=10**9
    def __call__(self):return self.n
    def sleep(self,t):self.n+=int(t*10**9)


class FakeProcess:
    def __init__(self,clock,*,hang=False,terminate_wait_fails=False):
        self.pid=7654321;self._handle=123456;self.code=None;self.clock=clock;self.polls=0
        self.hang=hang;self.terminate_wait_fails=terminate_wait_fails;self.terminations=0;self.waits=0
    def poll(self):
        self.polls+=1
        if not self.hang and self.polls>3 and self.code is None:self.code=0
        return self.code
    def terminate(self):
        self.terminations+=1
        if not self.terminate_wait_fails:self.code=9
    def wait(self,timeout):
        self.waits+=1
        if self.terminate_wait_fails:raise subprocess.TimeoutExpired('fixed mock',timeout)
        return self.code


class TelemetryTests(unittest.TestCase):
    def test_windows64_layout(self):
        self.assertEqual((ctypes.sizeof(r.MemoryStatus),ctypes.sizeof(r.PerformanceInfo),ctypes.sizeof(r.ProcessInfo)),(64,104,80))
    def test_page_units_and_private_commit(self):
        s=sample();self.assertEqual(s['system_commit_available_bytes'],(s['system_commit_limit_pages']-s['system_commit_total_pages'])*4096)
        self.assertNotEqual(s['process_private_commit_bytes'],s['process_working_set_bytes'])
        q.audit_sample(s)
    def test_address_space_cannot_satisfy_commit_floor(self):
        s=sample();s['system_commit_available_bytes']=1
        self.assertFalse(r.gate(s,**p.PROFILE)['allowed'])
    def test_observer_commit_allowance_is_separate(self):
        s=sample(42);s['current_process_available_commit_bytes']=1
        self.assertFalse(r.gate(s,**p.PROFILE)['allowed']);self.assertNotEqual(s['observer_pid'],s['measured_process_pid'])
    def test_missing_negative_bool_and_nonfinite_rejected(self):
        for value in (None,-1,True,float('nan'),'123'):
            s=sample();s['disk_free_bytes']=value
            with self.subTest(value=value),self.assertRaises(r.ResourceObservationError):r.gate(s,**p.PROFILE)
    def test_private_cap_and_disk_floor(self):
        s=sample();s['process_private_commit_bytes']=2*1024**3;s['disk_free_bytes']=1
        check=r.gate(s,**p.PROFILE);self.assertEqual(check['reasons'],['DISK_BELOW_FLOOR','OWNED_PROCESS_PRIVATE_COMMIT_ABOVE_CAP'])
    def test_unknown_threshold_rejected(self):
        for key in p.PROFILE:
            args=dict(p.PROFILE);args[key]=True
            with self.subTest(key=key),self.assertRaises(ValueError):r.gate(sample(),**args)
    def test_invalid_page_observation(self):
        with self.assertRaises(r.ResourceObservationError):r.decode(None,NS(PageSize=0,CommitTotal=1,CommitLimit=2),None)
        with self.assertRaises(r.ResourceObservationError):r.decode(None,NS(PageSize=4096,CommitTotal=3,CommitLimit=2),None)
    def test_api_failure_captured_before_next_api(self):
        calls=[]
        def first(*a):calls.append('first');return 0
        def later(*a):calls.append('later');return 1
        k=NS(GetCurrentProcess=lambda:1,GetProcessId=lambda h:os.getpid(),GlobalMemoryStatusEx=first)
        api=NS(GetPerformanceInfo=later,GetProcessMemoryInfo=later)
        with patch.object(r,'functions',return_value=(k,api)),patch.object(r.c,'get_last_error',return_value=123):
            with self.assertRaisesRegex(r.ResourceObservationError,'WinError=123'):r.snapshot('.')
        self.assertEqual(calls,['first'])
    def test_wrong_borrowed_handle_pid_fails_before_query(self):
        fn=unittest.mock.Mock()
        k=NS(GetProcessId=lambda h:12,GlobalMemoryStatusEx=fn)
        with patch.object(r,'functions',return_value=(k,NS())):
            with self.assertRaises(r.ResourceObservationError):r.snapshot('.',process_handle=7,process_id=13)
        fn.assert_not_called()


class ProcessTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name)
        self.output_patch=patch.object(p,'OUTPUT',self.base);self.output_patch.start()
        self.real_spawn=patch('subprocess.Popen',side_effect=AssertionError('no real processes in tests'));self.real_spawn.start()
        self.clock=Clock();self.launches=[];self.hang=False;self.wait_fails=False
    def tearDown(self):
        self.real_spawn.stop();self.output_patch.stop();self.tmp.cleanup()
    def request(self,j=1):return p.spec(j,clock=self.clock)
    def spawn(self,command,**kwargs):
        self.launches.append((command,kwargs));request_path=Path(command[-1]);s=p.read(request_path)
        proc=FakeProcess(self.clock,hang=getattr(self,'hang',False),terminate_wait_fails=getattr(self,'wait_fails',False));self.proc=proc
        identity=dict(pid=proc.pid,ppid=os.getpid(),job_id=s['job_id'],kind=s['kind'],nonce=s['nonce'],spec_sha256=p.sha(request_path),
            source_sha256=s['source_sha256'],runtime_lock_sha256=s['runtime_lock_sha256'],direct_executable_sha256=s['direct_executable_sha256'],started_ns=self.clock())
        p.write(request_path.parent/'start.json',dict(**identity,resource=sample(proc.pid,proc.pid,self.clock())))
        state='RETURNED';error=None;payload=dict(bytes=s['bytes'],sha256=hashlib.sha256(bytes(s['bytes'])).hexdigest())
        if s['kind']=='EXIT':proc.code=17;return proc
        if s['kind']=='RAISE_NESTED':
            try:p._nested_failure()
            except RuntimeError:error=dict(constructed_fixture=True,traceback=traceback.format_exc())
            state='ERROR';proc.code=1
        if s['kind']=='IMPORT_RUNTIME':
            counts={k:0 for k in ('environment_creations','resets','simulation','solve_attempts','lstsq_attempts','cold_fit_attempts',
                'cold_estimator_entries','cold_linear_solve_attempts','cold_linear_lstsq_attempts')}
            payload=dict(runtime_verified=True,dependency_import_only=True,guard=dict(operation_counts=counts,
                network=dict(attempted_network_calls=0),online_LLM_API_calls=0,zero_new_physical_interactions=True))
        if s['kind']=='TAMPER':identity['nonce']='0'*32
        if not self.hang:p.write(request_path.parent/'receipt.json',dict(**identity,state=state,error=error,completed_ns=self.clock(),
            resource_at_finish=sample(proc.pid,proc.pid,self.clock()),payload=payload))
        return proc
    def observe(self,root,**kwargs):
        return sample(kwargs.get('process_id'),stamp=self.clock())
    def attempt(self,j=1,observe=None):
        return p.attempt(self.base/'job',self.request(j),spawn=self.spawn,observe=observe or self.observe,clock=self.clock,sleep=self.clock.sleep)
    def test_fixed_request_rejects_science_and_arbitrary_arguments(self):
        for key in ('seed','task','collector','script','command'):
            s=self.request();s[key]='forbidden'
            with self.subTest(key=key),self.assertRaises(ValueError):p.validate_spec(s)
    def test_request_source_and_runtime_binding(self):
        for key in ('source_sha256','runtime_lock_sha256','direct_executable_sha256'):
            s=self.request();s[key]={} if key=='source_sha256' else '0'*64
            with self.subTest(key=key),self.assertRaises(ValueError):p.validate_spec(s)
    def test_payload_and_timeout_cannot_change(self):
        for key in ('bytes','timeout_seconds','job_id'):
            s=self.request();s[key]=999
            with self.subTest(key=key),self.assertRaises(ValueError):p.validate_spec(s)
    def test_resource_rejection_precedes_spawn(self):
        def low(*a,**k):s=sample();s['system_commit_available_bytes']=0;return s
        result=self.attempt(observe=low)
        self.assertEqual(result['status'],'ADMISSION_REJECTED');self.assertEqual(self.launches,[])
    def test_unknown_preflight_preserves_error_and_zero_launch(self):
        def unknown(*a,**k):raise r.ResourceObservationError('synthetic unknown')
        result=self.attempt(observe=unknown)
        self.assertEqual(result['status'],'PARENT_EXCEPTION');self.assertEqual(result['launches'],0)
        self.assertIn('synthetic unknown',result['parent_error'])
    def test_exact_direct_interpreter_command_and_bounded_return(self):
        result=self.attempt();self.assertEqual(result['status'],'RETURNED');self.assertEqual(len(self.launches),1)
        command,kwargs=self.launches[0];self.assertEqual(command[:5],[str(p.executable()),'-I','-S',str(p.WORKER),'--spec'])
        self.assertFalse(kwargs.get('shell',False));self.assertEqual(self.proc.terminations,0)
        self.assertEqual(result['artifact_sha256']['stdout.log'],hashlib.sha256(b'').hexdigest())
    def test_timeout_only_terminates_owned_handle_no_retry(self):
        self.hang=True;result=self.attempt(5)
        self.assertEqual(result['status'],'TIMEOUT_TERMINATED');self.assertEqual((len(self.launches),self.proc.terminations,self.proc.waits),(1,1,1))
        self.assertEqual([e['pid'] for e in result['events'] if e['kind']=='TERMINATE_OWNED_HANDLE'],[self.proc.pid])
    def test_live_private_cap_terminates(self):
        self.hang=True
        def large(root,**kw):
            s=self.observe(root,**kw)
            if kw:s['process_private_commit_bytes']=2*1024**3
            return s
        result=self.attempt(observe=large);self.assertEqual(result['status'],'RESOURCE_TERMINATED');self.assertEqual(self.proc.terminations,1)
    def test_live_unknown_resource_is_not_a_retry(self):
        self.hang=True
        def unknown(root,**kw):
            if kw:raise r.ResourceObservationError('lost live observation')
            return sample()
        result=self.attempt(observe=unknown);self.assertEqual(result['status'],'UNKNOWN_RESOURCE_TERMINATED');self.assertEqual(len(self.launches),1)
    def test_termination_timeout_not_reported_terminal(self):
        self.hang=True;self.wait_fails=True;result=self.attempt(5)
        self.assertEqual(result['status'],'PROCESS_NOT_CONFIRMED_TERMINAL');self.assertIsNone(result['returncode'])
        self.assertEqual(self.proc.terminations,1)
    def test_preexisting_output_not_reused(self):
        (self.base/'job').mkdir()
        with self.assertRaises(FileExistsError):self.attempt()
        self.assertEqual(self.launches,[])
    def test_external_directory_rejected_before_launch(self):
        with self.assertRaises(ValueError):p.attempt(self.base.parent/'external',self.request(),spawn=self.spawn)
        self.assertEqual(self.launches,[])
    def test_full_parent_stack_and_owned_cleanup(self):
        self.hang=True
        def broken(root,**kw):
            if kw:raise RuntimeError('constructed parent stack')
            return sample()
        result=self.attempt(observe=broken);self.assertEqual(result['status'],'PARENT_EXCEPTION')
        self.assertIn('test_occam_resources_v2.py',result['parent_error']);self.assertEqual(self.proc.terminations,1)
    def test_wrong_receipt_nonce_and_future_time_rejected(self):
        result=self.attempt();s=p.read(self.base/'job/spec.json');start=p.read(self.base/'job/start.json');receipt=p.read(self.base/'job/receipt.json')
        for key,value in (('nonce','0'*32),('pid',1),('ppid',1),('completed_ns',0)):
            bad=copy.deepcopy(receipt);bad[key]=value
            with self.subTest(key=key):self.assertEqual(p.classify(s,result['spec_sha256'],result['pid'],0,start,bad,None),'INVALID_RECEIPT')
    def test_missing_receipt_never_borrowed_from_baseline(self):
        result=self.attempt();s=p.read(self.base/'job/spec.json');start=p.read(self.base/'job/start.json')
        self.assertEqual(p.classify(s,result['spec_sha256'],result['pid'],17,start,None,None),'UNRECEIPTED_EXIT')
    def test_literal_audit_with_runner_logic_disabled(self):
        result=self.attempt();folder=self.base/'job';s=p.read(folder/'spec.json');start=p.read(folder/'start.json');receipt=p.read(folder/'receipt.json')
        with patch.object(p,'classify',side_effect=AssertionError),patch.object(r,'gate',side_effect=AssertionError),patch.object(r,'decode',side_effect=AssertionError):
            row=q.audit_job(s,result,start,receipt,request_hash=p.sha(folder/'spec.json'),artifact_hashes=result['artifact_sha256'])
        self.assertEqual(row['status'],'RETURNED')
    def test_auditor_rejects_result_order_and_false_costs(self):
        result=self.attempt();folder=self.base/'job';s=p.read(folder/'spec.json');start=p.read(folder/'start.json');receipt=p.read(folder/'receipt.json')
        for key,value in (('completed_ns',0),('launches',2),('new_environment_operations',1)):
            bad=copy.deepcopy(result);bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):q.audit_job(s,bad,start,receipt,request_hash=p.sha(folder/'spec.json'),artifact_hashes=bad['artifact_sha256'])
    def test_auditor_detects_unit_conversion_error(self):
        s=sample();s['system_commit_available_bytes']=s['system_commit_available_bytes']//4096
        with self.assertRaisesRegex(ValueError,'page/byte'):q.audit_sample(s)
    def test_complete_nested_stack_is_available_without_process(self):
        try:p._nested_failure()
        except RuntimeError:trace=traceback.format_exc()
        self.assertIn('ValueError: constructed inner fixture cause',trace);self.assertIn('direct cause',trace)
        self.assertIn('RuntimeError: constructed outer fixture failure',trace)
    def test_all_eight_synthetic_record_contracts(self):
        for j in range(1,9):
            with self.subTest(job_id=j):
                self.hang=j==5;folder=self.base/('synthetic%02d'%j)
                result=p.attempt(folder,self.request(j),spawn=self.spawn,observe=self.observe,clock=self.clock,sleep=self.clock.sleep)
                request=p.read(folder/'spec.json');start=p.read(folder/'start.json');receipt=p.read(folder/'receipt.json') if (folder/'receipt.json').exists() else None
                row=q.audit_job(request,result,start,receipt,request_hash=p.sha(folder/'spec.json'),artifact_hashes=result['artifact_sha256'])
                self.assertEqual(row['status'],p.JOBS[j-1][3])
    def test_auditor_rejects_future_resource_and_missing_guard_fields(self):
        result=self.attempt();folder=self.base/'job';s=p.read(folder/'spec.json');start=p.read(folder/'start.json');receipt=p.read(folder/'receipt.json')
        bad=copy.deepcopy(result);bad['samples'][0]['sample']['sample_completed_ns']=result['completed_ns']+1
        with self.assertRaises(ValueError):q.audit_job(s,bad,start,receipt,request_hash=p.sha(folder/'spec.json'),artifact_hashes=bad['artifact_sha256'])
        folder=self.base/'import_synthetic';result=p.attempt(folder,self.request(7),spawn=self.spawn,observe=self.observe,clock=self.clock,sleep=self.clock.sleep)
        s=p.read(folder/'spec.json');start=p.read(folder/'start.json');receipt=p.read(folder/'receipt.json');receipt['payload']['guard']['operation_counts']={}
        with self.assertRaisesRegex(ValueError,'guard zero'):q.audit_job(s,result,start,receipt,request_hash=p.sha(folder/'spec.json'),artifact_hashes=result['artifact_sha256'])
    def test_worker_audit_blocks_network_and_descendants(self):
        for event in ('socket.connect','socket.__new__','subprocess.Popen','os.system','os.spawn','os.posix_spawn'):
            with self.subTest(event=event),self.assertRaises(RuntimeError):p._worker_audit(event,())
    def test_unexpected_orchestration_failure_preserves_unstarted(self):
        with patch.object(q,'RUN',self.base/'qualification'),patch.object(q,'verify_freeze',return_value=dict(source_sha256={})),\
            patch.object(q,'git',return_value='f'*40),patch.object(p,'sha',return_value='a'*64),\
            patch.object(p,'attempt',side_effect=ValueError('constructed orchestration failure')) as mocked,\
            patch.object(r,'snapshot',return_value=sample()):
            result=q.qualify()
        self.assertEqual(mocked.call_count,1);self.assertEqual(result['unresolved_attempts'],[1]);self.assertEqual(len(result['outcomes']),8)
        self.assertEqual([x['state'] for x in result['outcomes'][1:]],['NOT_STARTED']*7)
        self.assertTrue(all(x['task_metrics'] is None for x in result['outcomes'][1:]));self.assertFalse(result['science_collection_opened'])

    def test_only_parameterless_local_hostname_event_allowed(self):
        self.assertIsNone(p._worker_audit('socket.gethostname',()))
        for args in ((1,),('unexpected',),None):
            with self.subTest(args=args),self.assertRaises(RuntimeError):p._worker_audit('socket.gethostname',args)
    def test_dns_connections_and_name_resolution_remain_blocked(self):
        for event in ('socket.getaddrinfo','socket.gethostbyname','socket.gethostbyaddr','socket.getnameinfo','socket.connect','socket.bind','socket.__new__'):
            with self.subTest(event=event),self.assertRaises(RuntimeError):p._worker_audit(event,())


if __name__=='__main__':unittest.main()

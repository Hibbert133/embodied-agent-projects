from pathlib import Path
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects')
pairs=(('src/analysis/occam_resource_process_v1.py','src/analysis/occam_resource_process_v2.py'),
 ('src/analysis/occam_resource_qualification_v1.py','src/analysis/occam_resource_qualification_v2.py'),
 ('scripts/occam_resource_fixture_v1.py','scripts/occam_resource_fixture_v2.py'),
 ('scripts/qualify_occam_resources_v1.py','scripts/qualify_occam_resources_v2.py'),
 ('tests/test_occam_resources_v1.py','tests/test_occam_resources_v2.py'))
for old,new in pairs:
    text=(ROOT/old).read_text(encoding='utf8')
    for a,b in (('occam_resource_process_v1','occam_resource_process_v2'),('occam_resource_qualification_v1','occam_resource_qualification_v2'),
        ('occam_resource_fixture_v1','occam_resource_fixture_v2'),('qualify_occam_resources_v1','qualify_occam_resources_v2'),
        ('test_occam_resources_v1','test_occam_resources_v2'),('occam_resources_v1','occam_resources_v2'),
        ('occam_resource_software_qualification_v1','occam_resource_software_qualification_v2'),
        ('OCCAM_RESOURCE_SOFTWARE_SPEC_V1','OCCAM_RESOURCE_SOFTWARE_SPEC_V2'),('OCCAM_RESOURCE_SOFTWARE_RESULT_V1','OCCAM_RESOURCE_SOFTWARE_RESULT_V2'),
        ('OCCAM_RESOURCE_QUALIFICATION_V1','OCCAM_RESOURCE_QUALIFICATION_V2')):text=text.replace(a,b)
    if 'process_v2.py' in new:
        old_hook="def _worker_audit(event,args):\n    if event.startswith('socket.')"
        assert old_hook in text;text=text.replace(old_hook,"def _worker_audit(event,args):\n    if event=='socket.gethostname' and args==():return\n    if event.startswith('socket.')")
        old_import="            from src.analysis.response_action_io_v1 import verify_runtime\n            guard={}\n            with read_only(guard):verify_runtime(read(RUNTIME_LOCK))"
        assert old_import in text;text=text.replace(old_import,"            guard={}\n            with read_only(guard):\n                from src.analysis.response_action_io_v1 import verify_runtime\n                verify_runtime(read(RUNTIME_LOCK))")
    if 'qualification_v2.py' in new and new.startswith('src/'):
        assert "value['reused_unique_tests']!=2586" in text;text=text.replace("value['reused_unique_tests']!=2586","value['reused_unique_tests']!=2619")
        needle="    j=request['job_id'];_require(type(j) is int and 1<=j<=8,'job id')"
        assert needle in text;text=text.replace(needle,"    _require(request['schema']=='OCCAM_RESOURCE_SOFTWARE_SPEC_V2' and result['schema']=='OCCAM_RESOURCE_SOFTWARE_RESULT_V2','v2 schema')\n"+needle)
    if new.startswith('tests/'):
        needle="\n\nif __name__=='__main__':unittest.main()"
        assert needle in text;text=text.replace(needle,"""
    def test_only_parameterless_local_hostname_event_allowed(self):
        self.assertIsNone(p._worker_audit('socket.gethostname',()))
        for args in ((1,),('unexpected',),None):
            with self.subTest(args=args),self.assertRaises(RuntimeError):p._worker_audit('socket.gethostname',args)
    def test_dns_connections_and_name_resolution_remain_blocked(self):
        for event in ('socket.getaddrinfo','socket.gethostbyname','socket.gethostbyaddr','socket.getnameinfo','socket.connect','socket.bind','socket.__new__'):
            with self.subTest(event=event),self.assertRaises(RuntimeError):p._worker_audit(event,())
"""+needle)
    compile(text,new,'exec')
    with (ROOT/new).open('x',encoding='utf8',newline='\n') as f:f.write(text)
print('created five independent v2 source files; v1 untouched')

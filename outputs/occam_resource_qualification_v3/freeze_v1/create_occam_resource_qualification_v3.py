from pathlib import Path
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects')
pairs=(('src/analysis/occam_resource_process_v2.py','src/analysis/occam_resource_process_v3.py'),
 ('src/analysis/occam_resource_qualification_v2.py','src/analysis/occam_resource_qualification_v3.py'),
 ('scripts/occam_resource_fixture_v2.py','scripts/occam_resource_fixture_v3.py'),
 ('scripts/qualify_occam_resources_v2.py','scripts/qualify_occam_resources_v3.py'),
 ('tests/test_occam_resources_v2.py','tests/test_occam_resources_v3.py'))
for old,new in pairs:
    text=(ROOT/old).read_text(encoding='utf8')
    for a,b in (('occam_resource_process_v2','occam_resource_process_v3'),('occam_resource_qualification_v2','occam_resource_qualification_v3'),
        ('occam_resource_fixture_v2','occam_resource_fixture_v3'),('qualify_occam_resources_v2','qualify_occam_resources_v3'),
        ('test_occam_resources_v2','test_occam_resources_v3'),('occam_resources_v2','occam_resources_v3'),
        ('occam_resource_software_qualification_v2','occam_resource_software_qualification_v3'),
        ('OCCAM_RESOURCE_SOFTWARE_SPEC_V2','OCCAM_RESOURCE_SOFTWARE_SPEC_V3'),('OCCAM_RESOURCE_SOFTWARE_RESULT_V2','OCCAM_RESOURCE_SOFTWARE_RESULT_V3'),
        ('OCCAM_RESOURCE_QUALIFICATION_V2','OCCAM_RESOURCE_QUALIFICATION_V3')):text=text.replace(a,b)
    if new.startswith('src/') and 'process_v3' in new:
        text=text.replace('from src.analysis import occam_resource_observation_v1 as resources','from src.analysis import occam_resource_observation_v1 as resources\nfrom src.analysis import occam_platform_bootstrap_v1 as bootstrap')
        text=text.replace("'src/analysis/command_contrast_io_v1.py')","'src/analysis/command_contrast_io_v1.py','src/analysis/occam_platform_bootstrap_v1.py')")
        text=text.replace('direct_executable_sha256=sha(executable()))','direct_executable_sha256=sha(executable()),platform_module_sha256=bootstrap.module_sha256())')
        text=text.replace("'source_sha256','runtime_lock_sha256','direct_executable_sha256'}","'source_sha256','runtime_lock_sha256','direct_executable_sha256','platform_module_sha256'}")
        text=text.replace("    if value['direct_executable_sha256']!=sha(executable()):", "    if value['platform_module_sha256']!=bootstrap.module_sha256():raise ValueError('locked platform module changed')\n    if value['direct_executable_sha256']!=sha(executable()):")
        text=text.replace("direct_executable_sha256=request['direct_executable_sha256']).items()","direct_executable_sha256=request['direct_executable_sha256'],platform_module_sha256=request['platform_module_sha256']).items()")
        text=text.replace('direct_executable_sha256=sha(Path(sys.executable)),started_ns=started)','direct_executable_sha256=sha(Path(sys.executable)),platform_module_sha256=bootstrap.module_sha256(),started_ns=started)')
        a="            with read_only(guard):\n                from src.analysis.response_action_io_v1 import verify_runtime\n                verify_runtime(read(RUNTIME_LOCK))\n            payload=dict(runtime_verified=True,guard=guard,dependency_import_only=True)"
        b="            with bootstrap.in_process_queries(request['platform_module_sha256']) as platform_query:\n                with read_only(guard):\n                    from src.analysis.response_action_io_v1 import verify_runtime\n                    verify_runtime(read(RUNTIME_LOCK))\n            payload=dict(runtime_verified=True,guard=guard,dependency_import_only=True,platform_query=platform_query)"
        assert a in text;text=text.replace(a,b)
    if new.startswith('src/') and 'qualification_v3' in new:
        text=text.replace("value['reused_unique_tests']!=2619","value['reused_unique_tests']!=2621")
        text=text.replace("OWN=(*p.SOURCES[:3],","OWN=(*p.SOURCES[:3],'src/analysis/occam_platform_bootstrap_v1.py',")
        text=text.replace("direct_executable_sha256=request['direct_executable_sha256'])","direct_executable_sha256=request['direct_executable_sha256'],platform_module_sha256=request['platform_module_sha256'])")
        needle="            guard=payload['guard'];counts=guard['operation_counts']"
        extra="""            info=payload['platform_query']
            _require(info['schema']=='OCCAM_PLATFORM_BOOTSTRAP_V1' and info['platform_module_sha256']==request['platform_module_sha256']
                and info['optional_shell_probe_disabled'] is True and info['original_function_restored'] is True,'platform query source/restore')
            _require(len(info['native_windows_version'])==3 and all(type(v) is int and v>=0 for v in info['native_windows_version'])
                and type(info['optional_command_calls_suppressed']) is int and info['optional_command_calls_suppressed']>=0,'native version/query count')
"""
        assert needle in text;text=text.replace(needle,extra+needle)
        needle="        _require(request['source_sha256']=="
        pos=text.index(needle)
        text=text[:pos]+"        _require(request['platform_module_sha256']==p.read(FREEZE)['input_sha256']['.python310/Lib/platform.py'],'platform frozen input')\n"+text[pos:]
    if new.startswith('tests/'):
        text=text.replace("direct_executable_sha256=s['direct_executable_sha256'],started_ns=self.clock())","direct_executable_sha256=s['direct_executable_sha256'],platform_module_sha256=s['platform_module_sha256'],started_ns=self.clock())")
        needle="        if s['kind']=='TAMPER':identity['nonce']='0'*32"
        extra="""        if s['kind']=='IMPORT_RUNTIME':payload['platform_query']=dict(schema='OCCAM_PLATFORM_BOOTSTRAP_V1',platform_module_sha256=s['platform_module_sha256'],
            native_windows_version=[10,0,33333],optional_command_calls_suppressed=1,optional_shell_probe_disabled=True,original_function_restored=True)
"""
        assert needle in text;text=text.replace(needle,extra+needle)
    compile(text,new,'exec')
    with (ROOT/new).open('x',encoding='utf8',newline='\n') as f:f.write(text)
print('created independent v3 process, qualification, workers and regression sources')

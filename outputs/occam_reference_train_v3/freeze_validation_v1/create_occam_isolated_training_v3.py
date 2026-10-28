from pathlib import Path
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects')
pairs=(('src/analysis/occam_reference_train_io_v2.py','src/analysis/occam_reference_train_io_v3.py'),
 ('src/analysis/occam_reference_train_host_v2.py','src/analysis/occam_reference_train_host_v3.py'),
 ('src/analysis/occam_reference_train_audit_v3.py','src/analysis/occam_reference_train_audit_v4.py'),
 ('src/analysis/occam_reference_learning_io_v2.py','src/analysis/occam_reference_learning_io_v3.py'),
 ('src/analysis/occam_reference_learner_v2.py','src/analysis/occam_reference_learner_v3.py'),
 ('scripts/train_occam_reference_v2.py','scripts/train_occam_reference_v3.py'))
for old,new in pairs:
    s=(ROOT/old).read_text(encoding='utf8')
    for a,b in (('occam_reference_train_io_v2','occam_reference_train_io_v3'),('occam_reference_learner_v2','occam_reference_learner_v3'),
        ('train_occam_reference_v2','train_occam_reference_v3'),('OCCAM_REFERENCE_TRAIN_V2','OCCAM_REFERENCE_TRAIN_V3'),
        ('occam_reference_train_v2','occam_reference_train_v3'),('occam_reference_train_seeds_v2','occam_reference_train_seeds_v3'),
        ('occam_training_v2_20261028','occam_training_v3_20261028')):s=s.replace(a,b)
    if new.endswith('train_io_v3.py'):
        for a,b in (('169000','172000'),('169002','172002'),('169100','172100'),('169153','172153'),('169003','172003'),('169099','172099'),
            ('169154','172154'),('169999','172999'),('170000','173000'),('171999','174999'),
            ('2026102841','2026102861'),('2026102842','2026102862'),('2026102843','2026102863')):s=s.replace(a,b)
        s=s.replace('model_init_rng_seed=2026102834,optimizer_rng_seed=2026102835)',
            'model_init_rng_seed=2026102834,optimizer_rng_seed=2026102835,global_rng_seed_numpy=2026102864,global_rng_seed_python=2026102865)')
        s=s.replace('    head=io.git(\'rev-parse\',\'HEAD\');names=',"    from src.analysis.occam_native_case_io_v1 import runtime_bindings\n    bindings=runtime_bindings()\n    head=io.git('rev-parse','HEAD');names=")
        s=s.replace("m=dict(experiment_run_id='occam_reference_train_v3_", "m=dict(native_runtime_bindings=bindings,experiment_run_id='occam_reference_train_v3_")
        s=s.replace("    m['manifest_id']=io.digest(m);", "    m['manifest_id']=io.digest(m);")
        s=s.replace("    q=io.read(VALIDATION/'complete.json');", "    from src.analysis.occam_native_case_io_v1 import require_science_resources\n    require_science_resources(initial=True)\n    q=io.read(VALIDATION/'complete.json');")
        s=s.replace("    if phase=='TRAIN':", "    io.require(not (Path(path).parent/'CLOSED_TECHNICAL_FAILURE.json').exists(),'closed isolated allocation cannot resume')\n    from src.analysis.occam_native_case_io_v1 import require_science_resources\n    require_science_resources(initial=False)\n    if phase=='TRAIN':")
        s=s.replace("complete_limits=dict(executions=684,control_steps=342000,all_resets=34884,physical_frames=19152000),", "complete_limits=dict(executions=684,control_steps=342000,all_resets=34884,physical_frames=19152000),\n    isolated_execution=execution(),")
        s+='''

def execution():
    return dict(schema='OCCAM_ISOLATED_NATIVE_CASE_V1',one_complete_case_per_process=True,worker_wall_seconds=210,
        termination_wait_seconds=5,resource_sample_interval_seconds=.25,worker_private_commit_cap_bytes=2*1024**3,
        admission_available_commit_bytes=4*1024**3,initial_disk_bytes=4*1024**3,phase_disk_bytes=2*1024**3,
        live_available_commit_bytes=512*1024**2,live_disk_bytes=512*1024**2,
        phase_wall_seconds_max=dict(NATIVE=10800,TRAIN=43200),no_retries=True,full_runtime_hash_check_each_worker=True)
'''
    if new.endswith('train_host_v3.py'):
        s=s.replace('import numpy as np','import numpy as np\nimport traceback')
        s=s.replace('noise_namespace_oracle=2026102842','noise_namespace_oracle=a.registry()[\'noise_namespace\']')
        s=s.replace("row['error']=dict(type=type(error).__name__,message=str(error))","row['error']=dict(type=type(error).__name__,message=str(error),traceback=traceback.format_exc())")
        s=s.replace("row['close_error']=dict(type=type(error).__name__,message=str(error))","row['close_error']=dict(type=type(error).__name__,message=str(error),traceback=traceback.format_exc())")
    if new.endswith('train_audit_v4.py'):
        s=s.replace('V3 corrects only a stale namespace assertion and preserves failed export paths.','V4 reads independently frozen isolated-case v3 records without resimulation.')
        s=s.replace("return raw/'audit_repair_v3' if phase=='NATIVE' else raw","return raw")
    compile(s,new,'exec')
    with (ROOT/new).open('x',encoding='utf8',newline='\n') as f:f.write(s)
print('new allocation/host/reader and source-identical learning wrappers created; old sources untouched')

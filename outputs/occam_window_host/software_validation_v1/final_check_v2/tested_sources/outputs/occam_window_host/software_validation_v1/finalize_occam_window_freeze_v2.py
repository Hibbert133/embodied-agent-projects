"""Final fourth bounded software attempt; preserve the earlier passed snapshot.

Add independently checked manifest/case brackets before any native execution.
Package a large inventory without committing its original large file.
"""
from pathlib import Path
from time import perf_counter_ns
import gzip,hashlib,shutil,subprocess,sys,unittest
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import occam_window_io_v1 as a
from src.analysis.release_learning_guard_v1 import read_only
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
from outputs.information_release.validation_v1.validate_freeze import index_bytes
io=a.io


def main():
    started=perf_counter_ns();base=a.VALIDATION;old=io.read(base/'complete.json');io.require(old['integrity']=='PASSED','previous complete metadata checks')
    out=base/'final_check_v2';out.mkdir(exist_ok=False);io.write(out/'prior_complete.json',old)
    # Only the independent audit integration changed after the earlier check.
    changed={n for n,h in old['source_sha256'].items() if io.sha(ROOT/n)!=h}
    io.require(changed=={'src/analysis/occam_window_audit_v1.py'},'explicitly owned pre-collection audit change')
    own=set(old['source_sha256'])|{'src/analysis/occam_window_envelope_v1.py','tests/test_occam_window_envelope_v1.py'}
    helper=base/'finalize_occam_window_freeze_v2.py';shutil.copyfile(__file__,helper);compile(helper.read_bytes(),str(helper),'exec');own.add(helper.relative_to(ROOT).as_posix())
    source={n:io.sha(ROOT/n) for n in sorted(own)};io.write(out/'source_before_tests.json',source)
    snapshot=out/'tested_sources';snapshot.mkdir()
    for n in own:
        target=snapshot/n;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/n).read_bytes())
    guard={};ids=[]
    with (out/'tests.log').open('x',encoding='utf8',newline='\n') as log,read_only(guard,max_solve=2000):
        suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(n) for n in ('tests.test_occam_window_host_v1','tests.test_occam_window_envelope_v1'))
        def collect(s):
            for t in s:
                if isinstance(t,unittest.TestSuite):collect(t)
                else:ids.append(t.id())
        collect(suite);result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    io.write(out/'tests.json',dict(success=result.wasSuccessful(),tests=result.testsRun,ids=ids,guard=guard,software_attempt=4))
    io.require(result.wasSuccessful() and result.testsRun==len(set(ids))==31,'final31 unique tests')
    # Preserve the source-bound earlier full tracked scan; actual new index bytes
    # are all scanned again below. The legacy --staged flag does not parse index
    # blobs; index_bytes plus BASIC/EXTRA below does.
    for receipt in ('compile.json','dependencies.json','full_tracked_secrets.json','staged_secrets.json'):
        io.require(io.read(base/receipt)['returncode']==0,'previous validation '+receipt)
    for n,h in io.read(base/'source_reuse.json')['source_sha256'].items():io.require(io.sha(ROOT/n)==h,'old sources unchanged '+n)
    commands={}
    for label,args in (('compile',[sys.executable,'-m','compileall','-q','src','scripts','tests']),('dependencies',[sys.executable,'-m','pip','check'])):
        p=subprocess.run(args,cwd=ROOT,capture_output=True,text=True);commands[label]=dict(returncode=p.returncode,stdout=p.stdout,stderr=p.stderr)
        io.require(p.returncode==0,label)
    io.write(out/'commands.json',commands)
    original=a.QUERY/'inventory.json';raw=original.read_bytes();compressed=a.QUERY/'inventory.json.gz'
    with compressed.open('xb') as handle:
        with gzip.GzipFile(filename='',mode='wb',fileobj=handle,mtime=0) as stream:stream.write(raw)
    restored=Path(__file__).parent/'occam_window_seed_inventory_restored_v1.json';restored.write_bytes(gzip.decompress(compressed.read_bytes()))
    io.require(restored.read_bytes()==raw,'actual inventory restoration')
    io.write(a.QUERY/'inventory_bundle.json',dict(integrity='PASSED',original_path=original.relative_to(ROOT).as_posix(),original_bytes=len(raw),original_sha256=io.sha(original),
        compressed_path=compressed.relative_to(ROOT).as_posix(),compressed_bytes=compressed.stat().st_size,compressed_sha256=io.sha(compressed),actual_restore_sha256=io.sha(restored),
        original_retained_local=True,restore_retained_external=True))
    names=set(io.git('diff','--cached','--name-only').splitlines());raw_name=original.relative_to(ROOT).as_posix()
    io.require(raw_name in names,'only owned large inventory removed from index');io.git('-c','maintenance.auto=false','-c','gc.auto=0','restore','--staged','--',raw_name);names.remove(raw_name)
    names|=own|{p.relative_to(ROOT).as_posix() for p in a.QUERY.iterdir() if p.is_file() and p.name!='inventory.json'}
    def stage(label):
        nonlocal names
        names|={p.relative_to(ROOT).as_posix() for p in base.rglob('*') if p.is_file()}
        path=out/(label+'.nul');names.add(path.relative_to(ROOT).as_posix());path.write_bytes(b'\0'.join(n.encode() for n in sorted(names))+b'\0')
        io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+path.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    def check():
        actual=index_bytes(names)
        for n in actual:
            data=(ROOT/n).read_bytes()
            if n.endswith('.gz'):data=gzip.decompress(data)
            if b'\0' in data:continue
            text=data.decode('utf8',errors='replace');io.require(find_secret_rule(text) is None,'actual staged basic secret '+n)
            for label,p in EXTRA.items():io.require(p.search(text) is None,'actual staged extra secret '+label+' '+n)
        io.require(not io.git('diff','--check') and not io.git('diff','--cached','--check'),'ordinary and staged differences');return actual
    stage('owned_checked');actual=check();io.write(out/'index_disk_proof.json',dict(integrity='PASSED',actual_index_basic_extra_decompressed_scan=True,object_sha256=actual))
    for n,h in source.items():io.require(io.sha(ROOT/n)==h,'final tested source changed '+n)
    final=dict(integrity='PASSED',source_sha256=source,unique_test_total=2518,new_unique_tests=31,reused_unique_tests=2487,
        software_attempts=4,development_and_prior_check_test_executions=54,final_test_executions=31,total_test_executions=85,
        first_21_callback_tests_not_runtime_instrumented_disclosed=True,first21_source_solve_upper_bound=1302,guard=guard,
        prior_complete_sha256=io.sha(out/'prior_complete.json'),source_reuse_receipt_sha256=io.sha(base/'source_reuse.json'),
        inventory_actual_restore_verified=True,large_original_inventory_not_committed=True,new_robot_interactions=0,scientific_model_training=0,
        online_LLM_API_calls=0,synthetic_Adam_steps=0,native_population_not_executed_yet=True,publication_goal_complete=False,wall_ns=perf_counter_ns()-started)
    io.write(base/'complete.json',final,exclusive=False);io.write(out/'complete.json',final);stage('owned_final');check()
    print(dict(integrity='PASSED',new_unique_tests=31,unique_test_total=2518,owned_objects=len(names),inventory_restoration=True),flush=True)


if __name__=='__main__':main()

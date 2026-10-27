"""Retain CRLF presentation failure and validate the same scientific delivery."""
from pathlib import Path
from time import perf_counter_ns
import gzip,hashlib,shutil,subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
from scripts.check_tracked_secrets import find_secret_rule
start=perf_counter_ns();base=ROOT/'outputs/controller_agreement';out=base/'result_validation_v1';source=io.git('rev-parse','HEAD')
assert source=='0272551690b39902cdd275ac6f4f1aa0ae927f4a' and not (out/'complete.json').exists()
names={n.decode() for n in (out/'owned_initial.nul').read_bytes().split(b'\0') if n}
assert set(io.git('diff','--cached','--name-only').splitlines())==names and not io.git('diff','--name-only')
failure=out/'retained_presentation_failure01';failure.mkdir(exist_ok=False)
raw=(out/'report_build.log').read_bytes()
with (failure/'report_build.original.log.gz').open('xb') as f,gzip.GzipFile(filename='',mode='wb',fileobj=f,mtime=0) as z:z.write(raw)
assert gzip.decompress((failure/'report_build.original.log.gz').read_bytes())==raw
io.write(failure/'failure.json',dict(stage='actual_index_disk_check',error='index and disk differ outputs/controller_agreement/result_validation_v1/report_build.log',
    cause='PowerShell native-output CRLF normalized by Git',original_bytes=len(raw),original_sha256=hashlib.sha256(raw).hexdigest(),scientific_data_changed=False,
    no_repeated_scientific_analysis=True,new_physics=0,new_fits=0,online_LLM_API_calls=0))
(out/'report_build.log').write_bytes(raw.replace(b'\r\n',b'\n'))
report=ROOT/'reports/controller_agreement_v1_zh.md';text=report.read_text('utf8')
text+='\n结果交付首次索引字节检查检出了PowerShell日志CRLF被Git规范化。原始日志字节以确定性gzip和SHA保留，规范日志转LF；失败记录及两个交付脚本保留。未改科学数据、统计、冻结方法或重复分析。\n'
report.write_text(text,encoding='utf8',newline='\n')
tools=base/'presentation_tools_v1';shutil.copyfile(Path(__file__),tools/Path(__file__).name);compile((tools/Path(__file__).name).read_bytes(),str(__file__),'exec')
freeze=io.read(base/'freeze_validation_v1/complete.json');complete=io.read(base/'feasibility_v1/complete.json')
assert freeze['integrity']==complete['integrity']=='PASSED'
for n,h in freeze['source_sha256'].items():assert io.sha(ROOT/n)==h,n
for n,h in complete['artifact_sha256'].items():assert io.sha(base/'feasibility_v1'/n)==h,n
names|={p.relative_to(ROOT).as_posix() for folder in ('feasibility_v1','presentation_development_v1','presentation_tools_v1','result_validation_v1') for p in (base/folder).rglob('*') if p.is_file()}
def stage(label):
    global names
    names|={p.relative_to(ROOT).as_posix() for p in out.rglob('*') if p.is_file()}
    path=out/(label+'.nul');names.add(path.relative_to(ROOT).as_posix());path.write_bytes(b'\0'.join(n.encode() for n in sorted(names))+b'\0')
    io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+path.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
def check():
    actual=index_bytes(names)
    for n in actual:
        data=(ROOT/n).read_bytes()
        if n.endswith('.gz'):data=gzip.decompress(data)
        if b'\0' not in data:
            text=data.decode('utf8',errors='replace');assert find_secret_rule(text) is None,n
            for label,regex in EXTRA.items():assert regex.search(text) is None,(label,n)
    assert not io.git('diff','--check') and not io.git('diff','--cached','--check')
    return actual
stage('owned_repaired');proof=check()
p=subprocess.run([sys.executable,'scripts/check_tracked_secrets.py'],cwd=ROOT,capture_output=True,text=True,encoding='utf8',errors='replace')
io.write(out/'tracked_secret_scan.json',dict(returncode=p.returncode,stdout=p.stdout,stderr=p.stderr));assert p.returncode==0
io.write(out/'source_test_reuse.json',dict(integrity='PASSED',unique_tests=2448,new_tests_at_result=0,unchanged_source_sha256=freeze['source_sha256'],
    freeze_check_sha256=io.sha(base/'freeze_validation_v1/complete.json'),compile_dependency_receipt_sha256={p.name:io.sha(p) for p in (base/'freeze_validation_v1/compile.json',base/'freeze_validation_v1/dependencies.json')},
    no_scientific_source_changes_after_freeze=True))
io.write(out/'index_disk_proof.json',dict(integrity='PASSED',source_git_commit=source,object_sha256=proof,actual_index_basic_extra_and_decompressed_gzip_scan=True))
io.write(out/'complete.json',dict(integrity='PASSED',classification='POST_HOC_DESCRIPTIVE_TRAIN_ONLY',source_frozen_commit=source,unique_tests=2448,new_result_tests=0,
    new_physics=0,new_fits=0,online_LLM_API_calls=0,scientific_decision='INSUFFICIENT_SUPPORT_FOR_COLLECTION_SAVINGS',publication_goal_complete=False,
    scientific_records_unchanged_since_first_delivery=True,retained_CRLF_presentation_failure=True,
    report_sha256=io.sha(report),artifact_sha256={n:io.sha(ROOT/n) for n in sorted(names)},wall_ns=perf_counter_ns()-start))
stage('owned_final');proof=check();print(dict(integrity='PASSED',owned_objects=len(names),bytes=sum((ROOT/n).stat().st_size for n in names),scientific_status='DESCRIPTIVE_INSUFFICIENT_SUPPORT'),flush=True)

"""Deliver only owned artifacts; independent results and source remain unchanged."""
from pathlib import Path
from time import perf_counter_ns
import shutil,subprocess,sys,gzip
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
from scripts.check_tracked_secrets import find_secret_rule
start=perf_counter_ns();base=ROOT/'outputs/controller_agreement';out=base/'result_validation_v1';out.mkdir(exist_ok=False)
source=io.git('rev-parse','HEAD');assert source=='0272551690b39902cdd275ac6f4f1aa0ae927f4a' and not io.git('status','--porcelain','--untracked-files=no')
freeze=io.read(base/'freeze_validation_v1/complete.json');complete=io.read(base/'feasibility_v1/complete.json')
assert freeze['integrity']==complete['integrity']=='PASSED'
for n,h in freeze['source_sha256'].items():assert io.sha(ROOT/n)==h,n
for n,h in complete['artifact_sha256'].items():assert io.sha(base/'feasibility_v1'/n)==h,n
assert io.read(base/'feasibility_v1/presentation/independent_statistics_audit.json')['integrity']=='PASSED'
tools=base/'presentation_tools_v1';tools.mkdir(exist_ok=False)
for name in ('verify_controller_agreement_commit_v1.py','build_controller_agreement_report_v1.py','plot_controller_agreement_v1.py','finalize_controller_agreement_result_v1.py'):
    shutil.copyfile(Path(__file__).parent/name,tools/name);compile((tools/name).read_bytes(),name,'exec')
shutil.copyfile(Path(__file__).parent/'controller_agreement_postcommit_0272551690b3.json',out/'freeze_committed_bytes.json')
shutil.copyfile(Path(__file__).parent/'controller_agreement_report_build_v1.log',out/'report_build.log')
names={p.relative_to(ROOT).as_posix() for folder in ('feasibility_v1','presentation_development_v1','presentation_tools_v1') for p in (base/folder).rglob('*') if p.is_file()}
names|={'reports/controller_agreement_v1_zh.md','docs/research/controller_agreement_result_decision_v1_zh.md'}
def stage(label):
    global names
    names|={p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()}
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
stage('owned_initial');proof=check()
p=subprocess.run([sys.executable,'scripts/check_tracked_secrets.py'],cwd=ROOT,capture_output=True,text=True,encoding='utf8',errors='replace')
io.write(out/'tracked_secret_scan.json',dict(returncode=p.returncode,stdout=p.stdout,stderr=p.stderr));assert p.returncode==0
io.write(out/'source_test_reuse.json',dict(integrity='PASSED',unique_tests=2448,new_tests_at_result=0,
    unchanged_source_sha256=freeze['source_sha256'],freeze_check_sha256=io.sha(base/'freeze_validation_v1/complete.json'),
    compile_dependency_receipt_sha256={p.name:io.sha(p) for p in (base/'freeze_validation_v1/compile.json',base/'freeze_validation_v1/dependencies.json')},
    no_scientific_source_changes_after_freeze=True))
io.write(out/'index_disk_proof.json',dict(integrity='PASSED',source_git_commit=source,object_sha256=proof,actual_index_basic_extra_and_decompressed_gzip_scan=True))
io.write(out/'complete.json',dict(integrity='PASSED',classification='POST_HOC_DESCRIPTIVE_TRAIN_ONLY',source_frozen_commit=source,
    unique_tests=2448,new_result_tests=0,new_physics=0,new_fits=0,online_LLM_API_calls=0,
    scientific_decision='INSUFFICIENT_SUPPORT_FOR_COLLECTION_SAVINGS',publication_goal_complete=False,
    report_sha256=io.sha(ROOT/'reports/controller_agreement_v1_zh.md'),
    artifact_sha256={n:io.sha(ROOT/n) for n in sorted(names)},wall_ns=perf_counter_ns()-start))
stage('owned_final');proof=check();print(dict(integrity='PASSED',owned_objects=len(names),bytes=sum((ROOT/n).stat().st_size for n in names),scientific_status='DESCRIPTIVE_INSUFFICIENT_SUPPORT'),flush=True)

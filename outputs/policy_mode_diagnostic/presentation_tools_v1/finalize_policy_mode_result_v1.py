"""Retain complete science, derived originals and exact-index delivery checks."""
from pathlib import Path
from time import perf_counter_ns
import gzip,hashlib,shutil,subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
from src.analysis import correction_effect_independent_v1 as independent
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
from scripts.check_tracked_secrets import find_secret_rule
start=perf_counter_ns();base=ROOT/'outputs/policy_mode_diagnostic';science=base/'diagnostic_v1';out=base/'result_validation_v1';out.mkdir(exist_ok=False)
head=io.git('rev-parse','HEAD');assert head=='074ef5632712f50ce1d1a811c0cd2a689feacbf2' and not io.git('status','--porcelain','--untracked-files=no')
freeze=io.read(base/'freeze_validation_v1/complete.json');complete=io.read(science/'complete.json')
assert freeze['integrity']==complete['integrity']=='PASSED' and io.read(science/'presentation/statistics_audit.json')['integrity']=='PASSED'
for n,h in freeze['source_sha256'].items():assert io.sha(ROOT/n)==h,n
for n,h in complete['artifact_sha256'].items():assert io.sha(science/n)==h,n
tools=base/'presentation_tools_v1';tools.mkdir(exist_ok=False)
for name in ('verify_policy_mode_commit_v1.py','build_policy_mode_report_v1.py','plot_policy_mode_diagnostic_v1.py','finalize_policy_mode_result_v1.py'):
    shutil.copyfile(Path(__file__).parent/name,tools/name);compile((tools/name).read_bytes(),name,'exec')
shutil.copyfile(Path(__file__).parent/'policy_mode_postcommit_074ef5632712.json',out/'freeze_committed_bytes.json')


def zipped(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as raw,gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0) as f:f.write(data)
    assert gzip.decompress(path.read_bytes())==data


# Derived CSVs and shell stdout are not scientific primary records. Retain their
# exact original bytes and produce LF copies before, not after, index validation.
normalized=[]
for folder in ('diagnostic_v1/presentation','presentation_drafts_v1'):
    for p in (base/folder).rglob('*.csv'):
        raw=p.read_bytes()
        if b'\r\n' in raw:
            target=out/'derived_originals'/p.relative_to(base).with_suffix(p.suffix+'.gz');zipped(target,raw)
            p.write_bytes(raw.replace(b'\r\n',b'\n'));normalized.append(dict(path=p.relative_to(ROOT).as_posix(),raw_bytes=len(raw),raw_sha256=hashlib.sha256(raw).hexdigest(),retained_gzip=target.relative_to(ROOT).as_posix()))
raw_log=(Path(__file__).parent/'policy_mode_report_build_v1.log').read_bytes();zipped(out/'derived_originals/report_build.log.gz',raw_log)
(out/'report_build.log').write_bytes(raw_log.replace(b'\r\n',b'\n'))
io.write(out/'presentation_qa.json',dict(integrity='PASSED',csv_originals=normalized,raw_shell_log_retained=True,
    initial_font_warning='Microsoft YaHei lacks superscript minus/six; changed label to ASCII 1e-6',
    initial_png_and_plot_source_retained=True,final_png_visually_inspected=True,scientific_data_changed=False))

# Full condition marginal, as declared in the protocol; no new scientific metric.
windows=io.read(science/'windows.json');table=['## H2三任务与两条件完整边际','',
    '|任务|条件|完整／162|可用组|发送差L1|模式项L1|连续项L1|','|---|---|---:|---:|---:|---:|---:|']
for task in ('push-v3','reach-v3','door-open-v3'):
    for context in ('UNCHANGED','CHANGED'):
        rows=[r for r in windows if r['task']==task and r['context']==context and r['horizon']==2 and r['metrics'] is not None]
        if rows:
            w=independent.weights(rows);v={k:sum(float(q)*r['metrics'][k] for q,r in zip(w,rows)) for k in ('sent_total_L1','sent_mode_L1','sent_state_L1')}
            table.append(f"|{task}|{context}|{len(rows)}/162|{len({r['group'] for r in rows})}|{v['sent_total_L1']:.8g}|{v['sent_mode_L1']:.8g}|{v['sent_state_L1']:.8g}|")
        else:table.append(f'|{task}|{context}|0/162|0|缺失|缺失|缺失|')
report=ROOT/'reports/policy_mode_diagnostic_v1_zh.md';text=report.read_text('utf8');assert '## H2三任务与两条件完整边际' not in text
text=text.replace('## 六窗完整总表','\n'.join(table)+'\n\n## 六窗完整总表');report.write_text(text,encoding='utf8',newline='\n')

# Large primary JSON remains local. Commit complete pieces and an independently
# restored, byte-verified gzip alternative for the small remote archive.
large=science/'windows.json';raw=large.read_bytes();parts=base/'large_record_parts_v1';parts.mkdir(exist_ok=False);items=[]
for i in range(0,len(raw),4*1024**2):
    p=parts/('windows.part%03d.bin'%(i//(4*1024**2)));p.write_bytes(raw[i:i+4*1024**2]);items.append(dict(path=p.name,bytes=p.stat().st_size,sha256=io.sha(p)))
zipped(parts/'windows.json.gz',raw)
restoration=base/'restorations_v1';restoration.mkdir(exist_ok=False);restored=b''.join((parts/r['path']).read_bytes() for r in items)
assert restored==raw==gzip.decompress((parts/'windows.json.gz').read_bytes());(restoration/'windows.json').write_bytes(restored)
io.write(parts/'index.json',dict(integrity='PASSED',raw_local_path=large.relative_to(ROOT).as_posix(),raw_bytes=len(raw),raw_sha256=io.sha(large),parts=items,
    gzip_alternative='windows.json.gz',gzip_sha256=io.sha(parts/'windows.json.gz'),actual_reconstruction_verified=True,
    retained_restoration=restoration.relative_to(ROOT).as_posix()+'/windows.json',raw_and_restoration_retained_locally=True))
names={p.relative_to(ROOT).as_posix() for folder in ('diagnostic_v1','presentation_drafts_v1','presentation_tools_v1','large_record_parts_v1') for p in (base/folder).rglob('*') if p.is_file() and p!=large}
names|={'reports/policy_mode_diagnostic_v1_zh.md','docs/research/policy_mode_result_decision_v1_zh.md'}
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
            for label,p in EXTRA.items():assert p.search(text) is None,(label,n)
    assert not io.git('diff','--check') and not io.git('diff','--cached','--check');return actual
stage('owned_initial');proof=check()
p=subprocess.run([sys.executable,'scripts/check_tracked_secrets.py'],cwd=ROOT,capture_output=True,text=True,encoding='utf8',errors='replace')
io.write(out/'tracked_secret_scan.json',dict(returncode=p.returncode,stdout=p.stdout,stderr=p.stderr));assert p.returncode==0
io.write(out/'test_source_reuse.json',dict(integrity='PASSED',unique_tests=2463,new_tests_at_result=0,unchanged_source_sha256=freeze['source_sha256'],
    prior_check_sha256=io.sha(base/'freeze_validation_v1/complete.json'),compile_dependency_sha256={p.name:io.sha(p) for p in (base/'freeze_validation_v1/compile.json',base/'freeze_validation_v1/dependencies.json')}))
io.write(out/'index_disk_proof.json',dict(integrity='PASSED',actual_index_basic_extra_decompressed_scan=True,object_sha256=proof))
io.write(out/'complete.json',dict(integrity='PASSED',classification='POST_HOC_FUNCTIONAL_NOT_PHYSICAL_CAUSAL',frozen_source_commit=head,
    new_physics=0,new_fits=0,online_LLM_API_calls=0,unique_tests=2463,report_sha256=io.sha(report),large_record_index_sha256=io.sha(parts/'index.json'),
    publication_goal_complete=False,receipt_sha256={n:io.sha(ROOT/n) for n in sorted(names)},wall_ns=perf_counter_ns()-start))
stage('owned_final');check();print(dict(integrity='PASSED',owned_objects=len(names),bytes=sum((ROOT/n).stat().st_size for n in names),large_record_parts=len(items)),flush=True)

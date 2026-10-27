"""Retain generated-SVG whitespace check failure and finish exact delivery checks."""
from pathlib import Path
from time import perf_counter_ns
import gzip,hashlib,subprocess,sys,shutil
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import graybox_qualification_io_v2 as a
from src.analysis.release_learning_guard_v1 import read_only
from scripts.archive_action_response import members
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
io=a.io;start=perf_counter_ns();path=Path(sys.argv[1]).resolve();m=a.checked(path);root=path.parent;out=a.BASE/'result_validation_v2';guard={}
assert io.git('rev-parse','HEAD')==m['source_git_commit'] and not (out/'complete.json').exists()
p=subprocess.run(['git','diff','--cached','--check'],cwd=ROOT,capture_output=True);assert p.returncode!=0
with (out/'failed_diff_check01.txt.gz').open('xb') as raw,gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0) as f:f.write(p.stdout+p.stderr)
diff=p.stdout+p.stderr;lines=diff.decode('utf8',errors='replace').splitlines();violations=[s for s in lines if ': trailing whitespace.' in s]
assert violations and all('/presentation/qualification.svg:' in s for s in violations)
assert gzip.decompress((out/'failed_diff_check01.txt.gz').read_bytes())==diff
shutil.copyfile(Path(__file__).parent/'validate_graybox_qualification_delivery_v2.py',out/'validator_before_svg_diff_fix.py.saved')
svg=root/'presentation/qualification.svg';before_svg=io.sha(svg);(root/'presentation/.gitattributes').write_bytes(b'*.svg binary\n')
io.write(out/'attempt01_failure.json',dict(integrity='FAILED',stage='STAGED_DIFF_CHECK',returncode=p.returncode,
    cause='Matplotlib-generated SVG path strings contain trailing spaces; preserve original figure bytes with a scoped binary artifact rule',
    violation_count=len(violations),full_diff_check_raw_sha256=hashlib.sha256(diff).hexdigest(),full_diff_check_gzip_sha256=io.sha(out/'failed_diff_check01.txt.gz'),
    svg_sha256=before_svg,no_scientific_data_or_code_change=True))
with read_only(guard):
    a.source_contract();freeze=io.read(a.VALIDATION/'complete.json');reuse=io.read(a.VALIDATION/'source_reuse.json')
    for mapping in (freeze['source_sha256'],reuse['source_sha256']):
        for n,h in mapping.items():assert io.sha(ROOT/n)==h,n
    for n,h in freeze['receipt_sha256'].items():assert io.sha(a.VALIDATION/n)==h,n
    result=io.read(root/'qual_evaluation/result.json');assert result['status']=='CLOSED_NEGATIVE' and result['invalid_forecasts']==0
    assert result['status']==('QUALIFIED_RESPONSE_CONTRAST_COMPONENT_ONLY' if all(result['gates'].values()) else 'CLOSED_NEGATIVE')
    assert io.read(root/'qual_evaluation/audit.json')['result_sha256']==io.sha(root/'qual_evaluation/result.json')
    old=io.read(out/'integrity.json');assert old['integrity']=='PASSED' and old['full_pipeline_finished'] and old['actual_new_costs']['executions']==432 and old['actual_new_costs']['control_steps']==29967
    assert old['actual_new_costs']==io.read(root/'presentation/costs.json')['new_total']
    catalog=io.read(a.BASE/'archives_v2'/root.name/'catalog.json');assert len(catalog['files'])==9
    for item in catalog['files']:
        index=ROOT/item['index'];value,_=members(index);assert io.sha(index)==item['index_sha256'] and value['source_sha256']==item['sha256']==io.sha(ROOT/item['source'])==io.sha(Path(item['actual_restore']['target']))
    figure=io.read(root/'presentation/figure_receipt.json');assert io.sha(svg)==before_svg==figure['svg_sha256']
    visual=io.read(root/'presentation/figure_visual_check.json');assert visual['inspection']=='ACTUAL_RENDER_VIEWED' and visual['png_sha256']==io.sha(root/'presentation/qualification.png')
    report=ROOT/'reports/graybox_qualification_v2_zh.md';assert io.read(root/'presentation/report_receipt.json')['report_sha256']==io.sha(report)
for n in ('finalize_graybox_qualification_delivery_v3.py','verify_graybox_qualification_result_v2.py'):(root/'presentation_tools'/n).write_bytes((Path(__file__).parent/n).read_bytes())
names={n.decode() for n in (out/'owned_initial.nul').read_bytes().split(b'\0') if n}|{p.relative_to(ROOT).as_posix() for base in (out,root/'presentation_tools') for p in base.iterdir() if p.is_file()}
compiled=[]
for n in names:
    if n.endswith('.py'):compile((ROOT/n).read_bytes(),n,'exec');compiled.append(n)
def stage(label):
    global names
    names|={p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()};spec=out/(label+'.nul');names.add(spec.relative_to(ROOT).as_posix());spec.write_bytes(b'\0'.join(n.encode() for n in sorted(names))+b'\0')
    io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+spec.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
def check():
    actual=index_bytes(names)
    for n in actual:
        data=(ROOT/n).read_bytes()
        if b'\0' not in data:
            for label,pattern in EXTRA.items():assert pattern.search(data.decode('utf8',errors='replace')) is None,(label,n)
    assert not io.git('diff','--check') and not io.git('diff','--cached','--check');return actual
stage('owned_repaired');actual=check();io.write(out/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=actual,basic_and_extra_actual_index_secret_scan=True,original_svg_bytes_preserved=True))
io.write(out/'complete.json',dict(integrity='PASSED',scientific_status='CLOSED_NEGATIVE',source_manifest_sha256=io.sha(path),report_sha256=io.sha(report),costs_sha256=io.sha(root/'presentation/costs.json'),
    full_tracked_secret_scan_source_bound=io.sha(a.VALIDATION/'full_tracked_secret_scan.json'),unique_test_total=2428,new_tests_at_result=0,new_physics=0,new_primary_model_fits=0,
    online_LLM_API_calls=0,original_failure_and_raw_restorations_retained=True,original_svg_preserved=True,failed_diff_check_retained=True,read_only_guard=guard,new_tools_compiled=compiled,
    publication_goal_complete=False,wall_ns=perf_counter_ns()-start))
stage('owned_final');check();print(dict(integrity='PASSED',status='CLOSED_NEGATIVE',owned_objects=len(names),restored=9),flush=True)

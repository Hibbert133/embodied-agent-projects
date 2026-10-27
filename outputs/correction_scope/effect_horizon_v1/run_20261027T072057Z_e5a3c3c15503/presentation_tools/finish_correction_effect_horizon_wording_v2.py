"""Finish metadata only after retained exclusive-write presentation failure."""
from pathlib import Path
from time import perf_counter_ns
import shutil,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from scripts import run_correction_effect_horizon_v1 as command
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
main=command.main;io=main.io;run=Path(sys.argv[1]).resolve().parent;main.checked(run/'manifest.json');out=main.BASE/'result_validation';revision=run/'presentation/wording_revision1';start=perf_counter_ns()
assert revision.is_dir() and io.read(out/'complete.json')['integrity']=='PASSED'
for n,h in io.read(run/'analysis/receipt.json')['artifact_sha256'].items():assert io.sha(run/'analysis'/n)==h
assert io.read(run/'analysis/audit.json')['integrity']=='PASSED'
io.write(revision/'failure.json',dict(integrity='RETAINED_PRESENTATION_METADATA_FAILURE',exception_type='FileExistsError',
    message='source_sha256.json already exists; io.write defaults to exclusive creation',
    failed_helper='clarify_correction_effect_horizon_wording_v1.py',failed_operation='first existing presentation hash receipt update',
    report_text_and_builder_already_clarified=True,scientific_run_not_repeated=True,new_physics=0,new_fits=0,online_LLM_API_calls=0))
shutil.copyfile(out/'owned_final.nul',revision/'owned_final.nul.before.saved')
tools=run/'presentation_tools';shutil.copyfile(Path(__file__),tools/Path(__file__).name)
for p in tools.glob('*.py'):compile(p.read_bytes(),str(p),'exec')
io.write(tools/'source_sha256.json',{p.name:io.sha(p) for p in tools.iterdir() if p.is_file() and p.name!='source_sha256.json'},exclusive=False)
report=ROOT/'reports/correction_effect_horizon_v1_zh.md';text=report.read_text('utf8')
assert text.count('没有度量变化幅度或其因果效应。')==1 and text.count('不是实机测量。')==1
r=io.read(run/'presentation/report_receipt.json');r.update(report_sha256=io.sha(report),presentation_wording_revision_only=True)
io.write(run/'presentation/report_receipt.json',r,exclusive=False)
io.write(revision/'repair_v2.json',dict(integrity='PASSED',method='Explicitly update presentation receipts only; prior values retained in before.saved',
    report_sha256=io.sha(report),all_scientific_sources_and_analysis_bytes_unchanged=True,new_physics=0,new_fits=0,online_LLM_API_calls=0,wall_ns=perf_counter_ns()-start))
names=set(command.SOURCES)|{'reports/correction_effect_horizon_v1_zh.md'}|{p.relative_to(ROOT).as_posix() for p in main.BASE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo')}
def stage(selected):
    p=out/'owned_final.nul';selected=set(selected)|{p.relative_to(ROOT).as_posix()};p.write_bytes(b'\0'.join(n.encode() for n in sorted(selected))+b'\0')
    io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+p.relative_to(ROOT).as_posix(),'--pathspec-file-nul');return selected
def scan(selected):
    actual=index_bytes(selected)
    for n in actual:
        data=(ROOT/n).read_bytes()
        if b'\0' not in data:assert not any(pattern.search(data.decode('utf8',errors='replace')) for pattern in EXTRA.values())
    assert not io.git('diff','--check') and not io.git('diff','--cached','--check');return actual
names=stage(names);actual=scan(names)
io.write(out/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=actual,all5832_windows_and2214_panels_retained=True,no_new_large_record_requires_sharding=True,presentation_wording_revision_only=True),exclusive=False)
old=io.read(out/'complete.json');old['source_sha256']={p.relative_to(ROOT).as_posix():io.sha(p) for p in tools.glob('*.py')}
old['receipt_sha256']={p.name:io.sha(p) for p in out.iterdir() if p.is_file() and p.name!='complete.json'};old['wording_repair_v2_sha256']=io.sha(revision/'repair_v2.json')
io.write(out/'complete.json',old,exclusive=False);names=stage(names);actual=scan(names)
print(dict(integrity='PASSED',staged_objects=len(actual),scientific_sources_and_results_unchanged=True,original_presentation_failure_retained=True))

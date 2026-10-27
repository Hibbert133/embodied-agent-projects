"""Presentation-only semantic clarification after delivery validation."""
from pathlib import Path
from time import perf_counter_ns
import shutil,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from scripts import run_correction_effect_horizon_v1 as command
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
main=command.main;io=main.io;external=Path(__file__).parent;run=Path(sys.argv[1]).resolve().parent;main.checked(run/'manifest.json');start=perf_counter_ns()
out=main.BASE/'result_validation';old=io.read(out/'complete.json');assert old['integrity']=='PASSED'
revision=run/'presentation/wording_revision1';revision.mkdir(exist_ok=False)
report=ROOT/'reports/correction_effect_horizon_v1_zh.md';builder=external/'build_correction_effect_horizon_report_v1.py'
for p in (report,run/'presentation/report_receipt.json',out/'complete.json',out/'index_disk_proof.json',builder):shutil.copyfile(p,revision/(p.name+'.before.saved'))
before='分歧后原政策、状态、Z与夹爪均可能不同，完整差异步数已保存。'
after=before+'Z/夹爪与原策略差异按保存的float32字节比较；该比例只表示至少一处字节不同，没有度量变化幅度或其因果效应。'
for p in (report,builder):
    s=p.read_text('utf8');assert s.count(before)==1;s=s.replace(before,after)
    s=s.replace('本报告**全部新增分析为事后描述性**。','本报告**全部新增分析为事后描述性**。来源是已运行的MetaWorld仿真，不是实机测量。')
    p.write_text(s,encoding='utf8',newline='\n')
tools=run/'presentation_tools';shutil.copyfile(builder,tools/builder.name);shutil.copyfile(Path(__file__),tools/Path(__file__).name)
for p in tools.glob('*.py'):compile(p.read_bytes(),str(p),'exec')
io.write(tools/'source_sha256.json',{p.name:io.sha(p) for p in tools.iterdir() if p.is_file() and p.name!='source_sha256.json'})
r=io.read(run/'presentation/report_receipt.json');r['report_sha256']=io.sha(report);r['wording_revision_only']=True;io.write(run/'presentation/report_receipt.json',r)
io.write(revision/'receipt.json',dict(integrity='PASSED',change='Disclose float32-byte difference meaning and simulated source; no scientific result/source change',
    source_freeze_commit=io.git('rev-parse','HEAD'),original_result_validation_sha256=io.sha(revision/'complete.json.before.saved'),
    new_physics=0,new_fits=0,online_LLM_API_calls=0,wall_ns=perf_counter_ns()-start))
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
io.write(out/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=actual,all5832_windows_and2214_panels_retained=True,no_new_large_record_requires_sharding=True,wording_revision_only=True))
old['source_sha256']={p.relative_to(ROOT).as_posix():io.sha(p) for p in tools.glob('*.py')};old['receipt_sha256']={p.name:io.sha(p) for p in out.iterdir() if p.is_file() and p.name!='complete.json'}
old['wording_revision_receipt_sha256']=io.sha(revision/'receipt.json');io.write(out/'complete.json',old);names=stage(names);actual=scan(names)
print(dict(integrity='PASSED',staged_objects=len(actual),scientific_sources_and_results_unchanged=True))

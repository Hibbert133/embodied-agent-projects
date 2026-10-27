"""Freeze only the plain JSONL reader and retain the original failed pass."""
from pathlib import Path
from time import perf_counter_ns
import subprocess,sys
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from scripts import run_staggered_selective_scope_v1 as original
from scripts import run_staggered_selective_reader_v2 as command
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
main=original.main;io=main.io;BASE=main.BASE
def run():
    out=BASE/'reader_freeze_v2';out.mkdir(exist_ok=False);start=perf_counter_ns();path=next(BASE.glob('run_*/manifest.json'));main.checked(path)
    io.require(io.read(path.parent/'pipeline_control/construct_receipt.json')['integrity']=='PASSED','original construction complete')
    failure=io.read(path.parent/'pipeline_control/audit_failure.json');io.require('BadGzipFile' in failure['exception'],'retained original plain/gzip reader failure')
    io.require(not io.git('status','--porcelain','--untracked-files=no') and not io.git('diff','--cached','--name-only'),'original source unchanged before reader freeze')
    before=(ROOT/'src/analysis/staggered_selective_independent_v1.py').read_text('utf8')
    expected=before.replace('from math import gcd','from math import gcd\nimport json').replace("iterator=iter(io.rows(folder/'events.jsonl'))","iterator=iter(plain_rows(folder/'events.jsonl'))")
    expected=expected.replace("io.write(out/'audit.json',result)","io.write(path.parent/'reader_audit_v2/audit.json',result)")
    expected=expected.replace('def rational(units):',"def plain_rows(path):\n    with Path(path).open('r',encoding='utf8') as stream:\n        for line in stream:yield json.loads(line)\n\ndef rational(units):")
    io.require((ROOT/'src/analysis/staggered_selective_reader_v2.py').read_text('utf8')==expected,'reader-only text transformation, same independent mathematics')
    inputs={path.relative_to(ROOT).as_posix():io.sha(path)}
    for p in (path.parent/'construction').rglob('*'):
        if p.is_file():inputs[p.relative_to(ROOT).as_posix()]=io.sha(p)
    io.require(len(list((path.parent/'construction').glob('P*/events.jsonl')))==5,'all original event sources')
    names=set(original.SOURCES)|set(command.SOURCES)|{p.relative_to(ROOT).as_posix() for p in BASE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo')}
    def stage(selected,label):
        p=out/(label+'.nul');selected=set(selected)|{p.relative_to(ROOT).as_posix()};p.write_bytes(b'\0'.join(n.encode() for n in sorted(selected))+b'\0')
        io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+p.relative_to(ROOT).as_posix(),'--pathspec-file-nul');return selected
    def scan(selected):
        actual=index_bytes(selected)
        for n in actual:
            data=(ROOT/n).read_bytes()
            if b'\0' not in data:io.require(not any(pattern.search(data.decode('utf8',errors='replace')) for pattern in EXTRA.values()),'new staged supplemental secret '+n)
        io.require(not io.git('diff','--check') and not io.git('diff','--cached','--check'),'reader diff checks');return actual
    names=stage(names,'owned_initial')
    for name,args in (('compile',[sys.executable,'-m','compileall','-q','src','scripts','tests']),('dependencies',[sys.executable,'-m','pip','check'])):
        p=subprocess.run(args,cwd=ROOT,capture_output=True,text=True);io.write(out/(name+'.json'),dict(command=args,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr));io.require(p.returncode==0,'reader '+name)
    names=stage(names|{p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()},'owned_scan');actual=scan(names)
    io.write(out/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=actual,previously_tracked_files_unchanged=True,
        full_tracked_secret_scan_reused_sha256=io.sha(BASE/'freeze_validation/tracked_secret_scan.json'),new_actual_index_basic_and_extra_secrets_checked=True))
    io.write(out/'complete.json',dict(integrity='PASSED',source_sha256={n:io.sha(ROOT/n) for n in command.SOURCES},unchanged_input_sha256=inputs,
        original_primary_freeze=io.git('rev-parse','HEAD'),only_reading_and_output_location_changed=True,new_physics=0,new_model_fits=0,online_LLM_API_calls=0,
        unique_source_bound_reused_tests=2228,new_unit_tests=0,wall_ns=perf_counter_ns()-start))
    names=stage(names|{p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()},'owned_final');actual=scan(names)
    print(dict(integrity='PASSED',staged_objects=len(actual),primary_construction_not_repeated=True),flush=True)
if __name__=='__main__':run()

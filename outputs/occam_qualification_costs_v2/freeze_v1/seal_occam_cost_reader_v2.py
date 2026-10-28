"""Seal the legacy-accounting compatibility repair before whole-population costs."""
from pathlib import Path
from time import perf_counter_ns
import hashlib,json,shutil,subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
BASE=ROOT/'outputs/occam_qualification_costs_v2';sys.path.insert(0,str(BASE/'tools'))
import run_costs_v2 as run
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
OUT=BASE/'freeze_v1';SOURCE='33eb50dd25610763e3f24eaf59dd9d3f94384d52'


def git(*args):return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT)


def main():
    assert git('rev-parse','HEAD').decode().strip()==SOURCE and not git('status','--porcelain','--untracked-files=no').strip()
    assert not git('diff','--cached','--name-only').strip() and not run.OUT.exists()
    f=run.gate.read(run.FREEZE);assert f['new_unique_tests']==15
    for key in ('source_sha256','saved_metadata_test_inputs_sha256','reused_cost_source_sha256','reused_guard_source_sha256'):run.gate.verify(f[key])
    m=run.gate.read(run.RUN/'manifest.json');run.gate.verify(m['source_sha256']);run.gate.verify(m['input_sha256'])
    auxiliary=Path(__file__).resolve().parent
    shutil.copyfile(auxiliary/'occam_postqualification_descriptions_20261029/costs/complete.json',BASE/'development_v1/v1_entry_receipt.json')
    p=subprocess.run([str(ROOT/'.venv/Scripts/python.exe'),'-B','-m','pip','check'],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    (OUT/'pip_check_stdout.log').write_bytes(p.stdout);(OUT/'pip_check_stderr.log').write_bytes(p.stderr);assert p.returncode==0
    start=perf_counter_ns();p=subprocess.run([str(ROOT/'.venv/Scripts/python.exe'),'-B','scripts/check_tracked_secrets.py','--staged'],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    (OUT/'tracked_secret_scan_stdout.log').write_bytes(p.stdout);(OUT/'tracked_secret_scan_stderr.log').write_bytes(p.stderr)
    run.gate.write(OUT/'tracked_secret_scan.json',dict(returncode=p.returncode,wall_ns=perf_counter_ns()-start,
        actual_script_scans_all_preexisting_tracked_disk_files=True,new_staged_objects_scanned_separately_basic_and_extra=True))
    assert p.returncode==0
    shutil.copyfile(__file__,OUT/Path(__file__).name)
    run.gate.write(OUT/'delivery_validation.json',dict(integrity='PASSED_COST_ACCOUNTING_READER_V2_FREEZE',source_parent_commit=SOURCE,
        new_unique_tests=15,development_test_executions=15,formal_test_executions=15,old_unchanged_cost_tests_reused=25,
        freeze_sha256=run.gate.sha(run.FREEZE),scientific_source_sha256=m['source_sha256'],scientific_input_sha256=m['input_sha256'],
        old_failure_preserved=True,actual_cost_reanalysis_started=False,original_task_qualification=False,
        original_primary_statistics_sha256=run.gate.sha(run.RUN/'statistics_v1/statistics.json'),new_robot_interactions=0,
        new_real_model_queries=0,online_LLM_API_calls=0,publication_goal_complete=False))
    owned={p.relative_to(ROOT).as_posix() for p in BASE.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    owned|={'docs/protocols/occam_qualification_costs_reader_v2_zh.md','reports/occam_qualification_costs_reader_v2_freeze_zh.md',
            'outputs/occam_qualification_costs_v1/analysis_v1/failure.json'}
    def stage(label):
        p=OUT/(label+'.nul');owned.add(p.relative_to(ROOT).as_posix());p.write_bytes(b'\0'.join(n.encode() for n in sorted(owned))+b'\0')
        for flags in ((),('--renormalize',)):git('add',*flags,'--pathspec-from-file='+p.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    def check():
        objects=index_bytes(owned);assert set(objects)==owned
        for name in objects:
            data=(ROOT/name).read_bytes()
            if name.endswith('.py'):compile(data,name,'exec')
            if b'\0' not in data:
                text=data.decode('utf8');assert find_secret_rule(text) is None and not any(r.search(text) for r in EXTRA.values()),name
        assert not git('diff','--check').strip() and not git('diff','--cached','--check').strip();return objects
    stage('owned_checked');run.gate.write(OUT/'index_disk_proof.json',dict(integrity='PASSED',objects=check(),actual_index_basic_extra_scan=True))
    owned.add((OUT/'index_disk_proof.json').relative_to(ROOT).as_posix());stage('owned_final');check()
    print(dict(integrity='PASSED_COST_READER_V2_STAGED',files=len(owned),new_unique_tests=15),flush=True)


if __name__=='__main__':main()

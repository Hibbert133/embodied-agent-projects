"""Seal only the read-only cost addendum, leaving all science inputs intact."""
from pathlib import Path
from time import perf_counter_ns
import shutil,subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
BASE=ROOT/'outputs/occam_qualification_costs_v1';sys.path.insert(0,str(BASE/'tools'))
import run_costs_v1 as r
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
OUT=BASE/'freeze_v1';SOURCE='bc588f4b27213f083198d34b16da71eec3e18773'


def git(*args):return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT)


def main():
    assert git('rev-parse','HEAD').decode().strip()==SOURCE and not git('status','--porcelain','--untracked-files=no').strip()
    assert not git('diff','--cached','--name-only').strip() and not r.OUT.exists()
    f=r.gate.read(r.FREEZE);assert f['new_unique_tests']==25 and not f['current_QUAL_outcomes_read']
    for label in ('source_sha256','component_sha256','reused_guard_source_sha256'):r.gate.verify(f[label])
    m=r.gate.read(r.RUN/'manifest.json');assert len(m['source_sha256'])==1393
    r.gate.verify(m['source_sha256']);r.gate.verify(m['input_sha256'])
    proof=r.gate.read(BASE/'development_v1/live_analysis_refusal.json')
    assert proof['outcome_reads']==0 and proof['IO_counters_unchanged'] and not proof['analysis_directory_created']
    p=subprocess.run([str(ROOT/'.venv/Scripts/python.exe'),'-B','-m','pip','check'],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    (OUT/'pip_check_stdout.log').write_bytes(p.stdout);(OUT/'pip_check_stderr.log').write_bytes(p.stderr);assert p.returncode==0
    start=perf_counter_ns()
    p=subprocess.run([str(ROOT/'.venv/Scripts/python.exe'),'-B','scripts/check_tracked_secrets.py','--staged'],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    (OUT/'tracked_secret_scan_stdout.log').write_bytes(p.stdout);(OUT/'tracked_secret_scan_stderr.log').write_bytes(p.stderr)
    r.gate.write(OUT/'tracked_secret_scan.json',dict(returncode=p.returncode,wall_ns=perf_counter_ns()-start,
        actual_script_scans_all_preexisting_tracked_disk_files=True,new_staged_objects_scanned_separately_basic_and_extra=True))
    assert p.returncode==0
    shutil.copyfile(__file__,OUT/Path(__file__).name)
    r.gate.write(OUT/'delivery_validation.json',dict(integrity='PASSED_COMPLETE_QUAL_COST_ADDENDUM_FREEZE',source_parent_commit=SOURCE,
        freeze_sha256=r.gate.sha(r.FREEZE),new_unique_tests=25,development_test_executions=48,formal_test_executions=25,
        scientific_source_sha256=m['source_sha256'],scientific_input_sha256=m['input_sha256'],
        QUAL_outcomes_read=False,actual_cost_analysis_started=False,new_robot_interactions=0,
        new_real_model_queries=0,online_LLM_API_calls=0,original_primary_comparisons_unchanged=True,publication_goal_complete=False))
    owned={p.relative_to(ROOT).as_posix() for p in BASE.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    owned|={'docs/protocols/occam_qualification_costs_v1_zh.md','reports/occam_qualification_costs_freeze_v1_zh.md'}
    def stage(label):
        p=OUT/(label+'.nul');owned.add(p.relative_to(ROOT).as_posix());p.write_bytes(b'\0'.join(n.encode() for n in sorted(owned))+b'\0')
        for flags in ((),('--renormalize',)):git('add',*flags,'--pathspec-from-file='+p.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    def check():
        actual=index_bytes(owned);assert set(actual)==owned
        for name in actual:
            raw=(ROOT/name).read_bytes()
            if name.endswith('.py'):compile(raw,name,'exec')
            if b'\0' not in raw:
                text=raw.decode('utf8');assert find_secret_rule(text) is None and not any(x.search(text) for x in EXTRA.values()),name
        assert not git('diff','--check').strip() and not git('diff','--cached','--check').strip();return actual
    stage('owned_checked');r.gate.write(OUT/'index_disk_proof.json',dict(integrity='PASSED',objects=check(),actual_index_basic_extra_scan=True))
    owned.add((OUT/'index_disk_proof.json').relative_to(ROOT).as_posix());stage('owned_final');check()
    print(dict(integrity='PASSED_COST_ADDENDUM_STAGED',files=len(owned),new_unique_tests=25),flush=True)


if __name__=='__main__':main()

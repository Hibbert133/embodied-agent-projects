"""Commit owned complete-result tools before touching any QUAL outcome."""
from pathlib import Path
import shutil,subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
BASE=ROOT/'outputs/occam_reference_qualification_v1/qual_delivery_tools_v1';sys.path.insert(0,str(BASE))
import qual_result_delivery_v1 as d
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
OUT=BASE/'freeze_v1';SOURCE='22a9cc59ed403c520417c6ea53397fcb56884725'


def git(*args):return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT)


def main():
    assert git('rev-parse','HEAD').decode().strip()==SOURCE and not git('status','--porcelain','--untracked-files=no').strip()
    assert not git('diff','--cached','--name-only').strip() and not d.OUT.exists()
    f=d.b.c.read(d.FREEZE);assert f['unit_tests']==12 and not f['QUAL_outcomes_read'] and f['records_exported']==0
    for n,h in f['source_sha256'].items():assert d.b.c.sha(ROOT/n)==h,n
    m=d.b.c.read(d.RUN/'manifest.json')
    for n,h in {**m['source_sha256'],**m['input_sha256']}.items():assert d.b.c.sha(ROOT/n)==h,n
    assert len(m['source_sha256'])==1393
    proof=d.b.c.read(BASE/'development_v1/live_export_refusal.json');assert not proof['export_directory_created']
    p=subprocess.run([str(ROOT/'.venv/Scripts/python.exe'),'-B','-m','pip','check'],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    (OUT/'pip_check_stdout.log').write_bytes(p.stdout);(OUT/'pip_check_stderr.log').write_bytes(p.stderr);assert p.returncode==0
    shutil.copyfile(__file__,OUT/Path(__file__).name)
    d.b.c.write(OUT/'delivery_validation.json',dict(integrity='PASSED_FULL_RESULT_DELIVERY_TOOLS_FREEZE',source_parent_commit=SOURCE,
        freeze_sha256=d.b.c.sha(d.FREEZE),new_unique_tests=12,development_test_executions=12,formal_test_executions=12,
        prior_generic_bundle_checks_reused=13,prior_first_window_gate_checks_reused=43,
        source_binding=f['source_sha256'],scientific_source_sha256=m['source_sha256'],
        scientific_input_sha256=m['input_sha256'],QUAL_outcomes_read=False,real_QUAL_exports_or_restorations=0,
        original_scientific_comparisons_unchanged=True,counters=d.zeros(),publication_goal_complete=False))
    owned={p.relative_to(ROOT).as_posix() for p in BASE.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    owned|={'docs/protocols/occam_qualification_result_delivery_v1_zh.md','docs/research/correction_scope_contribution_review_v8_zh.md',
            'reports/occam_qualification_result_delivery_tools_v1_zh.md','outputs/research_context/primary_sources_v8_20261029/source_index.json'}
    def stage(label):
        p=OUT/(label+'.nul');owned.add(p.relative_to(ROOT).as_posix());p.write_bytes(b'\0'.join(n.encode() for n in sorted(owned))+b'\0')
        for flags in ((),('--renormalize',)):git('add',*flags,'--pathspec-from-file='+p.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    def check():
        actual=index_bytes(owned);assert set(actual)==owned
        for n in actual:
            raw=(ROOT/n).read_bytes()
            if n.endswith('.py'):compile(raw,n,'exec')
            if b'\0' not in raw:
                text=raw.decode('utf8');assert find_secret_rule(text) is None and not any(x.search(text) for x in EXTRA.values()),n
        assert not git('diff','--check').strip() and not git('diff','--cached','--check').strip();return actual
    stage('owned_checked');d.b.c.write(OUT/'index_disk_proof.json',dict(integrity='PASSED',objects=check(),actual_index_basic_extra_scan=True))
    owned.add((OUT/'index_disk_proof.json').relative_to(ROOT).as_posix());stage('owned_final');check()
    print(dict(integrity='PASSED_FULL_RESULT_TOOLS_STAGED',files=len(owned),new_unique_tests=12),flush=True)


if __name__=='__main__':main()

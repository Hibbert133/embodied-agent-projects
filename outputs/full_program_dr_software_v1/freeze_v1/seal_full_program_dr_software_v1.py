"""Seal standard DR arithmetic and preserve the current independent experiment."""
from pathlib import Path
import shutil,subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
BASE=ROOT/'outputs/full_program_dr_software_v1';sys.path.insert(0,str(BASE/'tools'))
import freeze_sequential_dr_v1 as f
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
OUT=BASE/'freeze_v1';SOURCE='737471225e796cc12018c32b97f87296abe486fd'


def git(*args):return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT)


def main():
    assert git('rev-parse','HEAD').decode().strip()==SOURCE and not git('status','--porcelain','--untracked-files=no').strip()
    assert not git('diff','--cached','--name-only').strip()
    r=f.guard.read(OUT/'complete.json');assert r['new_unique_tests']==34 and not r['real_data_read_or_evaluated']
    for label in ('source_sha256','reused_guard_source_sha256'):f.guard.verify(r[label])
    q=f.guard.read(f.guard.RUN/'manifest.json');f.guard.verify(q['source_sha256']);f.guard.verify(q['input_sha256'])
    args=[str(ROOT/'.venv/Scripts/python.exe'),'-B','-m','pip','check'];p=subprocess.run(args,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    (OUT/'pip_check_stdout.log').write_bytes(p.stdout);(OUT/'pip_check_stderr.log').write_bytes(p.stderr);assert p.returncode==0
    shutil.copyfile(__file__,OUT/Path(__file__).name)
    f.guard.write(OUT/'delivery_validation.json',dict(integrity='PASSED_STANDARD_DR_COMPONENT_FREEZE',source_parent_commit=SOURCE,
        freeze_sha256=f.guard.sha(OUT/'complete.json'),new_unique_tests=34,development_test_executions=34,formal_test_executions=34,
        frozen_scientific_source_sha256=q['source_sha256'],frozen_scientific_input_sha256=q['input_sha256'],
        scalar_math_only=True,real_data_evaluation_or_Q_fitting=False,old_closed_DR_reparameterization_not_reopened=True,
        original_scientific_comparisons_unchanged=True,new_robot_interactions=0,new_real_model_queries=0,online_LLM_API_calls=0,publication_goal_complete=False))
    owned={p.relative_to(ROOT).as_posix() for p in BASE.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    owned|={'docs/protocols/full_program_dr_software_v1_zh.md','reports/full_program_dr_software_v1_zh.md'}
    def stage(label):
        p=OUT/(label+'.nul');owned.add(p.relative_to(ROOT).as_posix());p.write_bytes(b'\0'.join(n.encode() for n in sorted(owned))+b'\0')
        for flags in ((),('--renormalize',)):git('add',*flags,'--pathspec-from-file='+p.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    def check():
        actual=index_bytes(owned);assert set(actual)==owned
        for name in actual:
            data=(ROOT/name).read_bytes()
            if name.endswith('.py'):compile(data,name,'exec')
            if b'\0' not in data:
                text=data.decode('utf8');assert find_secret_rule(text) is None and not any(x.search(text) for x in EXTRA.values()),name
        assert not git('diff','--check').strip() and not git('diff','--cached','--check').strip();return actual
    stage('owned_checked');f.guard.write(OUT/'index_disk_proof.json',dict(integrity='PASSED',objects=check(),actual_index_basic_extra_scan=True))
    owned.add((OUT/'index_disk_proof.json').relative_to(ROOT).as_posix());stage('owned_final');check()
    print(dict(integrity='PASSED_STANDARD_DR_COMPONENT_STAGED',files=len(owned),new_unique_tests=34),flush=True)


if __name__=='__main__':main()

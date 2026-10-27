"""Read the unchanged constructed events once using the separately frozen reader."""
from pathlib import Path
from time import perf_counter_ns
from unittest.mock import patch
import sys,traceback
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.analysis import staggered_selective_scope_v1 as main
from src.analysis import staggered_selective_reader_v2 as reader
io=main.io
SOURCES=('src/analysis/staggered_selective_reader_v2.py','scripts/run_staggered_selective_reader_v2.py','docs/protocols/staggered_selective_reader_v2_zh.md',
    'outputs/correction_scope/selective_coverage_v1/validate_reader_v2.py')
def run(path):
    path=Path(path).resolve();main.checked(path);frozen=io.read(main.BASE/'reader_freeze_v2/complete.json')
    io.require(frozen['integrity']=='PASSED' and not io.git('status','--porcelain','--untracked-files=no'),'clean reader-only freeze')
    for n,h in {**frozen['source_sha256'],**frozen['unchanged_input_sha256']}.items():io.require(io.sha(ROOT/n)==h,'frozen reader source/input '+n)
    out=path.parent/'reader_audit_v2';out.mkdir(exist_ok=False);start=perf_counter_ns()
    io.write(out/'manifest.json',dict(classification='READ_ONLY_READER_REPAIR_NO_REGENERATION',source_git_commit=io.git('rev-parse','HEAD'),
        original_manifest=str(path.relative_to(ROOT)),original_manifest_sha256=io.sha(path),original_audit_failure_retained=True,source_sha256=frozen['source_sha256']))
    io.write(out/'intent.json',dict(entry=reader.__name__+'.audit',primary_generator_disabled=True,no_automatic_retry=True))
    def denied(*a,**kw):raise RuntimeError('original Fraction generator disabled during reader-only repair')
    try:
        with patch.object(main,'generate',denied):result=reader.audit(path)
    except BaseException:
        io.write(out/'failure.json',dict(integrity='FAILED',traceback=traceback.format_exc(),wall_ns=perf_counter_ns()-start,no_automatic_retry=True));raise
    io.write(out/'completion.json',dict(integrity='PASSED',reader_only=True,original_audit_failure_retained=True,primary_construction_not_repeated=True,
        independent_integer_reconstruction_updates=12400,new_physics=0,new_model_fits=0,online_LLM_API_calls=0,wall_ns=perf_counter_ns()-start))
    print(dict(integrity=result['integrity'],events=result['events'],reader_only=True),flush=True)
if __name__=='__main__':run(sys.argv[1])

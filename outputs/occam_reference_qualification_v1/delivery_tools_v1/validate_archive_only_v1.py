"""Freeze three portable-restoration engineering checks before the real restore."""
from pathlib import Path
import io,json,sys,unittest
from contextlib import redirect_stdout,redirect_stderr
from time import perf_counter_ns
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from outputs.occam_reference_qualification_v1.delivery_tools_v1 import qualification_bundle_v1 as b
TOOLS=Path(__file__).parent;OUT=TOOLS/'archive_only_validation_v1'


def main():
    OUT.mkdir(exist_ok=False);started=perf_counter_ns()
    paths=[TOOLS/n for n in ('recover_native_archive_only_v1.py','test_archive_only_restore_v1.py','validate_archive_only_v1.py')]
    hashes={p.relative_to(ROOT).as_posix():b.c.sha(p) for p in paths};console=io.StringIO()
    with redirect_stdout(console),redirect_stderr(console):
        suite=unittest.defaultTestLoader.loadTestsFromName('outputs.occam_reference_qualification_v1.delivery_tools_v1.test_archive_only_restore_v1')
        result=unittest.TextTestRunner(stream=console,verbosity=2).run(suite)
    (OUT/'unit_tests.log').write_text(console.getvalue(),encoding='utf8',newline='\n')
    b.require(result.wasSuccessful() and result.testsRun==3,'all portable restoration checks')
    for p in paths:compile(p.read_bytes(),str(p),'exec')
    b.c.write(OUT/'complete.json',dict(integrity='PASSED_ARCHIVE_ONLY_ENGINEERING_VALIDATION',source_sha256=hashes,
        unit_tests=3,compile_files=3,unit_log_sha256=b.c.sha(OUT/'unit_tests.log'),original_raw_files_used=False,
        scientific_tests_added=0,new_physics=0,new_fits=0,online_LLM_API_calls=0,wall_ns=perf_counter_ns()-started))
    print(json.dumps(dict(integrity='PASSED_ARCHIVE_ONLY_ENGINEERING_VALIDATION',tests=3)),flush=True)


if __name__=='__main__':main()

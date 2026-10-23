"""Rebind25 array checks after an EOF-only delivery correction, keeping receipts."""
from pathlib import Path
from time import perf_counter_ns
import ast,sys,unittest
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
from src.analysis.release_learning_guard_v1 import read_only
OUT=Path(__file__).parent


def main():
    old=io.read(OUT/'complete.json');new={n:io.sha(ROOT/n) for n in old['source_sha256']}
    changed=[n for n in new if new[n]!=old['source_sha256'][n]]
    name='src/analysis/release_learning_record_audit_v1.py'
    io.require(changed==[name],'only EOF repair since passed checks')
    before=(OUT/'record_audit_before_eof_repair.py.saved').read_bytes();after=(ROOT/name).read_bytes()
    io.require(after==before.rstrip(b'\r\n')+b'\n' and ast.dump(ast.parse(before))==ast.dump(ast.parse(after)),'identical AST and exact EOF-only repair')
    compile(after,name,'exec');guard={};started=perf_counter_ns()
    with (OUT/'unit_after_eof.log').open('x',encoding='utf-8') as log:
        with read_only(guard,max_solve=5,max_lstsq=1):
            result=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromName('tests.test_release_learning_v1'))
    io.require(result.wasSuccessful() and result.testsRun==25,'all25 checks after EOF repair')
    io.write(OUT/'post_eof_validation.json',dict(integrity='PASSED',source_sha256=new,prior_complete_sha256=io.sha(OUT/'complete.json'),
        changed_file=name,before_sha256=old['source_sha256'][name],after_sha256=new[name],identical_ast=True,EOF_only=True,
        new_unique_test_count=25,repeat_execution_not_added_to_unique_count=True,tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),
        guard=guard,scientific_model_fits=0,new_physical_activity=0,online_LLM_API_calls=0,wall_ns=perf_counter_ns()-started))
    print(dict(integrity='PASSED',tests=25,identical_AST=True,physical_operations=0),flush=True)


if __name__=='__main__':main()

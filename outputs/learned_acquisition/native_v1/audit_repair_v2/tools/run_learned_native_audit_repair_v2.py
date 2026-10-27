"""One supplemental audit attempt, recording failures without physical retries."""
from pathlib import Path
from time import perf_counter_ns
import gzip,hashlib,os,sys,traceback
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1';os.environ['MKL_NUM_THREADS']='1'
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import learned_acquisition_native_io_v1 as a
from src.analysis import learned_acquisition_native_audit_v2 as repair
io=a.io;base=a.BASE/'audit_repair_v2';frozen=io.read(base/'complete.json')
assert frozen['integrity']=='PASSED' and not io.git('status','--porcelain','--untracked-files=no')
for name,h in frozen['source_sha256'].items():assert io.sha(ROOT/name)==h
path=a.BASE/'run_20261027T042530Z_3c437c6d3f5d/manifest.json';out=path.parent/'audit_repair_control_v2';out.mkdir(exist_ok=False);start=perf_counter_ns()
io.write(out/'intent.json',dict(source_git_commit=io.git('rev-parse','HEAD'),source_freeze_sha256=io.sha(base/'complete.json'),manifest_sha256=io.sha(path),pid=os.getpid(),executable=sys.executable,no_automatic_retry=True))
try:
    result=repair.audit(path)
    def raw_hash(p):
        h=hashlib.sha256()
        with gzip.open(p,'rb') as stream:
            for block in iter(lambda:stream.read(1024**2),b''):h.update(block)
        return h.hexdigest()
    first=raw_hash(path.parent/'native/decision_queries.jsonl.gz');second=raw_hash(path.parent/'native_audit_repair_v2/decision_queries.jsonl.gz');assert first==second
    io.write(out/'receipt.json',dict(integrity='PASSED',result=result,original_and_repair_query_decoded_sha256=first,
        all_original_live_query_and_decision_values_unchanged=True,original_frozen_qualification='FAILED_RETAINED',wall_ns=perf_counter_ns()-start))
    print(dict(integrity='PASSED',gate=io.read(path.parent/'native_audit_repair_v2/native_gate.json'),counters=result['counters']),flush=True)
except BaseException:
    io.write(out/'failure.json',dict(integrity='FAILED',exception=traceback.format_exc(),wall_ns=perf_counter_ns()-start,no_automatic_retry=True));raise

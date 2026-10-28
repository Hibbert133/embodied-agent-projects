"""One fixed pinned training command, binary logs, no retries or model changes."""
from pathlib import Path
from time import perf_counter_ns
import os,subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import occam_native_case_io_v1 as c
RUN=c.OUTPUT/'occam_reference_train_v3_20261028T071949Z_c92356173d9e'
PYTHON=Path(r'C:/Users/Administrator/Documents/ChatGPT/robotic agent/.venv-history-training-cpu22/Scripts/python.exe')
m=c.check_manifest(RUN/'manifest.json');spec=c.read(RUN/'learning_spec.json')
for phase,n in (('native',36),('train',648)):
    assert c.read(RUN/phase/'audit.json')['integrity']=='PASSED'
    p=c.read(RUN/phase/'process_audit.json');assert p['integrity']=='PASSED_ISOLATED_PROCESS_AND_BYTE_CONTINUITY_ONLY' and p['executions']==n
assert spec['allocated_episodes']==648 and c.sha(spec['public_trajectories'])==spec['public_sha256']
assert not (RUN/'learning').exists()
out=RUN/'learning_process_v1';out.mkdir(exist_ok=False);started=perf_counter_ns()
args=[str(PYTHON),str(ROOT/'scripts/train_occam_reference_v3.py'),'--spec',str(RUN/'learning_spec.json'),'--output',str(RUN/'learning')]
c.write(out/'intent.json',dict(command=args,source_manifest_id=m['manifest_id'],public_sha256=spec['public_sha256'],spec_sha256=c.sha(RUN/'learning_spec.json'),
    parent_pid=os.getpid(),started_ns=started,no_retries=True,frozen_training_wall_seconds=spec['learning']['training_wall_seconds_max'],
    frozen_Adam_updates_max=spec['learning']['Adam_updates_max'],online_LLM_API_calls=0))
with (out/'stdout.log').open('xb') as stdout,(out/'stderr.log').open('xb') as stderr:
    child=subprocess.Popen(args,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    c.write(out/'start.json',dict(pid=child.pid,parent_pid=os.getpid(),started_ns=perf_counter_ns(),direct_configured_training_runtime=True))
    code=child.wait()
c.write(out/'complete.json',dict(returncode=code,pid=child.pid,parent_pid=os.getpid(),stdout_sha256=c.sha(out/'stdout.log'),stderr_sha256=c.sha(out/'stderr.log'),
    wall_ns=perf_counter_ns()-started,learner_complete_receipt_exists=(RUN/'learning/complete.json').exists(),new_native_environment_processes=0,online_LLM_API_calls=0))
print(dict(returncode=code,process_receipt=str(out/'complete.json')),flush=True)
raise SystemExit(code)

from pathlib import Path
from time import perf_counter_ns
import subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import correction_program_support_v1 as m
io=m.io;start=perf_counter_ns();path=m.prepare();out=path.parent/'pipeline_control';out.mkdir(exist_ok=False)
print(str(path),flush=True)
for phase in ('analyze','audit'):
    cmd=[sys.executable,'scripts/run_correction_program_support_v1.py',phase,'--manifest',str(path)]
    io.write(out/(phase+'_intent.json'),dict(phase=phase,command=cmd,source_git_commit=io.git('rev-parse','HEAD')))
    t=perf_counter_ns();p=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,encoding='utf8',errors='replace')
    io.write(out/(phase+'_receipt.json'),dict(phase=phase,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr,wall_ns=perf_counter_ns()-t))
    print(dict(phase=phase,returncode=p.returncode,stdout=p.stdout.strip()),flush=True)
    if p.returncode:
        io.write(out/'failed.json',dict(status='FAILED',phase=phase,no_automatic_retry=True,wall_ns=perf_counter_ns()-start))
        raise SystemExit(p.returncode)
io.write(out/'completion.json',dict(status='COMPLETED',phases=['analyze','audit'],wall_ns=perf_counter_ns()-start,
    new_physics=0,new_model_fits=0,new_policy_queries=0,online_LLM_API_calls=0))

"""Exactly one frozen read-only reference run; retain each process receipt."""
from pathlib import Path
from time import perf_counter_ns
import subprocess,sys
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io

def run(manifest):
    manifest=Path(manifest).resolve();out=manifest.parent/'pipeline_control';out.mkdir(exist_ok=False);start=perf_counter_ns()
    phases=('train','audit-models','replay','audit-replay');complete=[]
    for phase in phases:
        command=[sys.executable,'scripts/run_correction_scope_risk_reference_v1.py',phase,str(manifest)]
        io.write(out/(phase+'_intent.json'),dict(command=command,saved_ns=perf_counter_ns(),no_automatic_retry=True))
        tick=perf_counter_ns();p=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,encoding='utf8',errors='replace')
        io.write(out/(phase+'_receipt.json'),dict(command=command,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr,wall_ns=perf_counter_ns()-tick))
        if p.returncode:
            io.write(out/'failed.json',dict(status='FAILED',phase=phase,complete=complete,wall_ns=perf_counter_ns()-start,no_automatic_retry=True))
            raise RuntimeError('Frozen reference phase failed; records retained: '+phase)
        complete.append(phase);print(dict(phase=phase,status='COMPLETED'),flush=True)
    io.write(out/'completion.json',dict(status='COMPLETED',phases=complete,wall_ns=perf_counter_ns()-start,new_physics=0,new_policy_queries=0,online_LLM_API_calls=0))

if __name__=='__main__':run(sys.argv[1])

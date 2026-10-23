"""Read-only native record audit; worlds, physical steps, fitting and network denied."""
from pathlib import Path
import argparse,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.analyze_acquisition_support_v1 import guarded
from src.analysis.memory_acquisition_audit_v1 import audit
from src.analysis.response_qualification_io_v1 import write
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);v=p.parse_args()
    result,guard=guarded(lambda:audit(v.manifest));write(v.manifest.parent/'native/audit_guard.json',guard)
    print({k:result[k] for k in ('integrity','native_software_contract','executions','counts','coverage')},flush=True)

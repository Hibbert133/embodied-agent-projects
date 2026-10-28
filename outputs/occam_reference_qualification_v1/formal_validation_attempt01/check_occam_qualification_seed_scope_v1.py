"""Read-only preregistration collision check; does not create an allocation."""
from pathlib import Path
from time import perf_counter_ns
import gzip,json,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis.episode_seed_inventory_v2 import discover,scan
from src.analysis.episode_seed_inventory_audit_v2 import audit
from src.analysis.response_qualification_io_v1 import write
out=ROOT/'outputs/occam_reference_qualification_v1/seed_precheck_v1';out.mkdir(parents=True,exist_ok=False)
start=perf_counter_ns();inventory=scan(ROOT,175000,177999,discover(ROOT));check=audit(ROOT,inventory)
with gzip.open(out/'inventory.json.gz','xt',encoding='utf8') as f:json.dump(inventory,f,ensure_ascii=False,separators=(',',':'))
write(out/'audit.json',check);write(out/'complete.json',dict(integrity='PASSED' if inventory['status']=='NO_REGISTERED_COLLISION' else 'FAILED',
    status=inventory['status'],sources=len(inventory['sources']),wall_ns=perf_counter_ns()-start,allocation_created=False,new_physics=0,online_LLM_API_calls=0))
print(dict(status=inventory['status'],sources=len(inventory['sources']),blockers=len(inventory['blockers'])),flush=True)

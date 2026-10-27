"""Read-only, source-bound query; does not reserve seeds or authorize sampling."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys,time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.analysis.episode_seed_inventory_v2 import scan,verify_unchanged
from src.analysis.episode_seed_inventory_audit_v2 import audit
from src.analysis.release_learning_guard_v1 import read_only

def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf8',newline='\n')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--lower',type=int,required=True);p.add_argument('--upper',type=int,required=True)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args();out=args.output.resolve();out.relative_to(ROOT)
    out.mkdir(parents=True,exist_ok=False);start=time.perf_counter_ns();guard={}
    files=['src/analysis/episode_seed_inventory_v2.py','src/analysis/episode_seed_inventory_audit_v2.py','scripts/check_episode_seed_scope_v2.py']
    source={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in files}
    commit=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True,check=True).stdout.strip()
    try:
        with read_only(guard):
            result=scan(ROOT,args.lower,args.upper);write(out/'inventory.json',result)
            independent=audit(ROOT,result);write(out/'audit.json',independent);verify_unchanged(ROOT,result)
        for name,h in source.items():
            if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=h:raise ValueError('source changed during query '+name)
        write(out/'receipt.json',dict(integrity='PASSED',source_commit=commit,source_sha256=source,guard=guard,wall_ns=time.perf_counter_ns()-start,
            artifact_sha256={n:hashlib.sha256((out/n).read_bytes()).hexdigest() for n in ('inventory.json','audit.json')},
            query_status=result['status'],seed_reservation_created=False,sampling_authorized=False,new_physics=0,new_model_fits=0,online_LLM_API_calls=0))
        print(json.dumps(dict(status=result['status'],sources=len(result['sources']),records=len(result['records']),audit=independent['integrity'],sampling_authorized=False)))
        return 0 if result['status']=='NO_REGISTERED_COLLISION' else 2
    except Exception as exc:
        write(out/'failure.json',dict(integrity='FAILED',error_type=type(exc).__name__,error=str(exc),source_commit=commit,source_sha256=source,
            guard=guard,wall_ns=time.perf_counter_ns()-start,seed_reservation_created=False,sampling_authorized=False));raise

if __name__=='__main__':raise SystemExit(main())

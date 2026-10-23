"""Prepare a frozen manifest, then execute one native software qualification."""
from pathlib import Path
import argparse,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis import memory_acquisition_io_v1 as a
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=('prepare','collect'));p.add_argument('--manifest',type=Path);v=p.parse_args()
    if v.phase=='prepare':print(a.prepare(),flush=True)
    else:
        if v.manifest is None:p.error('manifest required')
        from src.analysis.memory_acquisition_collect_v1 import collect
        print(collect(v.manifest),flush=True)

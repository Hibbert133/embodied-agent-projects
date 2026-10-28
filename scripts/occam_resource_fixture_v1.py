"""Fixed, no-physics software worker; no arbitrary script or robot arguments."""
from pathlib import Path
import argparse,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis.occam_resource_process_v1 import fixture

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec',required=True)
    args=parser.parse_args()
    raise SystemExit(fixture(args.spec))

"""One fixed native-case worker; arbitrary scripts or restore states forbidden."""
from pathlib import Path
import argparse,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis.occam_qualification_case_process_v1 import worker

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--request',required=True)
    args=parser.parse_args();raise SystemExit(worker(args.request))

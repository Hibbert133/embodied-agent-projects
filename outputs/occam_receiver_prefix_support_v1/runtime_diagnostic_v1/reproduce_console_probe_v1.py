"""Reproduce either recorded synthetic timing command; never run a trajectory.

The original two commands were executed in the tool console. receipt.json is a
post-execution record of those runs; this convenience script does not overwrite it.
"""
from pathlib import Path
from time import perf_counter
import argparse,cProfile,json,pstats,sys
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'outputs/occam_receiver_prefix_support_v1/tools'))
import run_prefix_support_v1 as r
from test_prefix_support_v1 import fixture
from src.probe.occam_qualification_provider_v1 import TrainedProvider


def main(guarded):
    start=perf_counter();bank=r.read(r.TRAIN/'learning/META_FINAL_raw.json');print('BANK_READ_S',perf_counter()-start,bank['dimensions'],flush=True)
    start=perf_counter();provider=TrainedProvider(bank,adapt=True);print('INIT_S',perf_counter()-start,flush=True)
    query=fixture((0,))['windows'][0]['query'];prof=cProfile.Profile();guard=r.Guard([])
    if guarded:sys.addaudithook(guard);guard.enabled=True
    start=perf_counter()
    try:prof.enable();provider.declare(query);prof.disable();print('DECLARE_S',perf_counter()-start,flush=True)
    finally:guard.enabled=False
    pstats.Stats(prof).sort_stats('cumtime').print_stats(15)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--guarded',action='store_true');args=parser.parse_args();main(args.guarded)

from pathlib import Path
import argparse,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    p=argparse.ArgumentParser();p.add_argument('--spec',required=True);p.add_argument('--output',required=True);v=p.parse_args()
    from src.analysis.occam_reference_learner_v2 import train
    r=train(v.spec,v.output);print({k:r[k] for k in ('integrity','counters','Torch_solve_attempts','allocated_episodes','nonempty_episodes','wall_ns')},flush=True)


if __name__=='__main__':main()

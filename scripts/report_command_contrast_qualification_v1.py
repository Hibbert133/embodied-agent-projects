"""Whole-group contrast statistics and Chinese report, after independent audit."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis.command_contrast_statistics_v1 import evaluate,report


def main():
    p=argparse.ArgumentParser(); p.add_argument('--manifest',type=Path,required=True); a=p.parse_args()
    evaluate(a.manifest); print(report(a.manifest))


if __name__=='__main__': main()

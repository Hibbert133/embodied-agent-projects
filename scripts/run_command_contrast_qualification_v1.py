"""Freeze-gated command-contrast preparation and single-shot native phases."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis import command_contrast_io_v1 as io


def main():
    p=argparse.ArgumentParser(); p.add_argument('phase',choices=('prepare','software-native','qual')); p.add_argument('--manifest',type=Path)
    a=p.parse_args()
    if a.phase=='prepare':
        if a.manifest is not None: p.error('prepare does not accept an existing manifest')
        manifest,receipt=io.prepare(); print(json.dumps({'manifest':str(manifest) if manifest else None,'receipt':str(receipt)}))
        return 0 if manifest else 2
    if a.manifest is None: p.error('--manifest required')
    from src.analysis.command_contrast_collect_v1 import collect
    print(collect(a.manifest,'SOFTWARE_NATIVE' if a.phase=='software-native' else 'QUAL')); return 0


if __name__=='__main__': raise SystemExit(main())

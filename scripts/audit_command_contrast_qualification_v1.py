"""Read-only native/scientific record audit; never creates or steps a world."""
import argparse
import json
from pathlib import Path
import sys
from time import perf_counter_ns
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis.command_contrast_audit_v1 import audit
from src.analysis import command_contrast_io_v1 as allocation


def main():
    p=argparse.ArgumentParser(); p.add_argument('phase',choices=('software-native','qual')); p.add_argument('--manifest',type=Path,required=True)
    a=p.parse_args(); cohort='SOFTWARE_NATIVE' if a.phase=='software-native' else 'QUAL'
    try: print(json.dumps(audit(a.manifest,cohort),ensure_ascii=False))
    except BaseException as error:
        target=a.manifest.resolve().parent/('software_native' if cohort=='SOFTWARE_NATIVE' else 'collection')
        if target.is_dir(): allocation.io.write(target/f'audit_failure_{perf_counter_ns()}.json',{'status':'FAILED','type':type(error).__name__,'message':str(error),'new_environment_steps':0,'new_api_calls':0})
        raise


if __name__=='__main__': main()

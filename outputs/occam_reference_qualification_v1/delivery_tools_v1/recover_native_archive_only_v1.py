"""Restore committed Native records using only the index, shards and destination.

The original-raw comparison remains in recover_native_actual_git_v1. Here each
file is verified against the committed SHA index, without requiring originals.
"""
from pathlib import Path
from time import perf_counter_ns
import argparse,hashlib,json,re,sys
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from outputs.occam_reference_qualification_v1.delivery_tools_v1 import qualification_bundle_v1 as b
from outputs.occam_reference_qualification_v1.delivery_tools_v1.recover_native_actual_git_v1 import git
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
INDEX='outputs/occam_reference_qualification_v1/native_delivery_v1/bundle_index.json'


def restore_zip(target,index,destination,scan):
    destination=Path(destination).resolve()
    # Both roots deliberately point at the new destination. The mandatory
    # independent size/SHA comparisons against the index still apply to every
    # canonical/alias file; the second source comparison is now the same file.
    result=b.recover(destination,target,index,destination,scan=scan)
    return dict(**result,original_raw_files_required=False,original_raw_byte_comparison=False,
                size_and_SHA_against_committed_index=True)


def main(source,destination,receipt):
    start=perf_counter_ns();b.require(re.fullmatch('[0-9a-f]{40}',source) is not None,'complete containing commit SHA')
    raw=git('show',source+':'+INDEX);index=json.loads(raw)
    b.require(index['schema']=='OCCAM_QUALIFICATION_ZIP_ALIASES_V1' and index['phase']=='NATIVE'
        and index['executions']==174 and len(index['files'])==2288 and len(index['aliases'])==348,'exact Native dataset')
    destination=Path(destination).resolve();target=destination.with_suffix('.zip');oids={}
    original_tree=(ROOT/'outputs/occam_reference_qualification_v1/qualification_v1').resolve()
    counts=dict(original_scientific_record_read_attempts=0)
    active=[True]
    def guard(event,args):
        if active[0] and event=='open' and isinstance(args[0],(str,bytes)):
            p=Path(args[0].decode() if isinstance(args[0],bytes) else args[0]).resolve()
            if p==original_tree or original_tree in p.parents:
                counts['original_scientific_record_read_attempts']+=1
                raise RuntimeError('Original Native/QUAL trees are forbidden in archive-only restoration')
    sys.addaudithook(guard)
    try:
        with target.open('xb') as stream:
            for part in index['parts']:
                n=part['path'];b.safe_name(n)
                b.require(n.startswith('outputs/occam_reference_qualification_v1/native_delivery_v1/bundle_parts/') and n.endswith('.bin'),'owned shard')
                data=git('show',source+':'+n)
                b.require(len(data)==part['bytes']<=4*1024**2 and hashlib.sha256(data).hexdigest()==part['sha256'],'committed shard bytes')
                stream.write(data);oids[n]=git('rev-parse',source+':'+n).decode().strip()
        def scan(data,name):
            text=data.decode('utf8');b.require(find_secret_rule(text) is None and not any(p.search(text) for p in EXTRA.values()),'decoded credential pattern '+name)
        result=restore_zip(target,index,destination,scan)
        b.require(not any(counts.values()),'zero reads from original scientific trees')
    finally:active[0]=False
    proof=dict(integrity='PASSED_ACTUAL_GIT_ARCHIVE_ONLY_NATIVE_RESTORATION',containing_commit=source,
        index_sha256=hashlib.sha256(raw).hexdigest(),part_git_oids=oids,result=result,guard=counts,
        restored_directory=str(destination),assembled_zip=str(target),full_fresh_clone_not_performed=True,
        no_new_physics_or_fits=True,online_LLM_API_calls=0,wall_ns=perf_counter_ns()-start)
    b.c.write(receipt,proof)
    print(dict(integrity=proof['integrity'],files=result['files'],original_raw_files_required=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',required=True);parser.add_argument('--restore',required=True);parser.add_argument('--receipt',required=True)
    args=parser.parse_args();main(args.source,args.restore,args.receipt)

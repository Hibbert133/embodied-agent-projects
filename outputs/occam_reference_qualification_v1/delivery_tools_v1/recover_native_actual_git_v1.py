"""Reassemble committed Native shards and restore every original byte."""
from pathlib import Path
from time import perf_counter_ns
import argparse,hashlib,json,re,subprocess,sys
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from outputs.occam_reference_qualification_v1.delivery_tools_v1 import qualification_bundle_v1 as b
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
OUT=ROOT/'outputs/occam_reference_qualification_v1/native_delivery_v1'


def git(*args):return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT)


def main(source,restore):
    start=perf_counter_ns();b.require(re.fullmatch('[0-9a-f]{40}',source) is not None,'literal complete committed data SHA')
    b.require(git('rev-parse',source).decode().strip()==source,'actual source commit')
    name=(OUT/'bundle_index.json').relative_to(ROOT).as_posix();raw=git('show',source+':'+name)
    b.require(raw==(ROOT/name).read_bytes(),'actual committed index equals delivered index');index=json.loads(raw)
    b.require(index['phase']=='NATIVE' and index['executions']==174 and index['schema']=='OCCAM_QUALIFICATION_ZIP_ALIASES_V1','complete Native dataset only')
    b.require(len(index['files'])==2288 and len(index['aliases'])==348,'whole original Native population')
    restore=Path(restore).resolve();target=restore.with_suffix('.zip');oids={}
    with target.open('xb') as stream:
        for part in index['parts']:
            n=part['path'];b.safe_name(n)
            b.require(n.startswith('outputs/occam_reference_qualification_v1/native_delivery_v1/bundle_parts/') and n.endswith('.bin'),'owned bounded data shard')
            data=git('show',source+':'+n)
            b.require(len(data)==part['bytes']<=4*1024**2 and hashlib.sha256(data).hexdigest()==part['sha256'],'actual committed shard bytes')
            oids[n]=git('rev-parse',source+':'+n).decode().strip();stream.write(data)
    def scan(data,name):
        text=data.decode('utf8');b.require(find_secret_rule(text) is None and not any(p.search(text) for p in EXTRA.values()),'restored credential pattern '+name)
    result=b.recover(ROOT,target,index,restore,scan=scan)
    proof=dict(integrity='PASSED_ACTUAL_COMMIT_QUALIFICATION_NATIVE_PARTS_AND_FILES_RESTORATION',source_commit=source,
        science_source_commit=index['source_git_commit'],manifest_id=index['manifest_id'],phase='NATIVE',
        index_sha256=hashlib.sha256(raw).hexdigest(),part_count=len(index['parts']),part_git_oids=oids,
        result=result,restore_directory=str(restore),assembled_actual_git_zip=str(target),
        actual_blob_bytes_not_worktree_shards=True,new_physics=0,new_fits=0,online_LLM_API_calls=0,
        wall_ns=perf_counter_ns()-start,publication_goal_complete=False)
    b.c.write(OUT/'actual_git_recovery.json',proof)
    print(dict(integrity=proof['integrity'],source_commit=source,files=result['files'],parts=proof['part_count']),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',required=True);parser.add_argument('--restore',required=True);args=parser.parse_args();main(args.source,args.restore)

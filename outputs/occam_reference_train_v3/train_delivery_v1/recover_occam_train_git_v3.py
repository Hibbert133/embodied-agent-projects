"""Restore all complete TRAIN original bytes from actual committed ZIP shards."""
from pathlib import Path
from time import perf_counter_ns
import argparse,hashlib,importlib.util,json,re,shutil,subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import occam_native_case_io_v1 as c
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
OUT=c.BASE/'train_delivery_v1'


def main(source):
    started=perf_counter_ns();assert re.fullmatch('[0-9a-f]{40}',source)
    def git(*args):return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT)
    assert git('rev-parse','HEAD').decode().strip()==source and not git('status','--porcelain','--untracked-files=no').strip()
    name=(OUT/'bundle_index.json').relative_to(ROOT).as_posix();raw=git('show',source+':'+name)
    assert raw==(ROOT/name).read_bytes();index=json.loads(raw)
    assert index['schema']=='OCCAM_TRAIN_ZIP_ALIASES_V1' and len(index['files'])==8450 and len(index['aliases'])==1296
    folder=Path(r'C:/Users/Administrator/Documents/ChatGPT/robotic agent/tg02')
    assert shutil.disk_usage(folder.parent).free>=index['bundle_bytes']+sum(p['bytes'] for p in index['files'].values())+256*1024**2
    folder.mkdir(exist_ok=False);bundle=folder/'train_records.zip';digest=hashlib.sha256();oids={}
    with bundle.open('xb') as output:
        for part in index['parts']:
            data=git('show',source+':'+part['path']);assert len(data)==part['bytes'] and hashlib.sha256(data).hexdigest()==part['sha256']
            output.write(data);digest.update(data);oids[part['path']]=git('rev-parse',source+':'+part['path']).decode().strip()
    assert digest.hexdigest()==index['bundle_sha256'] and bundle.stat().st_size==index['bundle_bytes']
    tool_name='outputs/occam_reference_train_v3/delivery_tools_v1/train_bundle_v1.py'
    assert git('show',source+':'+tool_name)==(ROOT/tool_name).read_bytes()
    spec=importlib.util.spec_from_file_location('committed_train_recovery',ROOT/tool_name)
    tool=importlib.util.module_from_spec(spec);spec.loader.exec_module(tool)
    def scan(raw,name):
        text=raw.decode('utf8');assert find_secret_rule(text) is None and not any(p.search(text) for p in EXTRA.values()),name
    restored=tool.recover(ROOT,bundle,index,folder/'files',scan=scan)
    result=dict(integrity='PASSED_ACTUAL_COMMIT_TRAIN_PARTS_AND_FILES_RESTORATION',source_commit=source,
        index_path=name,index_sha256=hashlib.sha256(raw).hexdigest(),part_git_oids=oids,part_count=len(oids),
        result=restored,restore_path=str(folder),source_validator_shared_with_local_restoration_disclosed=True,
        alias_decoded_scan_reuses_exact_canonical_stream_scan=True,independent_record_audits_preceded_delivery=True,
        new_physics=0,new_fits=0,online_LLM_API_calls=0,wall_ns=perf_counter_ns()-started)
    c.write(OUT/'actual_git_recovery.json',result);shutil.copyfile(Path(__file__),OUT/Path(__file__).name)
    print(dict(integrity=result['integrity'],parts=len(oids),files=restored['files'],decoded_lines=restored['decoded_canonical_gzip_lines']),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source',required=True);args=parser.parse_args();main(args.source)

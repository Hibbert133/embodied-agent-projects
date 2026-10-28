"""Recover the ten native parts from the actual committed objects."""
from pathlib import Path
from time import perf_counter_ns
import hashlib,importlib.util,json,shutil,subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import occam_native_case_io_v1 as c
SOURCE='d2dc35e56e174a1e26388068f617f82caf89df34'
OUT=c.BASE/'native_delivery_v1'


def main():
    start=perf_counter_ns();index_path=(OUT/'bundle_index.json').relative_to(ROOT).as_posix()
    def git(*args):return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT)
    assert git('rev-parse','HEAD').decode().strip()==SOURCE and not git('status','--porcelain','--untracked-files=no').strip()
    raw=git('show',SOURCE+':'+index_path);assert raw==(ROOT/index_path).read_bytes();index=json.loads(raw)
    folder=Path(r'C:/Users/Administrator/Documents/ChatGPT/robotic agent/ng02');folder.mkdir(exist_ok=False);bundle=folder/'native_records.zip';h=hashlib.sha256();objects={}
    with bundle.open('xb') as output:
        for part in index['parts']:
            data=git('show',SOURCE+':'+part['path']);assert len(data)==part['bytes'] and hashlib.sha256(data).hexdigest()==part['sha256']
            output.write(data);h.update(data);objects[part['path']]=git('rev-parse',SOURCE+':'+part['path']).decode().strip()
    assert h.hexdigest()==index['bundle_sha256'] and bundle.stat().st_size==index['bundle_bytes']
    spec=importlib.util.spec_from_file_location('native_delivery_source',OUT/'prepare_occam_native_delivery_v3.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    restored=module.verify_bundle(bundle,index,folder/'files')
    result=dict(integrity='PASSED_ACTUAL_COMMIT_PARTS_AND_FILES_RESTORATION',source_commit=SOURCE,index_path=index_path,index_sha256=hashlib.sha256(raw).hexdigest(),
        part_git_oids=objects,part_count=len(objects),result=restored,restore_path=str(folder),source_validator_shared_with_local_restoration_disclosed=True,
        independent_native_record_audits_preceded_delivery=True,new_physics=0,new_fits=0,online_LLM_API_calls=0,wall_ns=perf_counter_ns()-start)
    c.write(OUT/'actual_git_recovery.json',result);shutil.copyfile(Path(__file__),OUT/Path(__file__).name)
    print(dict(integrity=result['integrity'],parts=len(objects),files=restored['files'],decoded_gzip_lines=restored['decoded_gzip_lines']),flush=True)


if __name__=='__main__':main()

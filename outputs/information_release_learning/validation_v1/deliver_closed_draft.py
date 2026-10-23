"""Stage only owned closed-draft artifacts and verify actual indexed bytes."""
from pathlib import Path
import hashlib,subprocess,sys
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
OUT=Path(__file__).parent


def stage(names,label):
    path=OUT/(label+'.nul');names=set(names)|{path.relative_to(ROOT).as_posix()}
    path.write_bytes(b'\0'.join(n.encode('utf-8') for n in sorted(names))+b'\0')
    for flags in ((),('--renormalize',)):
        io.git('-c','maintenance.auto=false','-c','gc.auto=0','add',*flags,
            '--pathspec-from-file='+path.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    return names


def indexed(allowed):
    names=io.git('diff','--cached','--name-only').splitlines();io.require(set(names)<=allowed,'only owned paths in index')
    proc=subprocess.Popen(['git','cat-file','--batch'],cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE)
    hashes={}
    try:
        for name in names:
            proc.stdin.write((':'+name+'\n').encode('utf-8'));proc.stdin.flush();header=proc.stdout.readline().split()
            io.require(len(header)==3 and header[1]==b'blob','actual indexed blob '+name)
            data=proc.stdout.read(int(header[2]));io.require(proc.stdout.read(1)==b'\n','blob boundary')
            io.require(data==(ROOT/name).read_bytes(),'index/disk byte mismatch '+name)
            if b'\0' not in data:
                text=data.decode('utf-8',errors='replace')
                io.require(find_secret_rule(text) is None and not any(p.search(text) for p in EXTRA.values()),'staged secret pattern '+name)
            hashes[name]=hashlib.sha256(data).hexdigest()
        proc.stdin.close();io.require(proc.wait(timeout=60)==0,'indexed byte reader')
    finally:
        if proc.poll() is None:proc.kill();proc.wait()
    return hashes


def main():
    receipt=io.read(OUT/'post_eof_validation.json');io.require(receipt['integrity']=='PASSED','passed closed-draft checks after EOF repair')
    for n,h in receipt['source_sha256'].items():io.require(io.sha(ROOT/n)==h,'checked source changed '+n)
    owned=set(receipt['source_sha256'])|{'.gitattributes','AGENTS.md','RESEARCH_PLAN.md',
        'docs/research/release_learning_distinction_audit_v1_zh.md','reports/release_learning_precollection_review_v1_zh.md',
        (OUT/'deliver_closed_draft.py').relative_to(ROOT).as_posix()}
    for p in (ROOT/'outputs/information_release_learning').rglob('*'):
        if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc':owned.add(p.relative_to(ROOT).as_posix())
    io.require(set(io.git('diff','--cached','--name-only').splitlines())<=owned,'existing index contains only these owned paths')
    compile((OUT/'deliver_closed_draft.py').read_bytes(),str(OUT/'deliver_closed_draft.py'),'exec')
    allowed=stage(owned,'owned_paths_v1');sha=indexed(allowed)
    for args in (('diff','--check'),('diff','--cached','--check')):
        p=subprocess.run(['git',*args],cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
        io.require(p.returncode==0,'ordinary/staged diff check '+p.stderr)
    io.write(OUT/'delivery_receipt.json',dict(integrity='PASSED',classification='CLOSED_DESIGN_AND_ARRAY_INFRASTRUCTURE_CHECKPOINT',
        checked_source_sha256=receipt['source_sha256'],initial_index_sha256=sha,actual_index_and_disk_bytes_equal=True,
        supplemental_secret_scan='actual owned indexed text; repository rules and additional provider/GitHub patterns',
        prior_full_tracked_scan_sha256=io.sha(OUT/'tracked_secret_scan.json'),no_unrelated_paths_staged=True,
        ordinary_and_staged_diff_checks='PASSED',new_environment_activity=0,scientific_training=0,online_LLM_API_calls=0,
        native_qualified=False,algorithm_distinction_established=False,publication_goal_complete=False))
    allowed=stage(allowed|{(OUT/'delivery_receipt.json').relative_to(ROOT).as_posix()},'owned_paths_v2')
    final=indexed(allowed)
    p=subprocess.run(['git','diff','--cached','--check'],cwd=ROOT,capture_output=True,text=True)
    io.require(p.returncode==0,'final staged diff check')
    print(dict(integrity='PASSED',owned_index_objects=len(final),new_unique_tests=25,closed_before_collection=True),flush=True)


if __name__=='__main__':main()

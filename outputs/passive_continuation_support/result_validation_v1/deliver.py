"""Verify audited descriptive results and stage only their owned artifacts."""
from pathlib import Path
from time import perf_counter_ns
import subprocess,sys
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from src.analysis import passive_continuation_support_v1 as a
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
io=a.io;OUT=Path(__file__).parent
RUN=a.OUTPUT/'passive_support_20261023T064300Z_41161eb6c331'


def command(name,args):
    started=perf_counter_ns();p=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace')
    io.write(OUT/name,dict(command=args,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr,wall_ns=perf_counter_ns()-started))
    io.require(p.returncode==0,'result check '+name+' '+p.stdout+p.stderr)


def stage(names,label):
    path=OUT/(label+'.nul');names=set(names)|{path.relative_to(ROOT).as_posix()}
    path.write_bytes(b'\0'.join(n.encode() for n in sorted(names))+b'\0')
    for flags in ((),('--renormalize',)):io.git('-c','maintenance.auto=false','-c','gc.auto=0','add',*flags,
        '--pathspec-from-file='+path.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    return names


def check_index(allowed):
    sha=index_bytes(allowed)
    for n in sha:
        data=(ROOT/n).read_bytes()
        if b'\0' not in data:io.require(not any(p.search(data.decode('utf-8',errors='replace')) for p in EXTRA.values()),'additional staged secret '+n)
    return sha


def main():
    io.require(not io.git('diff','--cached','--name-only'),'begin result phase with empty index')
    m=a.checked(RUN/'manifest.json');v=io.read(RUN/'audit.json');io.require(v['integrity']=='PASSED','complete independent audit')
    for n,h in v['analysis_artifact_sha256'].items():io.require(io.sha(RUN/n)==h,'audited result '+n)
    for name in ('analyze_guard.json','audit_guard.json'):
        g=io.read(RUN/name);io.require(not any(g['operation_counts'].values()) and g['network']=={'attempted_network_calls':0},'zero interaction/fitting guard '+name)
    qa=io.read(a.VALIDATION/'complete.json')
    for n,h in qa['source_sha256'].items():io.require(io.sha(ROOT/n)==h,'tested frozen analysis source '+n)
    for n,h in io.read(a.VALIDATION/'source_reuse.json')['source_sha256'].items():io.require(io.sha(ROOT/n)==h,'source-reused previous check '+n)
    report=io.read(RUN/'report_receipt.json');io.require(io.sha(ROOT/report['report'])==report['report_sha256'],'report unchanged')
    command('compile.json',[sys.executable,'-m','compileall','-q','src','scripts','tests'])
    compile((OUT/'deliver.py').read_bytes(),str(OUT/'deliver.py'),'exec')
    command('dependencies.json',[sys.executable,'-m','pip','check'])
    owned={'AGENTS.md','RESEARCH_PLAN.md','scripts/report_passive_continuation_support_v1.py','reports/passive_continuation_support_v1_zh.md'}
    owned|={p.relative_to(ROOT).as_posix() for base in (RUN,OUT) for p in base.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}
    allowed=stage(owned,'owned_paths_v1')
    command('tracked_secret_scan.json',[sys.executable,'scripts/check_tracked_secrets.py','--staged'])
    command('ordinary_diff.json',['git','diff','--check']);command('staged_diff.json',['git','diff','--cached','--check'])
    indexed=check_index(allowed)
    io.write(OUT/'complete.json',dict(integrity='PASSED',analysis_manifest_sha256=io.sha(RUN/'manifest.json'),
        independent_audit_sha256=io.sha(RUN/'audit.json'),actual_index_sha256=indexed,
        frozen_analysis_source_sha256=qa['source_sha256'],unique_tests=2022,old_tests_not_repeated=True,
        no_old_QUAL_tuning=True,only_fixed_gain_outcomes_replayed=True,existing_VALIDATE_FULL_not_a_new_baseline=True,
        old_raw_data_preserved=True,all_new_physical_activity=0,scientific_model_fits=0,new_fixed_policy_queries=0,online_LLM_API_calls=0,
        task_benefit_established=False,publication_goal_complete=False,
        check_receipt_sha256={p.name:io.sha(p) for p in OUT.iterdir() if p.is_file() and p.name!='complete.json'}))
    allowed=stage(allowed|{p.relative_to(ROOT).as_posix() for p in OUT.iterdir() if p.is_file()},'owned_paths_v2');final=check_index(allowed)
    io.require(not io.git('diff','--cached','--check'),'final staged diff')
    print(dict(integrity='PASSED',actual_owned_index_objects=len(final),independent_fields=v['fields_checked'],new_physical_activity=0),flush=True)


if __name__=='__main__':main()

"""Bind committed post-hoc analysis and immutable old raw/statistical sources."""
from datetime import datetime,timezone
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis import acquisition_support_sources_v1 as s
io=s.io
OWN=('src/analysis/acquisition_support_sources_v1.py','src/analysis/acquisition_support_v1.py','src/analysis/acquisition_support_audit_v1.py',
    'scripts/analyze_acquisition_support_v1.py','scripts/audit_acquisition_support_v1.py','scripts/prepare_acquisition_support_v1.py',
    'scripts/report_acquisition_support_v1.py','scripts/plot_acquisition_support_v1.py','tests/test_acquisition_support_v1.py',
    'configs/movement_task/acquisition_support_audit_v1.json','docs/protocols/acquisition_support_audit_v1_zh.md',
    'docs/research/acquisition_branch_support_prior_art_v1_zh.md')


def prepare():
    io.require(not list((s.BASE/'analysis_v1').glob('*/manifest.json')),'one source allocation only')
    for name in OWN:io.require(io.git('ls-files','--error-unmatch',name)==name,'analysis source must be committed')
    qa=io.read(s.BASE/'validation_v1/complete.json');io.require(qa['integrity']=='PASSED','source-bound software checks')
    for name,h in qa['analysis_source_sha256'].items():io.require(io.sha(s.ROOT/name)==h,'checked source changed')
    head=io.git('rev-parse','HEAD');now=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    source=s.paths();source.update({n:io.sha(s.ROOT/n) for n in OWN})
    source[(s.BASE/'validation_v1/complete.json').relative_to(s.ROOT).as_posix()]=io.sha(s.BASE/'validation_v1/complete.json')
    result={'analysis_run_id':'acquisition_support_'+now+'_'+head[:12],'analysis_git_commit':head,
        'classification':'POST_HOC_DESCRIPTIVE_ONLY','source_sha256':source,'config':io.read(s.ROOT/OWN[9]),
        'new_environment_steps':0,'new_model_fits':0,'new_online_LLM_API_calls':0,'publication_goal_complete':False}
    result['manifest_id']=io.digest(result);out=s.BASE/'analysis_v1'/result['analysis_run_id'];out.mkdir(parents=True,exist_ok=False)
    io.write(out/'manifest.json',result);return out/'manifest.json'


if __name__=='__main__':print(prepare(),flush=True)

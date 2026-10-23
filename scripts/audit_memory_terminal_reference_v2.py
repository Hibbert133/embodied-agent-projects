"""Reader-name-only repair; preserve frozen primary data and failed v1 audit."""
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
import argparse,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.analyze_acquisition_support_v1 import guarded
from src.analysis.memory_terminal_audit_v2 import audit
from src.analysis import memory_terminal_qualification_v1 as q
from tests.test_memory_terminal_audit_repair_v2 import DISABLED
io=q.io


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);a=p.parse_args()
    m=q.checked(a.manifest);base=q.BASE/'audit_repair_v2';qa=io.read(base/'complete.json')
    io.require(qa['integrity']=='PASSED' and qa['tests']==3,'checked auditor repair')
    for n,h in qa['source_sha256'].items():
        io.require(io.sha(io.ROOT/n)==h and io.git('ls-files','--error-unmatch',n)==n,'committed effective audit source')
    with ExitStack() as stack:
        for name in DISABLED:stack.enter_context(patch(name,side_effect=RuntimeError('Independent audit called main implementation')))
        result,guard=guarded(lambda:audit(a.manifest))
    guard['main_numeric_functions_disabled']=list(DISABLED)
    io.write(a.manifest.parent/'audit_interaction_guard.json',guard)
    io.write(a.manifest.parent/'audit_repair_binding_v2.json',{'integrity':'PASSED','original_manifest_sha256':io.sha(a.manifest),
        'original_auditor_sha256':m['source_sha256']['src/analysis/memory_terminal_audit_v1.py'],
        'effective_source_sha256':qa['source_sha256'],'repair_validation_sha256':io.sha(base/'complete.json'),
        'original_failure_record_sha256':io.sha(base/'failure_record.json'),'audit_sha256':io.sha(a.manifest.parent/'audit.json'),
        'primary_outputs_regenerated':False,'comparison_or_tolerance_changes':False,'new_environment_steps':0,'new_model_fits':0,'new_online_LLM_API_calls':0})
    print({k:result[k] for k in ('integrity','exact_rational_identities','estimate_rows','fields_checked')},flush=True)

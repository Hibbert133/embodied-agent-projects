"""Versioned orchestration repair; frozen v1 and the collected data stay intact."""
from pathlib import Path
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects')
source=(ROOT/'src/analysis/learned_acquisition_native_audit_v1.py').read_text('utf8')
body=source[source.index('def audit(path):'):]
body=body.replace("out=path.parent/'native';start=perf_counter_ns();completion=io.read(out/'completion.json')", "original=path.parent/'native';out=path.parent/'native_audit_repair_v2';out.mkdir(exist_ok=False);start=perf_counter_ns();completion=io.read(original/'completion.json')")
for name in ('summary.json','cases.jsonl.gz','events.jsonl.gz','witnesses.jsonl.gz'):
    body=body.replace("out/'"+name+"'","original/'"+name+"'")
body=body.replace("io.sha(out/name)","io.sha(original/name)")
body=body.replace("same(set(programs),set(a.PROGRAMS))","check_program_membership(programs)")
body=body.replace("'PASSED_NATIVE_INTEGRATION_ONLY' if software_complete and behavior else 'NATIVE_BEHAVIOR_CHAIN_NOT_ESTABLISHED'", "'SUPPLEMENTAL_NATIVE_CHAIN_RECONSTRUCTED_ORIGINAL_QUAL_FAILED' if software_complete and behavior else 'SUPPLEMENTAL_BEHAVIOR_CHAIN_NOT_ESTABLISHED_ORIGINAL_QUAL_FAILED'")
body=body.replace("gate=dict(status=", "gate=dict(original_frozen_audit_status='FAILED_RETAINED',repair_not_retroactive_frozen_qualification=True,status=")
body=body.replace("result=dict(integrity='PASSED',", "result=dict(integrity='PASSED',original_frozen_audit_status='FAILED_RETAINED',repair_not_retroactive_frozen_qualification=True,repair_source_git_commit=io.git('rev-parse','HEAD'),")
assert "same(set(" not in body and "original/'events.jsonl.gz'" in body
header='''"""Read-only v2 orchestration repair. Never changes v1 qualification or physics.

V1 reconstructed all54 cases then failed because JSON normalization rejects sets.
Only compare dictionary keys as sorted lists; outputs are in a fresh v2 folder.
The numerical inference, PI, actuator and witness reconstructors remain v1.
"""
from collections import Counter
from itertools import groupby
from pathlib import Path
from time import perf_counter_ns
from unittest.mock import patch
import gzip,json
import numpy as np
from src.analysis.learned_acquisition_native_audit_v1 import a,io,same,reconstruct,command_replay
from src.analysis.release_learning_guard_v1 import read_only
from src.analysis.short_probe_journal_audit_v1 import physical_rows_equal
from src.analysis.capsule_record_json_v2 import normalize


def check_program_membership(programs):
    io.require(type(programs) is dict,'program records indexed by unique dictionary keys')
    same(sorted(programs),sorted(a.PROGRAMS),'missing or unregistered program in native unit')


'''
target=ROOT/'src/analysis/learned_acquisition_native_audit_v2.py'
with target.open('x',encoding='utf8',newline='\n') as stream:stream.write(header+body)
print(str(target))

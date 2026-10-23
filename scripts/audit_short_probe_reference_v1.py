"""Read-only independent population and physical-journal audit."""
import argparse
import gzip
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1];sys.path.insert(0, str(ROOT))
from src.analysis import short_probe_study_io_v1 as io
from src.analysis.short_probe_study_audit_v1 import audit_records, population


def lines(paths):
    for path in paths:
        with gzip.open(path, 'rt', encoding='utf-8') as f:
            for line in f:
                yield json.loads(line)


def run(path, phase):
    m, models, designs = io.load(path);folder = path.parent/phase.lower()
    completion = io.read(folder/'completion.json')
    if any(completion[k] != m[k] for k in io.IDENTITY) or completion['phase'] != phase or completion['status'] != 'COLLECTED_FOR_INDEPENDENT_AUDIT':
        raise ValueError('completed collection receipt required')
    names = {'events.jsonl.gz','summary.json','status.json'} | {f"cases_{s['stream']:02}.jsonl.gz" for s in population(phase)}
    if set(completion['artifact_sha256']) != names or {p.name for p in folder.iterdir()} != names | {'completion.json'}:
        raise ValueError('collection artifact set differs')
    if any(io.sha(folder/name) != value for name,value in completion['artifact_sha256'].items()):
        raise ValueError('completed collection bytes changed')
    summary = io.read(folder/'summary.json')
    result = audit_records(m, phase, summary, lines(folder/f"cases_{s['stream']:02}.jsonl.gz" for s in population(phase)),
        lines([folder/'events.jsonl.gz']), models, designs)
    result.update(summary_sha256=io.sha(folder/'summary.json'), completion_sha256=io.sha(folder/'completion.json'))
    io.write(path.parent/(phase.lower()+'_record_audit.json'), result)
    print(json.dumps({k:result[k] for k in ('phase','integrity','executions_checked','events_checked','required_four_step_policy_chain')}), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser();p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--phase', choices=('SMOKE','MAIN'), required=True);a = p.parse_args();run(a.manifest.resolve(), a.phase)

"""Compare actual compact archive objects with every newly delivered source file."""
from pathlib import Path
import gzip
import hashlib
import json
import subprocess

ROOT = Path('C:/Users/Administrator/Desktop/embodied-agent-projects')
OUT = ROOT / 'outputs/research_archive/low_rank_risk_pilot_v1'
SOURCE = 'e34d244251362e94b3d70edb4fa6ca0b935a580e'
BASE_SOURCE = '068277fbb0090f9b3e81facd0dd875958316b661'


def git(*args):
    return subprocess.check_output(['git', '-c', 'maintenance.auto=false', '-c', 'gc.auto=0', *args], cwd=ROOT)


def main():
    local = json.loads((OUT / 'local_receipt.json').read_text(encoding='utf-8'))
    catalog = json.loads((OUT / 'catalog.json').read_text(encoding='utf-8'))
    assert local['integrity'] == catalog['integrity'] == 'PASSED'
    assert local['source_local_commit'] == catalog['source_local_commit'] == SOURCE
    assert git('rev-parse', 'HEAD').decode().strip() == SOURCE
    assert not git('status', '--porcelain', '--untracked-files=no').strip()
    changed = set(git('diff', '--name-only', BASE_SOURCE, SOURCE).decode().splitlines())
    rows = {r['path']: r for r in catalog['files'] if r['path'] in changed}
    assert set(rows) == changed and all(r['published'] for r in rows.values())
    proof = {}
    with subprocess.Popen(['git', 'cat-file', '--batch'], cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE) as proc:
        for name in sorted(changed):
            proc.stdin.write((local['archive_commit'] + ':' + name + '\n').encode())
            proc.stdin.flush()
            header = proc.stdout.readline().split()
            assert len(header) == 3 and header[1] == b'blob'
            data = proc.stdout.read(int(header[2]))
            assert proc.stdout.read(1) == b'\n' and data == (ROOT / name).read_bytes(), name
            assert header[0].decode() == rows[name]['oid'] and hashlib.sha256(data).hexdigest() == rows[name]['sha256']
            if name.endswith('.gz'):
                gzip.decompress(data).decode('utf-8')
            proof[name] = dict(bytes=len(data), sha256=rows[name]['sha256'], git_oid=rows[name]['oid'])
        proc.stdin.close()
        assert proc.wait(timeout=60) == 0
    receipt = dict(integrity='PASSED_ACTUAL_ARCHIVE_SOURCE_AND_DISK_BYTES_BEFORE_PUBLICATION',
        archive_commit=local['archive_commit'], source_local_commit=SOURCE, base_source_local_commit=BASE_SOURCE,
        phase_files=len(proof), phase_omitted=0, phase_bytes=sum(r['bytes'] for r in proof.values()), objects=proof,
        full_QUAL_raw_data_published=False, complete_QUAL_raw_restoration_not_claimed=True,
        canonical_NATIVE_and_TRAIN_part_proofs_reused_without_new_recovery=True,
        new_environment_interactions=0, online_LLM_API_calls=0)
    with (OUT / 'prepublication_proof.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print({k: receipt[k] for k in ('integrity', 'archive_commit', 'phase_files', 'phase_bytes')})


if __name__ == '__main__':
    main()

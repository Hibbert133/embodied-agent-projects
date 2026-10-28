"""Test and stage only the new read-only census tools; do not analyze real rows."""
from pathlib import Path
from time import perf_counter_ns
from unittest import mock
import gzip
import hashlib
import json
import subprocess
import sys
import unittest
import run_opportunity_v1 as run

ROOT = run.ROOT
sys.path.insert(0, str(ROOT))
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
OUT = run.FREEZE.parent
PARENT = 'bb120f1c554e27937c4ce1bad76d77423a07ce5e'


def check_index(owned):
    names = run.git('diff', '--cached', '--name-only').decode().splitlines()
    if set(names) != owned:
        raise ValueError('no unrelated staged paths')
    result = {}
    with subprocess.Popen(['git', 'cat-file', '--batch'], cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE) as proc:
        for name in names:
            proc.stdin.write((':'+name+'\n').encode())
            proc.stdin.flush()
            header = proc.stdout.readline().split()
            if len(header) != 3 or header[1] != b'blob':
                raise ValueError('actual index object missing')
            data = proc.stdout.read(int(header[2]))
            if proc.stdout.read(1) != b'\n' or data != (ROOT / name).read_bytes():
                raise ValueError('actual index and disk bytes differ: '+name)
            if name.endswith('.py'):
                compile(data, name, 'exec')
            decoded = gzip.decompress(data) if name.endswith('.gz') else data
            if b'\0' not in decoded:
                text = decoded.decode('utf-8')
                if find_secret_rule(text) or any(rule.search(text) for rule in EXTRA.values()):
                    raise ValueError('actual indexed credential pattern: '+name)
            result[name] = dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), git_oid=header[0].decode())
        proc.stdin.close()
        if proc.wait(timeout=60) != 0:
            raise RuntimeError('index reader failed')
    if run.git('diff', '--check').strip() or run.git('diff', '--cached', '--check').strip():
        raise ValueError('ordinary/staged diff checks')
    return result


def main():
    start = perf_counter_ns()
    if run.git('rev-parse', 'HEAD').decode().strip() != PARENT or run.git('status', '--porcelain', '--untracked-files=no').strip():
        raise ValueError('unchanged source parent and clean tracked state')
    if run.OUT.exists():
        raise ValueError('actual census must not start before freeze')
    OUT.mkdir(exist_ok=False)
    before = {p.relative_to(ROOT).as_posix(): run.sha(p) for p in run.source_paths()}
    inputs = {p.relative_to(ROOT).as_posix(): run.sha(p) for p in run.inputs()}
    manifest = run.read(run.RUN / 'manifest.json')
    science = {**manifest['source_sha256'], **manifest['input_sha256']}
    run.verify(science)
    old_freeze = ROOT / 'outputs/occam_reference_qualification_v1/freeze_validation_v1/complete.json'
    old = run.read(old_freeze)
    if old['integrity'] != 'PASSED' or old['unique_tests'] != 2695:
        raise ValueError('passed source-bound scientific receipt')
    if run.sha(old_freeze.parent / 'validation_receipt.json') != old['validation_receipt_sha256']:
        raise ValueError('old validation receipt bytes')
    def no_real_rows(*args, **kwargs):
        raise RuntimeError('formal array tests cannot parse original scientific CSV')
    with (OUT / 'unit.log').open('x', encoding='utf-8', newline='\n') as stream:
        with mock.patch.object(run, 'csv_read', no_real_rows):
            result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
                unittest.defaultTestLoader.loadTestsFromName('test_opportunity_v1'))
    run.write(OUT / 'unit_receipt.json', dict(integrity='PASSED' if result.wasSuccessful() else 'FAILED',
        tests=result.testsRun, failures=len(result.failures), errors=len(result.errors),
        constructed_fixtures_only=True, actual_scientific_CSV_parses_forbidden=True,
        intentional_guard_rejection_test=True, successful_environment_or_network_actions=0))
    if not result.wasSuccessful() or result.testsRun != 16:
        raise ValueError('all 16 constructed-fixture tests')
    run.verify(before)
    run.write(OUT / 'source_binding.json', dict(integrity='PASSED', source_parent_commit=PARENT,
        new_source_sha256=before, scientific_source_sha256=manifest['source_sha256'],
        scientific_input_sha256=manifest['input_sha256'], old_2695_checks_receipt_sha256=run.sha(old_freeze),
        old_compilation_and_scientific_checks_source_bound_reused=True, no_simulation_tests_repeated=True))
    with (OUT / 'pip_check_stdout.log').open('xb') as stdout, (OUT / 'pip_check_stderr.log').open('xb') as stderr:
        proc = subprocess.run([sys.executable, '-B', '-m', 'pip', 'check'], cwd=ROOT, stdout=stdout, stderr=stderr)
    if proc.returncode != 0:
        raise ValueError('dependency check failed')
    run.write(run.FREEZE, dict(integrity='FROZEN_RECORD_ONLY_OPPORTUNITY_CENSUS_V1',
        source_parent_commit=PARENT, source_sha256=before, input_sha256=inputs,
        manifest_id=run.MID, original_statistics_sha256=run.STAT,
        new_unique_tests=16, development_test_executions=16, formal_test_executions=16,
        source_bound_original_scientific_tests_reused=2695, actual_census_started=False,
        analysis_scope='POST_HOC_ALL_1740_REGISTRATION_29_PROGRAMS_12_FIXED_MENU_54_UNITS',
        worker_hard_timeout_seconds=120, new_environment_interactions=0, new_model_queries=0,
        new_fits=0, new_episode_seed_allocations=0, online_LLM_API_calls=0,
        publication_goal_complete=False))
    owned = {p.relative_to(ROOT).as_posix() for p in run.BASE.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    owned.update(run.DOCS)
    def stage(label):
        spec = OUT / (label + '.nul')
        owned.add(spec.relative_to(ROOT).as_posix())
        spec.write_bytes(b'\0'.join(n.encode() for n in sorted(owned)) + b'\0')
        for flags in ((), ('--renormalize',)):
            run.git('add', *flags, '--pathspec-from-file='+spec.relative_to(ROOT).as_posix(), '--pathspec-file-nul')
    stage('owned_initial')
    print(json.dumps(dict(stage='FORMAL_16_PASSED_SOURCES_BOUND_NO_ACTUAL_CENSUS', files=len(owned))), flush=True)
    scan_start = perf_counter_ns()
    with (OUT / 'tracked_secret_stdout.log').open('xb') as stdout, (OUT / 'tracked_secret_stderr.log').open('xb') as stderr:
        proc = subprocess.run([sys.executable, '-B', 'scripts/check_tracked_secrets.py', '--staged'], cwd=ROOT, stdout=stdout, stderr=stderr)
    run.write(OUT / 'tracked_secret_receipt.json', dict(returncode=proc.returncode, wall_ns=perf_counter_ns()-scan_start,
        actual_script_scans_all_tracked_worktree_files=True, actual_index_EXTRA_scan_separate=True))
    if proc.returncode != 0:
        raise ValueError('secret scan blocks commit')
    owned.update(p.relative_to(ROOT).as_posix() for p in OUT.iterdir() if p.is_file())
    stage('owned_checked')
    run.write(OUT / 'index_disk_proof.json', dict(integrity='PASSED', objects=check_index(owned), actual_index_basic_EXTRA_scan=True))
    run.verify(before)
    run.verify(inputs)
    run.verify(science)
    run.write(OUT / 'delivery_validation.json', dict(integrity='PASSED_RECORD_ONLY_CENSUS_SOFTWARE_FREEZE',
        new_unique_tests=16, no_actual_scientific_CSV_parses=True, actual_census_started=False,
        original_statistics_sha256=run.STAT, tested_source_sha256=before, source_hash_passes=2,
        dependency_returncode=0, secret_scan_returncode=0, ordinary_and_staged_diff_checks=True,
        newly_staged_Python_compiled_in_memory=True, wall_ns=perf_counter_ns()-start,
        new_environment_interactions=0, new_model_queries=0, new_fits=0, online_LLM_API_calls=0))
    owned.update(p.relative_to(ROOT).as_posix() for p in OUT.iterdir() if p.is_file())
    stage('owned_final')
    objects = check_index(owned)
    print(json.dumps(dict(integrity='PASSED_READY_FOR_CENSUS_FREEZE_COMMIT', files=len(objects), bytes=sum(p['bytes'] for p in objects.values()))), flush=True)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()

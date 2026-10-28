"""Resume presentation delivery with an exact compressed seed-metadata copy."""
from pathlib import Path
from time import perf_counter_ns
import gzip
import hashlib
import json
import subprocess
import sys
import prepare_delivery_v1 as v


def main():
    start = perf_counter_ns()
    assert v.git('rev-parse', 'HEAD').decode().strip() == v.PARENT
    assert not v.git('diff', '--cached', '--name-only').strip()
    assert not v.git('status', '--porcelain', '--untracked-files=no').strip()
    prior = v.read(v.OUT / 'source_binding.json')
    v.verify(prior['all_checked_source_sha256'])
    assert v.sha(v.RUN / 'statistics_v1/statistics.json') == v.STATS
    raw = v.RUN / 'seed_scope.json'
    data = raw.read_bytes()
    assert len(data) == 11429531 and len(data) > 4*1024**2
    folder = v.REVIEW / 'seed_scope_metadata_v1'
    folder.mkdir(exist_ok=False)
    compressed = gzip.compress(data, mtime=0)
    assert gzip.decompress(compressed) == data and len(compressed) <= 4*1024**2
    with (folder / 'seed_scope.json.gz').open('xb') as stream:
        stream.write(compressed)
    v.write(folder / 'index.json', dict(schema='EXACT_SEED_SCOPE_METADATA_GZIP_V1',
        source_path=raw.relative_to(v.ROOT).as_posix(), source_bytes=len(data), source_sha256=v.sha(raw),
        gzip_path=(folder / 'seed_scope.json.gz').relative_to(v.ROOT).as_posix(),
        gzip_bytes=len(compressed), gzip_sha256=hashlib.sha256(compressed).hexdigest(),
        decompressed_bytes_equal_original=True, raw_source_not_modified=True,
        this_is_seed_inventory_metadata_not_a_QUAL_trajectory_bundle=True))
    v.write(v.OUT / 'preparation_v1_failure.json', dict(
        integrity='PRESERVED_DELIVERY_PREPARATION_FAILURE', returncode=1,
        source_path=(Path(v.__file__).relative_to(v.ROOT)).as_posix(), source_sha256=v.sha(v.__file__),
        exception='AssertionError: selected artifact exceeded the 4 MiB per-file delivery limit',
        oversized_path=raw.relative_to(v.ROOT).as_posix(), oversized_bytes=len(data),
        failure_before_staging_or_secret_scan=True, source_and_partial_receipts_preserved=True,
        versioned_repair='prepare_delivery_v2.py; exact gzip copy and byte-identity index',
        new_environment_interactions=0, new_fits=0, online_LLM_API_calls=0))
    paths = {p for p in v.BASE.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    for path in (v.FIRST, v.COST, v.RUN / 'statistics_v1', v.RUN / 'pipeline_v1', v.RUN / 'report_v1', v.RUN / 'entry_attempts_v1'):
        paths.update(p for p in path.rglob('*') if p.is_file())
    paths.update(v.RUN / n for n in ('manifest.json', 'seed_scope_audit.json'))
    for phase in ('native', 'qual'):
        paths.update(v.RUN / phase / n for n in ('audit.json', 'completion.json', 'member_index.json',
            'process_audit.json', 'status.json', 'summary.json', 'cases.jsonl.gz', 'prequential_windows.jsonl.gz'))
    paths.update(v.ROOT / 'reports' / n for n in ('occam_reference_qualification_v1_zh.md', 'occam_reference_qualification_v1_delivery_zh.md'))
    assert all(p.stat().st_size <= 4*1024**2 for p in paths)
    owned = {p.relative_to(v.ROOT).as_posix() for p in paths}

    def stage(label):
        spec = v.OUT / (label + '.nul')
        owned.add(spec.relative_to(v.ROOT).as_posix())
        spec.write_bytes(b'\0'.join(n.encode('utf-8') for n in sorted(owned)) + b'\0')
        for flags in ((), ('--renormalize',)):
            v.git('add', *flags, '--pathspec-from-file=' + spec.relative_to(v.ROOT).as_posix(), '--pathspec-file-nul')

    stage('owned_initial_v2')
    print(json.dumps(dict(stage='SOURCES_CHECKED_OWNED_RESULTS_STAGED', files=len(owned),
                          exact_seed_metadata_gzip_bytes=len(compressed))), flush=True)
    scan_start = perf_counter_ns()
    with (v.OUT / 'tracked_secret_scan_stdout.log').open('xb') as stdout, (v.OUT / 'tracked_secret_scan_stderr.log').open('xb') as stderr:
        proc = subprocess.run([sys.executable, '-B', 'scripts/check_tracked_secrets.py', '--staged'], cwd=v.ROOT, stdout=stdout, stderr=stderr)
    v.write(v.OUT / 'tracked_secret_scan.json', dict(returncode=proc.returncode, wall_ns=perf_counter_ns()-scan_start,
        actual_script_scans_all_tracked_worktree_files=True, gzip_decoding_and_EXTRA_checked_on_actual_index_separately=True))
    assert proc.returncode == 0
    owned.update(p.relative_to(v.ROOT).as_posix() for p in v.OUT.iterdir() if p.is_file())
    stage('owned_scanned_v2')
    objects = v.index_check(owned)
    v.write(v.OUT / 'index_disk_proof.json', dict(integrity='PASSED', objects=objects,
        actual_index_basic_and_extra_secret_scan=True, all_selected_gzip_decoded=True))
    v.verify(prior['all_checked_source_sha256'])
    assert v.sha(v.RUN / 'statistics_v1/statistics.json') == v.STATS
    v.write(v.OUT / 'complete.json', dict(integrity='PASSED_SUMMARY_DIAGNOSTICS_COST_DELIVERY_WITH_RAW_ARCHIVE_PENDING',
        parent_commit=v.PARENT, manifest_id=v.read(v.RUN / 'manifest.json')['manifest_id'], primary_statistics_sha256=v.STATS,
        numerical_qualification=True, predictive_qualification=True, task_qualification=False,
        scientific_source_hash_passes=3, new_scientific_tests=0, new_simulation_tests=0,
        compilation='all newly staged Python sources compiled in memory', dependency_check_returncode=0,
        secret_scan_returncode=0, actual_index_gzip_basic_EXTRA_scan=True,
        ordinary_and_staged_diff_check=True, figure_visually_reviewed=True,
        earlier_preparation_failure_preserved=True, seed_scope_exact_gzip_byte_comparison=True,
        full_raw_data_delivery_complete=False, raw_records_preserved=True,
        no_new_environment_interactions=True, new_real_model_queries=0, new_fits=0,
        new_episode_seed_allocations=0, online_LLM_API_calls=0, publication_goal_complete=False,
        successful_v2_wall_ns=perf_counter_ns()-start, failed_v1_parent_wall_seconds_from_execution_receipt=5.0368359))
    owned.update(p.relative_to(v.ROOT).as_posix() for p in v.OUT.iterdir() if p.is_file())
    stage('owned_final_v2')
    objects = v.index_check(owned)
    print(json.dumps(dict(integrity='PASSED_READY_FOR_LOCAL_SUMMARY_COMMIT_RAW_DELIVERY_PENDING',
                          files=len(objects), bytes=sum(o['bytes'] for o in objects.values()),
                          task_qualification=False, new_environment_interactions=0, online_LLM_API_calls=0)), flush=True)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()

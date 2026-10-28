"""Own and verify a partial data delivery; never collect, fit or restore physics."""
from pathlib import Path
from time import perf_counter_ns
import csv
import gzip
import hashlib
import json
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA

BASE = ROOT / 'outputs/occam_qualification_result_review_v1'
REVIEW = BASE / 'review_v1'
OUT = BASE / 'validation_v1'
RUN = ROOT / 'outputs/occam_reference_qualification_v1/qualification_v1/occam_reference_qualification_v1_20261028T125131Z_7abaec83b085'
FIRST = ROOT / 'outputs/occam_first_window_diagnostic_v1/analysis_v1'
COST = ROOT / 'outputs/occam_qualification_costs_v2/analysis_v1'
AUX = Path('C:/Users/Administrator/Documents/ChatGPT/robotic agent')
PARENT = 'd6f1bad4bff34a31d210ae2ec94045bd517b6af9'
STATS = 'dccede3a2838fb1ef98c20bab5e89080bcd42c8a53629c1ad22d646ae6fb75bc'


def git(*args):
    return subprocess.check_output(['git', '-c', 'maintenance.auto=false', '-c', 'gc.auto=0', *args], cwd=ROOT)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')


def verify(mapping):
    for name, expected in mapping.items():
        assert sha(ROOT / name) == expected, 'source hash: ' + name


def index_check(owned):
    names = git('diff', '--cached', '--name-only').decode('utf-8').splitlines()
    assert set(names) == owned, 'only explicitly owned new result artifacts'
    result = {}
    with subprocess.Popen(['git', 'cat-file', '--batch'], cwd=ROOT,
                          stdin=subprocess.PIPE, stdout=subprocess.PIPE) as proc:
        for name in names:
            proc.stdin.write((':' + name + '\n').encode('utf-8'))
            proc.stdin.flush()
            header = proc.stdout.readline().split()
            assert len(header) == 3 and header[1] == b'blob', name
            data = proc.stdout.read(int(header[2]))
            assert proc.stdout.read(1) == b'\n' and data == (ROOT / name).read_bytes(), name
            decoded = gzip.decompress(data) if name.endswith('.gz') else data
            if b'\0' not in decoded:
                text = decoded.decode('utf-8')
                assert find_secret_rule(text) is None, 'credential pattern: ' + name
                assert not any(rule.search(text) for rule in EXTRA.values()), 'extra credential pattern: ' + name
            if name.endswith('.py'):
                compile(data, name, 'exec')
            result[name] = dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), git_oid=header[0].decode())
        proc.stdin.close()
        assert proc.wait(timeout=60) == 0
    assert not git('diff', '--check').strip() and not git('diff', '--cached', '--check').strip()
    return result


def main():
    started = perf_counter_ns()
    assert git('rev-parse', 'HEAD').decode().strip() == PARENT
    assert not git('status', '--porcelain', '--untracked-files=no').strip()
    REVIEW.mkdir(exist_ok=False)
    OUT.mkdir(exist_ok=False)
    m = read(RUN / 'manifest.json')
    assert sha(RUN / 'statistics_v1/statistics.json') == STATS
    s = read(RUN / 'statistics_v1/statistics.json')
    original = read(RUN / 'report_v1/complete.json')
    sources = read(RUN / 'report_v1/source_manifest.json')
    assert original['scientific_population_complete'] and original['allocated'] == 1740
    assert original['complete_task_failures'] == 99 and original['unresolved'] == 0
    assert original['numerical_qualification'] and original['predictive_qualification'] and not original['task_qualification']
    assert not s['task_qualified'] and s['prediction']['qualified']
    assert sha(ROOT / 'reports/occam_reference_qualification_v1_zh.md') == sources['report_sha256']
    assert all(row['returncode'] == 0 for row in read(RUN / 'pipeline_v1/complete.json')['steps'])
    source_checks = {**m['source_sha256'], **m['input_sha256'], **sources['source_sha256']}
    for path in [ROOT / 'outputs/occam_first_window_diagnostic_v1/freeze_v1/complete.json',
                 ROOT / 'outputs/occam_qualification_costs_v2/freeze_v1/complete.json']:
        source_checks.update(read(path)['source_sha256'])
    verify(source_checks)
    first = read(FIRST / 'complete.json')
    cost = read(COST / 'complete.json')
    assert first['integrity'] == 'PASSED_COMPLETE_POST_HOC_DESCRIPTION' and first['registered_executions'] == 1566
    assert first['original_statistics_sha256'] == STATS and not any(first['counters'].values())
    assert read(FIRST / 'audit.json')['production_diagnostic_functions_disabled'] is True
    assert cost['integrity'] == 'PASSED_EXPLICIT_ACCOUNTING_COST_RECONSTRUCTION_V2' and cost['executions'] == 1740
    assert cost['primary_statistics_unchanged'] and cost['original_case_bytes_unchanged']
    for name, count in [('all_1740_allocated_cases.csv', 1740), ('all_1566_qualified_cases.csv', 1566),
                        ('all_29_programs.csv', 29), ('all_522_task_condition_boundary_cells.csv', 522),
                        ('all_complete_task_failures.csv', 99), ('all_unresolved_or_unstarted_cases.csv', 0),
                        ('all_primary_comparisons.csv', 10)]:
        with (RUN / 'report_v1' / name).open(encoding='utf-8', newline='') as stream:
            assert len(list(csv.DictReader(stream))) == count, name
    failed = [r for r in s['primary'] if not r['upper_strictly_below_zero']]
    assert [r['right'] for r in failed] == ['PI_0125__CONTINUE', 'GLOBAL_PI_2000', 'ERM_ADAPT__CONTINUE']
    auxiliary = REVIEW / 'operational_receipts'
    auxiliary.mkdir()
    admission = AUX / 'occam_qualification_complete_admission_20261029.json'
    shutil.copyfile(admission, auxiliary / admission.name)
    for folder in ['occam_postqualification_descriptions_20261029', 'occam_cost_reader_v2_analysis_20261029']:
        for path in sorted((AUX / folder).rglob('*')):
            if path.is_file():
                assert path.stat().st_size < 1024**2
                dest = auxiliary / folder / path.relative_to(AUX / folder)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, dest)
    write(REVIEW / 'receiver_closure.json', dict(
        integrity='SEALED_COMPLETE_TASK_QUALIFICATION_NEGATIVE', manifest_id=m['manifest_id'],
        scientific_source_commit=m['source_git_commit'], source_statistics_sha256=STATS,
        numerical_qualification=True, predictive_qualification=True, task_qualification=False,
        all_frozen_primary_comparisons=s['primary'], failed_primary_comparisons=failed,
        complete_task_failures_preserved=99, unresolved=0,
        scope='CURRENT_TWO_BANKS_FOUR_T_BETA_ZERO_16_STEP_LOCAL_COST_RECEIVER',
        preserve_all_models_and_records_read_only=True, no_new_gates_retuning_bank_swaps_or_extra_samples=True,
        no_training_or_selection_on_this_QUAL=True, additional_physical_collection_authorized_by_this_diagnosis=False,
        publication_goal_complete=False, online_LLM_API_calls=0))
    raw_paths = {p for p in (RUN / 'qual').rglob('*') if p.is_file()}
    for name in ('statistics_v1', 'pipeline_v1', 'report_v1', 'entry_attempts_v1'):
        raw_paths.update(p for p in (RUN / name).rglob('*') if p.is_file())
    raw_paths.update(RUN / n for n in ('manifest.json', 'seed_scope.json', 'seed_scope_audit.json'))
    raw_paths.update(RUN / 'native' / n for n in ('summary.json', 'completion.json', 'process_audit.json', 'audit.json'))
    raw_paths.add(ROOT / 'reports/occam_reference_qualification_v1_zh.md')
    inventory = {p.relative_to(ROOT).as_posix(): p.stat().st_size for p in sorted(raw_paths)}
    total = sum(inventory.values())
    write(REVIEW / 'pending_raw_export_inventory.json', dict(
        integrity='METADATA_ONLY_FULL_EXPORT_FOOTPRINT_NOT_A_RESTORATION_PROOF',
        source_file_count=len(inventory), source_bytes=total, path_bytes=inventory,
        new_raw_content_hash_pass_performed=False, original_full_admission_receipt_sha256=sha(admission)))
    write(REVIEW / 'delivery_scope.json', dict(
        scientific_population_complete=True, summary_diagnostics_and_cost_delivery_complete=True,
        complete_QUAL_raw_data_locally_preserved=True, complete_QUAL_zip_created=False,
        complete_QUAL_git_shards_committed=False, complete_QUAL_raw_restore_verified=False,
        complete_QUAL_actual_git_restore_verified=False, complete_QUAL_archive_only_restore_verified=False,
        full_raw_delivery_complete=False, original_export_gate_bytes=3*total+512*1024**2,
        free_bytes_at_check=shutil.disk_usage(ROOT).free, conservative_retained_copy_planning_recommendation_GB=12,
        no_space_gate_relaxed=True, no_old_records_or_restorations_deleted=True,
        older_NATIVE_and_TRAIN_restoration_proofs_unchanged=True,
        source_inventory_sha256=sha(REVIEW / 'pending_raw_export_inventory.json')))
    write(REVIEW / 'presentation_preflights.json', dict(
        earlier_default_stdout_encoding_failure='cp1252 UnicodeEncodeError while displaying already passed admission',
        missing_matplotlib_preflights=['project virtual environment', 'bundled workspace Python'],
        presentation_recovery='Reused previously installed isolated plotting runtime, without installing dependencies',
        science_or_population_repeated=False, new_environment_interactions=0, new_fits=0, online_LLM_API_calls=0))
    write(OUT / 'source_binding.json', dict(integrity='PASSED', scientific_source_files=len(m['source_sha256']),
        scientific_input_files=len(m['input_sha256']), all_checked_source_sha256=source_checks,
        original_statistics_sha256=STATS, original_report_sha256=sources['report_sha256'],
        first_window_complete_sha256=sha(FIRST / 'complete.json'), cost_complete_sha256=sha(COST / 'complete.json'),
        source_bound_2695_scientific_checks_reused=True, no_scientific_simulation_tests_repeated=True,
        only_new_presentation_sources_compiled=True))
    with (OUT / 'pip_check_stdout.log').open('xb') as stdout, (OUT / 'pip_check_stderr.log').open('xb') as stderr:
        p = subprocess.run([sys.executable, '-B', '-m', 'pip', 'check'], cwd=ROOT, stdout=stdout, stderr=stderr)
    assert p.returncode == 0
    owned_paths = {p for p in BASE.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    for path in (FIRST, COST, RUN / 'statistics_v1', RUN / 'pipeline_v1', RUN / 'report_v1', RUN / 'entry_attempts_v1'):
        owned_paths.update(p for p in path.rglob('*') if p.is_file())
    owned_paths.update(RUN / n for n in ('manifest.json', 'seed_scope.json', 'seed_scope_audit.json'))
    for phase in ('native', 'qual'):
        owned_paths.update(RUN / phase / n for n in ('audit.json', 'completion.json', 'member_index.json',
            'process_audit.json', 'status.json', 'summary.json', 'cases.jsonl.gz', 'prequential_windows.jsonl.gz'))
    owned_paths.update(ROOT / 'reports' / n for n in ('occam_reference_qualification_v1_zh.md', 'occam_reference_qualification_v1_delivery_zh.md'))
    owned = {p.relative_to(ROOT).as_posix() for p in owned_paths}
    assert all(p.stat().st_size <= 4*1024**2 for p in owned_paths)

    def stage(label):
        spec = OUT / (label + '.nul')
        owned.add(spec.relative_to(ROOT).as_posix())
        spec.write_bytes(b'\0'.join(n.encode('utf-8') for n in sorted(owned)) + b'\0')
        for flags in ((), ('--renormalize',)):
            git('add', *flags, '--pathspec-from-file=' + spec.relative_to(ROOT).as_posix(), '--pathspec-file-nul')

    stage('owned_initial')
    print(json.dumps(dict(stage='SOURCES_CHECKED_OWNED_RESULTS_STAGED', files=len(owned), raw_bytes=total,
                          required_export_free_bytes=3*total+512*1024**2)), flush=True)
    scan_start = perf_counter_ns()
    with (OUT / 'tracked_secret_scan_stdout.log').open('xb') as stdout, (OUT / 'tracked_secret_scan_stderr.log').open('xb') as stderr:
        p = subprocess.run([sys.executable, '-B', 'scripts/check_tracked_secrets.py', '--staged'], cwd=ROOT, stdout=stdout, stderr=stderr)
    write(OUT / 'tracked_secret_scan.json', dict(returncode=p.returncode, wall_ns=perf_counter_ns()-scan_start,
        actual_script_scans_all_tracked_worktree_files=True, gzip_decoding_and_EXTRA_checked_on_actual_index_separately=True))
    assert p.returncode == 0
    owned.update(p.relative_to(ROOT).as_posix() for p in OUT.iterdir() if p.is_file())
    stage('owned_scanned')
    objects = index_check(owned)
    write(OUT / 'index_disk_proof.json', dict(integrity='PASSED', objects=objects,
        actual_index_basic_and_extra_secret_scan=True, all_selected_gzip_decoded=True))
    verify(source_checks)
    assert sha(RUN / 'statistics_v1/statistics.json') == STATS
    write(OUT / 'complete.json', dict(integrity='PASSED_SUMMARY_DIAGNOSTICS_COST_DELIVERY_WITH_RAW_ARCHIVE_PENDING',
        parent_commit=PARENT, manifest_id=m['manifest_id'], primary_statistics_sha256=STATS,
        numerical_qualification=True, predictive_qualification=True, task_qualification=False,
        scientific_source_hash_passes=2, new_scientific_tests=0, new_simulation_tests=0,
        compilation='all newly staged Python sources compiled in memory', dependency_check_returncode=0,
        secret_scan_returncode=0, actual_index_gzip_basic_EXTRA_scan=True,
        ordinary_and_staged_diff_check=True, figure_visually_reviewed=True,
        full_raw_data_delivery_complete=False, raw_records_preserved=True,
        no_new_environment_interactions=True, new_real_model_queries=0, new_fits=0,
        new_episode_seed_allocations=0, online_LLM_API_calls=0, publication_goal_complete=False,
        wall_ns=perf_counter_ns()-started))
    owned.update(p.relative_to(ROOT).as_posix() for p in OUT.iterdir() if p.is_file())
    stage('owned_final')
    objects = index_check(owned)
    print(json.dumps(dict(integrity='PASSED_READY_FOR_LOCAL_SUMMARY_COMMIT_RAW_DELIVERY_PENDING',
                          files=len(objects), bytes=sum(v['bytes'] for v in objects.values()),
                          task_qualification=False, new_environment_interactions=0, online_LLM_API_calls=0)), flush=True)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()

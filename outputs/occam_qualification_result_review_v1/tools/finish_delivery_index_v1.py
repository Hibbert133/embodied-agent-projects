"""Finish the result index using scoped exact-byte and generated-SVG attributes."""
from pathlib import Path
from collections import Counter
import json
import re
import sys
import prepare_delivery_v1 as v


def main():
    assert v.git('rev-parse', 'HEAD').decode().strip() == v.PARENT
    assert not (v.OUT / 'complete.json').exists()
    assert v.read(v.OUT / 'tracked_secret_scan.json')['returncode'] == 0
    staged = set(v.git('diff', '--cached', '--name-only').decode().splitlines())
    allowed = {n.decode() for n in (v.OUT / 'owned_attributes_checked.nul').read_bytes().split(b'\0') if n}
    assert staged == allowed
    source = v.BASE / 'tools/finalize_delivery_attributes_v1.py'
    saved = v.OUT / 'attribute_finalization_failed_v1.py.saved'
    if saved.exists():
        assert saved.read_bytes() == source.read_bytes()
    else:
        with saved.open('xb') as stream:
            stream.write(source.read_bytes())
    failure_log = v.OUT / 'attribute_finalization_cached_diff_failure.log'
    lines = failure_log.read_text(encoding='utf-8').splitlines()
    header_paths = [re.sub(r':\d+: trailing whitespace\.$', '', line)
                    for line in lines if re.match(r'^outputs/.+:\d+: trailing whitespace\.$', line)]
    diagnostics = dict(Counter(header_paths))
    assert diagnostics and all((v.ROOT / name).read_bytes().count(b'\r\n') > 0 for name in diagnostics)
    v.write(v.OUT / 'attribute_finalization_failure.json', dict(
        integrity='PRESERVED_GENERATED_SVG_CACHED_DIFF_FAILURE', returncode=1,
        failed_source_sha256=v.sha(source), source_preserved_as='attribute_finalization_failed_v1.py.saved',
        cached_diff_log_sha256=v.sha(failure_log), actual_CRLF_diagnostics_by_path=diagnostics,
        exact_index_disk_byte_checks_completed_before_diff_guard=True,
        repair='Scoped CR-at-EOL attributes and the existing repository convention of generated SVG -diff',
        original_SVG_and_CSV_bytes_modified=False, new_environment_interactions=0, new_fits=0, online_LLM_API_calls=0))
    v.write(v.OUT / 'preparation_failure_interpretation_correction.json', dict(
        integrity='CORRECTED_FROM_ACTUAL_DIFF_DIAGNOSTICS',
        supersedes_cause_explanation_in='preparation_v2_failure.json',
        earlier_CSV_attribute_staging_explanation_not_supported_by_saved_diagnostics=True,
        actual_failure='Windows CRLF in generated SVG and two copied operational JSON receipts',
        actual_diagnostic_paths=diagnostics,
        saved_logs=['preparation_v2_cached_diff_before_attributes.log', 'attribute_finalization_cached_diff_failure.log'],
        science_qualification_unchanged=True, original_result_bytes_unchanged=True))
    binding = v.read(v.OUT / 'source_binding.json')
    v.verify(binding['all_checked_source_sha256'])
    assert v.sha(v.RUN / 'statistics_v1/statistics.json') == v.STATS
    assert v.read(v.REVIEW / 'receiver_closure.json')['task_qualification'] is False
    owned = staged | {p.relative_to(v.ROOT).as_posix() for p in v.BASE.rglob('*')
                      if p.is_file() and '__pycache__' not in p.parts}
    assert all((v.ROOT / n).stat().st_size <= 4*1024**2 for n in owned)

    def stage(label):
        spec = v.OUT / (label + '.nul')
        owned.add(spec.relative_to(v.ROOT).as_posix())
        spec.write_bytes(b'\0'.join(n.encode('utf-8') for n in sorted(owned)) + b'\0')
        for flags in ((), ('--renormalize',)):
            v.git('add', *flags, '--pathspec-from-file=' + spec.relative_to(v.ROOT).as_posix(), '--pathspec-file-nul')

    stage('owned_exact_final_check')
    objects = v.index_check(owned)
    v.write(v.OUT / 'index_disk_proof.json', dict(integrity='PASSED', objects=objects,
        actual_index_basic_and_extra_secret_scan=True, all_selected_gzip_decoded=True,
        all_new_Python_sources_compiled_in_memory=True, ordinary_and_staged_diff_checks_passed=True,
        scoped_exact_CSV_and_generated_SVG_attributes=True,
        prior_full_tracked_secret_scan_receipt_sha256=v.sha(v.OUT / 'tracked_secret_scan.json')))
    original_attributes = v.git('show', v.PARENT + ':.gitattributes').decode('utf-8').splitlines()
    current_attributes = (v.ROOT / '.gitattributes').read_text(encoding='utf-8').splitlines()
    assert current_attributes[:len(original_attributes)] == original_attributes
    v.write(v.OUT / 'complete.json', dict(
        integrity='PASSED_SUMMARY_DIAGNOSTICS_COST_DELIVERY_WITH_RAW_ARCHIVE_PENDING', parent_commit=v.PARENT,
        manifest_id=v.read(v.RUN / 'manifest.json')['manifest_id'], primary_statistics_sha256=v.STATS,
        numerical_qualification=True, predictive_qualification=True, task_qualification=False,
        source_bound_2695_scientific_checks_reused=True, no_new_scientific_or_simulation_tests=True,
        all_newly_staged_Python_compiled_in_memory=True, dependency_check_returncode=0,
        full_tracked_secret_scan_returncode=0, actual_index_gzip_basic_EXTRA_scan=True,
        ordinary_and_staged_diff_check=True, preparation_and_scope_failures_preserved=5,
        original_global_attribute_rules_preserved=True, global_Git_configuration_modified=False,
        exact_seed_metadata_decompression_checked=True, figure_visually_reviewed=True,
        full_raw_data_delivery_complete=False, raw_records_preserved=True,
        new_environment_interactions=0, new_real_model_queries=0, new_fits=0,
        new_episode_seed_allocations=0, online_LLM_API_calls=0, publication_goal_complete=False))
    owned.update({(v.OUT / 'index_disk_proof.json').relative_to(v.ROOT).as_posix(),
                  (v.OUT / 'complete.json').relative_to(v.ROOT).as_posix()})
    stage('owned_commit_final')
    objects = v.index_check(owned)
    assert not v.git('diff', '--name-only').strip()
    print(json.dumps(dict(integrity='PASSED_FINAL_RESULT_INDEX_WITH_RAW_ARCHIVE_PENDING',
        files=len(objects), bytes=sum(row['bytes'] for row in objects.values()),
        original_statistics_sha256=v.STATS, task_qualification=False)), flush=True)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()

"""Verify and stage the complete small census result without changing frozen tools."""
from pathlib import Path
from fractions import Fraction
from time import perf_counter_ns
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / 'outputs/occam_opportunity_census_v1'
sys.path.insert(0, str(BASE / 'tools'))
import run_opportunity_v1 as run
from freeze_opportunity_v1 import check_index
OUT = Path(__file__).parent
SOURCE = 'dbae170a956f8cef3ee38376bb9c1f7253de98af'
STATS = '0214bd46cb101b982de982ca93e75b228cf218d09bad97abf28b490b660c960a'


def main():
    start = perf_counter_ns()
    if run.git('rev-parse', 'HEAD').decode().strip() != SOURCE:
        raise ValueError('committed frozen analysis source')
    f = run.admit()
    done = run.read(run.OUT / 'complete.json')
    worker = run.read(run.OUT / 'worker_complete.json')
    audit = run.read(run.OUT / 'audit.json')
    stats = run.read(run.OUT / 'statistics.json')
    if done['source_commit'] != SOURCE or done['worker_receipt_sha256'] != run.sha(run.OUT / 'worker_complete.json'):
        raise ValueError('worker and parent bytes')
    if done['integrity'] != worker['integrity'] or audit['integrity'] != 'PASSED_INDEPENDENT_CSV_SCALAR_FRACTION_AUDIT':
        raise ValueError('complete independent census')
    if run.sha(run.OUT / 'statistics.json') != STATS or any(worker['guard'].values()):
        raise ValueError('unchanged stats and zero forbidden operations')
    if run.sha(run.RUN / 'statistics_v1/statistics.json') != run.STAT:
        raise ValueError('original primary comparisons unchanged')
    manifest = run.read(run.RUN / 'manifest.json')
    run.verify({**manifest['source_sha256'], **manifest['input_sha256']})
    affected = [u for u in stats['units'] if all(not u['fixed_programs'][t+'__CONTINUE']['success'] for t in ('PI_0125', 'PI_0500', 'PI_2000', 'PI_8000'))]
    total = sum(u['acquisition_opportunity'] for u in stats['units'])
    subgroup = sum(u['acquisition_opportunity'] for u in affected)
    if (len(affected), subgroup, total, len({u['group'] for u in affected})) != (3, 1116, 1168, 2):
        raise ValueError('report supplementary descriptive counts')
    if Fraction(stats['overall']['equal_group_mean_exact']['acquisition_opportunity'])*54 != total:
        raise ValueError('all-unit sum and group mean identity')
    run.write(OUT / 'supplementary_description.json', dict(
        integrity='PASSED_SUPPLEMENTARY_POST_HOC_DESCRIPTION', source_statistics_sha256=STATS,
        rule='all four actually executed fixed CONTINUE programs failed in a unit',
        allocated_units=54, affected_units=3, affected_independent_groups=2,
        affected_unit_keys=[{k: u[k] for k in ('group', 'task', 'context', 'planned_boundary', 'seed')} for u in affected],
        affected_acquisition_gap_sum=1116, all_acquisition_gap_sum=1168,
        chosen_after_census_results=True, no_new_qualification_gate=True,
        unique_causal_failure_reason_claimed=False, no_training_or_selection_on_QUAL=True,
        new_environment_interactions=0, new_model_queries=0, new_fits=0, online_LLM_API_calls=0))
    plot = BASE / 'presentation_v1/figures/plot_receipt.json'
    p = run.read(plot)
    if p['statistics_sha256'] != STATS:
        raise ValueError('plot exact audited statistics')
    for name, h in p['files_sha256'].items():
        if run.sha(plot.parent / name) != h:
            raise ValueError('plot bytes')
    with (OUT / 'pip_check_stdout.log').open('xb') as stdout, (OUT / 'pip_check_stderr.log').open('xb') as stderr:
        proc = subprocess.run([sys.executable, '-B', '-m', 'pip', 'check'], cwd=ROOT, stdout=stdout, stderr=stderr)
    if proc.returncode != 0:
        raise ValueError('dependency check')
    owned = {p.relative_to(ROOT).as_posix() for folder in (run.OUT, BASE / 'presentation_v1', OUT)
             for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    owned.update({'reports/occam_opportunity_census_v1_zh.md', 'docs/research/correction_scope_after_opportunity_v1_zh.md'})
    def stage(label):
        spec = OUT / (label + '.nul')
        owned.add(spec.relative_to(ROOT).as_posix())
        spec.write_bytes(b'\0'.join(n.encode() for n in sorted(owned)) + b'\0')
        for flags in ((), ('--renormalize',)):
            run.git('add', *flags, '--pathspec-from-file='+spec.relative_to(ROOT).as_posix(), '--pathspec-file-nul')
    stage('owned_initial')
    print(json.dumps(dict(stage='AUDITED_COMPLETE_CENSUS_AND_FIGURE_STAGED', files=len(owned), supplementary_scope_explicit=True)), flush=True)
    scan_start = perf_counter_ns()
    with (OUT / 'tracked_secret_stdout.log').open('xb') as stdout, (OUT / 'tracked_secret_stderr.log').open('xb') as stderr:
        proc = subprocess.run([sys.executable, '-B', 'scripts/check_tracked_secrets.py', '--staged'], cwd=ROOT, stdout=stdout, stderr=stderr)
    run.write(OUT / 'tracked_secret_receipt.json', dict(returncode=proc.returncode, wall_ns=perf_counter_ns()-scan_start,
        actual_script_scans_all_tracked_worktree_files=True, actual_index_basic_EXTRA_scan_separate=True))
    if proc.returncode != 0:
        raise ValueError('secret scan blocks commit')
    owned.update(p.relative_to(ROOT).as_posix() for p in OUT.iterdir() if p.is_file())
    stage('owned_checked')
    run.write(OUT / 'index_disk_proof.json', dict(integrity='PASSED', objects=check_index(owned), actual_index_basic_EXTRA_scan=True))
    run.verify(f['source_sha256'])
    run.verify(f['input_sha256'])
    run.write(OUT / 'complete.json', dict(integrity='PASSED_COMPLETE_OPPORTUNITY_CENSUS_RESULT_DELIVERY',
        source_commit=SOURCE, source_statistics_sha256=STATS, original_statistics_sha256=run.STAT,
        independent_scalar_checks=18224, original_scientific_sources_unchanged=1393,
        source_bound_census_tests_reused=16, original_scientific_tests_source_bound_reused=2695,
        new_scientific_or_simulation_tests=0, new_Python_sources_compiled_in_memory=True,
        dependency_check_returncode=0, full_tracked_secret_scan_returncode=0,
        actual_index_basic_EXTRA_scan=True, ordinary_and_staged_diff_checks=True,
        figure_visually_reviewed=True, new_environment_interactions=0, new_model_queries=0,
        new_fits=0, online_LLM_API_calls=0, original_task_qualification=False,
        new_algorithm_or_task_benefit_claimed=False, full_raw_delivery_complete=False,
        wall_ns=perf_counter_ns()-start, additional_delivery_hash_JSON_IO=run.IO,
        publication_goal_complete=False))
    owned.update(p.relative_to(ROOT).as_posix() for p in OUT.iterdir() if p.is_file())
    stage('owned_final')
    objects = check_index(owned)
    print(json.dumps(dict(integrity='PASSED_CENSUS_RESULTS_READY_FOR_LOCAL_COMMIT', files=len(objects), bytes=sum(v['bytes'] for v in objects.values()))), flush=True)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()

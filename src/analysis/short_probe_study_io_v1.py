"""Exact-byte frozen inputs and source checks; no new environment execution."""
import hashlib
import json
from pathlib import Path
import subprocess
from src.analysis.capsule_record_json_v2 import normalize
from src.analysis.short_probe_study_v1 import METHODS, TASKS, population
from src.probe.cache_acquisition_evidence_v1 import digest

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT/'configs/short_probe_reference/development_v1.json'
PROTOCOL = 'docs/protocols/short_probe_reference_development_v1.md'
IDENTITY = ('experiment_run_id', 'manifest_id', 'source_git_commit')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, value, *, exclusive=True):
    with Path(path).open('x' if exclusive else 'w', encoding='utf-8', newline='\n') as f:
        json.dump(normalize(value), f, ensure_ascii=False, indent=2, allow_nan=False);f.write('\n')


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def clean():
    if git('status', '--porcelain', '--untracked-files=no'):
        raise ValueError('commit clean tracked implementation before preparing or executing')
    if git('ls-files', '--others', '--exclude-standard', 'src', 'scripts', 'tests',
           'configs/short_probe_reference', PROTOCOL, 'reports/short_probe_reference/.gitattributes'):
        raise ValueError('new study source/config/protocol must be tracked before freeze')


def validate(c):
    fixed = {'protocol_id':'short_probe_reference_development_v1', 'methods':list(METHODS), 'tasks':list(TASKS),
        'logical_total_steps':500, 'noise_std':.05, 'noise_namespace':47001, 'bootstrap_samples':10000,
        'bootstrap_seed':20261022, 'new_api_calls':0, 'new_nominal_training':0, 'new_selector_fits':0, 'policy_updates':0,
        'output_root':'outputs/short_probe_reference/development_v1'}
    if any(c.get(k) != v for k, v in fixed.items()):
        raise ValueError('registered standard-reference scope changed')
    values = {'smoke':(1,9,63,21200,21208,[21209,21399],31500,63,1800000),
              'main':(54,648,4536,20200,20847,[20848,21199],2268000,4536,128000000)}
    keys = ('streams','units','executions','seed_start','seed_end','reserved','maximum_environment_steps','maximum_controlled_resets','maximum_simulation_frames')
    for phase, expected in values.items():
        if set(c[phase]) != set(keys) or tuple(c[phase][k] for k in keys) != expected:
            raise ValueError('registered population or budget changed')


def sources(c):
    from scripts import run_paired_probe_effects_v1 as previous
    prior, models = previous.load(ROOT/c['source_manifest'])
    for key in ('source_completion','source_record_audit','source_numeric_audit','nominal_designs','nominal_models'):
        if sha(ROOT/c[key]) != c[key+'_sha256']:
            raise ValueError('bound prior artifact changed: '+key)
    done = read(ROOT/c['source_completion']);record = read(ROOT/c['source_record_audit']);numeric = read(ROOT/c['source_numeric_audit'])
    if any(x[k] != prior[k] for x in (done, record, numeric) for k in IDENTITY):
        raise ValueError('prior completed study identity changed')
    if done['status'] != 'COMPLETED_FOR_REVIEW' or done['failure'] is not None or len(done['steps']) != 6 or any(v['returncode'] for v in done['steps']) or record['integrity'] != 'PASSED' or numeric['integrity'] != 'PASSED':
        raise ValueError('prior completed and audited phase required')
    old_folder = (ROOT/c['source_manifest']).parent
    if sha(old_folder/'main/summary.json') != record['summary_sha256'] or numeric['summary_sha256'] != record['summary_sha256']:
        raise ValueError('prior audited summary changed')
    design = read(ROOT/c['nominal_designs']);saved_models = read(ROOT/c['nominal_models'])['joint']
    if design['status'] != 'NOMINAL_PROGRAMS_PREPARED_NOT_PHYSICAL_QUALIFICATION' or design['failure'] is not None or design['candidate_rows_evaluated'] != 432 or design['candidate_library_enumerations_completed'] != 3:
        raise ValueError('complete saved nominal design preparation required')
    if sha(ROOT/design['design_source_path']) != design['design_source_sha256'] or design['nominal_source_sha256'] != c['nominal_models_sha256']:
        raise ValueError('saved nominal design source changed')
    if set(design['designs']) != set(TASKS) or digest(models) != digest(saved_models):
        raise ValueError('foreign nominal response source')
    for task in TASKS:
        d = design['designs'][task]
        if digest(models[task]) != design['nominal_model_payload_sha256'][task] or digest(d) != design['design_evidence_sha256'][task] or d['selected_candidate_id'] is None:
            raise ValueError('saved task design/model binding changed')
    qualified = read(ROOT/prior['config']['restore_qualification_manifest'])
    return prior, models, design['designs'], qualified


def load(path):
    m = read(path);validate(m['config'])
    if digest({k:v for k,v in m.items() if k != 'manifest_id'}) != m['manifest_id'] or any(sha(ROOT/p) != h for p,h in m['input_sha256'].items()):
        raise ValueError('frozen manifest or input changed')
    prior, models, designs, qualified = sources(m['config'])
    if prior['manifest_id'] != m['prior_manifest_id'] or m['population_oracle'] != {p:population(p) for p in ('SMOKE','MAIN')}:
        raise ValueError('frozen population/source differs')
    if any(m[k] != prior[k] for k in ('library_source_sha256','native_library_sha256','policy_sha256')) or sha(Path(qualified['native_library_path'])) != m['native_library_sha256']:
        raise ValueError('qualified runtime changed')
    return m, models, designs

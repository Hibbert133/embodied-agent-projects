"""Independent frozen continuation of previously unspent CAL/QUAL assignments.

The failed v1 run remains terminal. No training, parameter change or new seed
selection is available through this entry. Existing reservation ownership and
absence of any earlier CAL/QUAL execution are checked separately from census.
"""
from pathlib import Path
from copy import deepcopy
from datetime import datetime,timezone
import shutil
from src.analysis import graybox_response_io_v1 as prior
io=prior.io;ROOT=prior.ROOT;BASE=ROOT/'outputs/graybox_qualification';OUTPUT=BASE/'qualification_v2';VALIDATION=BASE/'freeze_validation_v2'
CONFIG=ROOT/'configs/movement_task/graybox_qualification_v2.json';PROTOCOL=ROOT/'docs/protocols/graybox_qualification_v2_zh.md';SEEDS=ROOT/'docs/protocols/graybox_qualification_seeds_v2.json'
SOURCE=ROOT/'outputs/graybox_response/qualification_v1/graybox_response_20261027T174316Z_cf2712de2ed7'
MODEL_SHA='101030e545e92232b1855dc59eb77617025e56353786e4c10c2ae7922203927a'
SPLITS=('CAL','QUAL');KEYS=prior.KEYS;ROLES=prior.ROLES;IDENTITY=prior.IDENTITY;Q_CHOICES=prior.Q_CHOICES
SOURCE_NAMES=('manifest.json','training/models.json','training/completion.json','training/public_nominal_traces.json','training/public_train_families.json',
    'training_audit_repair_v2.json','software/audit.json','nominal/audit.json','train/audit.json','pipeline_control/training_audit_failure.json','pipeline_control/process_receipt.json',
    'software/completion.json','nominal/completion.json','train/completion.json','software/summary.json','nominal/summary.json','train/summary.json')
IMPORTS=('training/models.json','training/completion.json','training/public_nominal_traces.json','training/public_train_families.json','nominal/audit.json','train/audit.json')

def population(split):
    io.require(split in SPLITS,'supplement has only unspent CAL/QUAL');return prior.population(split)
def validate_spec(v):
    io.require(v.get('split') in SPLITS,'no repeated SOFTWARE/NOMINAL/TRAIN');prior.validate_spec(v)
def limits(split):population(split);return prior.limits(split)
family_key=prior.family_key;initial_fault=prior.initial_fault;destination=prior.destination;noise=prior.noise;packets=prior.packets;case_cap=prior.case_cap

def config():
    old=prior.config();ll={s:limits(s) for s in SPLITS}
    return dict(protocol='GRAYBOX_QUALIFICATION_SUPPLEMENT_V2',source_run=SOURCE.relative_to(ROOT).as_posix(),source_manifest_id='2f91934d109310c2781250d275c56e1dc3bae97d8b34beee3f6e5af1c088b7a2',
        fixed_model_sha256=MODEL_SHA,existing_assignments_unchanged=True,old_failure_preserved=True,populations={s:population(s) for s in SPLITS},limits=ll,
        combined_limits={k:sum(v[k] for v in ll.values()) for k in next(iter(ll.values()))},
        scientific_rules={k:deepcopy(old[k]) for k in ('noise_sigma','actor','models','cal_candidates','q_choices','selected_model','calibration','qualification')},
        new_primary_training=0,new_nominal_grid_fits=0,new_C4_C8_fits=0,new_episode_seed_allocations=0,online_LLM_API_calls=0,
        imported_source_costs_separate=dict(executions=459,control_steps=31017,all_resets=23409,physical_frames=11859585,
            main_ridge_solves=9,main_nominal_grid_passes=27,independent_training_lstsq_including_failed_and_supplemental=18,independent_nominal_grid_passes=54),
        full_task_tail_evaluated=False,new_model_used_for_control=False,publication_goal_complete=False)

def registry():
    return dict(protocol='GRAYBOX_QUALIFICATION_SUPPLEMENT_V2',existing_reservation=prior.SEEDS.relative_to(ROOT).as_posix(),
        source_manifest=(SOURCE/'manifest.json').relative_to(ROOT).as_posix(),reservation_owner='GRAYBOX_RESPONSE_V1_SAME_UNSPENT_ASSIGNMENTS',
        cal_episode_seed_range=[113200,113208],qual_episode_seed_range=[113300,113326],new_seed_allocation=False,
        changed_operator_namespace_base=2026103000,noise_namespace_base=2026103010,packet_namespace_base=2026103020,bootstrap_seed=2026103060)

def require_unspent(root):
    root=Path(root)
    io.require(not (root/'model_lock.json').exists(),'no earlier process choice')
    for split in SPLITS:io.require(not (root/split.lower()).exists() and not any((root/'pipeline_control').glob(split+'*')),'no previous CAL/QUAL attempt or outcome')

def source_contract():
    old=prior.checked(SOURCE/'manifest.json');io.require(old['manifest_id']==config()['source_manifest_id'],'same frozen source population')
    io.require(io.sha(SOURCE/'training/models.json')==MODEL_SHA,'unchanged trained model, no refit')
    model=io.read(SOURCE/'training/models.json');io.require(model['bank']['selected_q_index'] is None,'no process choice before CAL')
    failure=io.read(SOURCE/'pipeline_control/training_audit_failure.json')
    io.require(failure['integrity']=='FAILED' and "KeyError: 'operation_counts'" in failure['exception'],'original technical failure retained')
    io.require(io.read(SOURCE/'pipeline_control/process_receipt.json')['returncode']==1 and not (SOURCE/'pipeline_control/completion.json').exists(),'source pipeline terminal failed')
    io.require(not (SOURCE/'training/audit.json').exists(),'supplement never impersonates original audit')
    require_unspent(SOURCE)
    repair=io.read(SOURCE/'training_audit_repair_v2.json')
    io.require(repair['integrity']=='PASSED' and repair['models_sha256']==MODEL_SHA and repair['original_failed_audit_preserved'] is True,'explicit successful supplemental audit')
    for n,h in repair['source_sha256'].items():io.require(io.sha(SOURCE/'training'/n)==h,'unchanged reconstructed training source '+n)
    totals=dict(executions=0,control_steps=0,all_resets=0,physical_frames=0)
    for split in ('SOFTWARE','NOMINAL','TRAIN'):
        folder=SOURCE/split.lower();done=io.read(folder/'completion.json');audit=io.read(folder/'audit.json');summary=io.read(folder/'summary.json')
        io.require(done['status']=='COLLECTED_FOR_INDEPENDENT_AUDIT' and audit['integrity']=='PASSED' and done['artifact_sha256']==audit['artifact_sha256'],'audited source '+split)
        for n,h in done['artifact_sha256'].items():io.require(io.sha(folder/n)==h,'unchanged original raw '+split+'/'+n)
        cases=list(io.rows(folder/'cases.jsonl.gz'));io.require(len(cases)==len(prior.population(split)) and [dict((k,c[k]) for k in KEYS) for c in cases]==prior.population(split),'source actual assignments, not unstarted presentation rows')
        totals['executions']+=len(cases);totals['control_steps']+=summary['control_steps'];totals['all_resets']+=summary['lifecycle']['counts']['reset_attempts'];totals['physical_frames']+=summary['lifecycle']['counts']['simulation_frames_completed']
    io.require(totals=={k:config()['imported_source_costs_separate'][k] for k in totals},'original costs retained')
    io.require(io.read(SOURCE/'software/audit.json')['software_contract']=='PASSED' and io.read(SOURCE/'nominal/audit.json')['nominal_contract']=='PASSED','existing source contracts')
    return dict(integrity='PASSED_UNSPENT_EXISTING_RESERVATION',source_manifest_id=old['manifest_id'],model_sha256=MODEL_SHA,actual_source_costs=totals,
        no_original_CAL_or_QUAL_attempt=True,original_failure_preserved=True,source_sha256={n:io.sha(SOURCE/n) for n in SOURCE_NAMES})

def seed_scope():
    from src.analysis.episode_seed_inventory_v2 import discover,scan,verify_unchanged
    from src.analysis.episode_seed_inventory_audit_v2 import audit
    owners={p.resolve() for p in (prior.CONFIG,prior.PROTOCOL,prior.SEEDS,SOURCE/'manifest.json',CONFIG,PROTOCOL,SEEDS)}
    paths=discover(ROOT);result=scan(ROOT,113000,113999,paths);verify_unchanged(ROOT,result);independent=audit(ROOT,result)
    owner_names={p.relative_to(ROOT).as_posix() for p in owners};validate_owner_inventory(result,owner_names)
    io.require({p.relative_to(ROOT).as_posix() for p in paths}<=set(result['sources']),'complete external ownership discovery')
    return dict(integrity='PASSED_NO_EXTERNAL_OWNER_CONFLICT',inventory=result,independent_audit=independent,
        exact_registered_owner_conflict_exceptions={p.relative_to(ROOT).as_posix():io.sha(p) for p in sorted(owners)},all_owner_sources_remain_in_census=True,
        existing_reservation_not_new_unreserved_seeds=True,no_new_seed_allocations=True,unused_execution_proof_separate=True)

def validate_owner_inventory(result,owners):
    io.require(result['query']==dict(lower=113000,upper=113999) and not result['blocking_issues'],'exact query and no undecidable seed metadata')
    io.require(set(owners)<=set(result['sources']),'all seven registered owners retained in complete census')
    io.require(all(r['source'] in owners for r in result['blockers']),'unapproved external seed reservation or use')

def checked(path):
    path=Path(path).resolve();m=io.read(path);value=dict(m);mid=value.pop('manifest_id')
    io.require(path.parent.parent==OUTPUT.resolve() and mid==io.digest(value) and m['config']==config() and io.read(CONFIG)==config() and io.read(SEEDS)==registry(),'immutable supplement manifest/config/registry')
    for n,h in {**m['source_sha256'],**m['input_sha256']}.items():io.require(io.sha(ROOT/n)==h,'immutable supplement input '+n)
    for n,h in m['import_sha256'].items():io.require(io.sha(path.parent/n)==h,'unchanged imported source '+n)
    return m

def phase_model(path,split):
    population(split);root=Path(path).parent;bank=deepcopy(io.read(root/'training/models.json')['bank'])
    if split=='QUAL':bank['selected_q_index']=io.read(root/'model_lock.json')['selected_q_index']
    return bank,io.digest(bank)

def phase_gate(path,split):
    m=checked(path);population(split);root=Path(path).parent
    audit=io.read(root/'training/audit.json');io.require(audit['integrity']=='PASSED' and audit['models_sha256']==MODEL_SHA and audit['imported_supplemental_audit'] is True,'explicit imported successful repair')
    if split=='QUAL':
        lock=io.read(root/'model_lock.json');io.require(lock['status']=='FROZEN_BEFORE_QUAL','CAL lock before QUAL')
        for n,h in lock['artifact_sha256'].items():io.require(io.sha(root/n)==h,'unchanged locked artifact '+n)
    return m

def prepare(sources):
    frozen=io.read(VALIDATION/'complete.json');io.require(frozen['integrity']=='PASSED' and not io.git('status','--porcelain','--untracked-files=no'),'clean committed supplementary freeze')
    io.require(not list(OUTPUT.glob('*/manifest.json')) and io.read(CONFIG)==config() and io.read(SEEDS)==registry(),'one supplementary population only')
    io.require(shutil.disk_usage(ROOT).free>=4*1024**3,'four GiB before supplementary sampling')
    tracked=set(io.git('ls-files').splitlines())
    for n,h in frozen['source_sha256'].items():io.require(n in tracked and io.sha(ROOT/n)==h,'checked tracked supplement source '+n)
    contract=source_contract();scope=seed_scope();head=io.git('rev-parse','HEAD');runtime=ROOT/'outputs/correction_scope/freeze_validation_v1/runtime_lock.json'
    from src.analysis.response_action_io_v1 import verify_runtime
    verify_runtime(io.read(runtime));out=OUTPUT/('graybox_qualification_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+head[:12]);out.mkdir(parents=True,exist_ok=False)
    imported={}
    for n in IMPORTS:
        target=out/n;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((SOURCE/n).read_bytes());imported[n]=io.sha(target)
    audit=io.read(SOURCE/'training_audit_repair_v2.json');audit.update(imported_supplemental_audit=True,original_audit_still_failed=True,source_path=(SOURCE/'training_audit_repair_v2.json').relative_to(ROOT).as_posix())
    io.write(out/'training/audit.json',audit);imported['training/audit.json']=io.sha(out/'training/audit.json')
    m=dict(experiment_run_id=out.name,source_git_commit=head,config=config(),source_sha256={n:io.sha(ROOT/n) for n in sources},
        input_sha256={**{(SOURCE/n).relative_to(ROOT).as_posix():h for n,h in contract['source_sha256'].items()},runtime.relative_to(ROOT).as_posix():io.sha(runtime)},
        import_sha256=imported,imported_training_not_new_fitting=True,publication_goal_complete=False)
    m['manifest_id']=io.digest(m);io.write(out/'manifest.json',m);io.write(out/'existing_source_contract.json',contract);io.write(out/'seed_scope.json',scope);return out/'manifest.json'

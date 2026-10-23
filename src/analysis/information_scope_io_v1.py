"""Source-bound mathematical study; no physical data allocation or promotion."""
from pathlib import Path
from datetime import datetime,timezone
from src.analysis import response_qualification_io_v1 as io
from src.analysis import latent_response_diagnosis_io_v1 as previous

ROOT=io.ROOT;BASE=ROOT/'outputs/information_scope';OUTPUT=BASE/'reference_v1';VALIDATION=BASE/'validation_v1'
CONFIG=ROOT/'configs/movement_task/information_scope_reference_v1.json'
PROTOCOL=ROOT/'docs/protocols/information_scope_reference_v1_zh.md'
PREVIOUS_MANIFEST=previous.OUTPUT/'latent_response_diagnosis_20261022T210319Z_32b47031cb85/manifest.json'
READING=Path('C:/Users/Administrator/Documents/ChatGPT/robotic agent/research_sources/acquisition_mechanism_20261023_v1')
OWN=('src/analysis/information_scope_reference_v1.py','src/analysis/information_scope_io_v1.py',
     'src/analysis/information_scope_audit_v1.py','scripts/run_information_scope_v1.py',
     'scripts/report_information_scope_v1.py','scripts/plot_information_scope_v1.py',
     'tests/test_information_scope_v1.py')


def config():
    return dict(protocol='INFORMATION_SCOPE_FINITE_REFERENCE_V1',
        classification='CONSTRUCTED_MATHEMATICAL_COUNTEREXAMPLES_AND_STANDARD_DECISION_REFERENCES_NOT_NEW_ROBOT_ALGORITHM',
        mathematical_construction_known_before_freeze=True,statistically_independent_validation=False,
        family_A=dict(weights=[['1/4','1/2','1/4'],['1/3','1/3','1/3'],['2/5','1/5','2/5']],
                      symmetric_posterior_low=['1/10','1/4','2/5'],full_binary_surjective_channels=True,records=162),
        family_B='Same three predictive marginals; all nine pairs of symmetric posteriors; six channels;162 positive controls',
        probability_records=324,unique_probability_problems=270,duplicate_rows_deliberate=54,
        all_joint_entries_strictly_positive=True,common_prior=['1/2','1/2'],
        numeric_KL_tolerance=1e-12,numeric_decision_tie_tolerance=1e-10,
        witness=dict(P_weights=['1/4','1/2','1/4'],Q_weights=['2/5','1/5','2/5'],posterior=['1/10','1/2','9/10'],channel=[0,0,1]),
        noninformative_witness=dict(P=[['1/4','1/4'],['1/4','1/4']],Q=[['3/8','1/8'],['3/8','1/8']]),
        decision_grid=dict(direction=['FORWARD','REVERSE'],fine_cost=[0,4,8,12],coarse_cost=[0,1,4],fine_shift=[-5,0,20],coarse_shift=[-5,0,20],problems=216,
            cutoff=500,interpretation='INTEGER_SYNTHETIC_STEP_EQUIVALENTS_NOT_PHYSICAL_CONTROL_STEPS',
            tails=['KEEP','ADOPT_025','ADOPT_050','ADOPT_100','STOP'],
            durations=[[120,109,98,75],[120,95,70,20]],failure_theta0=['0','1/20','1/10','1/5'],failure_theta1='0',
            failures_pay_cutoff_once=True,acquisition_changes_success_duration=True,post_rejection_keeps_actual_shift=True),
        reference_methods=['WORKING_BAYES','ORACLE_JOINT_IMPLEMENTED','ORACLE_IDEAL_EXECUTED','OPTIMISTIC_POST_MISMATCH',
             'WORKING_IGNORE_STATE','WORKING_IGNORE_COST','DIRECT_KEEP','DIRECT_025','DIRECT_050','DIRECT_100','ALWAYS_FINE_WORKING','ALWAYS_COARSE_WORKING'],
        saved_policy_records=2592,policies_saved_before_true_evaluation=True,oracle_references_explicitly_privileged=True,
        inference_or_true_law_not_fitted_or_available_to_robot=True,
        no_physical_model_control_probability_safety_or_paper_promotion=True,
        new_environment_creations=0,new_resets=0,new_control_steps=0,new_physical_frames=0,new_fits=0,
        new_optimizer_updates=0,new_policy_queries=0,new_online_LLM_API_calls=0,new_task_seeds=0,
        publication_goal_complete=False)


def inputs():
    prior=previous.checked(PREVIOUS_MANIFEST)
    result={PREVIOUS_MANIFEST.relative_to(ROOT).as_posix():io.sha(PREVIOUS_MANIFEST)}
    for name in ('analysis/completion.json','analysis/audit.json','report_receipt.json'):
        p=PREVIOUS_MANIFEST.parent/name;result[p.relative_to(ROOT).as_posix()]=io.sha(p)
    for name in ('reports/latent_response_diagnosis_v1_zh.md','docs/research/latent_response_diagnosis_followup_v1_zh.md',
                 'reports/task_value_learner_diagnosis_v1.md','docs/research/response_training_controls_novelty_audit_v1_zh.md'):
        result[name]=io.sha(ROOT/name)
    return result


def checked(path):
    path=Path(path).resolve();m=io.read(path);body=dict(m);mid=body.pop('manifest_id')
    io.require(path.parent.parent==OUTPUT.resolve() and io.digest(body)==mid and m['config']==config(),'owned finite-reference manifest')
    for name,h in m['source_sha256'].items():io.require(io.sha(ROOT/name)==h,'frozen finite-reference source '+name)
    for name,h in m['input_sha256'].items():io.require(io.sha(ROOT/name)==h,'old result source changed')
    for name,h in m['local_document_sha256'].items():io.require(io.sha(READING/name)==h,'primary PDF/text snapshot changed')
    return m


def prepare():
    qa=io.read(VALIDATION/'complete.json')
    io.require(qa['integrity']=='PASSED' and not io.git('status','--porcelain','--untracked-files=no'),'clean passed mathematical freeze')
    io.require(not list(OUTPUT.glob('*/manifest.json')) and io.read(CONFIG)==config(),'one constructed census')
    for name,h in qa['source_sha256'].items():io.require(io.sha(ROOT/name)==h and io.git('ls-files','--error-unmatch',name)==name,'committed tested source')
    head=io.git('rev-parse','HEAD');m=dict(experiment_run_id='information_scope_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+head[:12],
        source_git_commit=head,source_sha256=qa['source_sha256'],input_sha256=inputs(),config=config(),
        local_document_sha256={p.name:io.sha(p) for p in READING.iterdir() if p.is_file()},
        last_goal_turn_classification='PROGRESS_VERIFIED_LOCAL_DIAGNOSIS_DELIVERY_ff7b6b4',publication_goal_complete=False)
    m['manifest_id']=io.digest(m);out=OUTPUT/m['experiment_run_id'];out.mkdir(parents=True,exist_ok=False);io.write(out/'manifest.json',m)
    return out/'manifest.json'

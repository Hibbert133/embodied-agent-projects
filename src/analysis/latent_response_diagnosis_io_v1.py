"""Read-only forensic protocol; no new episode allocation, learning or promotion."""
from pathlib import Path
from datetime import datetime,timezone
from src.analysis import response_qualification_io_v1 as io
from src.analysis import latent_response_io_v1 as latent,acquisition_reference_io_v1 as reference
ROOT=io.ROOT;BASE=ROOT/'outputs/latent_response_diagnosis';OUTPUT=BASE/'analysis_v1';VALIDATION=BASE/'validation_v1'
CONFIG=ROOT/'configs/movement_task/latent_response_diagnosis_v1.json';PROTOCOL=ROOT/'docs/protocols/latent_response_diagnosis_v1_zh.md'
LATENT=latent.OUTPUT/'latent_response_20261022T190735Z_e4410b8985e3'
REFERENCE=reference.OUTPUT/'acquisition_reference_20261022T133659Z_dc7058a8f6d5'
METHODS=('SS_SENT','SS_NO_SENT','SS_CURRENT_SENT','DIRECT_MLP_H8','DIRECT_RIDGE_H8','PERSIST_ZERO','HISTORY_LINEAR10','QUADRATIC_STATE20')
NEURAL=METHODS[:4];CHECKPOINTS=(1000,2000,3000,4000,5000)
MENU=('RAW_CONTINUE','FIXED_PD_KEEP','FIXED_PID_KEEP','LOCAL_PD_KEEP','LOCAL_PID_KEEP',
    'LOCAL_PID_REFERENCE_RESET','LOCAL_PID_REFERENCE_CARRY','LOCAL_PID_REFERENCE_RESET_NO_PROBE')
ADOPTION_MENU=('RAW_CONTINUE','LOCAL_PID_KEEP','LOCAL_PID_REFERENCE_RESET','LOCAL_PID_REFERENCE_CARRY')
REFERENCE_BRANCHES=('LOCAL_PID_REFERENCE_RESET','LOCAL_PID_REFERENCE_CARRY')
REGIMES=('ALL_WINDOWS','ENTRY_ONLY','START_01_08','START_09_16','START_17_24')
OWN=('src/analysis/latent_response_diagnosis_io_v1.py','src/analysis/latent_response_diagnosis_math_v1.py',
    'src/analysis/latent_response_diagnosis_reader_v1.py','src/analysis/latent_response_diagnosis_v1.py',
    'src/analysis/latent_response_diagnosis_audit_v1.py','scripts/run_latent_response_diagnosis_v1.py',
    'scripts/report_latent_response_diagnosis_v1.py','scripts/plot_latent_response_diagnosis_v1.py','tests/test_latent_response_diagnosis_v1.py')


def config():
    return {'protocol':'LATENT_RESPONSE_FAILURE_DIAGNOSIS_V1','classification':'POST_HOC_DESCRIPTIVE_ONLY',
        'source_populations':{'latent':{'executions':792,'steps':59268,'groups_by_split':{'SOFTWARE':3,'TRAIN':36,'CAL':9,'QUAL':18}},
            'reference_QUAL':{'executions':540,'steps':65854,'independent_groups':9,'paired_units':54}},
        'latent_training_queries':4186,'training_available_trajectories':168,'saved_CAL_QUAL_query_count':428,
        'methods':list(METHODS),'TRAIN_checkpoints_only':list(CHECKPOINTS),'no_checkpoint_selection':True,
        'CAL_QUAL':'SAVED_ENTRY_FORECASTS_ONLY_NO_CHECKPOINT_REEVALUATION','TRAIN_final_model_query_forwards':33488,
        'TRAIN_earlier_checkpoint_query_forwards':66976,'each_pass_maximum_new_model_query_forwards':100464,
        'expected_prediction_rows_each_pass':103888,'regimes':list(REGIMES),
        'training_objective':'TRAJECTORY_EQUAL_THEN_WINDOW_EQUAL_MEAN_ACTUAL_MASKED_XY_SQUARED_CUMULATIVE_ERROR',
        'cohort_descriptions':'WITHIN_TRAJECTORY_THEN_WITHIN_INDEPENDENT_GROUP_THEN_EQUAL_GROUPS_AVAILABLE_SUPPORT_EXPLICIT',
        'no_new_confidence_intervals_or_qualification_or_task_claims':True,
        'error_components':'prediction-minus-nominal-target-change + nominal-minus-native-target-change + native-target-minus-hand-change',
        'component_cross_terms_retained':True,'noise_and_private_native_values':'EVALUATOR_ONLY_NOT_MODEL_INPUT',
        'menu':list(MENU),'same_acquisition_adoption_submenu':list(ADOPTION_MENU),'menu_state':'RAW_PI_COMMON_PREFIX_NOT_C8_PREFIX','oracle_ties':'ALL_RECORDED_MINIMIZERS_RETAINED',
        'oracle_scope':'OPTIMISTIC_REALIZED_FUTURE_RECORD_MENU_NOT_DEPLOYABLE_NOT_LEARNABILITY_OR_OFF_POLICY_PROOF',
        'reference_decomposition':'L_REF-L_RAW=(L_KEEP-L_RAW)+(L_REF-L_KEEP), full observed cutoff loss, no extra fees added',
        'DIRECT_C8_and_MOVE_INTEGRAL':'EXTERNAL_WHOLE_PROGRAM_CONTROLS_DIFFERENT_PREFIX_NOT_PREMOVE_ACTION_MENU',
        'new_environment_creations':0,'new_resets':0,'new_control_steps':0,'new_physical_frames':0,'new_model_fits':0,
        'new_optimizer_updates':0,'new_policy_training':0,'new_online_LLM_API_calls':0,'publication_goal_complete':False}


def source_inventory():
    result={}
    def bind(p):p=Path(p);result[p.relative_to(ROOT).as_posix()]=io.sha(p)
    lm=latent.checked(LATENT/'manifest.json');bind(LATENT/'manifest.json');bind(LATENT/'model_lock.json')
    for split in latent.SPLITS:
        folder=LATENT/split.lower();audit=io.read(folder/'audit.json');io.require(audit['integrity']=='PASSED' and audit['native_target_updates_bit_exact'],'complete source/native audit')
        for name,h in audit['artifact_sha256'].items():io.require(io.sha(folder/name)==h,'unchanged latent raw '+name);bind(folder/name)
        for name in ('audit.json','completion.json','trajectory_audit.json'):bind(folder/name)
    for split in ('CAL','QUAL'):
        folder=LATENT/(split.lower()+'_evaluation');audit=io.read(folder/'audit.json');io.require(audit['integrity']=='PASSED','source statistics audit')
        for name,h in audit['artifact_sha256'].items():io.require(io.sha(folder/name)==h,'unchanged original statistics');bind(folder/name)
        bind(folder/'audit.json')
    done=io.read(LATENT/'training/completion.json');io.require(io.sha(LATENT/'training/models.json')==done['models_sha256']
        and io.sha(LATENT/'training/public_train_bundle.json')==done['public_bundle_sha256'],'original weights/public TRAIN')
    for name in ('models.json','public_train_bundle.json','completion.json','audit.json','support.json','neural/completion.json','neural/training_log.jsonl'):
        bind(LATENT/'training'/name)
    for task in io.TASKS:
        for method in NEURAL:
            for k in CHECKPOINTS:bind(LATENT/'training/neural'/(task+'_'+method+f'_checkpoint_{k}.json'))
    folder=REFERENCE/'qual';audit=io.read(folder/'audit.json');io.require(audit['integrity']=='PASSED','complete reference audit')
    for name,h in audit['artifact_sha256'].items():io.require(io.sha(folder/name)==h,'reference raw changed');bind(folder/name)
    for name in ('audit.json','completion.json','statistics.json','statistics_audit.json','statistics_receipt.json','bootstrap_group_indices.json'):bind(folder/name)
    io.require(io.read(folder/'statistics_audit.json')['source_statistics_sha256']==io.sha(folder/'statistics.json'),'original reference comparisons unchanged')
    bind(REFERENCE/'manifest.json');return result


def checked(path):
    p=Path(path).resolve();m=io.read(p);body=dict(m);mid=body.pop('manifest_id')
    io.require(p.name=='manifest.json' and p.parent.parent==OUTPUT.resolve() and io.digest(body)==mid and m['config']==config(),'owned descriptive diagnosis manifest')
    for name,h in m['analysis_source_sha256'].items():io.require(io.sha(ROOT/name)==h,'frozen diagnosis source changed '+name)
    for name,h in m['input_sha256'].items():io.require(io.sha(ROOT/name)==h,'old source changed '+name)
    return m


def prepare():
    qa=io.read(VALIDATION/'complete.json');io.require(qa['integrity']=='PASSED' and not io.git('status','--porcelain','--untracked-files=no'),'clean checked diagnostic freeze')
    io.require(not list(OUTPUT.glob('*/manifest.json')) and io.read(CONFIG)==config(),'one descriptive census')
    for name,h in qa['source_sha256'].items():io.require(io.sha(ROOT/name)==h and io.git('ls-files','--error-unmatch',name)==name,'committed tested analysis source')
    head=io.git('rev-parse','HEAD');m={'experiment_run_id':'latent_response_diagnosis_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+head[:12],
        'analysis_git_commit':head,'analysis_source_sha256':qa['source_sha256'],'input_sha256':source_inventory(),'config':config(),
        'previous_goal_turn':'PROGRESS_DELIVERED_792_CASE_QUALIFICATION_AND_VERIFIED_LOCAL_RESULT','publication_goal_complete':False}
    m['manifest_id']=io.digest(m);out=OUTPUT/m['experiment_run_id'];out.mkdir(parents=True,exist_ok=False);io.write(out/'manifest.json',m);return out/'manifest.json'

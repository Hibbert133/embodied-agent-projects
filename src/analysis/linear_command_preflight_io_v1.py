"""Read-only TRAIN inputs and fail-closed boundaries for command preflight."""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import builtins
import os
import sys
from unittest.mock import patch
import numpy as np
from src.analysis import observable_history_io_v1 as io

ROOT = io.ROOT
SOURCE = ROOT/'outputs/response_training_controls/development_v1/training_controls_20261021T191002Z_a7a33756b1c7'
OUTPUT = ROOT/'outputs/linear_command_preflight/analysis_v1'
VALIDATION = ROOT/'outputs/linear_command_preflight/validation_v1'
CONFIG = ROOT/'configs/movement_task/linear_command_preflight_v1.json'
PROTOCOL = ROOT/'docs/protocols/linear_command_preflight_v1_zh.md'
INDEX_SHA = 'b76a5e0260b6f0de174697a99c739501c4baed20255f89c533fdd82f538bcf78'
FIT_SHA = '151ee1cbc809294eb29b17c1a4effafef25c741bf5ee1e55db60e19bdc462640'
REQUIRED = ('src/probe/linear_command_preflight_v1.py','src/analysis/linear_command_preflight_io_v1.py',
            'scripts/run_linear_command_preflight_v1.py','scripts/audit_linear_command_preflight_v1.py',
            'scripts/report_linear_command_preflight_v1.py','tests/test_linear_command_preflight_v1.py',
            'tests/test_linear_command_preflight_pipeline_v1.py')


def expected_config():
    return {'protocol':'linear_command_preflight_v1','scope':'POSTHOC_TRAIN_ONLY_ALGEBRA_AND_DESIGN_GEOMETRY',
            'source_result_commit':'97efaf6e2d9876b2725bd5ca5cd0145d26b4eff7','fit_public_sha256':FIT_SHA,'models_index_sha256':INDEX_SHA,
            'features':['H10','F20','F43'],'sources':['FEEDBACK8','BALANCED8'],'tasks':list(io.TASKS),
            'whole_groups':list(range(12)),'source_trajectories':144,'models':18,'query_xy_offset':.25,
            'query_positions':13402,'model_query_pairs':40206,'candidate_model_pairs':160824,'model_trajectory_pairs':432,
            'candidate_ids':['X_PLUS','X_MINUS','Y_PLUS','Y_MINUS'],'history_observations':3,'first_decision_step':2,
            'weighting':'One total weight per source trajectory; no output refitting',
            'rank_tolerance':'max(weighted_design.shape)*float64_epsilon*largest_singular_value',
            'conditional_columns':'XY commands; Z/grip and every other feature are nuisance columns',
            'box_tolerance':1e-12,'new_environment_steps':0,'new_all_resets':0,'new_physical_frames':0,
            'new_online_llm_api_calls':0,'new_model_fits':0,'candidate_selection':'NONE; all fixed hypothetical queries preserved',
            'physical_qualification':False,'task_benefit':False,'reserved_seed_execution':False}


def source_files():
    io.require(io.sha(SOURCE/'training/models.json') == INDEX_SHA and io.sha(SOURCE/'fit_public.json') == FIT_SHA,
               'audited FIT/index bytes changed')
    index = io.read(SOURCE/'training/models.json')['models']
    selected = {k:v for k,v in index.items() if v['kind']=='LINEAR'}
    io.require(len(selected)==18 and {(v['source'],v['task'],v['feature']) for v in selected.values()} ==
               {(s,t,f) for s in ('FEEDBACK8','BALANCED8') for t in io.TASKS for f in ('H10','F20','F43')},
               'complete old linear population required')
    paths = [SOURCE/'training/models.json',SOURCE/'fit_public.json',SOURCE/'delivery_v1/costs_and_provenance.json']
    for entry in selected.values():
        path=SOURCE/'training'/entry['file']; io.require(io.sha(path)==entry['sha256'],'old model changed'); paths.append(path)
    return selected, {p.relative_to(ROOT).as_posix():io.sha(p) for p in paths}


def make_manifest():
    io.require(not OUTPUT.exists(),'one frozen read-only run; preserve previous outputs')
    io.require(io.read(CONFIG)==expected_config(),'frozen configuration changed')
    io.require(not io.git('diff','--name-only') and not io.git('diff','--cached','--name-only'),'clean tracked freeze required')
    for name in (*REQUIRED,CONFIG.relative_to(ROOT).as_posix(),PROTOCOL.relative_to(ROOT).as_posix()):
        io.require(io.git('ls-files','--error-unmatch',name)==name,'uncommitted preflight source')
    validation=io.read(VALIDATION/'complete.json'); io.require(validation['integrity']=='PASSED','source-bound checks required')
    for name,digest in validation['python_source_sha256'].items(): io.require(io.sha(ROOT/name)==digest,'validated source changed')
    _,inputs=source_files(); commit=io.git('rev-parse','HEAD')
    value={'experiment_run_id':'linear_command_preflight_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+commit[:12],
           'source_git_commit':commit,'config':expected_config(),'input_sha256':inputs,
           'implementation_sha256':{n:io.sha(ROOT/n) for n in (*REQUIRED,CONFIG.relative_to(ROOT).as_posix(),PROTOCOL.relative_to(ROOT).as_posix())},
           'validation_sha256':io.sha(VALIDATION/'complete.json'),'physical_qualification':False}
    value['manifest_id']=io.digest(value); OUTPUT.mkdir(parents=True,exist_ok=False); io.write(OUTPUT/'manifest.json',value)
    return value


def load_manifest(folder=OUTPUT):
    io.require(folder.resolve()==OUTPUT.resolve(),'single owned run only')
    manifest=io.read(folder/'manifest.json'); fields=dict(manifest); identifier=fields.pop('manifest_id')
    io.require(io.digest(fields)==identifier and manifest['config']==expected_config(),'manifest changed')
    for name,digest in {**manifest['input_sha256'],**manifest['implementation_sha256']}.items():
        io.require(io.sha(ROOT/name)==digest,'bound input/source changed: '+name)
    return manifest


@contextmanager
def numeric_guard(allowed_inputs):
    active=[True]; original=builtins.__import__
    counts={'network_attempts':0,'forbidden_reads':0,'forbidden_imports':0,'child_process_attempts':0,'model_fit_attempts':0}
    allowed={Path(p).resolve() for p in allowed_inputs}
    output_root=(ROOT/'outputs').resolve(); own_root=OUTPUT.parent.resolve()
    def guarded_import(name,*args,**kwargs):
        if any(name==v or name.startswith(v+'.') for v in ('metaworld','mujoco','gym','gymnasium','torch','requests','httpx','openai','zhipuai')):
            counts['forbidden_imports']+=1; raise RuntimeError('read-only numeric preflight forbids simulator/training/network clients')
        return original(name,*args,**kwargs)
    def blocked_fit(*args,**kwargs):
        counts['model_fit_attempts']+=1; raise RuntimeError('no linear solves/refits; design SVD only')
    def audit(event,args):
        if not active[0]: return
        if event.startswith('socket.') and event!='socket.gethostname':
            counts['network_attempts']+=1; raise RuntimeError('no network transport')
        if event in ('subprocess.Popen','os.system','os.exec','os.posix_spawn'):
            counts['child_process_attempts']+=1; raise RuntimeError('no child process')
        if event=='open' and isinstance(args[0],(str,bytes)):
            path=Path(os.fsdecode(args[0])).resolve()
            mode=args[1]; flags=args[2] if isinstance(args[2],int) else 0
            writing=(isinstance(mode,str) and any(c in mode for c in 'wax+')) or bool(flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))
            if path.is_relative_to(output_root) and not path.is_relative_to(own_root) and (path not in allowed or writing):
                counts['forbidden_reads']+=1; raise RuntimeError('FIT-only allowlist rejects old DEV/CAL/TEST/private data or source writes')
    sys.addaudithook(audit); builtins.__import__=guarded_import
    try:
        with patch.object(np.linalg,'solve',blocked_fit),patch.object(np.linalg,'lstsq',blocked_fit): yield counts
    finally:
        active[0]=False; builtins.__import__=original

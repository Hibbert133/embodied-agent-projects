"""Freeze-bound storage repair; real QUAL audit with separately charged refits."""
from pathlib import Path
from contextlib import ExitStack
from dataclasses import asdict
from time import perf_counter_ns
from unittest.mock import patch
import argparse,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis import acquisition_reference_io_v1 as a
from src.analysis import acquisition_reference_streaming_audit_v2 as streaming
from src.analysis.capsule_record_json_v2 import normalize
from src.probe import task_passive_program_v1 as legacy
io=a.io;REPAIR=a.BASE/'audit_repair_v2'
OWN=('src/analysis/acquisition_reference_streaming_audit_v2.py','scripts/audit_acquisition_reference_streaming_v2.py','tests/test_acquisition_reference_streaming_v2.py')


def checked(path):
    path=path.resolve();m=a.checked(path);p=path.parent/'audit_repair_manifest_v2.json';v=io.read(p);body=dict(v);mid=body.pop('repair_manifest_id')
    io.require(mid==io.digest(body) and v['original_manifest_id']==m['manifest_id'],'repair manifest identity')
    for n,h in v['source_sha256'].items():io.require(io.sha(io.ROOT/n)==h,'repair source changed '+n)
    io.require(io.sha(REPAIR/'complete.json')==v['repair_checks_sha256'],'repair check binding')
    io.require(io.sha(path.parent/'qual/record_audit_process_receipt_v1.json')==v['original_failed_process_receipt_sha256'],'original failed receipt unchanged')
    return m,v


def prepare(path):
    path=path.resolve();m=a.checked(path);qa=io.read(REPAIR/'complete.json');old=io.read(path.parent/'qual/record_audit_process_receipt_v1.json')
    io.require(qa['integrity']=='PASSED' and qa['new_array_and_saved_record_tests']==5 and qa['actual_new_fits']==0,'guarded repair qualification')
    io.require(not io.git('status','--porcelain','--untracked-files=no'),'clean committed repair source')
    for n,h in qa['source_sha256'].items():io.require(io.sha(io.ROOT/n)==h and io.git('ls-files','--error-unmatch',n)==n,'committed checked repair source')
    io.require(old['status']=='FAILED' and old['failure']['type']=='MemoryError' and not any(old['costs'].values()),'storage failure before any refits')
    io.require(io.sha(path.parent/'qual/independent_refit_trace_v1.jsonl')==old['trace_sha256'],'retained empty first trace')
    io.require(io.read(path.parent/'qual/completion.json')['status']=='COLLECTED_FOR_INDEPENDENT_AUDIT','complete original data')
    v={'classification':'STORAGE_ONLY_CASE_STREAMING_REPAIR_V2','original_manifest_id':m['manifest_id'],'execution_source_git_commit':m['source_git_commit'],
        'repair_git_commit':io.git('rev-parse','HEAD'),'source_sha256':qa['source_sha256'],'repair_checks_sha256':io.sha(REPAIR/'complete.json'),
        'original_failed_process_receipt_sha256':io.sha(path.parent/'qual/record_audit_process_receipt_v1.json'),
        'unchanged_physical_replay_PID_memory_and_qualification_rules':True,'new_collection':False,'earlier_actual_QUAL_refits':0,'remaining_actual_QUAL_refits_max':216,
        'no_new_response_training_or_online_LLM':True}
    v['repair_manifest_id']=io.digest(v);io.write(path.parent/'audit_repair_manifest_v2.json',v);return v


def audit(path):
    path=path.resolve();m,repair=checked(path);out=path.parent/'qual';start=perf_counter_ns();failure=None;result=None
    io.require(not (out/'audit.json').exists() and not (out/'record_audit_process_receipt_v2.json').exists(),'one frozen streaming QUAL audit')
    from src.analysis.response_action_io_v1 import verify_runtime
    verify_runtime(io.read(a.VALIDATION/'runtime_lock.json'))
    from metaworld.sawyer_xyz_env import SawyerXYZEnv
    from gymnasium.envs.mujoco import MujocoEnv
    counters={'environment_creations':0,'resets':0,'simulation':0};network={};costs={'initial_C4_C8_refits_attempted':0,'initial_C4_C8_refits_returned':0,'optimizer_nfev':0}
    trace=out/'independent_refit_trace_v2.jsonl'
    with trace.open('x',encoding='utf-8',newline='\n') as stream:
        def deny(key):
            def blocked(*args,**kw):counters[key]+=1;raise RuntimeError('Read-only streaming audit cannot advance or create physics')
            return blocked
        def counted(name,original):
            def call(nominal,prefix):
                io.require(costs['initial_C4_C8_refits_attempted']<216,'remaining QUAL refit cap');costs['initial_C4_C8_refits_attempted']+=1
                row={'index':costs['initial_C4_C8_refits_attempted']-1,'function':name,'nominal_sha256':io.digest(normalize(nominal)),
                    'prefix_sha256':io.digest(normalize(asdict(prefix))),'started_ns':perf_counter_ns()}
                try:
                    value=original(nominal,prefix);costs['initial_C4_C8_refits_returned']+=1;costs['optimizer_nfev']+=int(value.get('nfev',0));row.update(status='RETURNED',result=normalize(value));return value
                except BaseException as error:row.update(status='FAILED',error={'type':type(error).__name__,'message':str(error)});raise
                finally:
                    row['wall_ns']=perf_counter_ns()-row['started_ns'];stream.write(json.dumps(row,allow_nan=False,separators=(',',':'))+'\n');stream.flush()
            return call
        try:
            with ExitStack() as stack:
                stack.enter_context(io.forbid_online_calls(network))
                for obj,name,key in ((SawyerXYZEnv,'__init__','environment_creations'),(SawyerXYZEnv,'reset','resets'),(MujocoEnv,'do_simulation','simulation')):stack.enter_context(patch.object(obj,name,deny(key)))
                stack.enter_context(patch.object(legacy,'infer_four',counted('infer_four',legacy.infer_four)))
                stack.enter_context(patch.object(legacy,'infer_operator',counted('infer_operator',legacy.infer_operator)))
                result=streaming.compute(path,'QUAL')
            io.require(not any(counters.values()) and network=={'attempted_network_calls':0},'read-only streaming guard')
            io.require(costs['initial_C4_C8_refits_attempted']==costs['initial_C4_C8_refits_returned']==result['costs']['independent_c4_c8_refits'],'real replay fit accounting')
            checked(path)
            result.update(audit_storage_version='CASE_STREAMING_V2',repair_git_commit=repair['repair_git_commit'],repair_manifest_id=repair['repair_manifest_id'],
                original_failed_audit_preserved=True,no_original_control_model_or_gate_change=True)
            io.write(out/'audit.json',result)
            io.write(out/'audit_interaction_guard.json',{'integrity':'PASSED','counters':counters,'network':network,
                'initial_C4_C8_refits_separately_charged':costs['initial_C4_C8_refits_attempted'],'new_response_training':0,'new_online_LLM_API_calls':0,'storage_version':2})
        except BaseException as error:failure={'type':type(error).__name__,'message':str(error)};raise
        finally:
            stream.flush();io.write(out/'record_audit_process_receipt_v2.json',{'status':'PASSED' if failure is None else 'FAILED','failure':failure,'cohort':'QUAL','costs':costs,
                'script_sha256':io.sha(__file__),'repair_manifest_id':repair['repair_manifest_id'],'trace_sha256':io.sha(trace),'guard_counters':counters,'network':network,
                'wall_ns':perf_counter_ns()-start,'new_response_training':0,'new_online_LLM_API_calls':0})
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=('prepare','audit'));p.add_argument('--manifest',type=Path,required=True);v=p.parse_args()
    r=prepare(v.manifest) if v.phase=='prepare' else audit(v.manifest)
    print({k:r[k] for k in (('repair_git_commit','repair_manifest_id') if v.phase=='prepare' else ('integrity','executions','costs','audit_storage_version'))},flush=True)

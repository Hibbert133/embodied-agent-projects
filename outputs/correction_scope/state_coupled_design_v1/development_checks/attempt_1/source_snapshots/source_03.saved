"""Constructed arithmetic only. Never creates/resets/advances an environment."""
from pathlib import Path
from time import perf_counter_ns
from datetime import datetime,timezone
from itertools import product
from copy import deepcopy
from unittest.mock import patch
import argparse,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import numpy as np
from src.analysis import response_qualification_io_v1 as io
from src.analysis import state_coupled_actuation_design_v1 as main
from src.analysis import state_coupled_actuation_independent_v1 as independent
from src.analysis.correction_scope_risk_reference_v1 import recorded_guard
from src.rollout.chronological_faults import deterministic_action
BASE=ROOT/'outputs/correction_scope/state_coupled_design_v1'
CONFIG=ROOT/'configs/movement_task/state_coupled_actuation_design_v1.json'
SOURCES=('src/analysis/state_coupled_actuation_design_v1.py','src/analysis/state_coupled_actuation_independent_v1.py',
    'tests/test_state_coupled_actuation_design_v1.py','scripts/verify_state_coupled_actuation_design_v1.py',
    'configs/movement_task/state_coupled_actuation_design_v1.json','docs/protocols/state_coupled_actuation_design_v1_zh.md',
    'docs/research/state_coupled_validity_decision_v1_zh.md','outputs/correction_scope/state_coupled_design_v1/validate_freeze.py',
    'src/rollout/chronological_faults.py')


def checked(path):
    path=Path(path).resolve();m=io.read(path);copy=dict(m);mid=copy.pop('manifest_id')
    assert path.parent.parent==BASE.resolve() and mid==io.digest(copy) and m['config']==io.read(CONFIG)
    for name,digest in m['source_sha256'].items():assert io.sha(ROOT/name)==digest
    return m


def prepare():
    v=io.read(BASE/'freeze_validation/complete.json');assert v['integrity']=='PASSED'
    assert not io.git('status','--porcelain','--untracked-files=no') and not list(BASE.glob('run_*/manifest.json'))
    for name,digest in v['source_sha256'].items():assert io.sha(ROOT/name)==digest
    config=io.read(CONFIG);assert config['actual_robot_episode_seeds']==[] and config['native_collector'] is None
    head=io.git('rev-parse','HEAD');out=BASE/('run_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+head[:12]);out.mkdir(exist_ok=False)
    m=dict(protocol=config['protocol'],status=config['status'],source_git_commit=head,config=config,source_sha256=v['source_sha256'],
        source_legacy_math_sha256=io.sha(ROOT/'src/rollout/chronological_faults.py'),robot_data_read=False,new_physics=0,new_model_fits=0,online_LLM_API_calls=0)
    m['manifest_id']=io.digest(m);io.write(out/'manifest.json',m);return out/'manifest.json'


def collect_constructed(path):
    path=Path(path).resolve();m=checked(path);base=path.parent;c=m['config'];start=perf_counter_ns();guard={};rows=0
    with recorded_guard(guard,base/'construction_failure.json'),(base/'constructed_records.jsonl').open('x',encoding='utf8',newline='\n') as f:
        for kind,x,ux,uy,uz,g,noise in product(c['kinds'],c['positions'],c['xy_commands'],c['xy_commands'],c['z_commands'],c['gripper_commands'],c['noise_rows_for_arithmetic_only']):
            d=deepcopy(c['fixture_spec']);d['kind']=kind;before=main.fixture_before(x);command=[ux,uy,uz,g]
            actual=main.evaluate(before,command,noise,d)
            f.write(json.dumps(dict(id=rows,kind=kind,position=x,command=command,noise_xyz=noise,actual=actual),ensure_ascii=False,separators=(',',':'))+'\n');rows+=1
        example=main.adoption_counterexample()
    assert rows==c['constructed_rows']==4320
    receipt=dict(integrity='FOR_INDEPENDENT_CONSTRUCTED_AUDIT',manifest_id=m['manifest_id'],constructed_rows=rows,
        records_sha256=io.sha(base/'constructed_records.jsonl'),adoption_counterexample=example,guard=guard,wall_ns=perf_counter_ns()-start,
        not_MetaWorld_or_task_outcomes=True,new_physics=0,new_model_fits=0,online_LLM_API_calls=0)
    io.write(base/'construction.json',receipt);return receipt


def audit(path):
    path=Path(path).resolve();m=checked(path);base=path.parent;c=m['config'];start=perf_counter_ns();guard={};fields=0;flat=0;max_error=0.;rows=0
    saved=io.read(base/'construction.json');assert saved['records_sha256']==io.sha(base/'constructed_records.jsonl')
    assert m['source_legacy_math_sha256']==io.sha(ROOT/'src/rollout/chronological_faults.py')
    def deny(*args,**kwargs):raise RuntimeError('main spatial operator disabled during independent constructed audit')
    disabled=('evaluate','weight','local_endpoint','before_state','spec','endpoint','fixture_definition','fixture_before','adoption_counterexample')
    expected_requests=iter(product(c['kinds'],c['positions'],c['xy_commands'],c['xy_commands'],c['z_commands'],c['gripper_commands'],c['noise_rows_for_arithmetic_only']))
    with recorded_guard(guard,base/'audit_failure.json'),patch.multiple(main,**{n:deny for n in disabled}), (base/'constructed_records.jsonl').open(encoding='utf8') as f:
        for line in f:
            row=json.loads(line);assert row['id']==rows;rows+=1
            kind,x,ux,uy,uz,g,noise=next(expected_requests)
            assert row['kind']==kind and row['position']==x and row['command']==[ux,uy,uz,g] and row['noise_xyz']==noise
            d=deepcopy(c['fixture_spec']);d['kind']=row['kind'];obs=[0.]*39;obs[0]=row['position']
            before=dict(at_calls=0,current=dict(observation=obs,success=False,terminated=False,truncated=False))
            expected=independent.literal(before,row['command'],row['noise_xyz'],d);actual=row['actual']
            assert set(actual)==set(expected)|{'schema','at_calls'} and actual['schema']=='EVALUATOR_STATE_COUPLED_ACTION_V1' and actual['at_calls']==0
            for key,value in expected.items():
                if key=='final_clip_oracle':assert actual[key]==value;fields+=4;continue
                aa=np.asarray(actual[key],float);bb=np.asarray(value,float);error=float(np.max(abs(aa-bb)))
                max_error=max(max_error,error);assert aa.shape==bb.shape and error<=c['independent_scalar_absolute_tolerance'];fields+=aa.size
            if row['kind'] in ('FLAT_LEFT','FLAT_RIGHT'):
                fault=d['left' if row['kind']=='FLAT_LEFT' else 'right'];legacy=deterministic_action(row['command'],fault)
                legacy[:3]+=np.asarray(row['noise_xyz'],np.float32);legacy=np.clip(legacy,-1,1)
                assert legacy.tobytes()==np.asarray(actual['executed_action_oracle'],np.float32).tobytes();flat+=1
        assert rows==4320 and flat==2880 and next(expected_requests,None) is None
        # Recompute the explicitly invented x_next=x+applied_x example literally.
        examples=[];d=deepcopy(c['fixture_spec']);d['left']['matrix_xy']=d['right']['matrix_xy']=[[1.,0.],[0.,1.]]
        for label,u in (('SMALL',.01),('LARGE',.5)):
            def calc(x,kind):
                dd=deepcopy(d);dd['kind']=kind;obs=[0.]*39;obs[0]=x
                before=dict(at_calls=0,current=dict(observation=obs,success=False,terminated=False,truncated=False))
                return independent.literal(before,[u,0.,0.,0.],[0.]*3,dd)
            first=calc(-.4,'SMOOTH_STATE');next_x=-.4+first['executed_action_oracle'][0];second=calc(next_x,'SMOOTH_STATE')
            examples.append(dict(label=label,initial_x=-.4,command_x=u,initial_weight=first['state_weight_oracle'],
                initial_prediction_error=first['executed_action_oracle'][0]-calc(-.4,'FLAT_LEFT')['executed_action_oracle'][0],
                invented_kinematic_next_x=next_x,next_weight=second['state_weight_oracle'],
                next_prediction_error=second['executed_action_oracle'][0]-calc(next_x,'FLAT_LEFT')['executed_action_oracle'][0],
                endpoint_matrix_determinants=[1.,1.],not_a_robot_or_task_result=True))
        assert examples==saved['adoption_counterexample']
    receipt=dict(integrity='PASSED',manifest_id=m['manifest_id'],records_sha256=io.sha(base/'constructed_records.jsonl'),construction_sha256=io.sha(base/'construction.json'),
        constructed_rows=rows,legacy_float32_byte_exact_rows=flat,checked_scalar_fields=fields,maximum_scalar_absolute_gap=max_error,
        scalar_tolerance=c['independent_scalar_absolute_tolerance'],main_functions_disabled=list(disabled),guard=guard,wall_ns=perf_counter_ns()-start,
        not_robot_or_method_qualification=True,new_physics=0,new_model_fits=0,online_LLM_API_calls=0)
    io.write(base/'audit.json',receipt);return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=('prepare','construct','audit'));p.add_argument('--manifest');args=p.parse_args()
    if args.phase=='prepare':print(prepare())
    else:
        r={'construct':collect_constructed,'audit':audit}[args.phase](args.manifest)
        print({k:v for k,v in r.items() if k in ('integrity','constructed_rows','legacy_float32_byte_exact_rows','checked_scalar_fields','maximum_scalar_absolute_gap')})

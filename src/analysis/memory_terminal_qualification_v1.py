"""One immutable finite-model output run; no sampled/native robot experiment."""
from pathlib import Path
from time import perf_counter_ns
from itertools import product
from math import fsum
import csv,json
from src.analysis import response_qualification_io_v1 as io
from src.analysis import memory_terminal_world_v1 as world
from src.analysis.two_stage_terminal_dr_v1 import LoggedTerminal,estimate
BASE=io.ROOT/'outputs/memory_terminal_reference'
CONFIG=io.ROOT/'configs/movement_task/memory_terminal_reference_v1.json'
OWN=('src/probe/task_memory_option_v1.py','src/analysis/two_stage_terminal_dr_v1.py','src/analysis/memory_terminal_world_v1.py',
    'src/analysis/memory_terminal_qualification_v1.py','src/analysis/memory_terminal_audit_v1.py',
    'scripts/run_memory_terminal_reference_v1.py','scripts/audit_memory_terminal_reference_v1.py',
    'scripts/report_memory_terminal_reference_v1.py','tests/test_memory_terminal_reference_v1.py',
    'configs/movement_task/memory_terminal_reference_v1.json','docs/protocols/memory_terminal_reference_v1_zh.md',
    'docs/research/memory_terminal_reference_prior_art_v1_zh.md')


def checked(path):
    path=Path(path).resolve();v=io.read(path);body=dict(v);mid=body.pop('manifest_id')
    io.require(path.name=='manifest.json' and path.parent.parent==(BASE/'qualification_v1').resolve() and io.digest(body)==mid,'owned immutable manifest')
    for n,h in v['source_sha256'].items():io.require(io.sha(io.ROOT/n)==h,'frozen source changed '+n)
    io.require(v['config']==io.read(CONFIG),'frozen numerical config changed');return v


def stats(rows,truth):
    values={k:[(r['population_atom_probability'],r['estimate'][k]) for r in rows] for k in ('whole_DR','whole_IS','whole_regression','logged_whole_loss')}
    result={}
    for key,pairs in values.items():
        mean=fsum(p*v for p,v in pairs);variance=fsum(p*(v-mean)**2 for p,v in pairs)
        result[key]={'mean':mean,'bias':mean-truth,'variance':variance,'MSE':fsum(p*(v-truth)**2 for p,v in pairs)}
    return result


def run(path):
    start=perf_counter_ns();path=Path(path).resolve();m=checked(path);out=path.parent;config=m['config'];atoms=world.atoms()
    io.require(len(atoms)==config['expected_finite_atoms'] and abs(fsum(a['probability_under_true_behavior'] for a in atoms)-1)<1e-12,'complete finite atom mass')
    with (out/'finite_atoms.jsonl').open('x',encoding='utf-8',newline='\n') as f:
        for a in atoms:f.write(json.dumps(a,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n')
    summaries=[];all_rows=[]
    with (out/'estimates.jsonl').open('x',encoding='utf-8',newline='\n') as f:
        for first,tail,mode in product(world.FIRST_POLICIES,world.TAIL_POLICIES,world.MODES):
            rows=[];truth=world.target_truth(first,tail)
            for a in atoms:
                r=LoggedTerminal.from_dict(a['record']);inputs=world.inputs(r.before,r.after,mode,first,tail);value=estimate(r,**inputs)
                saved={'first_target_policy':first,'tail_target_policy':tail,'mode':mode,'atom_id':a['atom_id'],
                    'population_atom_probability':a['probability_under_true_behavior'],'prediction_input_before':r.before.to_dict(),
                    'prediction_input_after':None if r.after is None else r.after.to_dict(),'prediction_and_policy_arguments':inputs,'estimate':value,
                    'nuisance_models_are_fixed_or_evaluator_oracle_fixtures':True,'not_a_robot_or_sampled_trajectory':True}
                f.write(json.dumps(saved,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n');rows.append(saved);all_rows.append(saved)
            arithmetic=stats(rows,truth);expected=mode!='BOTH_WRONG';ok=abs(arithmetic['whole_DR']['bias'])<=config['unbiased_identity_absolute_tolerance']
            summaries.append({'first_target_policy':first,'tail_target_policy':tail,'mode':mode,'known_target_whole_loss':truth,'finite_atoms':len(rows),
                'expected_unbiased_under_declared_fixture':expected,'DR_identity_within_tolerance':ok,'estimators':arithmetic,
                'DR_atoms_outside_0_500':sum(not 0<=r['estimate']['whole_DR']<=500 for r in rows),
                'not_a_robot_task_success_test':True})
    robust=[s for s in summaries if s['expected_unbiased_under_declared_fixture']];wrong=[s for s in summaries if not s['expected_unbiased_under_declared_fixture']]
    io.require(len(all_rows)==config['expected_estimator_rows'] and len(summaries)==config['expected_setting_summaries'] and len(robust)==40,'all settings retained')
    io.require(all(s['DR_identity_within_tolerance'] for s in robust),'standard identity qualification failed')
    io.require(len(wrong)==8 and any(not s['DR_identity_within_tolerance'] for s in wrong),'both-wrong negative examples must remain')
    contrasts=[]
    for x in (0,1):
        before=world.pre(x);q=world.true_q1(before,'POSTSTATE_ADAPTIVE')
        for action,mu in zip(world.ACTIONS,q):
            subset=[a for a in atoms if a['record']['before']['observed_code']==x and a['record']['action']==action]
            marginal=fsum(a['probability_under_true_behavior']*a['record']['full_deadline_loss'] for a in subset)/fsum(a['probability_under_true_behavior'] for a in subset)
            contrasts.append({'visible_code':x,'first_action':action,'fixed_poststate_policy_whole_loss':before.completed_steps+mu,
                'behavior_marginal_whole_loss':marginal,'synthetic_counterexample_not_robot_gain':True})
    result={'qualification':'PASSED_STANDARD_REFERENCE_IDENTITIES_ONLY','classification':'FULLY_ENUMERATED_SYNTHETIC_MODEL_NOT_ROBOT_VALIDATION',
        'finite_atoms':len(atoms),'estimate_rows':len(all_rows),'setting_summaries':summaries,'conditional_action_comparisons':contrasts,
        'robust_identities_passed':len(robust),'both_wrong_settings_preserved':len(wrong),'clipping_used':False,
        'numerical_estimator_calls':len(all_rows),'new_robot_executions':0,'new_environment_steps':0,'new_resets':0,'new_physical_frames':0,
        'new_model_fits':0,'new_online_LLM_API_calls':0,'new_random_streams':0,'publication_goal_complete':False}
    io.write(out/'results.json',result)
    flat=[]
    for s in summaries:
        flat.append({k:v for k,v in s.items() if k!='estimators'}|{key+'_'+metric:value for key,values in s['estimators'].items() for metric,value in values.items()})
    with (out/'setting_summaries.csv').open('x',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(flat[0]));w.writeheader();w.writerows(flat)
    checked(path)
    names=('finite_atoms.jsonl','estimates.jsonl','results.json','setting_summaries.csv')
    io.write(out/'completion.json',{'status':'ENUMERATED_FOR_INDEPENDENT_ARITHMETIC_AUDIT','manifest_id':m['manifest_id'],
        'artifact_sha256':{n:io.sha(out/n) for n in names},'wall_ns':perf_counter_ns()-start,
        'finite_model_not_independent_unseen_data':True,'development_precheck_disclosed':True,
        'new_environment_steps':0,'new_model_fits':0,'new_online_LLM_API_calls':0})
    return {k:result[k] for k in ('qualification','finite_atoms','estimate_rows','robust_identities_passed','both_wrong_settings_preserved')}

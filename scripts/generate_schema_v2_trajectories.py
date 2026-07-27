"""Regenerate selected transitions with corrected schema-v2 semantics."""
from __future__ import annotations
import csv, sys
from pathlib import Path
PROJECT_ROOT=Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path: sys.path.insert(0,str(PROJECT_ROOT))
from src.perturbations import ActionBiasPerturbation
from src.rollout import create_push_environment,create_push_policy,run_episode
SOURCE=PROJECT_ROOT/'outputs/day2_5/selected_config_50_seed.csv'
OUTPUT=PROJECT_ROOT/'outputs/day2_5/schema_v2_trajectories'
CASES=(('success',100),('failure',148),('near_success',135))
def main()->int:
    with SOURCE.open(encoding='utf-8',newline='') as file: prior={int(row['seed']):row for row in csv.DictReader(file)}
    OUTPUT.mkdir(parents=True,exist_ok=True); policy=create_push_policy(); rows=[]
    for label,seed in CASES:
        path=OUTPUT/f'{label}_x_positive_0.145_seed{seed}.jsonl'; env=create_push_environment(seed)
        try: result=run_episode(env,policy,seed=seed,max_steps=500,trajectory_path=path,perturbation=ActionBiasPerturbation((.145,0,0,0)))
        finally: env.close()
        old=prior[seed]
        rows.append({'seed':seed,'result':label,'success':result.success,'steps':result.steps,'episode_return':result.episode_return,'final_object_goal_distance':result.final_object_goal_distance,'trajectory_path':str(path.relative_to(PROJECT_ROOT)),'schema_version':2,'prior_success':old['success'],'prior_steps':old['steps'],'return_delta':result.episode_return-float(old['episode_return']),'final_distance_delta':result.final_object_goal_distance-float(old['final_object_goal_distance'])})
        print(label,seed,result.success,result.steps,result.episode_return,result.final_object_goal_distance)
    manifest=OUTPUT/'manifest.csv'
    with manifest.open('w',encoding='utf-8',newline='') as file:
        writer=csv.DictWriter(file,fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    print(manifest); return 0
if __name__=='__main__': raise SystemExit(main())

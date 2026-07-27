"""Render audited representative videos for the selected +x bias."""
from __future__ import annotations
import csv,sys
from pathlib import Path
PROJECT_ROOT=Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path: sys.path.insert(0,str(PROJECT_ROOT))
from src.perturbations import ActionBiasPerturbation,IdentityPerturbation
from src.rollout import create_push_environment,create_push_policy,run_episode

DETAIL=PROJECT_ROOT/'outputs/day2_5/selected_config_50_seed.csv'; VIDEOS=PROJECT_ROOT/'outputs/videos'; TRAJ=PROJECT_ROOT/'outputs/representative_trajectories'
def select_seeds():
    with DETAIL.open(encoding='utf-8',newline='') as f: rows=list(csv.DictReader(f))
    good=[r for r in rows if r['success'].lower()=='true']; bad=[r for r in rows if r['success'].lower()=='false']
    avg=sum(float(r['final_object_goal_distance']) for r in bad)/len(bad)
    return int(good[0]['seed']),int(min(bad,key=lambda r:abs(float(r['final_object_goal_distance'])-avg))['seed']),int(min(bad,key=lambda r:float(r['final_object_goal_distance']))['seed'])
def main():
    success,typical,near=select_seeds(); cases=[('baseline_x_positive_0_seed100_success',100,IdentityPerturbation()),(f'single_axis_bias_x_positive_0.145_seed{success}_success',success,ActionBiasPerturbation((.145,0,0,0))),(f'single_axis_bias_x_positive_0.145_seed{typical}_failure',typical,ActionBiasPerturbation((.145,0,0,0))),(f'single_axis_bias_x_positive_0.145_seed{near}_near_success_failure',near,ActionBiasPerturbation((.145,0,0,0)))]
    VIDEOS.mkdir(parents=True,exist_ok=True); TRAJ.mkdir(parents=True,exist_ok=True); policy=create_push_policy(); manifest=[]
    for i,(name,seed,p) in enumerate(cases,1):
        env=create_push_environment(seed,'rgb_array')
        try:r=run_episode(env,policy,seed=seed,max_steps=500,episode_id=i,perturbation=p,video_path=VIDEOS/f'{name}.mp4',trajectory_path=TRAJ/f'{name}.jsonl')
        finally:env.close()
        manifest.append({'video_path':str((VIDEOS/f'{name}.mp4').relative_to(PROJECT_ROOT)),'seed':seed,'perturbation':p.name+':'+str(p.parameters()),'success':r.success,'steps':r.steps,'final_object_goal_distance':r.final_object_goal_distance,'clipped_step_fraction':r.clipped_step_fraction})
        print(name,r.success,r.steps)
    with (VIDEOS/'manifest.csv').open('w',encoding='utf-8',newline='') as f:w=csv.DictWriter(f,fieldnames=list(manifest[0]));w.writeheader();w.writerows(manifest)
if __name__=='__main__':main()

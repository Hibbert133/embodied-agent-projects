"""Run paired-seed masked perturbation sweeps on MetaWorld push-v3."""
from __future__ import annotations
import argparse,csv,sys
from dataclasses import asdict,dataclass
from pathlib import Path
from statistics import mean
from typing import Any,Callable
PROJECT_ROOT=Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path: sys.path.insert(0,str(PROJECT_ROOT))
from src.perturbations import ActionBiasPerturbation,ActionPerturbation,ActionScalePerturbation,GaussianNoisePerturbation
from src.rollout import create_push_environment,create_push_policy,run_episode

DEFAULT_LEVELS={"action_scale":[1,.8,.6,.4,.2],"gaussian_noise":[0,.02,.05,.1,.2],"action_bias":[0,.02,.04,.06,.08,.1,.12]}
@dataclass(frozen=True)
class Config:
    kind:str; level:float; axis:str; direction:str; factory:Callable[[],ActionPerturbation]
    @property
    def key(self)->tuple[str,float,str,str]: return self.kind,self.level,self.axis,self.direction
@dataclass(frozen=True)
class SweepRow:
    schema_version:int; perturbation_type:str; perturbation_level:float; bias_axis:str; bias_direction:str
    episode_id:int; seed:int; success:bool; steps:int; episode_return:float; elapsed_time_ms:float
    clipped_step_count:int; clipped_step_fraction:float; clipped_element_count:int; clipped_element_fraction:float
    final_object_goal_distance:float; min_gripper_object_distance:float; object_displacement:float; progress_to_goal:float
@dataclass(frozen=True)
class SummaryRow:
    schema_version:int; perturbation_type:str; perturbation_level:float; bias_axis:str; bias_direction:str
    num_episodes:int; success_count:int; success_rate:float; mean_steps:float; mean_return:float
    mean_final_object_goal_distance:float; mean_min_gripper_object_distance:float; mean_object_displacement:float; mean_progress_to_goal:float
    clipped_step_fraction:float; clipped_element_fraction:float

def parse_args()->argparse.Namespace:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--num-episodes',type=int,default=20); p.add_argument('--seed-start',type=int,default=100); p.add_argument('--max-steps',type=int,default=500)
    p.add_argument('--perturbation-type',choices=('all','action_scale','gaussian_noise','action_bias'),default='all'); p.add_argument('--levels',type=float,nargs='+')
    p.add_argument('--bias-axis',choices=('x','y','all'),default='y'); p.add_argument('--bias-sign',choices=('positive','negative','all'),default='positive')
    p.add_argument('--output-csv',type=Path,default=PROJECT_ROOT/'outputs'/'perturbation_sweep_v2.csv'); p.add_argument('--summary-csv',type=Path,default=PROJECT_ROOT/'outputs'/'perturbation_summary_v2.csv'); return p.parse_args()
def configs(kind:str,levels:list[float]|None,axis:str,sign:str)->list[Config]:
    kinds=list(DEFAULT_LEVELS) if kind=='all' else [kind]; out=[]
    for k in kinds:
        vals=levels if levels is not None else DEFAULT_LEVELS[k]
        if k=='action_bias':
            axes=('x','y') if axis=='all' else (axis,); signs=('positive','negative') if sign=='all' else (sign,)
            for a in axes:
                for s in signs:
                    for v in vals:
                        mag=float(v); vector=[0.,0.,0.,0.]; vector[0 if a=='x' else 1]=mag*(1 if s=='positive' else -1)
                        out.append(Config(k,mag,a,s,lambda vector=tuple(vector):ActionBiasPerturbation(vector)))
        else:
            for v in vals:
                level=float(v); factory=(lambda level=level:ActionScalePerturbation(level)) if k=='action_scale' else (lambda level=level:GaussianNoisePerturbation(level))
                out.append(Config(k,level,'','',factory))
    return out
def save(rows:list[Any],path:Path)->Path:
    path=path.resolve(); path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_name('.'+path.name+'.tmp')
    with tmp.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0].__dataclass_fields__)); w.writeheader(); w.writerows(asdict(x) for x in rows)
    tmp.replace(path); return path
def summarize(rows:list[SweepRow])->list[SummaryRow]:
    result=[]
    for key in dict.fromkeys((r.perturbation_type,r.perturbation_level,r.bias_axis,r.bias_direction) for r in rows):
        g=[r for r in rows if (r.perturbation_type,r.perturbation_level,r.bias_axis,r.bias_direction)==key]; steps=sum(r.steps for r in g); elements=steps*4
        result.append(SummaryRow(2,*key,len(g),sum(r.success for r in g),mean(r.success for r in g),mean(r.steps for r in g),mean(r.episode_return for r in g),mean(r.final_object_goal_distance for r in g),mean(r.min_gripper_object_distance for r in g),mean(r.object_displacement for r in g),mean(r.progress_to_goal for r in g),sum(r.clipped_step_count for r in g)/steps,sum(r.clipped_element_count for r in g)/elements))
    return result
def sweep(args:argparse.Namespace)->tuple[list[SweepRow],list[SummaryRow]]:
    if args.num_episodes<=0 or args.max_steps<=0: raise ValueError('episode counts and max steps must be positive')
    cs=configs(args.perturbation_type,args.levels,args.bias_axis,args.bias_sign); policy=create_push_policy(); rows=[]
    for c in cs:
        for i in range(args.num_episodes):
            seed=args.seed_start+i; env=None
            try:
                env=create_push_environment(seed); r=run_episode(env,policy,seed=seed,max_steps=args.max_steps,episode_id=i+1,perturbation=c.factory())
            finally:
                if env is not None: env.close()
            rows.append(SweepRow(2,c.kind,c.level,c.axis,c.direction,i+1,seed,r.success,r.steps,r.episode_return,r.elapsed_time_ms,r.clipped_step_count,r.clipped_step_fraction,r.clipped_element_count,r.clipped_element_fraction,r.final_object_goal_distance,r.min_gripper_object_distance,r.object_displacement,r.progress_to_goal))
            print(f'{c.axis}{c.direction[:1]} {c.level:g} seed={seed} success={r.success} steps={r.steps}')
    summary=summarize(rows); print(save(rows,args.output_csv)); print(save(summary,args.summary_csv)); return rows,summary
def main()->int:
    try: sweep(parse_args())
    except Exception as e: print(f'[FAIL] {type(e).__name__}: {e}',file=sys.stderr); return 1
    return 0
if __name__=='__main__': raise SystemExit(main())

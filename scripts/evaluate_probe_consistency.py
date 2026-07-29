"""Evaluate whether repeated Agent-visible probes identify stochastic OOD noise."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from statistics import mean,median
from typing import Any,Sequence
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts.build_autoresearch_benchmark import get_conditions,save_csv  # noqa:E402
from src.diagnostic_probes import (build_repeated_agent_probe_context,estimate_planar_bias,
 run_repeated_symmetric_probes)  # noqa:E402
from src.rollout import create_push_environment  # noqa:E402

def parse()->argparse.Namespace:
 p=argparse.ArgumentParser(description=__doc__);p.add_argument("--seed-start",type=int,default=300)
 p.add_argument("--num-seeds",type=int,default=10);p.add_argument("--repeats",type=int,default=4)
 p.add_argument("--probe-steps",type=int,default=4);p.add_argument("--probe-magnitude",type=float,default=.2)
 p.add_argument("--fixed-threshold",type=float)
 p.add_argument("--noise-selection",type=Path,default=ROOT/"outputs/autoresearch/noise_calibration/selected.json")
 p.add_argument("--output-dir",type=Path,default=ROOT/"outputs/autoresearch/probe_consistency_tuning");return p.parse_args()

def select_threshold(rows:Sequence[dict[str,Any]])->dict[str,float]:
 """Oracle-only tuning selection; higher ties protect recoverable bias cases."""
 if not rows or {bool(r["is_stochastic_ood"]) for r in rows}!={False,True}:raise ValueError("both classes are required")
 scores=sorted({float(r["estimated_bias_std_norm"]) for r in rows})
 candidates=[scores[0]-1e-12,*[(a+b)/2 for a,b in zip(scores,scores[1:])],scores[-1]+1e-12]
 positives=[r for r in rows if r["is_stochastic_ood"]];negatives=[r for r in rows if not r["is_stochastic_ood"]]
 evaluated=[]
 for threshold in candidates:
  tpr=sum(float(r["estimated_bias_std_norm"])>threshold for r in positives)/len(positives)
  tnr=sum(float(r["estimated_bias_std_norm"])<=threshold for r in negatives)/len(negatives)
  evaluated.append((.5*(tpr+tnr),threshold,tpr,tnr))
 balanced,threshold,tpr,tnr=max(evaluated,key=lambda x:(x[0],x[1]))
 auc=sum((float(p["estimated_bias_std_norm"])>float(n["estimated_bias_std_norm"]))+
         .5*(float(p["estimated_bias_std_norm"])==float(n["estimated_bias_std_norm"])) for p in positives for n in negatives)/(len(positives)*len(negatives))
 return {"threshold":threshold,"balanced_accuracy":balanced,"stochastic_recall":tpr,"bias_specificity":tnr,"roc_auc":auc}

def evaluate_fixed_threshold(rows:Sequence[dict[str,Any]],threshold:float)->dict[str,float]:
 if threshold<0 or not rows:raise ValueError("non-negative threshold and rows are required")
 positives=[r for r in rows if r["is_stochastic_ood"]];negatives=[r for r in rows if not r["is_stochastic_ood"]]
 if not positives or not negatives:raise ValueError("both classes are required")
 tpr=sum(float(r["estimated_bias_std_norm"])>threshold for r in positives)/len(positives)
 tnr=sum(float(r["estimated_bias_std_norm"])<=threshold for r in negatives)/len(negatives)
 return {"threshold":threshold,"balanced_accuracy":.5*(tpr+tnr),"stochastic_recall":tpr,"bias_specificity":tnr}

def main()->int:
 a=parse()
 try:
  if min(a.num_seeds,a.repeats,a.probe_steps)<=0:raise ValueError("positive experiment sizes required")
  noise=float(json.loads(a.noise_selection.read_text(encoding="utf-8"))["noise_std"]);rows=[]
  for condition in get_conditions(noise):
   for seed in range(a.seed_start,a.seed_start+a.num_seeds):
    groups=run_repeated_symmetric_probes(lambda:create_push_environment(seed),seed=seed,
     perturbation_factory=condition.build,repeats=a.repeats,magnitude=a.probe_magnitude,steps=a.probe_steps)
    estimates=tuple(estimate_planar_bias(group) for group in groups);context=build_repeated_agent_probe_context(groups,estimates)
    metric=context["consistency"]
    rows.append({"condition_id":condition.condition_id,"seed":seed,"is_stochastic_ood":condition.kind=="gaussian_noise",
     "probe_environment_steps":context["probe_environment_steps"],**metric})
    print(f"condition={condition.condition_id} seed={seed} bias_std_norm={metric['estimated_bias_std_norm']:.6f}")
  summary=[]
  for condition in get_conditions(noise):
   selected=[r for r in rows if r["condition_id"]==condition.condition_id];values=[float(r["estimated_bias_std_norm"]) for r in selected]
   summary.append({"condition_id":condition.condition_id,"episodes":len(selected),"mean_bias_std_norm":mean(values),
    "median_bias_std_norm":median(values),"min_bias_std_norm":min(values),"max_bias_std_norm":max(values),
    "mean_relative_bias_std":mean(float(r["relative_bias_std"]) for r in selected),
    "mean_sign_agreement":mean(float(r["dominant_axis_sign_agreement"]) for r in selected)})
  selection=(select_threshold(rows) if a.fixed_threshold is None else evaluate_fixed_threshold(rows,a.fixed_threshold))
  out=a.output_dir.resolve();save_csv(out/"results.csv",rows);save_csv(out/"summary.csv",summary)
  artifact=("threshold_selection.json" if a.fixed_threshold is None else "fixed_threshold_evaluation.json")
  metadata=({"selection_split":f"seeds {a.seed_start}-{a.seed_start+a.num_seeds-1}",
   "rule":"maximize balanced accuracy; higher threshold tie protects bias recovery"} if a.fixed_threshold is None else
   {"evaluation_split":f"seeds {a.seed_start}-{a.seed_start+a.num_seeds-1}","rule":"frozen threshold; no validation retuning"})
  (out/artifact).write_text(json.dumps({**selection,**metadata},indent=2),encoding="utf-8")
  print(json.dumps(selection,indent=2));return 0
 except Exception as e:print(f"[FAIL] {type(e).__name__}: {e}",file=sys.stderr);return 1
if __name__=="__main__":raise SystemExit(main())

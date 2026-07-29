"""Compute an evidence-only Research-Agent versus random-search comparison."""
from __future__ import annotations
import argparse,csv,json,sys
from pathlib import Path
from typing import Any
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts.build_autoresearch_benchmark import save_csv  # noqa:E402
def parse()->argparse.Namespace:
 p=argparse.ArgumentParser(description=__doc__);p.add_argument("--run-dir",type=Path,required=True);return p.parse_args()
def key(row:dict[str,str])->tuple[float,float,float]:
 return (-float(row["conditional_recovery_rate"]),float(row["mean_recovery_environment_steps"]),float(row["mean_final_object_goal_distance"]))
def main()->int:
 run=parse().run_dir.resolve()
 try:
  with (run/"candidate_summary.csv").open(encoding="utf-8") as f:rows=list(csv.DictReader(f))
  if not rows:raise ValueError("candidate summary is empty")
  ranked=sorted(rows,key=key);comparison=[{"rank":i,**row} for i,row in enumerate(ranked,1)]
  research=min((r for r in rows if r["method"]=="research_agent"),key=key)
  random=min((r for r in rows if r["method"]=="random_search"),key=key)
  rr=float(research["conditional_recovery_rate"]);cr=float(random["conditional_recovery_rate"])
  rs=float(research["mean_recovery_environment_steps"]);cs=float(random["mean_recovery_environment_steps"])
  audit:dict[str,Any]={
   "selection_order":["higher conditional recovery rate","lower mean recovery environment steps","lower final distance"],
   "best_research_config":research,"best_random_config":random,
   "recovery_rate_difference":rr-cr,"mean_step_difference":rs-cs,
   "tuning_conclusion":"research_agent_better" if key(research)<key(random) else "tie_or_random_better",
   "claim_boundary":"six tuning cases only; validation and held-out claims are not permitted"}
  save_csv(run/"candidate_ranking.csv",comparison)
  (run/"comparison.json").write_text(json.dumps(audit,indent=2),encoding="utf-8")
  print(json.dumps(audit,indent=2));return 0
 except Exception as e:print(f"[FAIL] {type(e).__name__}: {e}",file=sys.stderr);return 1
if __name__=="__main__":raise SystemExit(main())

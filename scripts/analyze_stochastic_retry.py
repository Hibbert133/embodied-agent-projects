"""Analyze tuning-to-validation promotion for value-aware stochastic retry."""
from __future__ import annotations
import argparse,csv,json,sys
from pathlib import Path
from typing import Any
ROOT=Path(__file__).resolve().parents[1]
def parse()->argparse.Namespace:
 p=argparse.ArgumentParser(description=__doc__);p.add_argument("--tuning-summary",type=Path,required=True);p.add_argument("--validation-summary",type=Path,required=True);p.add_argument("--output",type=Path,required=True);return p.parse_args()
def read(path:Path)->dict[str,dict[str,str]]:
 with path.open(encoding="utf-8") as f:return {r["method"]:r for r in csv.DictReader(f)}
def compare(rows:dict[str,dict[str,str]])->dict[str,float]:
 baseline=rows["bias_compensation"];value=rows["value_aware"]
 return {"baseline_recovery_rate":float(baseline["conditional_recovery_rate"]),"value_recovery_rate":float(value["conditional_recovery_rate"]),
  "recovery_rate_difference":float(value["conditional_recovery_rate"])-float(baseline["conditional_recovery_rate"]),
  "baseline_mean_steps":float(baseline["mean_recovery_environment_steps"]),"value_mean_steps":float(value["mean_recovery_environment_steps"]),
  "mean_step_difference":float(value["mean_recovery_environment_steps"])-float(baseline["mean_recovery_environment_steps"])}
def main()->int:
 a=parse()
 try:
  tuning=compare(read(a.tuning_summary));validation=compare(read(a.validation_summary));audit:dict[str,Any]={"tuning":tuning,"validation":validation,
   "promotion_decision":"reject" if validation["recovery_rate_difference"]<0 or (validation["recovery_rate_difference"]==0 and validation["mean_step_difference"]>=0) else "promote",
   "claim_boundary":"fault class and repeatability do not identify the highest-value recovery skill"}
  output=a.output.resolve();output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(audit,indent=2),encoding="utf-8");print(json.dumps(audit,indent=2));return 0
 except Exception as e:print(f"[FAIL] {type(e).__name__}: {e}",file=sys.stderr);return 1
if __name__=="__main__":raise SystemExit(main())

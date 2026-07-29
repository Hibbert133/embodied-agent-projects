"""Create paired promotion evidence for consistency-gated validation."""
from __future__ import annotations
import argparse,csv,json,sys
from pathlib import Path
from statistics import mean
from typing import Any
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts.build_autoresearch_benchmark import save_csv  # noqa:E402
def parse()->argparse.Namespace:
 p=argparse.ArgumentParser(description=__doc__);p.add_argument("--results-csv",type=Path,required=True);p.add_argument("--output-dir",type=Path,required=True);return p.parse_args()
def main()->int:
 a=parse()
 try:
  with a.results_csv.open(encoding="utf-8") as f:rows=list(csv.DictReader(f))
  grouped:dict[tuple[str,str],dict[str,dict[str,str]]]={}
  for row in rows:grouped.setdefault((row["condition_id"],row["seed"]),{})[row["method"]]=row
  deltas=[]
  for (condition,seed),methods in sorted(grouped.items()):
   reference=methods["research_r1_c1"];gated=methods["consistency_gated_r1_c1"]
   ref_success=reference["recovery_success"]=="True";gate_success=gated["recovery_success"]=="True"
   deltas.append({"condition_id":condition,"seed":seed,"reference_success":ref_success,"gated_success":gate_success,
    "outcome_change":"improved" if gate_success and not ref_success else "harmed" if ref_success and not gate_success else "unchanged",
    "reference_steps":reference["recovery_environment_steps"],"gated_steps":gated["recovery_environment_steps"],
    "step_delta":float(gated["recovery_environment_steps"])-float(reference["recovery_environment_steps"]),
    "gated_skill":gated["skill_id"],"consistency_score":gated["consistency_score"]})
  ref_rate=sum(r["reference_success"] for r in deltas)/len(deltas);gate_rate=sum(r["gated_success"] for r in deltas)/len(deltas)
  audit:dict[str,Any]={"cases":len(deltas),"reference_recovery_rate":ref_rate,"gated_recovery_rate":gate_rate,
   "recovery_rate_difference":gate_rate-ref_rate,"mean_step_difference":mean(float(r["step_delta"]) for r in deltas),
   "improved_outcomes":sum(r["outcome_change"]=="improved" for r in deltas),"harmed_outcomes":sum(r["outcome_change"]=="harmed" for r in deltas),
   "abstentions":sum(r["gated_skill"]=="abstain_and_escalate" for r in deltas)}
  audit["promotion_decision"]="reject" if audit["recovery_rate_difference"]<0 or (audit["recovery_rate_difference"]==0 and audit["mean_step_difference"]>=0) else "promote"
  audit["interpretation"]="stochastic-fault detection is not equivalent to predicting recovery value"
  out=a.output_dir.resolve();save_csv(out/"paired_deltas.csv",deltas);(out/"comparison.json").write_text(json.dumps(audit,indent=2),encoding="utf-8")
  print(json.dumps(audit,indent=2));return 0
 except Exception as e:print(f"[FAIL] {type(e).__name__}: {e}",file=sys.stderr);return 1
if __name__=="__main__":raise SystemExit(main())

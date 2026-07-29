"""Run two bounded Research-Agent rounds and a matched random-search control."""
from __future__ import annotations
import argparse,csv,json,subprocess,sys
from pathlib import Path
from typing import Any
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from scripts.build_autoresearch_benchmark import save_csv,save_jsonl  # noqa:E402
from src.autoresearch import (DOMINANCE_RATIOS,EVIDENCE_DETAILS,PROBE_MAGNITUDES,PROBE_STEPS,
 SECONDARY_AXIS_THRESHOLDS,SCHEDULE_OPTIONS,ExperimentBudget,RecoveryPolicyConfig)  # noqa:E402
from src.research_agent import AnthropicResearchAgent  # noqa:E402

def parse()->argparse.Namespace:
 p=argparse.ArgumentParser(description=__doc__); p.add_argument("--model",default="glm-5.1");p.add_argument("--base-url")
 p.add_argument("--api-timeout",type=float,default=300);p.add_argument("--api-max-retries",type=int,default=2)
 p.add_argument("--benchmark-dir",type=Path,default=ROOT/"outputs/autoresearch/benchmark_tuning")
 p.add_argument("--output-dir",type=Path,default=ROOT/"outputs/autoresearch/search_tuning")
 p.add_argument("--max-api-calls",type=int,default=100);p.add_argument("--max-environment-steps",type=int,default=30000)
 return p.parse_args()
def load_jsonl(p:Path)->list[dict[str,Any]]: return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
def choose_cases(cases_path:Path)->list[str]:
 with cases_path.open(encoding="utf-8") as file: rows=list(csv.DictReader(file))
 groups:dict[str,list[dict[str,str]]]={}
 for r in rows:
  if r["initial_success"]=="False": groups.setdefault(r["counterfactual_label"],[]).append(r)
 chosen:list[dict[str,str]]=[]; covered:set[str]=set()
 for label in sorted(groups):
  candidates=sorted(groups[label],key=lambda r:(r["condition_id"] in covered,r["case_id"]))
  chosen.append(candidates[0]);covered.add(candidates[0]["condition_id"])
 failed=sorted((r for values in groups.values() for r in values),key=lambda r:r["case_id"])
 for row in failed:
  if len(chosen)>=6: break
  if row["condition_id"] not in covered: chosen.append(row);covered.add(row["condition_id"])
 for row in failed:
  if len(chosen)>=6: break
  if row not in chosen: chosen.append(row)
 return [row["case_id"] for row in chosen]
def space()->dict[str,Any]:
 return {"probe_steps_per_direction":PROBE_STEPS,"probe_magnitude":PROBE_MAGNITUDES,
  "secondary_axis_threshold":SECONDARY_AXIS_THRESHOLDS,"dominance_ratio":DOMINANCE_RATIOS,
  "allowed_schedules":SCHEDULE_OPTIONS,"offer_abstain":[True],"evidence_detail":EVIDENCE_DETAILS,
  "max_recovery_rollouts":[1]}
def random_config(rng:np.random.Generator,i:int)->RecoveryPolicyConfig:
 return RecoveryPolicyConfig.from_mapping({"config_id":f"random_{i:02d}","probe_steps_per_direction":int(rng.choice(PROBE_STEPS)),
  "probe_magnitude":float(rng.choice(PROBE_MAGNITUDES)),"secondary_axis_threshold":float(rng.choice(SECONDARY_AXIS_THRESHOLDS)),
  "dominance_ratio":float(rng.choice(DOMINANCE_RATIOS)),"allowed_schedules":list(SCHEDULE_OPTIONS[int(rng.integers(0,len(SCHEDULE_OPTIONS)))]),
  "offer_abstain":True,"evidence_detail":str(rng.choice(EVIDENCE_DETAILS)),"max_recovery_rollouts":1})
def ensure_fresh_output(output:Path)->None:
 if (output/"candidate_summary.csv").exists():
  raise RuntimeError(
   f"output directory already contains a completed run: {output}; "
   "choose a new --output-dir to preserve API and budget audit history"
  )
def evaluate(config:RecoveryPolicyConfig,a:argparse.Namespace,case_ids:list[str],method:str)->dict[str,Any]:
 dest=a.output_dir/method/config.config_id; dest.mkdir(parents=True,exist_ok=True); config_path=dest/"candidate.json"
 config_path.write_text(json.dumps(config.to_dict(),indent=2),encoding="utf-8")
 command=[sys.executable,str(ROOT/"scripts/evaluate_research_config.py"),"--config",str(config_path),"--agent-cases",str(a.benchmark_dir/"agent_cases.jsonl"),
  "--oracle-audit",str(a.benchmark_dir/"oracle_audit.jsonl"),"--case-ids",*case_ids,"--output-dir",str(dest)]
 subprocess.run(command,check=True)
 row=next(csv.DictReader((dest/"summary.csv").open(encoding="utf-8"))); return {"method":method,**row}
def main()->int:
 a=parse(); output=a.output_dir.resolve(); budget=ExperimentBudget(a.max_api_calls,a.max_environment_steps)
 try:
  ensure_fresh_output(output)
  ids=choose_cases(a.benchmark_dir/"cases.csv"); all_cases={x["case_id"]:x for x in load_jsonl(a.benchmark_dir/"agent_cases.jsonl")}; visible=[all_cases[x] for x in ids]
  agent=AnthropicResearchAgent(model=a.model,base_url=a.base_url,timeout_seconds=a.api_timeout,max_retries=a.api_max_retries)
  results=[]; audits=[]; used=set(); prior=[]
  for round_id in (1,2):
   budget.consume_api_call(); proposal,audit=agent.propose(agent_cases=visible,prior_results=prior,search_space=space(),round_id=round_id)
   audits.append({"round":round_id,"proposal":{"candidates":[x.to_dict() for x in proposal.candidates],"hypothesis":proposal.hypothesis,
    "targeted_counterexample_ids":proposal.targeted_counterexample_ids,"expected_metric_change":proposal.expected_metric_change},"request_audit":audit})
   for config in proposal.candidates:
    if config.config_id in used: raise RuntimeError(f"duplicate config_id across rounds: {config.config_id}")
    used.add(config.config_id); row=evaluate(config,a,ids,"research_agent"); results.append(row); prior.append(row)
    budget.consume_environment_steps(int(sum(float(r["total_recovery_environment_steps"]) for r in csv.DictReader((output/"research_agent"/config.config_id/"results.csv").open(encoding="utf-8")))))
   save_csv(output/"candidate_summary.csv",results);save_jsonl(output/"research_agent_audit.jsonl",audits)
  rng=np.random.default_rng(20260729)
  for i in range(1,5):
   config=random_config(rng,i); row=evaluate(config,a,ids,"random_search");results.append(row)
   budget.consume_environment_steps(int(sum(float(r["total_recovery_environment_steps"]) for r in csv.DictReader((output/"random_search"/config.config_id/"results.csv").open(encoding="utf-8")))))
  save_csv(output/"candidate_summary.csv",results);(output/"budget.json").write_text(json.dumps(budget.to_dict(),indent=2),encoding="utf-8")
  (output/"selected_case_ids.json").write_text(json.dumps(ids,indent=2),encoding="utf-8")
  print(f"summary: {(output/'candidate_summary.csv').resolve()}");print(f"budget: {(output/'budget.json').resolve()}");return 0
 except Exception as e: print(f"[FAIL] {type(e).__name__}: {e}",file=sys.stderr);return 1
if __name__=="__main__":raise SystemExit(main())

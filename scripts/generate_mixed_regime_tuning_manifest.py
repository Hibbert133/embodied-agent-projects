"""Generate an immutable mixed persistent-regime tuning manifest."""

from __future__ import annotations

import hashlib, json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from scripts.run_probemem_v2_smoke import _seed  # noqa: E402

CONFIG=Path("configs/probemem_online/mixed_regime_tuning_v1.json")
IMPLEMENTATION=(Path("scripts/generate_mixed_regime_tuning_manifest.py"),Path("scripts/run_mixed_regime_tuning.py"),Path("src/perturbations.py"),Path("scripts/run_probemem_v2_smoke.py"),Path("src/rollout/engine.py"))
INPUTS=(Path("configs/autoresearch/default_recovery_config.json"),Path("configs/probemem_online/seed_registry_v1.json"),Path("outputs/probemem_online/bootstrap_runs/probemem_online_bootstrap_20260803T093056Z_6e6c4ba0f6fe/bootstrap_snapshot.json"))

def _git(*args:str)->str:return subprocess.run(["git","-c",f"safe.directory={ROOT.as_posix()}",*args],cwd=ROOT,check=True,capture_output=True,text=True).stdout.strip()
def _sha(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def _hash(value:Any)->str:return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def build_units(config:dict[str,Any])->list[dict[str,Any]]:
    start,stop=map(int,config["seed_range"]); ns=config["random_namespaces"]
    return [{"unit_id":len(config["regimes"])*(seed-start)+index+1,"environment_seed":seed,"regime_id_oracle":regime["regime_id"],
             "initial_perturbation_seed":_seed(seed+index*100000,int(ns["initial_perturbation"])),
             "diagnostic_probe_seed":_seed(seed+index*100000,int(ns["registered_probe"])),
             "paired_verification_seed":_seed(seed+index*100000,int(ns["paired_verification"]))}
            for seed in range(start,stop+1) for index,regime in enumerate(config["regimes"])]

def main()->int:
    try:
        if _git("status","--porcelain"):raise RuntimeError("mixed tuning manifest requires clean worktree")
        config=json.loads((ROOT/CONFIG).read_text(encoding="utf-8")); units=build_units(config)
        if len(units)!=100:raise ValueError("mixed tuning requires 100 crossed units")
        commit=_git("rev-parse","HEAD"); stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"); run_id=f"probemem_online_mixed_tuning_{stamp}_{commit[:12]}"
        manifest={"schema_version":1,"experiment_run_id":run_id,"source_git_commit":commit,"created_at_utc":stamp,"config_path":CONFIG.as_posix(),"config_sha256":_sha(ROOT/CONFIG),"implementation_sha256":{p.as_posix():_sha(ROOT/p) for p in IMPLEMENTATION},"input_sha256":{p.as_posix():_sha(ROOT/p) for p in INPUTS},"population_units":units}
        manifest["manifest_id"]=_hash(manifest); out=ROOT/"outputs/probemem_online/mixed_tuning_runs"/run_id; out.mkdir(parents=True,exist_ok=False); (out/"immutable_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8"); print(f"manifest: {out/'immutable_manifest.json'}");return 0
    except Exception as exc:print(f"[FAIL] {type(exc).__name__}: {exc}",file=sys.stderr);return 1
if __name__=="__main__":raise SystemExit(main())

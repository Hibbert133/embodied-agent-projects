"""Immutable allocation, split gates, source hashes and resources for response qualification."""
from datetime import datetime, timezone
from contextlib import contextmanager
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import socket
from unittest.mock import patch

import numpy as np

ROOT=Path(__file__).resolve().parents[2]
DESIGN="configs/movement_task/response_model_qualification_design_v1.json"
DESIGN_SHA="1934b0e6c0382478e10825365b0cc2dcb5940359b4aca2f48bb907472e6e52d7"
DESIGN_DOC="docs/protocols/movement_response_model_qualification_design_v1.md"
DESIGN_DOC_SHA="84cd9e937b55b40bd6ac46a10affe8dac5bd9178183d89a165771d315cd54e7a"
CONFIG=ROOT/"configs/movement_task/response_model_qualification_execution_v1.json"
PROTOCOL="docs/protocols/movement_response_model_qualification_execution_v1.md"
OUTPUT=ROOT/"outputs/response_model_qualification/development_v1"
VALIDATION=ROOT/"outputs/response_model_qualification/freeze_validation_v1"
OLD_RUN="outputs/movement_task/development_v1/movement_task_20261019T191708Z_eee0803df5bf"
C8="outputs/cold_start_evidence/qualification_v1/cold_start_evidence_20261015T170124Z_c5b76fb5ddb6/models.json"
C8_SHA="08d2f6a7451e8e6f63aed9bf5bd15ce34158b2c219025547a483f6d925b423ad"
OLD_ARX="outputs/forward_prediction/baselines_v1/forward_prediction_20261014T064233Z_bb812df15401/models.json"
OLD_ARX_SHA="b3f2d7e69316dba65e722d74d49df25c7d651043e78bf4c0f6e1d37f1e599c80"
TASKS=("push-v3","reach-v3","door-open-v3")
SPLITS=("TRAIN","CAL","QUAL")
IDENTITY=("experiment_run_id","manifest_id","source_git_commit")
REQUIRED=("src/probe/response_qualification_behavior_v1.py","src/probe/response_qualification_model_v1.py",
    "src/analysis/response_qualification_io_v1.py","src/analysis/response_qualification_collect_v1.py",
    "src/analysis/response_qualification_evaluation_v1.py","src/analysis/response_qualification_audit_v1.py",
    "scripts/run_response_model_qualification_v1.py","scripts/audit_response_model_qualification_v1.py",
    "scripts/report_response_model_qualification_v1.py","tests/test_response_qualification_v1.py",PROTOCOL)


def require(ok,message):
    if not ok:raise ValueError(message)


def read(path):
    def unique(pairs):
        result={}
        for k,v in pairs:
            if k in result:raise ValueError("duplicate JSON key")
            result[k]=v
        return result
    return json.loads(Path(path).read_text(encoding="utf-8"),object_pairs_hook=unique)


def write(path,value,exclusive=True):
    with Path(path).open("x" if exclusive else "w",encoding="utf-8",newline="\n") as f:
        json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False);f.write("\n")


def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda:f.read(1048576),b""):h.update(b)
    return h.hexdigest()


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
def git(*args):return subprocess.check_output(["git",*args],cwd=ROOT,text=True).strip()


@contextmanager
def forbid_online_calls(receipt):
    """No scientific entry point has an online client; also reject transport attempts."""
    receipt["attempted_network_calls"]=0
    def denied(*args,**kwargs):
        receipt["attempted_network_calls"]+=1
        raise RuntimeError("Online network calls forbidden in this frozen study")
    with patch.object(socket.socket,"connect",denied),patch.object(socket.socket,"connect_ex",denied),patch.object(socket,"create_connection",denied):yield


def design():
    require(sha(ROOT/DESIGN)==DESIGN_SHA and sha(ROOT/DESIGN_DOC)==DESIGN_DOC_SHA,"frozen qualification design changed")
    return read(ROOT/DESIGN)


def population(split):
    require(split in SPLITS,"registered split required")
    groups,start=(18,26000) if split=="TRAIN" else (9,26100) if split=="CAL" else (18,26200)
    variants=("N47001","N47002") if split!="QUAL" else ("UNCHANGED","CHANGED")
    return [{"case_id":f"{split}/{g:02d}/{task}/{variant}","split":split,"group":g,"unit":3*g+i,
        "task":task,"seed":start+3*g+i,"variant":variant,"planned_boundary":(16,32,64)[g%3],
        "noise_namespace":47001 if variant!="N47002" else 47002}
        for g in range(groups) for i,task in enumerate(TASKS) for variant in variants]


def initial_fault(split):return {"matrix_xy":[[1.,0.],[0.,1.]],"bias_xy":[.12,-.08] if split=="QUAL" else [0.,0.],"deadzone_xy":[0.,0.]}


def destination(spec):
    if spec["split"]!="QUAL" or spec["variant"]=="UNCHANGED":return initial_fault(spec["split"])
    rng=np.random.default_rng(np.random.SeedSequence([89003,spec["group"]]))
    return {"matrix_xy":[[float(rng.uniform(.75,1.25)),float(rng.uniform(-.2,.2))],
        [float(rng.uniform(-.2,.2)),float(rng.uniform(.75,1.25))]],"bias_xy":rng.uniform(-.2,.2,2).tolist(),"deadzone_xy":[0.,0.]}


def noise(seed,namespace):
    require(namespace in (47001,47002),"registered noise namespace")
    key=int(np.random.SeedSequence([seed,namespace]).generate_state(1)[0])
    value=np.random.default_rng(key).normal(0,.05,(500,3)).astype("<f4");value.flags.writeable=False;return value


def expected_config():
    return {"protocol_id":"movement_response_model_qualification_execution_v1","design_sha256":DESIGN_SHA,
        "population":{s:population(s) for s in SPLITS},"max_total_steps":43200,"max_all_resets":13770,
        "max_controlled_resets":270,"max_frames":7101000,"per_execution_steps":160,
        "tail_steps":32,"movement_steps":64,"new_api_calls":0,"response_model_fits":6,
        "ridge":.001,"bootstrap_seed":20261025,"bootstrap_replicates":10000,
        "training_rows":"ALL_RECORDED_STEPS_WITH_TWO_REAL_PRIOR_DISPLACEMENTS",
        "calibration_quantiles":[.5,.9,.95],"missing_primary":"NO_ZERO_FILL; REQUIRE_ALL_18_GROUPS_HAVE_AT_LEAST_ONE_PAIRED_UNIT_AND_ALL_SIX_TASK_CONDITION_CELLS_AVAILABLE",
        "training_weight":"EACH_TRAJECTORY_TOTAL_WEIGHT_ONE; EACH_RESPONSE_WEIGHT_ONE_OVER_T",
        "output_root":"outputs/response_model_qualification/development_v1"}


def validate(config):require(digest(config)==digest(expected_config()),"execution allocation or numeric protocol changed")


def rows(path):
    with gzip.open(path,"rt",encoding="utf-8") as f:
        for line in f:yield json.loads(line)


def seed_scope():
    proposed=((26000,26053),(26100,26126),(26200,26253),(26300,26599))
    own={DESIGN,DESIGN_DOC,CONFIG.relative_to(ROOT).as_posix(),PROTOCOL}
    files=set((ROOT/"configs").rglob("*.json"))|set((ROOT/"outputs").rglob("manifest.json"))|set((ROOT/"docs/protocols").glob("*seed*.json"))
    inputs={};collisions=[]
    overlaps=lambda a,b:any(a<=hi and lo<=b for lo,hi in proposed)
    def walk(value,path,loc=""):
        if isinstance(value,dict):
            for k,v in value.items():
                if "seed" in k.lower() and not any(x in k.lower() for x in ("noise","namespace","bootstrap","generator","nonce")):
                    if type(v) is int and overlaps(v,v):collisions.append([path,loc+k,v])
                    if isinstance(v,list):
                        numbers=[x for x in v if type(x) is int]
                        if len(v)==len(numbers)==2 and numbers[0]<=numbers[1]:
                            if overlaps(*numbers):collisions.append([path,loc+k,numbers])
                        elif any(overlaps(x,x) for x in numbers):collisions.append([path,loc+k,"SEED_LIST_OVERLAP"])
                walk(v,path,loc+k+".")
            if type(value.get("seed_start")) is int:
                a=value["seed_start"];b=value.get("seed_end",a+value.get("num_seeds",1)-1)
                if type(b) is int and overlaps(a,b):collisions.append([path,loc,[a,b]])
        elif isinstance(value,list):
            for v in value:walk(v,path,loc)
    for path in sorted(files):
        name=path.relative_to(ROOT).as_posix()
        if name in own:continue
        inputs[name]=sha(path);walk(read(path),name)
    for path in sorted((ROOT/"docs/protocols").glob("*.md")):
        name=path.relative_to(ROOT).as_posix()
        if name in own:continue
        inputs[name]=sha(path)
        for line in path.read_text(encoding="utf-8").splitlines():
            if re.search("seed|种子|预留|保留",line,re.I):
                for a,b in re.findall(r"\b(\d{4,6})\s*(?:--|–|\.\.|-)\s*(\d{4,6})\b",line):
                    if overlaps(int(a),int(b)):collisions.append([name,a,b])
    require(not collisions,"registered seed collision: "+str(collisions[:3]))
    return {"status":"PASSED_NO_EXTERNAL_REGISTERED_COLLISION","proposed_ranges":proposed,"excluded_own_reservation_files":sorted(own),"inputs_sha256":inputs,"collisions":collisions}


def clean():
    require(not git("status","--porcelain","--untracked-files=no"),"clean tracked source required")
    tracked=set(git("ls-files").splitlines())
    require(all(p in tracked for p in (*REQUIRED,CONFIG.relative_to(ROOT).as_posix())),"complete implementation, audits and tests must be committed")
    require(not git("ls-files","--others","--exclude-standard","src","scripts","tests","configs/movement_task"),"uncommitted research code")


def prepare():
    clean();design();config=read(CONFIG);validate(config)
    require(not list(OUTPUT.glob("*/manifest.json")),"one-shot allocation already prepared")
    scope=seed_scope()
    old=read(ROOT/OLD_RUN/"manifest.json")
    require(sha(ROOT/OLD_RUN/"manifest.json")=="3321f87afc0273a3533b4550b100f5d6a55046a9c1a4879b39c8791a9a42de9d","wrong frozen runtime source")
    require(sha(ROOT/C8)==C8_SHA and sha(ROOT/OLD_ARX)==OLD_ARX_SHA,"frozen nominal model source changed")
    for name,expected in old["input_sha256"].items():require(sha(ROOT/name)==expected,"prior frozen input changed: "+name)
    for mode in ("unittest","compileall","pip_check","tracked_secret_scan","diff_check"):
        r=read(VALIDATION/(mode+"_receipt.json"));require(r["returncode"]==0 and sha(VALIDATION/(mode+".txt"))==r["output_sha256"],"passed repository check required")
        inputs=read(VALIDATION/r["code_inputs_file"])
        require(sha(VALIDATION/r["code_inputs_file"])==r["code_inputs_sha256"] and all(sha(ROOT/n)==h for n,h in inputs.items()),"validation source mismatch")
    names=set(old["input_sha256"])|set(git("ls-files","src","scripts","tests").splitlines())|set(REQUIRED)|{DESIGN,DESIGN_DOC,CONFIG.relative_to(ROOT).as_posix(),C8,OLD_ARX,OLD_RUN+"/manifest.json"}
    names|={p.relative_to(ROOT).as_posix() for p in VALIDATION.iterdir() if p.is_file()}
    commit=git("rev-parse","HEAD");run_id="response_qualification_"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_"+commit[:12]
    manifest={"experiment_run_id":run_id,"source_git_commit":commit,"config":config,"seed_scope":scope,
        "input_sha256":{n:sha(ROOT/n) for n in sorted(names)},**{k:old[k] for k in ("library_source_sha256","native_library_sha256","policy_sha256")}}
    manifest["manifest_id"]=digest(manifest);folder=OUTPUT/run_id;folder.mkdir(parents=True)
    write(folder/"manifest.json",manifest);print((folder/"manifest.json").relative_to(ROOT).as_posix(),flush=True)


def load(path):
    manifest=read(path);validate(manifest["config"]);design()
    require(digest({k:v for k,v in manifest.items() if k!="manifest_id"})==manifest["manifest_id"],"manifest changed")
    for name,expected in manifest["input_sha256"].items():require(sha(ROOT/name)==expected,"frozen input changed: "+name)
    return manifest


def phase_gate(folder,split):
    require(split in SPLITS,"registered split")
    if split=="CAL":
        require(read(folder/"training/completion.json")["status"]=="MODELS_SAVED_TRAIN_ONLY","TRAIN models required before CAL")
        require(read(folder/"training/audit.json")["integrity"]=="PASSED","independent TRAIN numerical audit required before CAL")
    if split=="QUAL":
        lock=read(folder/"qualification_lock.json")
        for name,expected in lock["artifact_sha256"].items():require(sha(folder/name)==expected,"pre-QUAL models/CAL artifact changed")
        require(lock["status"]=="FROZEN_BEFORE_QUAL_COLLECTION","pre-QUAL lock required")

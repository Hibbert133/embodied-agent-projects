"""Independent allocation and immutable gates for observable-history transfer v1."""
from datetime import datetime,timezone
from pathlib import Path
import re
import shutil
import numpy as np

from src.analysis.response_qualification_io_v1 import (ROOT,read,write,sha,digest,git,require,rows,forbid_online_calls,C8,C8_SHA,TASKS,IDENTITY)

CONFIG=ROOT/"configs/movement_task/observable_history_transfer_execution_v1.json"
PROTOCOL="docs/protocols/observable_history_transfer_execution_v1_zh.md"
DESIGN="configs/movement_task/observable_history_transfer_design_v1.json"
DESIGN_SHA="1dc9c743bab56375fa97d728d2188a6fae1e72c2eabb1baf302d15da25d557a9"
DESIGN_DOC="docs/protocols/observable_history_transfer_design_v1_zh.md"
DESIGN_DOC_SHA="849ad2a80322c1bf694904ea93e4eeb8857236bfe306d133c3623d9634e90252"
PREVIOUS="outputs/response_model_qualification/development_v1/response_qualification_20261020T092011Z_636d6b1f9e39"
OUTPUT=ROOT/"outputs/observable_history_transfer/development_v1"
VALIDATION=ROOT/"outputs/observable_history_transfer/freeze_validation_v1"
RUNTIME=ROOT/"outputs/observable_history_transfer/runtime_v1/environment.json"
TRAIN_PYTHON=Path("C:/Users/Administrator/Documents/ChatGPT/robotic agent/.venv-history-training-cpu22/Scripts/python.exe")
SPLITS=("TRAIN","CAL","TEST")
PROGRAMS=("FEEDBACK8","BALANCED8")
MODELS=("HISTORY_LINEAR10","STATE_LINEAR20","QUADRATIC_STATE20","GRU_WINDOW1","GRU_WINDOW16")
REQUIRED=("src/probe/observable_history_behavior_v1.py","src/probe/observable_history_model_v1.py",
    "src/analysis/observable_history_io_v1.py","src/analysis/observable_history_collect_v1.py","src/analysis/observable_history_audit_v1.py",
    "src/analysis/observable_history_evaluation_v1.py","scripts/train_observable_history_gru_v1.py","scripts/run_observable_history_transfer_v1.py",
    "scripts/report_observable_history_transfer_v1.py","tests/test_observable_history_transfer_v1.py","tests/test_observable_history_pipeline_v1.py",PROTOCOL)


def population(split):
    require(split in SPLITS,"registered split")
    groups,start=(18,60000) if split=="TRAIN" else (9,60100) if split=="CAL" else (18,60200)
    contexts=("NOMINAL","RANDOM") if split!="TEST" else ("NOMINAL_UNCHANGED","NOMINAL_CHANGED","BIASED_UNCHANGED","BIASED_CHANGED")
    return [{"case_id":f"{split}/{g:02d}/{task}/{context}/{program}","split":split,"group":g,"unit":3*g+i,
        "task":task,"seed":start+3*g+i,"variant":context+"/"+program,"context":context,"measurement_program":program,
        "planned_boundary":(16,32,64)[g%3],"noise_namespace":57001}
        for g in range(groups) for i,task in enumerate(TASKS) for context in contexts for program in PROGRAMS]


def affine(group,namespace):
    rng=np.random.default_rng(np.random.SeedSequence([namespace,group]))
    return {"matrix_xy":[[float(rng.uniform(.75,1.25)),float(rng.uniform(-.2,.2))],
        [float(rng.uniform(-.2,.2)),float(rng.uniform(.75,1.25))]],"bias_xy":rng.uniform(-.2,.2,2).tolist(),"deadzone_xy":[0.,0.]}


def initial_fault(spec):
    if spec["context"]=="RANDOM":return affine(spec["group"],98001 if spec["split"]=="TRAIN" else 98002)
    return {"matrix_xy":[[1.,0.],[0.,1.]],"bias_xy":[.12,-.08] if spec["context"].startswith("BIASED") else [0.,0.],"deadzone_xy":[0.,0.]}


def destination(spec):return affine(spec["group"],98003) if spec["context"].endswith("_CHANGED") else initial_fault(spec)


def measurement_program(spec):
    namespace={"TRAIN":98011,"CAL":98012,"TEST":98013}[spec["split"]]
    rng=np.random.default_rng(np.random.SeedSequence([namespace,spec["group"]]))
    actions=np.array([[.4,0,0,-1],[0,.4,0,-1],[-.4,0,0,-1],[0,-.4,0,-1]]*2,np.float32)
    return actions[rng.permutation(8)].tolist()


def noise(seed,namespace=57001):
    require(namespace==57001,"registered noise namespace")
    key=int(np.random.SeedSequence([seed,namespace]).generate_state(1)[0]);value=np.random.default_rng(key).normal(0,.05,(500,3)).astype("<f4")
    value.flags.writeable=False;return value


def expected_config():
    return {"protocol":"observable_history_transfer_execution_v1","population":{s:population(s) for s in SPLITS},"design_sha256":DESIGN_SHA,
        "programs":list(PROGRAMS),"models":list(MODELS),"per_execution_steps":168,"measurement_steps":8,"tail_steps":32,"movement_steps":64,
        "limits":{"executions":756,"control_steps":127008,"controlled_resets":756,"factory_resets":37800,"all_resets":38556,"physical_frames":19913040,"c4_c8_fit_attempts":1512,"response_fits":30},
        "gru":{"input_size":43,"hidden_size":32,"layers":1,"updates":5000,"batch_trajectories":32,"learning_rate":.001,"optimizer":"Adam","betas":[.9,.999],"eps":1e-8,"weight_decay":0.,
            "window_lengths":[1,16],"cpu_threads":1,"dtype":"float32","input_and_target_normalization":"TRAJECTORY_WEIGHTED_TRAIN_ONLY; SCALE_LE_1E-6_TO_ONE", "sampling":"UNIFORM_TRAJECTORY_THEN_UNIFORM_COMMON_TARGET_INDEX_T_GE_2",
            "initialization_seed_base":202610260,"sampling_seed_base":202610270,"same_init_across_windows":True,"gradient_clipping":None},
        "common_target_population":"ACTUAL_STEPS_T_GE_2_FOR_ALL_FIVE_MODELS; HISTORY_WINDOWS_INCLUDE_TRUE_INITIAL",
        "ridge":.001,"bootstrap":{"replicates":10000,"seed":20261028,"unit":"18_WHOLE_GROUPS_STRATIFIED_BY_BOUNDARY"},
        "cal_quantiles":[.5,.9,.95],"new_api_calls":0,"policy_training":0,"missing_primary":"RETAIN_NULL; ALL_18_GROUPS_HAVE_A_PAIRED_UNIT; ALL_24_CELLS_AVAILABLE",
        "disk_free_floor_bytes":600*1024**2,"training_timeout_seconds":7200,"test_before_lock":False}


def validate(config):
    require(sha(ROOT/DESIGN)==DESIGN_SHA and sha(ROOT/DESIGN_DOC)==DESIGN_DOC_SHA,"draft design source changed")
    require(digest(config)==digest(expected_config()),"frozen execution protocol changed")


def seed_scope():
    proposed=((60000,60053),(60100,60126),(60200,60253),(60300,60599))
    own={CONFIG.relative_to(ROOT).as_posix(),PROTOCOL};files=set((ROOT/"configs").rglob("*.json"))|set((ROOT/"outputs").rglob("manifest.json"))|set((ROOT/"docs/protocols").glob("*seed*.json"));inputs={};collisions=[]
    overlap=lambda lo,hi:any(lo<=b and a<=hi for a,b in proposed)
    def visit(v,name,key=""):
        if isinstance(v,dict):
            for k,value in v.items():
                if "seed" in k.lower() and not any(x in k.lower() for x in ("noise","namespace","bootstrap","generator","nonce","initialization","sampling")):
                    if type(value) is int and overlap(value,value):collisions.append([name,key+k,value])
                    if isinstance(value,list) and all(type(x) is int for x in value):
                        if len(value)==2 and value[0]<=value[1] and overlap(*value):collisions.append([name,key+k,value])
                        elif len(value)!=2 and any(overlap(x,x) for x in value):collisions.append([name,key+k,"LIST_OVERLAP"])
                visit(value,name,key+k+".")
            if type(v.get("seed_start")) is int:
                start=v["seed_start"];end=v.get("seed_end",start+v.get("num_seeds",1)-1)
                if type(end) is int and overlap(start,end):collisions.append([name,key,[start,end]])
        elif isinstance(v,list):
            for item in v:visit(item,name,key)
    for path in sorted(files):
        name=path.relative_to(ROOT).as_posix()
        if name in own:continue
        inputs[name]=sha(path);visit(read(path),name)
    for path in sorted((ROOT/"docs/protocols").glob("*.md")):
        name=path.relative_to(ROOT).as_posix()
        if name in own:continue
        inputs[name]=sha(path)
        for line in path.read_text(encoding="utf-8").splitlines():
            if re.search("seed|种子|预留|保留",line,re.I):
                for lo,hi in re.findall(r"\b(\d{4,6})\s*(?:--|–|\.\.|-)\s*(\d{4,6})\b",line):
                    if overlap(int(lo),int(hi)):collisions.append([name,lo,hi])
    require(not collisions,"seed range used/reserved: "+str(collisions[:3]))
    return {"status":"PASSED_NO_REGISTERED_COLLISION","proposed_ranges":proposed,"inputs_sha256":inputs,"own_registry_files":sorted(own),"collisions":collisions}


def clean():
    require(not git("status","--porcelain","--untracked-files=no"),"clean committed source required")
    tracked=set(git("ls-files").splitlines());require(all(n in tracked for n in (*REQUIRED,CONFIG.relative_to(ROOT).as_posix())),"collector/audits/models/tests/config must be frozen")
    require(not git("ls-files","--others","--exclude-standard","src","scripts","tests","configs/movement_task"),"uncommitted research implementation")


def phase_gate(root,split):
    require(split in SPLITS,"registered phase")
    if split=="CAL":require(read(root/"training/completion.json")["status"]=="THIRTY_MODELS_SAVED_TRAIN_ONLY" and read(root/"training/audit.json")["integrity"]=="PASSED","TRAIN model audit before CAL")
    if split=="TEST":
        lock=read(root/"test_lock.json");require(lock["status"]=="FROZEN_BEFORE_TEST","TEST requires pre-existing lock")
        for n,h in lock["artifact_sha256"].items():require(sha(root/n)==h,"TRAIN/CAL lock changed")


def check_disk():require(shutil.disk_usage(ROOT).free>=expected_config()["disk_free_floor_bytes"],"disk reserve exhausted: stop and retain partial records")


def prepare():
    clean();config=read(CONFIG);validate(config);check_disk();require(not list(OUTPUT.glob("*/manifest.json")),"one-shot study already allocated")
    scope=seed_scope();previous=read(ROOT/PREVIOUS/"manifest.json")
    for n,h in previous["input_sha256"].items():require(sha(ROOT/n)==h,"frozen old source changed: "+n)
    require(sha(ROOT/C8)==C8_SHA,"C8 nominal bank changed")
    for mode in ("unittest","compileall","pip_check","tracked_secret_scan","diff_check"):
        r=read(VALIDATION/(mode+"_receipt.json"));require(r["returncode"]==0,"passed check required: "+mode)
        inputs=read(VALIDATION/r["code_inputs_file"]);require(all(sha(ROOT/n)==h for n,h in inputs.items()) and sha(VALIDATION/(mode+".txt"))==r["output_sha256"],"validation source/result mismatch")
    runtime=read(RUNTIME)
    for n,h in runtime["file_sha256"].items():require(sha(n)==h,"training runtime changed")
    names=set(previous["input_sha256"])|set(git("ls-files","src","scripts","tests").splitlines())|set(REQUIRED)|{CONFIG.relative_to(ROOT).as_posix(),DESIGN,DESIGN_DOC,C8,PREVIOUS+"/manifest.json",RUNTIME.relative_to(ROOT).as_posix()}
    names|={p.relative_to(ROOT).as_posix() for p in VALIDATION.iterdir() if p.is_file()}
    commit=git("rev-parse","HEAD");run_id="observable_history_"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_"+commit[:12]
    m={"experiment_run_id":run_id,"source_git_commit":commit,"config":config,"seed_scope":scope,"training_python":str(TRAIN_PYTHON),"training_runtime":runtime,
        "input_sha256":{n:sha(ROOT/n) for n in sorted(names)},**{k:previous[k] for k in ("library_source_sha256","native_library_sha256","policy_sha256")}}
    m["manifest_id"]=digest(m);folder=OUTPUT/run_id;folder.mkdir(parents=True);write(folder/"manifest.json",m);print(folder/"manifest.json",flush=True)


def load(path):
    m=read(path);validate(m["config"]);require(digest({k:v for k,v in m.items() if k!="manifest_id"})==m["manifest_id"],"immutable manifest changed")
    for n,h in m["input_sha256"].items():require(sha(ROOT/n)==h,"frozen input changed: "+n)
    return m

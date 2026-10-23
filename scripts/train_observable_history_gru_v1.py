"""Isolated CPU trainer: strict public TRAIN bundle, fixed 1/16-frame GRUs."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter_ns

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
from src.probe.observable_history_model_v1 import HistoryTrajectory,inputs43,targets,gru_normalization,predict
from src.analysis.response_qualification_io_v1 import read,write,sha,require,forbid_online_calls,digest


def torch_module():
    import torch
    return torch


def configure():
    torch=torch_module();torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.use_deterministic_algorithms(True);torch.backends.mkldnn.enabled=False
    return torch


def network(torch):
    class Net(torch.nn.Module):
        def __init__(self):
            super().__init__();self.gru=torch.nn.GRU(43,32,batch_first=True);self.output=torch.nn.Linear(32,2)
        def forward(self,x,lengths):
            packed=torch.nn.utils.rnn.pack_padded_sequence(x,lengths,batch_first=True,enforce_sorted=False)
            _,h=self.gru(packed);return self.output(h[-1])
    return Net()


def parameters(net):
    return {"gru":{k:v.detach().cpu().numpy().tolist() for k,v in net.gru.state_dict().items()},
        "output_weight":net.output.weight.detach().cpu().numpy().tolist(),"output_bias":net.output.bias.detach().cpu().numpy().tolist()}


def training_schedule(rng,trajectories,batch=32):
    chosen=rng.integers(0,len(trajectories),size=batch)
    positions=np.array([rng.integers(2,len(trajectories[i].commands)) for i in chosen])
    return chosen,positions


def batch_arrays(trajectories,chosen,positions,window,statistics):
    x=np.zeros((len(chosen),window,43),np.float32);y=np.empty((len(chosen),2),np.float32);lengths=[]
    for j,(i,t) in enumerate(zip(chosen,positions)):
        public=inputs43(trajectories[i]);start=max(0,t-window+1);real=(public[start:t+1]-statistics["input_mean"])/statistics["input_scale"]
        x[j,:len(real)]=real;lengths.append(len(real));y[j]=(targets(trajectories[i])[t-2]-statistics["target_mean"])/statistics["target_scale"]
    return x,y,lengths


def fit_gru(torch,trajectories,task,window,initial_seed,sampling_seed,statistics,updates=5000,log=None):
    require(window in (1,16) and trajectories and all(t.task==task and t.split=="TRAIN" for t in trajectories),"strict TRAIN task data")
    require(all(len(t.commands)>=3 for t in trajectories),"common targets required")
    expected=gru_normalization(trajectories,task)
    for k in ("input_mean","input_scale","target_mean","target_scale"):require(np.allclose(statistics[k],expected[k],atol=1e-12,rtol=1e-9),"TRAIN normalization differs")
    start=perf_counter_ns();torch.manual_seed(initial_seed);net=network(torch);initial=digest(parameters(net));optimizer=torch.optim.Adam(net.parameters(),lr=.001,betas=(.9,.999),eps=1e-8,weight_decay=0.)
    rng=np.random.default_rng(sampling_seed);schedule=hashlib.sha256();losses=[]
    for index in range(updates):
        chosen,positions=training_schedule(rng,trajectories);schedule.update(np.array([chosen,positions],dtype="<i8").tobytes())
        x,y,lengths=batch_arrays(trajectories,chosen,positions,window,statistics)
        optimizer.zero_grad(set_to_none=True);output=net(torch.from_numpy(x),lengths);loss=torch.mean((output-torch.from_numpy(y))**2)
        require(bool(torch.isfinite(loss)),"nonfinite TRAIN loss; do not repair using CAL/TEST")
        loss.backward();require(all(p.grad is not None and bool(torch.isfinite(p.grad).all()) for p in net.parameters()),"nonfinite gradient")
        optimizer.step()
        if index==0 or (index+1)%500==0 or index+1==updates:
            entry={"update":index+1,"standardized_train_batch_mse":float(loss.detach()),"schedule_sha256_so_far":schedule.hexdigest()};losses.append(entry)
            if log is not None:log(entry)
    model={"method":"GRU_WINDOW"+str(window),"task":task,"window":window,"hidden_size":32,**statistics,**parameters(net),
        "initialization_seed":initial_seed,"sampling_seed":sampling_seed,"initial_parameters_sha256":initial,"sampling_schedule_sha256":schedule.hexdigest(),
        "optimizer":"Adam","updates":updates,"batch_trajectories":32,"learning_rate":.001,"dtype_train":"float32","inference":"FROZEN_FLOAT32_WEIGHTS_WITH_FLOAT64_EVALUATION",
        "parameter_count":sum(p.numel() for p in net.parameters()),"torch_version":torch.__version__,"probability_guarantee":False,"wall_ns":perf_counter_ns()-start,"loss_checkpoints":losses}
    require(all(np.isfinite(p.detach().numpy()).all() for p in net.parameters()),"nonfinite saved weights")
    return model


def torch_predict(torch,model,t):
    net=network(torch).double();net.gru.load_state_dict({k:torch.tensor(v,dtype=torch.float64) for k,v in model["gru"].items()})
    net.output.load_state_dict({"weight":torch.tensor(model["output_weight"],dtype=torch.float64),"bias":torch.tensor(model["output_bias"],dtype=torch.float64)});net.eval()
    positions=np.arange(2,len(t.commands));chosen=np.zeros(len(positions),int)
    if not len(positions):return np.empty((0,2))
    # A separate exact-length encoding avoids any padded-value information.
    public=inputs43(t);out=[]
    with torch.no_grad():
        for index in positions:
            window=public[max(0,index-model["window"]+1):index+1]
            x=(window-model["input_mean"])/model["input_scale"]
            y=net(torch.tensor(x[None],dtype=torch.float64),[len(x)]).numpy()[0]
            out.append(y*np.array(model["target_scale"])+model["target_mean"])
    return np.array(out)


def runtime_receipt():
    torch=torch_module();names=[Path(sys.executable),Path(sys.prefix)/"pyvenv.cfg"]
    folder=Path(sys.prefix)/"Lib/site-packages"
    names.extend(p for p in folder.rglob("*") if p.is_file() and p.suffix not in (".pyc",".pyo") and "__pycache__" not in p.parts)
    base=Path(sys.base_prefix);names.extend(p for p in (base/"python312.dll",base/"python3.dll",base/"python.exe") if p.exists())
    return {"python":sys.version,"torch":torch.__version__,"numpy":np.__version__,"python_path":str(Path(sys.executable)),"base_prefix":sys.base_prefix,
        "file_sha256":{str(p):sha(p) for p in names},"new_scientific_fits":0,"new_environment_steps":0,"new_api_calls":0}


def train_bundle(bundle_path,output):
    torch=configure();require(torch.__version__.startswith("2.2.2"),"frozen isolated torch version required")
    bundle=read(bundle_path);require(set(bundle)=={"schema","entries"} and bundle["schema"]=="PUBLIC_TRAIN_BUNDLE_V1","strict bundle schema")
    output.mkdir();results={};attempts=[];failure=None;start=perf_counter_ns()
    with (output/"training_log.jsonl").open("x",encoding="utf-8",newline="\n") as log:
        try:
            for entry in bundle["entries"]:
                require(set(entry)=={"task","source_bank","trajectories","statistics","initialization_seed","sampling_seed"},"extra private bundle field")
                ts=[HistoryTrajectory.from_dict(t) for t in entry["trajectories"]];key=entry["source_bank"]+"/"+entry["task"];results[key]={}
                for window in (1,16):
                    attempt={"key":key,"window":window,"status":"ATTEMPTED"};attempts.append(attempt)
                    def logger(row):log.write(json.dumps({"key":key,"window":window,**row})+"\n");log.flush()
                    model=fit_gru(torch,ts,entry["task"],window,entry["initialization_seed"],entry["sampling_seed"],entry["statistics"],log=logger)
                    results[key][model["method"]]=model;attempt["status"]="SAVED"
                    write(output/(key.replace("/","_")+"_"+model["method"]+".json"),model)
        except BaseException as error:failure={"type":type(error).__name__,"message":str(error)}
    write(output/"completion.json",{"status":"TWELVE_GRU_MODELS_SAVED" if failure is None else "GRU_TRAINING_FAILED_NO_REPAIR","attempts":attempts,"fits_attempted":len(attempts),
        "fits_saved":sum(a["status"]=="SAVED" for a in attempts),"source_bundle_sha256":sha(bundle_path),"failure":failure,"wall_ns":perf_counter_ns()-start,"new_environment_steps":0,"new_api_calls":0})
    if failure is not None:raise RuntimeError(str(failure))


def audit_bundle(bundle_path,model_path,output):
    torch=configure();bundle=read(bundle_path);bank=read(model_path)["models"];count=0;max_error=0.;schedules={}
    for entry in bundle["entries"]:
        ts=[HistoryTrajectory.from_dict(t) for t in entry["trajectories"]];key=entry["source_bank"]+"/"+entry["task"]
        for window in (1,16):
            model=bank[entry["source_bank"]][entry["task"]]["GRU_WINDOW"+str(window)];rng=np.random.default_rng(model["sampling_seed"]);schedule=hashlib.sha256()
            for _ in range(5000):
                a,b=training_schedule(rng,ts);schedule.update(np.array([a,b],dtype="<i8").tobytes())
            require(schedule.hexdigest()==model["sampling_schedule_sha256"],"sampling source or chronology mismatch");schedules[key+"/"+str(window)]=schedule.hexdigest()
            for t in ts:
                expected=torch_predict(torch,model,t);actual=predict(model,t);error=float(np.max(abs(actual-expected))) if len(actual) else 0.
                require(error<1e-10,"independent NumPy/PyTorch GRU differs");count+=len(actual);max_error=max(max_error,error)
    write(output,{"integrity":"PASSED","kind":"NUMPY_VS_TORCH_FORWARD_AND_TRAIN_SCHEDULE_AUDIT","predictions_checked":count,"maximum_absolute_error":max_error,
        "schedules":schedules,"model_fits":0,"new_environment_steps":0,"new_api_calls":0,"scope":"No optimizer replay; frozen training code/runtime, sample schedules and independent forward equations checked."})


def forward_bundle(bundle_path,model_path,output):
    torch=configure();bundle=read(bundle_path);models=read(model_path)["models"]
    require(set(bundle)=={"schema","trajectories"} and bundle["schema"]=="PUBLIC_FORWARD_BUNDLE_V1","public forward schema")
    count=0;maximum=0.
    for raw in bundle["trajectories"]:
        t=HistoryTrajectory.from_dict(raw)
        for bank in ("FEEDBACK8","BALANCED8"):
            for name in ("GRU_WINDOW1","GRU_WINDOW16"):
                model=models[bank][t.task][name];a=predict(model,t);b=torch_predict(torch,model,t)
                error=0. if not len(a) else float(np.max(abs(a-b)));require(error<1e-10,"independent forward mismatch")
                count+=len(a);maximum=max(maximum,error)
    write(output,{"integrity":"PASSED","kind":"INDEPENDENT_NUMPY_TORCH_FORWARD","source_bundle_sha256":sha(bundle_path),"models_sha256":sha(model_path),
        "trajectories":len(bundle["trajectories"]),"predictions_checked":count,"maximum_absolute_error":maximum,"new_model_fits":0,"new_environment_steps":0,"new_api_calls":0})


def software(output):
    torch=configure();rng=np.random.default_rng(812345);trajectories=[]
    for j in range(6):
        initial=np.zeros(39);commands=rng.uniform(-.6,.6,(24,4));s=initial.copy();observations=[]
        for command in commands:s=s.copy();s[:2]+=.002*command[:2];s[3]=command[3];observations.append(s)
        trajectories.append(HistoryTrajectory("push-v3",f"SOFTWARE_ONLY_{j}","TRAIN",initial,commands,observations))
    stats=gru_normalization(trajectories,"push-v3");results=[]
    for window in (1,16):
        model=fit_gru(torch,trajectories,"push-v3",window,202610260,202610270,stats,updates=100)
        errors=[float(np.max(abs(torch_predict(torch,model,t)-predict(model,t)))) for t in trajectories]
        require(max(errors)<1e-10 and model["parameter_count"]==7458,"GRU reset/mask/parameter contract")
        require(model["loss_checkpoints"][-1]["standardized_train_batch_mse"]<model["loss_checkpoints"][0]["standardized_train_batch_mse"],"synthetic optimizer did not improve")
        results.append({"window":window,"maximum_forward_error":max(errors),"initial_parameters_sha256":model["initial_parameters_sha256"],"sampling_sha256":model["sampling_schedule_sha256"],"updates":100})
    require(results[0]["initial_parameters_sha256"]==results[1]["initial_parameters_sha256"] and results[0]["sampling_sha256"]==results[1]["sampling_sha256"],"window control initialization/sampling mismatch")
    write(output,{"integrity":"PASSED","results":results,"new_scientific_fits":0,"software_gru_fits":2,"new_environment_steps":0,"new_api_calls":0})


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("mode",choices=("runtime","train","audit","forward","software"));p.add_argument("--bundle",type=Path);p.add_argument("--models",type=Path);p.add_argument("--output",required=True,type=Path);args=p.parse_args()
    with forbid_online_calls({}):
        if args.mode=="runtime":write(args.output,runtime_receipt())
        elif args.mode=="train":train_bundle(args.bundle,args.output)
        elif args.mode=="audit":audit_bundle(args.bundle,args.models,args.output)
        elif args.mode=="forward":forward_bundle(args.bundle,args.models,args.output)
        else:software(args.output)

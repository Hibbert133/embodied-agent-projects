"""Frozen CPU training worker: FIT export only, no development-response access."""
import argparse
from pathlib import Path
import json
import sys
from time import perf_counter_ns
import shutil
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.analysis import response_training_controls_io_v1 as allocation
from src.analysis import observable_history_io_v1 as io
from src.probe import response_training_controls_v1 as core
from src.probe.observable_history_model_v1 import HistoryTrajectory, targets


def configure():
    import torch
    io.require(torch.__version__.startswith("2.2.2") and np.__version__ == "1.26.4", "qualified isolated runtime required")
    torch.set_num_threads(1); torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True); torch.backends.mkldnn.enabled = False
    return torch


def network(torch):
    class Net(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.gru = torch.nn.GRU(43, 32, batch_first=True)
            self.output = torch.nn.Linear(32, 2)
        def forward(self, x, lengths):
            packed = torch.nn.utils.rnn.pack_padded_sequence(x, lengths, batch_first=True, enforce_sorted=False)
            _, hidden = self.gru(packed)
            return self.output(hidden[-1])
    return Net()


def parameters(net):
    return {"gru": {k: v.detach().cpu().numpy().tolist() for k, v in net.gru.state_dict().items()},
        "output_weight": net.output.weight.detach().cpu().numpy().tolist(), "output_bias": net.output.bias.detach().cpu().numpy().tolist()}


def fit_one(torch, trajectories, task, feature, loss_kind, window, initial_seed, sampling_seed, attempt, updates=5000, logger=None):
    import hashlib
    core.training_data(trajectories, task)
    stats = core.statistics(trajectories, task, feature, loss_kind)
    cache = [core.prepared(t, stats, window) for t in trajectories]
    torch.manual_seed(initial_seed)
    net = network(torch)
    initial_hash = io.digest(parameters(net))
    optimizer = torch.optim.Adam(net.parameters(), lr=.001, betas=(.9, .999), eps=1e-8, weight_decay=0.)
    rng = np.random.default_rng(sampling_seed); schedule_hash = hashlib.sha256(); checkpoints = []
    start = perf_counter_ns(); attempt["updates_completed"] = 0
    for index in range(updates):
        chosen, positions = core.schedule(rng, trajectories)
        schedule_hash.update(np.asarray([chosen, positions+2], dtype="<i8").tobytes())
        x, y, lengths = core.minibatch(cache, chosen, positions)
        optimizer.zero_grad(set_to_none=True)
        predicted = net(torch.from_numpy(x), lengths)
        loss = torch.mean((predicted-torch.from_numpy(y))**2)
        io.require(bool(torch.isfinite(loss)), "nonfinite FIT loss")
        loss.backward()
        io.require(all(p.grad is not None and bool(torch.isfinite(p.grad).all()) for p in net.parameters()), "nonfinite FIT gradient")
        gradient_norm = float(torch.sqrt(sum(torch.sum(p.grad.detach()**2) for p in net.parameters())))
        optimizer.step(); attempt["updates_completed"] = index+1
        if index == 0 or (index+1) % 500 == 0 or index+1 == updates:
            entry = {"update": index+1, "batch_mse_before_update": float(loss.detach()), "gradient_norm": gradient_norm,
                "parameter_norm_after_update": float(torch.sqrt(sum(torch.sum(p.detach()**2) for p in net.parameters()))),
                "schedule_sha256_so_far": schedule_hash.hexdigest()}
            checkpoints.append(entry)
            if logger:
                logger(entry)
    io.require(all(bool(torch.isfinite(p).all()) for p in net.parameters()), "nonfinite saved FIT parameters")
    model = {"schema": "TRAINING_CONTROL_GRU_V1", "task": task, "feature": feature, "loss": loss_kind,
        "window": window, "stats": stats, **parameters(net), "initialization_seed": initial_seed,
        "sampling_seed": sampling_seed, "initial_parameters_sha256": initial_hash, "sampling_schedule_sha256": schedule_hash.hexdigest(),
        "updates": updates, "parameter_count": sum(p.numel() for p in net.parameters()), "active_parameter_count": 5250 if feature == "F20" else 7458,
        "fit_trajectory_ids_sha256": io.digest([t.trajectory_id for t in trajectories]), "checkpoints": checkpoints,
        "probability_guarantee": False, "wall_ns": perf_counter_ns()-start}
    io.require(model["parameter_count"] == 7458, "same architecture parameter count")
    return model


def torch_predict(torch, model, trajectory):
    """Independent framework double forward, with exact real sequence lengths."""
    net = network(torch).double()
    net.gru.load_state_dict({k: torch.tensor(v, dtype=torch.float64) for k, v in model["gru"].items()})
    net.output.load_state_dict({"weight": torch.tensor(model["output_weight"], dtype=torch.float64), "bias": torch.tensor(model["output_bias"], dtype=torch.float64)})
    stats = model["stats"]
    x = core.frames(trajectory, stats)
    n = len(x); out = []
    for first in range(0, n, 256):
        positions = range(first, min(n, first+256))
        lengths = [min(i+1, model["window"]) for i in positions]
        data = np.zeros((len(lengths), model["window"], 43), np.float64)
        for j, i in enumerate(positions):
            data[j, :lengths[j]] = x[max(0, i-model["window"]+1):i+1]
        with torch.no_grad():
            out.extend(net(torch.tensor(data), lengths).numpy())
    return np.asarray(out).reshape(n, 2)*stats["target_scale"]+stats["target_mean"]


def train(folder, torch):
    manifest = io.read(folder/"manifest.json"); cfg = manifest["config"]
    io.require(cfg == allocation.expected_config(), "frozen worker config")
    prepared = io.read(folder/"prepared.json")
    io.require(io.sha(folder/"fit_public.json") == prepared["fit_public_sha256"], "FIT export changed")
    source = allocation.read_bundle(folder/"fit_public.json", "FIT")
    output = folder/"training"; output.mkdir(exist_ok=False)
    attempts = []; models = {}; failure = None; start = perf_counter_ns()
    with (output/"attempts.jsonl").open("x", encoding="utf-8", newline="\n") as events, (output/"checkpoints.jsonl").open("x", encoding="utf-8", newline="\n") as logs:
        try:
            for k, entry in enumerate(source["entries"]):
                trajectories = [HistoryTrajectory.from_dict(t) for t in entry["trajectories"]]
                for feature in ("H10", "F20", "F43"):
                    key = f"{entry['source_bank']}/{entry['task']}/LINEAR_{feature}"
                    attempt = {"key": key, "kind": "LINEAR", "status": "STARTED", "updates_completed": 0}; attempts.append(attempt)
                    events.write(json.dumps(attempt)+"\n"); events.flush()
                    model = core.fit_linear(trajectories, entry["task"], feature)
                    path = key.replace("/", "_")+".json"; io.write(output/path, model)
                    models[key] = {"file": path, "sha256": io.sha(output/path), "kind": "LINEAR", "feature": feature, "task": entry["task"], "source": entry["source_bank"]}
                    attempt["status"] = "SAVED"; events.write(json.dumps(attempt)+"\n"); events.flush()
                for replicate in range(3):
                    initial_seed = cfg["initial_seed_base"]+6*replicate+k
                    sample_seed = cfg["sampling_seed_base"]+6*replicate+k
                    for feature in allocation.FEATURES:
                        for loss_kind in allocation.LOSSES:
                            for window in allocation.WINDOWS:
                                io.require(shutil.disk_usage(folder).free >= cfg["disk_free_floor_bytes"], "retain partial result: disk floor")
                                key = f"{entry['source_bank']}/{entry['task']}/{feature}_{loss_kind}_W{window}_R{replicate}"
                                attempt = {"key": key, "kind": "GRU", "status": "STARTED", "updates_completed": 0}; attempts.append(attempt)
                                events.write(json.dumps(attempt)+"\n"); events.flush()
                                def logger(row):
                                    logs.write(json.dumps({"key": key, **row})+"\n"); logs.flush()
                                model = fit_one(torch, trajectories, entry["task"], feature, loss_kind, window, initial_seed, sample_seed, attempt, logger=logger)
                                path = key.replace("/", "_")+".json"; io.write(output/path, model)
                                models[key] = {"file": path, "sha256": io.sha(output/path), "kind": "GRU", "feature": feature, "loss": loss_kind,
                                    "window": window, "replicate": replicate, "task": entry["task"], "source": entry["source_bank"]}
                                attempt["status"] = "SAVED"; events.write(json.dumps(attempt)+"\n"); events.flush()
                                print(json.dumps({"saved": len(models), "of": 162, "key": key, "wall_seconds": round((perf_counter_ns()-start)/1e9, 1)}), flush=True)
        except BaseException as error:
            failure = {"type": type(error).__name__, "message": str(error)}
    io.write(output/"models.json", {"manifest_id": manifest["manifest_id"], "models": models})
    io.write(output/"completion.json", {"status": "COMPLETE" if failure is None else "FAILED_NO_RETRY", "attempts": attempts,
        "models_saved": len(models), "fits_attempted": len(attempts), "optimizer_updates": sum(a["updates_completed"] for a in attempts),
        "models_index_sha256": io.sha(output/"models.json"), "failure": failure, "wall_ns": perf_counter_ns()-start,
        "new_environment_steps": 0, "new_api_calls": 0})
    io.require(failure is None and len(models) == 162, "preserved partial training; no retry")


def forward_audit(folder, torch):
    io.require(not (folder/"forward_audit.json").exists(), "do not repeat completed forward audit")
    index = io.read(folder/"training/models.json")["models"]
    completion = io.read(folder/"training/completion.json"); lock = io.read(folder/"model_lock.json")
    io.require(completion["status"] == "COMPLETE" and lock["models_index_sha256"] == io.sha(folder/"training/models.json"), "locked models before DEV")
    trajectories = [HistoryTrajectory.from_dict(t) for role in ("FIT", "DEV") for e in allocation.read_bundle(folder/(role.lower()+"_public.json"), role)["entries"] for t in e["trajectories"]]
    checked = 0; maximum = 0.; initializations = {}
    for key, entry in index.items():
        if entry["kind"] != "GRU":
            continue
        path = folder/"training"/entry["file"]; io.require(io.sha(path) == entry["sha256"], "model changed before forward audit")
        model = io.read(path)
        initial_key = (entry["source"], entry["task"], entry["replicate"])
        if initial_key not in initializations:
            torch.manual_seed(model["initialization_seed"])
            initializations[initial_key] = io.digest(parameters(network(torch)))
        io.require(initializations[initial_key] == model["initial_parameters_sha256"], "independent framework initialization differs")
        for t in trajectories:
            if t.task != entry["task"]:
                continue
            actual, expected = core.predict(model, t), torch_predict(torch, model, t)
            error = float(np.max(abs(actual-expected))) if len(actual) else 0.
            io.require(error < 1e-10, "NumPy/Torch double forward mismatch")
            maximum = max(maximum, error); checked += len(actual)
    io.write(folder/"forward_audit.json", {"integrity": "PASSED", "predictions_checked": checked, "maximum_absolute_error": maximum,
        "models_index_sha256": io.sha(folder/"training/models.json"), "initializations_independently_recreated": len(initializations),
        "new_model_fits": 0, "new_environment_steps": 0, "new_api_calls": 0})


def software(target, torch):
    io.require(target.parent.is_dir() and not target.exists(), "new software receipt in existing directory required")
    weights = target.parent/(target.stem+"_models"); weights.mkdir(exist_ok=False)
    rng = np.random.default_rng(725610)
    trajectories = []
    for j in range(6):
        commands = rng.uniform(-.6, .6, (24+j, 4)); state = np.zeros(39); observations = []
        for command in commands:
            state = state.copy(); state[:2] += .002*command[:2]; state[2] += .001*command[2]; state[3] = command[3]
            state[4:7] = [.1, .6, .02]; state[-3:] = [.2, .7, .1]; observations.append(state)
        trajectories.append(HistoryTrajectory("push-v3", "SOFTWARE_"+str(j), "TRAIN", np.zeros(39), commands, observations))
    result = []; initial = set(); schedules = set()
    for feature in allocation.FEATURES:
        for loss_kind in allocation.LOSSES:
            for window in allocation.WINDOWS:
                attempt = {}; model = fit_one(torch, trajectories, "push-v3", feature, loss_kind, window, 202610360, 202610361, attempt, updates=100)
                error = max(float(np.max(abs(core.predict(model, t)-torch_predict(torch, model, t)))) for t in trajectories)
                io.require(error < 1e-10 and model["checkpoints"][-1]["batch_mse_before_update"] < model["checkpoints"][0]["batch_mse_before_update"], "synthetic optimizer/forward contract")
                model_path = weights/f"{feature}_{loss_kind}_W{window}.json"; io.write(model_path, model)
                result.append({"feature": feature, "loss": loss_kind, "window": window, "maximum_forward_error": error,
                    "model_file": model_path.name, "model_sha256": io.sha(model_path)})
                initial.add(model["initial_parameters_sha256"]); schedules.add(model["sampling_schedule_sha256"])
    io.require(len(initial) == len(schedules) == 1, "same initialization and schedule across all eight variants")
    io.write(target, {"integrity": "PASSED", "software_neural_fits": 8, "software_optimizer_updates": 800, "scientific_model_fits": 0,
        "new_environment_steps": 0, "new_api_calls": 0, "results": result})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("train", "forward", "software")); parser.add_argument("path", type=Path)
    args = parser.parse_args()
    path = args.path.resolve()
    guard_path = path.parent/(path.stem+"_guard.json") if args.mode == "software" else path/(args.mode+"_guard.json")
    with allocation.numeric_guard(allow_training=args.mode == "train") as counters:
        try:
            torch = configure()
            {"train": train, "forward": forward_audit, "software": software}[args.mode](path, torch)
            io.require(not any(counters.values()), "numeric guard violation; preserve failure")
        except BaseException as error:
            io.write(guard_path, {"status": "FAILED", "counters": counters, "error": {"type": type(error).__name__, "message": str(error)}})
            raise
        io.write(guard_path, {"status": "PASSED", "counters": counters, "new_environment_steps": 0, "new_api_calls": 0})

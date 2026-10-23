"""Mechanical postprocessing after a bound, live Windows collector exits normally.

Does not change the frozen collector, parameters, population or scientific code.
The opened process handle binds the wait to the original process, not a stale
status file or a reused PID. No stage is retried or silently overwritten.
"""
import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import run_strong_chronological_reference_v1 as run


def main(path, collector_pid):
    manifest, _, _ = run.load(path)
    target = path.parent/"postprocess_pipeline_v1"
    target.mkdir()
    script = Path(__file__)
    state = {"experiment_run_id": manifest["experiment_run_id"], "manifest_id": manifest["manifest_id"],
        "source_git_commit": manifest["source_git_commit"], "collector_pid": collector_pid, "helper_pid": os.getpid(),
        "helper_path": script.relative_to(ROOT).as_posix(), "helper_sha256": run.sha(script),
        "status": "OPENING_BOUND_COLLECTOR_HANDLE", "stages": [], "visual_qa_complete": False, "local_result_commit_complete": False}
    def update():
        state["updated_utc"] = datetime.now(timezone.utc).isoformat()
        (target/"status.json").write_text(json.dumps(state, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    update()
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetExitCodeProcess.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.OpenProcess(0x00100000|0x1000, False, collector_pid)
    if not handle:
        state.update(status="FAILED_OPEN_PROCESS_HANDLE", windows_error=ctypes.get_last_error()); update()
        raise RuntimeError("cannot verify original collector; do not restart it")
    try:
        if kernel.WaitForSingleObject(handle, 0) != 258:
            raise RuntimeError("collector must be verified live at dispatch")
        state["status"] = "WAITING_FOR_BOUND_COLLECTOR"; update()
        print(f"Bound live collector PID={collector_pid}; helper PID={os.getpid()}", flush=True)
        last_progress = 0.
        while True:
            result = kernel.WaitForSingleObject(handle, 1000)
            if result == 0: break
            if result != 258: raise RuntimeError("collector process observation failed; no restart")
            if time.monotonic()-last_progress >= 30:
                try:
                    progress = run.read(path.parent/"main/status.json")
                    state["collector_progress"] = {k: progress[k] for k in ("status", "executions", "controlled_steps", "controlled_resets")}
                    state.pop("transient_progress_read_error", None)
                except (OSError, json.JSONDecodeError) as error:
                    state["transient_progress_read_error"] = type(error).__name__
                update(); last_progress = time.monotonic()
        code = wintypes.DWORD()
        if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)): raise RuntimeError("collector exit code unavailable")
        state["collector_exit_code"] = code.value
        if code.value != 0: raise RuntimeError("collector failed; preserve partial data and skip postprocessing")
    except BaseException as error:
        state.update(status="FAILED_COLLECTOR_WAIT", error_type=type(error).__name__, error=str(error)); update()
        raise
    finally:
        kernel.CloseHandle(handle)
    final = run.read(path.parent/"main/status.json")
    if final["status"] != "COMPLETED_REFERENCE" or final["executions"] != manifest["config"]["main"]["executions"]:
        state["status"] = "FAILED_INCOMPLETE_COLLECTION"; update()
        raise RuntimeError("normal process exit did not prove complete collection")
    python = ROOT/".venv/Scripts/python.exe"
    plotting = Path("C:/Python314/python.exe")
    args = ["--manifest", str(path), "--phase", "MAIN"]
    stages = [
        ("record_audit", [str(python), "scripts/audit_strong_chronological_reference_v1.py", *args, "--output", str(path.parent/"main_audit/audit.json")]),
        ("statistics_audit", [str(python), "scripts/audit_strong_reference_statistics_v1.py", *args, "--output", str(path.parent/"main_audit/statistics.json")]),
        ("chinese_report", [str(python), "scripts/report_strong_chronological_reference_v1.py", *args]),
        ("figure", [str(plotting), "scripts/plot_strong_chronological_reference_v1.py", *args])]
    for name, command in stages:
        state["status"] = "RUNNING_"+name.upper()
        item = {"name": name, "started_utc": datetime.now(timezone.utc).isoformat(), "command": command}
        state["stages"].append(item); update()
        print("Starting "+name, flush=True)
        log = target/(name+".log")
        with log.open("xb") as handle:
            child = subprocess.Popen(command, cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT)
            item["pid"] = child.pid; update()
            item["returncode"] = child.wait()
        item["finished_utc"] = datetime.now(timezone.utc).isoformat()
        item["log_path"] = log.relative_to(ROOT).as_posix(); item["log_sha256"] = run.sha(log); update()
        if item["returncode"] != 0:
            state["status"] = "FAILED_"+name.upper(); update()
            raise RuntimeError("postprocessing stage failed; preserve outputs: "+name)
    state["status"] = "READY_FOR_VISUAL_QA_AND_REVIEW"; update()
    print(state["status"], flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--manifest", type=Path, required=True); parser.add_argument("--collector-pid", type=int, required=True)
    args = parser.parse_args(); main(args.manifest.resolve(), args.collector_pid)

"""Stress MetaWorld environment lifecycle without making online-model calls."""

from __future__ import annotations

import argparse
import csv
import ctypes
import gc
import json
import os
import platform
import sys
from ctypes import wintypes
from pathlib import Path
from typing import Any, Sequence

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.rollout import create_push_environment, create_push_policy, run_episode  # noqa: E402


class _ProcessMemoryCounters(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


class _MemoryStatusEx(ctypes.Structure):
    _fields_ = [
        ("dwLength", wintypes.DWORD),
        ("dwMemoryLoad", wintypes.DWORD),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def _windows_memory_mb() -> tuple[float, float]:
    counters = _ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    process = ctypes.windll.kernel32.GetCurrentProcess()
    if not ctypes.windll.psapi.GetProcessMemoryInfo(
        process, ctypes.byref(counters), counters.cb
    ):
        raise OSError("GetProcessMemoryInfo failed")
    status = _MemoryStatusEx()
    status.dwLength = ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise OSError("GlobalMemoryStatusEx failed")
    scale = 1024.0 * 1024.0
    return counters.WorkingSetSize / scale, status.ullAvailPhys / scale


def memory_mb() -> tuple[float, float]:
    if platform.system() != "Windows":
        raise RuntimeError("this registered preflight currently supports Windows only")
    return _windows_memory_mb()


def summarize_samples(samples: Sequence[dict[str, Any]]) -> dict[str, Any]:
    if not samples:
        raise ValueError("at least one memory sample is required")
    rss = [float(item["process_rss_mb"]) for item in samples]
    available = [float(item["system_available_mb"]) for item in samples]
    return {
        "sample_count": len(samples),
        "process_rss_start_mb": rss[0],
        "process_rss_final_mb": rss[-1],
        "process_rss_peak_mb": max(rss),
        "process_rss_change_mb": rss[-1] - rss[0],
        "system_available_start_mb": available[0],
        "system_available_final_mb": available[-1],
        "system_available_min_mb": min(available),
    }


def _write_csv(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _sample(stage: str, index: int, seed: int, steps: int) -> dict[str, Any]:
    gc.collect()
    rss, available = memory_mb()
    return {
        "stage": stage,
        "index": index,
        "seed": seed,
        "environment_steps": steps,
        "process_rss_mb": rss,
        "system_available_mb": available,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs/probemem_v2/mujoco_endurance_preflight_v1.json",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=ROOT / "outputs/probemem_v2/mujoco_endurance_preflight.csv",
    )
    parser.add_argument(
        "--output-summary",
        type=Path,
        default=ROOT / "outputs/probemem_v2/mujoco_endurance_preflight_summary.json",
    )
    args = parser.parse_args()
    samples: list[dict[str, Any]] = []
    try:
        config = json.loads(args.config.resolve().read_text(encoding="utf-8"))
        if int(config["api_calls"]) != 0 or bool(config["rendering"]):
            raise ValueError("endurance preflight forbids API calls and rendering")
        seed_start, seed_stop = (int(item) for item in config["seed_range"])
        seeds = tuple(range(seed_start, seed_stop + 1))
        samples.append(_sample("start", 0, seeds[0], 0))

        action = np.zeros(4, dtype=np.float32)
        for index in range(1, int(config["construction_cycles"]) + 1):
            seed = seeds[(index - 1) % len(seeds)]
            env = create_push_environment(seed)
            completed = 0
            try:
                env.reset(seed=seed)
                for _ in range(int(config["construction_steps_per_cycle"])):
                    _, _, terminated, truncated, _ = env.step(action)
                    completed += 1
                    if terminated or truncated:
                        break
            finally:
                env.close()
                del env
            samples.append(_sample("construction", index, seed, completed))
            if index % 10 == 0:
                print(
                    f"construction={index} rss_mb={samples[-1]['process_rss_mb']:.1f} "
                    f"available_mb={samples[-1]['system_available_mb']:.1f}"
                )

        for index in range(1, int(config["rollout_cycles"]) + 1):
            seed = seeds[index - 1]
            env = create_push_environment(seed)
            try:
                result = run_episode(
                    env,
                    create_push_policy(),
                    seed=seed,
                    max_steps=int(config["rollout_max_steps"]),
                    episode_id=index,
                )
            finally:
                env.close()
                del env
            samples.append(_sample("rollout", index, seed, int(result.steps)))
            print(
                f"rollout={index} seed={seed} steps={result.steps} "
                f"rss_mb={samples[-1]['process_rss_mb']:.1f} "
                f"available_mb={samples[-1]['system_available_mb']:.1f}"
            )

        summary = {
            "protocol": config["protocol"],
            "status": "COMPLETED",
            "source_failed_run_id": config["source_failed_run_id"],
            "source_git_commit": os.environ.get("PROBEMEM_SOURCE_COMMIT", "UNSET"),
            "construction_cycles_completed": int(config["construction_cycles"]),
            "rollout_cycles_completed": int(config["rollout_cycles"]),
            **summarize_samples(samples),
        }
        _write_csv(args.output_csv.resolve(), samples)
        args.output_summary.resolve().parent.mkdir(parents=True, exist_ok=True)
        args.output_summary.resolve().write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8"
        )
        print(f"samples: {args.output_csv.resolve()}")
        print(f"summary: {args.output_summary.resolve()}")
        return 0
    except Exception as exc:
        if samples:
            _write_csv(args.output_csv.resolve(), samples)
        failure = {
            "status": "FAILED",
            "error_type": type(exc).__name__,
            "error": str(exc),
            **(summarize_samples(samples) if samples else {}),
        }
        args.output_summary.resolve().parent.mkdir(parents=True, exist_ok=True)
        args.output_summary.resolve().write_text(
            json.dumps(failure, indent=2) + "\n", encoding="utf-8"
        )
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

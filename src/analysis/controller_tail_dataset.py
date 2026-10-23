"""Offline factual-tail extraction; outcome/group metadata never enters evidence."""
import numpy as np
from src.probe.controller_tail_value import build_evidence, features, controller_field, controller_kind
from src.rollout.task_registry import create_task_policy


def sample_steps(start, length, stride=4):
    if type(start) is not int or type(length) is not int or stride != 4 or start < 8 or length > 500:
        raise ValueError("registered stable tail required")
    return sorted(set(range(start, length, stride)) | ({length - 1} if length > start else set()))


def extract(record, episode_id):
    decisions = [d for d in record["decisions"] if d.get("controller") is not None]
    if not decisions:
        return [], {"episode_id": episode_id, "stream": record["stream"], "task": record["task"],
                    "replicate": record["replicate"], "method": record["method"], "outcome": record["outcome"],
                    "stable_start": None, "controller": None, "controller_kind": None, "samples": 0,
                    "eligible": False, "reason": "NO_SAVED_CONTROLLER"}
    final = decisions[-1]; saved = final["controller"]
    start = max(8, final["at_host_calls"]); trace = record["trace"]
    indices = sample_steps(start, len(trace))
    metadata = {"episode_id": episode_id, "stream": record["stream"], "task": record["task"],
                "replicate": record["replicate"], "method": record["method"],
                "outcome": record["outcome"], "stable_start": start, "controller": saved,
                "controller_kind": controller_kind(saved), "samples": len(indices),
                "eligible": bool(indices), "reason": "STABLE_TAIL" if indices else "ENDED_BEFORE_STABLE_TAIL"}
    if not indices:
        return [], metadata
    if len(trace) != record["outcome"]["total_steps"]:
        raise ValueError("source outcome length mismatch")
    field = controller_field(saved); policy = create_task_policy(record["task"])
    output = []
    for step in indices:
        current = trace[step]
        if current["phase"] != "POLICY" or current["decision_sequence"] != final["sequence"]:
            raise ValueError("controller changed within extracted tail")
        if any(current["before"][k] for k in ("success", "terminated", "truncated")):
            raise ValueError("training feature at terminal state")
        past = trace[step-8:step]
        if any(a["after"] != b["before"] for a, b in zip(past, past[1:] + [current])):
            raise ValueError("discontinuous causal feature history")
        observations = [r["before"]["observation"] for r in past] + [current["before"]["observation"]]
        raw = np.asarray(policy.get_action(np.asarray(observations[-1])), np.float32)
        if not np.array_equal(raw, np.asarray(current["raw_policy"], np.float32)):
            raise ValueError("saved raw policy differs from frozen causal policy")
        evidence = build_evidence(record["task"], observations, [r["command"] for r in past], raw, saved, 500-step, field)
        if not np.array_equal(np.asarray(evidence.candidate_command, np.float32), np.asarray(current["command"], np.float32)):
            raise ValueError("factual command not from saved tail controller")
        loss = record["outcome"]["deadline_loss"] - step
        if not 0 <= loss <= 500-step:
            raise ValueError("invalid Monte Carlo cutoff target")
        output.append({"x": features(evidence), "target": loss/(500-step), "remaining": 500-step,
                       "step": step, "weight": 1/len(indices), "episode_id": episode_id,
                       "group": record["stream"], "task": record["task"], "kind": evidence.controller_kind,
                       "evidence_digest": evidence.digest})
    return output, metadata


def matched_sixteen(a, b):
    """New registered KEEP-vs-UPDATE pair; not an extension of the old registry."""
    if (a["method"], b["method"]) != ("KEEP_G8_AFTER16", "UPDATE_G16"):
        raise ValueError("unregistered critic qualification pair")
    for key in ("stream", "task", "replicate", "seed", "initial", "initial_noise_hash", "initial_physics_witness_oracle", "sixteen_physics_witness_oracle"):
        if a[key] != b[key]:
            raise ValueError("different actual prefix context")
    keys = ("command", "raw_policy", "before", "after", "noise_before_hash", "noise_after_hash",
            "executed_action_oracle", "phase", "simulation_time_before_oracle", "simulation_time_after_oracle")
    if len(a["trace"]) < 16 or len(b["trace"]) < 16:
        return False
    for left, right in zip(a["trace"][:16], b["trace"][:16]):
        if any(left[k] != right[k] for k in keys):
            raise ValueError("paired sixteen-step history differs")
    return not any(a["trace"][15]["after"][k] for k in ("success", "terminated", "truncated"))

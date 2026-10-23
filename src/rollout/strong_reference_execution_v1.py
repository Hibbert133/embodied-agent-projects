"""Physical host for the new supported-passive and history-query references."""
from dataclasses import asdict
from time import perf_counter_ns
import numpy as np
from scripts import run_cold_start_task_bridge as prior
from src.probe.chronological_cache_reference import VerifiedPoint
from src.probe.continuous import StepObservation
from src.probe.passive_supported_reference_v1 import MODES, OwnedPassiveCacheV1, run_passive_reference, PassiveReferenceFailure
from src.probe.history_query_execution_v1 import run_history_query_reference
from src.rollout.chronological_cache_execution import state_view
from src.rollout.chronological_faults import ChronologicalNoise, apply_fault
from src.rollout.task_registry import create_task_environment, create_task_policy

NEW_METHODS = (*MODES, "TASK_HISTORY_IVR4")


def execute(key, fault, state, old_model, joint_model, history, emit, ledger):
    method = key["method"]
    if method not in NEW_METHODS: raise ValueError("new strong reference method required")
    record = {**key, "state_before": state_view(state), "trace": [], "decisions": [], "initial": None,
        "ledger_before": ledger.snapshot(), "fit": None, "cache_write_error": None, "boundary_physics_witness_oracle": {}, "agent_global_sequences": []}
    tape, env, current = ChronologicalNoise(key["seed"]), None, None
    record["noise_commitment_oracle"] = tape.commitment_oracle
    pending, agent_sequence, policy_queries, calls, attempts = None, 0, 0, 0, 0
    global_sequences = {}
    try:
        emit("FACTORY_INTENT", {**key, "ledger": ledger.snapshot(), "noise_commitment_oracle": tape.commitment_oracle})
        with ledger.scope("FACTORY_SETUP"): env = create_task_environment(key["task"], key["seed"])
        emit("FACTORY_COMPLETE", {**key, "ledger": ledger.snapshot()})
        with ledger.scope("CONTROLLED_RESET"): observation, _ = env.reset(seed=key["seed"])
        current = StepObservation(tuple(observation), False, False, False)
        record.update(initial=asdict(current), initial_physics_witness_oracle=prior.physics_witness(env), initial_noise_hash=tape.past_hash(),
            clock_contract={"model_timestep_s": float(env.unwrapped.model.opt.timestep), "frame_skip": int(env.unwrapped.frame_skip)})
        emit("CONTROLLED_INITIAL", {**key, "initial": record["initial"], "physics_witness_oracle": record["initial_physics_witness_oracle"],
            "noise_hash": tape.past_hash(), "ledger": ledger.snapshot()})
        policy = create_task_policy(key["task"])

        def query(observation):
            nonlocal policy_queries
            policy_queries += 1
            return policy.get_action(observation)

        def persist(kind, payload):
            nonlocal agent_sequence, pending
            agent_sequence += 1
            envelope = prior.normal({"event": kind, "sequence": agent_sequence, "saved_ns": perf_counter_ns(), "payload": payload})
            outer = emit("AGENT_EVENT", {**key, "agent_event": envelope})
            global_sequences[agent_sequence] = outer["sequence"]
            record["agent_global_sequences"].append({"agent_sequence": agent_sequence, "global_sequence": outer["sequence"]})
            if kind == "DECISION": record["decisions"].append({**prior.normal(outer), **prior.normal(payload)})
            if kind == "STEP_INTENT":
                if pending is not None: raise ValueError("previous agent command not consumed")
                pending = envelope
            return envelope

        def step(command):
            nonlocal pending, current, calls, attempts
            if pending is None or current.success or current.terminated or current.truncated or calls >= 500:
                raise ValueError("no pending physical command or ended/exhausted case")
            selected = pending; pending = None; p = selected["payload"]
            sent = np.asarray(command, np.float32)
            if sent.astype(float).tolist() != p["command"] or prior.normal(asdict(current)) != p["before"] or p["at_host_calls"] != calls:
                raise ValueError("physical host ignored saved agent command/current observation")
            before = current
            phase = p.get("phase", "POLICY")
            intent = emit("STEP_INTENT", {**key, "at_host_calls": calls, "decision_sequence": global_sequences[p["decision_sequence"]],
                "agent_intent_sequence": selected["sequence"], "phase": phase, "command": p["command"], "raw_policy": p["raw_policy"],
                "before": asdict(before), "noise_before_hash": tape.past_hash(), "ledger_before": ledger.snapshot()})
            started = perf_counter_ns(); acted = apply_fault(intent["command"], fault, tape)
            before_time = float(env.unwrapped.data.time); attempts += 1
            with ledger.scope("CONTROL"): observation, _, terminated, truncated, info = env.step(acted)
            after_time = float(env.unwrapped.data.time); finished = perf_counter_ns(); calls += 1
            current = StepObservation(tuple(observation), bool(terminated), bool(truncated), bool(info.get("success", False)))
            dt = float(env.unwrapped.model.opt.timestep)*int(env.unwrapped.frame_skip)
            a, b = ledger.snapshot()["by_phase"].get("CONTROL", {}), intent["ledger_before"]["by_phase"].get("CONTROL", {})
            if (not np.isclose(after_time-before_time, dt, rtol=1e-10, atol=1e-10) or
                a.get("reset_attempts", 0) != b.get("reset_attempts", 0) or
                a.get("simulation_frames_completed", 0)-b.get("simulation_frames_completed", 0) != 5):
                raise ValueError("five-frame continuous no-reset clock violated")
            row = {"host_calls": calls, "intent_sequence": intent["sequence"], "decision_sequence": intent["decision_sequence"],
                "agent_intent_sequence": selected["sequence"], "phase": phase, "command": intent["command"], "raw_policy": p["raw_policy"],
                "before": asdict(before), "after": asdict(current), "noise_before_hash": intent["noise_before_hash"], "noise_after_hash": tape.past_hash(),
                "target_xy": (np.asarray(current.observation)[:2]-np.asarray(before.observation)[:2]).tolist(), "executed_action_oracle": acted.tolist(),
                "intent_saved_ns": intent["saved_ns"], "execution_started_ns": started, "completed_ns": finished,
                "simulation_time_before_oracle": before_time, "simulation_time_after_oracle": after_time,
                "ledger_before": intent["ledger_before"], "ledger_after": ledger.snapshot()}
            record["trace"].append(prior.normal(row)); emit("STEP_COMPLETE", {**key, **row})
            if calls in (4, 8, 16): record["boundary_physics_witness_oracle"][str(calls)] = prior.physics_witness(env)
            return current

        cache = state["cache"]
        if method in MODES:
            agent = run_passive_reference(mode=method, task=key["task"], episode=key["episode"], initial=current,
                previous=OwnedPassiveCacheV1(method, cache) if cache else None, model=old_model, policy=query, step=step, persist=persist)
            after = OwnedPassiveCacheV1.from_dict(agent["state_after"]).point if agent["state_after"] else None
            fit_sequence = agent["outcome"]["last_applied_fit_decision_sequence"]
            record["fit"] = next((e["payload"]["fit"] for e in agent["events"] if e["sequence"] == fit_sequence), None)
            stopped, probe = False, 0
        else:
            agent = run_history_query_reference(task=key["task"], episode=key["episode"], initial=current, previous=cache,
                past_queries=history, model=joint_model, policy=query, step=step, persist=persist)
            after = VerifiedPoint.from_dict(agent["state_after"]) if agent["state_after"] else None
            record["fit"], record["cache_write_error"] = agent["fit"], agent["cache_write_error"]
            stopped, probe = agent["outcome"]["stopped"], agent["outcome"]["fixed_probe_steps"]
        record["agent_record"] = agent
        if pending is not None or tape.cursor != calls or agent["outcome"]["total_steps"] != calls or agent["outcome"]["policy_queries"] != policy_queries:
            raise ValueError("agent/physical clock or actual query count differs")
        resets = ledger.snapshot()["by_phase"].get("CONTROLLED_RESET", {}).get("reset_completed", 0)-record["ledger_before"]["by_phase"].get("CONTROLLED_RESET", {}).get("reset_completed", 0)
        if resets != 1: raise ValueError("one controlled initial reset required")
        outcome = {"success": current.success, "stopped": stopped, "total_steps": calls, "environment_resets": resets,
            "fixed_probe_steps": probe, "policy_measure_steps": (min(calls, 8) if method == "PASSIVE8_KEEP" else calls) if method in MODES else 0,
            "policy_steps": calls-probe, "deadline_loss": calls if current.success else 500, "noise_rows_consumed": tape.cursor,
            "online_parameter_fits": agent["outcome"]["fit_attempts"], "optimizer_nfev": agent["outcome"]["optimizer_nfev"], "policy_queries": policy_queries}
        state["cache"], state["cusum"] = after, 0.
        record.update(outcome=outcome, state_after=state_view(state), ledger_after=ledger.snapshot())
        record["cache_event"] = emit("CACHE_STATE_AFTER_OUTCOME", {**key, "outcome": outcome, "state_after": record["state_after"], "cache_write_error": record["cache_write_error"]})
        return record
    except BaseException as error:
        record.update(error_type=type(error).__name__, error=str(error), completed_steps=calls, noise_rows_consumed=tape.cursor,
            unresolved_controlled_step_attempts=attempts-calls, ledger_after=ledger.snapshot(), partial_current=asdict(current) if current else None)
        if isinstance(error, PassiveReferenceFailure): record["agent_partial"] = error.record
        raise prior.BranchFailure(record) from error
    finally:
        if env is not None: env.close()

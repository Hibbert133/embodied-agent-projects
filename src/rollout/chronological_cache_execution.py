"""Execute one saved cache-reference choice on a single continuous live case."""
from collections import Counter
from dataclasses import asdict
from time import perf_counter_ns
import numpy as np
from scripts import run_cold_start_task_bridge as prior
from src.probe.chronological_cache_reference import (BLOCK8, METHODS, OLD_METHODS, VerifiedPoint, accepted_cache,
    initial_choice, check_choice, program, budget_valid)
from src.probe.cold_start_response import ColdPrefix, infer_operator as infer_joint
from src.probe.cold_cache_prediction import digest
from src.probe.continuous import StepObservation, ContinuousTransition
from src.probe.forward_prediction import ForwardHistory
from src.probe.operator_identification import OperatorSample, infer_operator as infer_old, affine_controller, identity_controller, encode_controller
from src.rollout.task_registry import create_task_environment, create_task_policy
from src.rollout.chronological_faults import ChronologicalNoise, apply_fault


def state_view(state):
    return {"cache": asdict(state["cache"]) if state["cache"] is not None else None, "cusum": float(state["cusum"])}


def execute(key, fault, state, old_model, joint_model, emit, ledger):
    method = key["method"]
    if method not in METHODS: raise ValueError("unregistered chronological reference")
    cache = state["cache"]
    record = {**key, "state_before": state_view(state), "trace": [], "decisions": [], "initial": None,
              "ledger_before": ledger.snapshot(), "fit": None, "cache_write_error": None, "boundary_physics_witness_oracle": {}}
    env = None; current = None; calls = 0; attempts = 0; last = None; samples = []; fit = None; fit_prefix = None
    tape = ChronologicalNoise(key["seed"])
    record["noise_commitment_oracle"] = tape.commitment_oracle
    try:
        emit("FACTORY_INTENT", {**key, "ledger": ledger.snapshot(), "noise_commitment_oracle": tape.commitment_oracle})
        with ledger.scope("FACTORY_SETUP"): env = create_task_environment(key["task"], key["seed"])
        emit("FACTORY_COMPLETE", {**key, "ledger": ledger.snapshot()})
        with ledger.scope("CONTROLLED_RESET"): observation, _ = env.reset(seed=key["seed"])
        current = StepObservation(tuple(observation), False, False, False)
        history = ForwardHistory(current.observation); policy = create_task_policy(key["task"])
        record.update(initial=asdict(current), initial_physics_witness_oracle=prior.physics_witness(env), initial_noise_hash=tape.past_hash(),
                      clock_contract={"model_timestep_s": float(env.unwrapped.model.opt.timestep), "frame_skip": int(env.unwrapped.frame_skip)})
        emit("CONTROLLED_INITIAL", {**key, "initial": record["initial"], "physics_witness_oracle": record["initial_physics_witness_oracle"], "noise_hash": tape.past_hash(), "ledger": ledger.snapshot()})
        def ended(): return current.success or current.terminated or current.truncated
        def choose(action, controller=None, commands=(), **extra):
            nonlocal last
            legal = {"RUN_IDENTITY", "RUN_CACHED", "PASSIVE8", "PROBE8", "PROBE16", "CHECK4", "RUN_POINT", "STOP_POINT_FIT", "STOP_BUDGET", "REFRESH8", "STOP_CHECK_SCOPE_OR_NUMERICS"}
            if action not in legal or (action in ("PASSIVE8", "PROBE8", "PROBE16", "CHECK4") and calls != 0) or (action == "REFRESH8" and calls != 4):
                raise ValueError("illegal or repeated action request")
            if controller is not None and controller.get("source") not in ("UNCORRECTED", "ESTIMATED_AFFINE"):
                raise ValueError("non-agent controller source")
            event = emit("DECISION", {**key, "at_host_calls": calls, "action": action, "controller": prior.normal(controller),
                                     "program": prior.normal(commands), "observation_sha256": prior.state_hash(current.observation),
                                     "noise_hash": tape.past_hash(), "cache_sha256": digest(state_view(state)), **extra})
            last = prior.normal(event); record["decisions"].append(last)
        def step(sent, phase, raw=None):
            nonlocal current, calls, attempts
            if ended() or calls >= 500: raise ValueError("ended or exhausted case stepped")
            before = current; sent = np.asarray(sent, np.float32); query = history.request(sent)
            intent = prior.normal(emit("STEP_INTENT", {**key, "at_host_calls": calls, "decision_sequence": last["sequence"], "phase": phase,
                "command": sent.tolist(), "raw_policy": raw, "before": asdict(before), "noise_before_hash": tape.past_hash(),
                "forward_query": prior.normal(asdict(query)) if query else None, "ledger_before": ledger.snapshot()}))
            started = perf_counter_ns(); acted = apply_fault(intent["command"], fault, tape)
            time_before = float(env.unwrapped.data.time); attempts += 1
            with ledger.scope("CONTROL"): observation, _, terminated, truncated, info = env.step(acted)
            time_after = float(env.unwrapped.data.time); finished = perf_counter_ns(); calls += 1
            current = StepObservation(tuple(observation), bool(terminated), bool(truncated), bool(info.get("success", False)))
            elapsed = float(env.unwrapped.model.opt.timestep)*int(env.unwrapped.frame_skip)
            if not np.isclose(time_after-time_before, elapsed, atol=1e-10, rtol=1e-10): raise ValueError("continuous simulation clock violated")
            b = intent["ledger_before"]["by_phase"].get("CONTROL", {}); a = ledger.snapshot()["by_phase"].get("CONTROL", {})
            if a.get("reset_attempts", 0) != b.get("reset_attempts", 0) or a.get("simulation_frames_completed", 0)-b.get("simulation_frames_completed", 0) != 5:
                raise ValueError("five-frame no-reset step violated")
            target = history.observe(ContinuousTransition(tuple(intent["command"]), before.observation, current.observation))
            if query is not None: samples.append(OperatorSample(calls, query, target))
            row = {"host_calls": calls, "intent_sequence": intent["sequence"], "decision_sequence": last["sequence"], "phase": phase,
                   "command": intent["command"], "raw_policy": raw, "before": asdict(before), "after": asdict(current),
                   "noise_before_hash": intent["noise_before_hash"], "noise_after_hash": tape.past_hash(), "target_xy": list(target),
                   "executed_action_oracle": acted.tolist(), "intent_saved_ns": intent["saved_ns"], "execution_started_ns": started, "completed_ns": finished,
                   "simulation_time_before_oracle": time_before, "simulation_time_after_oracle": time_after,
                   "ledger_before": intent["ledger_before"], "ledger_after": ledger.snapshot()}
            record["trace"].append(row); emit("STEP_COMPLETE", {**key, **row})
            if calls in (4, 8, 16): record["boundary_physics_witness_oracle"][str(calls)] = prior.physics_witness(env)
        def consume_saved_program():
            selected = last["program"]
            for command in selected:
                if ended(): break
                step(command, "FIXED_PROBE")
        def prefix():
            return ColdPrefix(key["task"], record["initial"]["observation"], tuple(tuple(r["command"]) for r in record["trace"]),
                              tuple(tuple(r["after"]["observation"]) for r in record["trace"]), True)
        def new_point():
            nonlocal fit, fit_prefix
            if method in OLD_METHODS:
                fit = infer_old(old_model, tuple(samples))
            else:
                fit_prefix = prefix(); fit = infer_joint(joint_model, fit_prefix)
            record["fit"] = prior.normal(fit)
            if fit["valid"]:
                choose("RUN_POINT", affine_controller(fit["matrix_xy"], fit["bias_xy"]), fit=record["fit"])
            else:
                choose("STOP_POINT_FIT", fit=record["fit"])
            fit = last["fit"]
        action = initial_choice(method, cache, key["episode"])
        if action == "RUN_IDENTITY": choose(action, identity_controller())
        elif action == "RUN_CACHED": choose(action, cache.controller)
        elif action == "PASSIVE8":
            choose(action, cache.controller if cache is not None else identity_controller(), policy_measure_steps=8)
        else:
            commands = BLOCK8*2 if action == "PROBE16" else program(method)[:4] if action == "CHECK4" else BLOCK8
            choose(action if budget_valid(500, len(commands)) else "STOP_BUDGET", commands=commands if budget_valid(500, len(commands)) else ())
        # Dispatch and all subsequent physical commands consume saved declarations.
        if last["action"] in ("PROBE8", "PROBE16", "CHECK4"):
            consume_saved_program()
            if not ended():
                if last["action"] == "CHECK4":
                    raw = np.asarray(policy.get_action(np.asarray(current.observation)), np.float32)
                    try:
                        result = check_choice(method, joint_model, prefix(), cache, state["cusum"], raw)
                    except (ValueError, np.linalg.LinAlgError) as error:
                        choose("STOP_CHECK_SCOPE_OR_NUMERICS", reason=str(error))
                    else:
                        action = result["action"]
                        commands = program(method)[4:] if action == "REFRESH8" else ()
                        if commands and not budget_valid(500-calls, len(commands)):
                            choose("STOP_BUDGET", check=result, raw_policy_for_check=raw.tolist())
                        else:
                            choose(action, cache.controller if action == "RUN_CACHED" else None, commands, check=result, raw_policy_for_check=raw.tolist())
                            state["cusum"] = last["check"]["cusum_after_check"]
                            if last["action"] == "REFRESH8":
                                consume_saved_program()
                                if not ended(): new_point()
                else: new_point()
        elif last["action"] == "PASSIVE8":
            for _ in range(8):
                if ended(): break
                raw = np.asarray(policy.get_action(np.asarray(current.observation)), np.float32)
                step(encode_controller(last["controller"], raw), "PASSIVE_PREFIX", raw.tolist())
            if not ended(): new_point()
        while not ended() and calls < 500 and last["controller"] is not None:
            raw = np.asarray(policy.get_action(np.asarray(current.observation)), np.float32)
            step(encode_controller(last["controller"], raw), "POLICY", raw.tolist())
        phases = Counter(row["phase"] for row in record["trace"])
        if tape.cursor != calls: raise ValueError("noise consumed outside physical steps")
        resets = ledger.snapshot()["by_phase"].get("CONTROLLED_RESET", {}).get("reset_completed", 0)-record["ledger_before"]["by_phase"].get("CONTROLLED_RESET", {}).get("reset_completed", 0)
        if resets != 1: raise ValueError("one controlled reset required")
        outcome = {"success": current.success, "stopped": last["controller"] is None and not ended(), "total_steps": calls, "environment_resets": resets,
                   "fixed_probe_steps": phases["FIXED_PROBE"], "policy_measure_steps": phases["PASSIVE_PREFIX"], "policy_steps": phases["POLICY"]+phases["PASSIVE_PREFIX"],
                   "deadline_loss": calls if current.success else 500, "noise_rows_consumed": tape.cursor,
                   "online_parameter_fits": int(fit is not None),
                   "optimizer_nfev": int(fit.get("nfev", sum(t["nfev"] for t in fit.get("optimizer_trials", [])))) if fit else 0}
        record.update(outcome=outcome, ledger_after=ledger.snapshot())
        if not current.success:
            state["cache"] = None; state["cusum"] = 0.
        elif fit is not None:
            try:
                state["cache"] = accepted_cache(fit, fit_prefix, key["task"], key["episode"], success=True,
                    joint_model=joint_model if method not in OLD_METHODS else None, evidence=[asdict(s) for s in samples])
            except (ValueError, np.linalg.LinAlgError) as error:
                state["cache"] = None; record["cache_write_error"] = str(error)
            state["cusum"] = 0.
        # A successful reuse retains the identical source and covariance, without renewal.
        record["state_after"] = state_view(state)
        record["cache_event"] = emit("CACHE_STATE_AFTER_OUTCOME", {**key, "outcome": outcome, "state_after": record["state_after"],
            "selected_fit_decision_sequence": next((d["sequence"] for d in reversed(record["decisions"]) if d.get("fit") is not None), None), "cache_write_error": record["cache_write_error"]})
    except BaseException as error:
        record.update(error_type=type(error).__name__, error=str(error), completed_steps=calls, noise_rows_consumed=tape.cursor,
                      unresolved_controlled_step_attempts=attempts-calls, ledger_after=ledger.snapshot(), partial_current=asdict(current) if current is not None else None)
        raise prior.BranchFailure(record) from error
    finally:
        if env is not None: env.close()
    return record

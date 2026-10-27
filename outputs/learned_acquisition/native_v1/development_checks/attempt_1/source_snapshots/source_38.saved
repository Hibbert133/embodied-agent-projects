"""Observe top-level MetaWorld resets and completed do_simulation requests.

Instrumentation delegates exactly once and never changes actions, RNG or model
state. Internal reset frames are a simulator cost, separate from robot Env.step.
"""
from collections import Counter
from contextlib import contextmanager
from functools import wraps
import operator


class LifecycleLedger:
    def __init__(self, emit, maximum_frames):
        if type(maximum_frames) is not int or maximum_frames <= 0:
            raise ValueError("positive simulator-frame cap required")
        self.emit, self.maximum_frames = emit, maximum_frames
        self.phase = "FACTORY_SETUP"
        self.counts = Counter()
        self.by_phase = {}
        self.stack = 0
        self.active = False

    def add(self, field, value=1):
        self.counts[field] += value
        self.by_phase.setdefault(self.phase, Counter())[field] += value

    def snapshot(self):
        return {"counts": dict(self.counts), "by_phase": {k: dict(v) for k, v in self.by_phase.items()}}

    @contextmanager
    def scope(self, phase):
        if phase not in ("FACTORY_SETUP", "GOAL_GENERATION", "CONTROLLED_RESET", "CONTROL"):
            raise ValueError("unregistered lifecycle phase")
        old = self.phase
        self.phase = phase
        try:
            yield
        finally:
            self.phase = old

    def reset_call(self, original, env, *args, **kwargs):
        if self.stack:
            raise RuntimeError("unexpected nested Sawyer reset entry")
        before = self.snapshot()
        self.add("reset_attempts")
        intent = self.emit("LIFECYCLE_RESET_INTENT", {"phase": self.phase, "before": before})
        self.stack += 1
        try:
            value = original(env, *args, **kwargs)
        except BaseException:
            self.add("reset_errors")
            raise
        else:
            self.add("reset_completed")
            self.emit("LIFECYCLE_RESET_COMPLETE", {"intent_sequence": intent["sequence"], "phase": self.phase, "after": self.snapshot()})
            return value
        finally:
            self.stack -= 1

    def simulation_call(self, original, env, ctrl, n_frames):
        frames = operator.index(n_frames)
        if isinstance(n_frames, bool) or frames <= 0:
            raise ValueError("positive integer frame request required")
        if self.counts["simulation_frames_attempted"] + frames > self.maximum_frames:
            self.add("frame_budget_rejections")
            raise RuntimeError("whole-study do_simulation frame cap reached")
        self.add("simulation_attempts")
        self.add("simulation_frames_attempted", frames)
        try:
            value = original(env, ctrl, n_frames)
        except BaseException:
            self.add("simulation_errors")
            self.add("uncertain_simulation_frames", frames)
            raise
        else:
            self.add("simulation_completed")
            self.add("simulation_frames_completed", frames)
            return value

    @contextmanager
    def instrument(self, reset_class, simulation_class, factory_module):
        if self.active:
            raise RuntimeError("ledger instrumentation already active")
        old_reset = reset_class.reset
        old_simulation = simulation_class.do_simulation
        old_factory = factory_module._make_tasks
        ledger = self
        @wraps(old_reset)
        def reset(env, *args, **kwargs):
            return ledger.reset_call(old_reset, env, *args, **kwargs)
        @wraps(old_simulation)
        def simulate(env, ctrl, n_frames):
            return ledger.simulation_call(old_simulation, env, ctrl, n_frames)
        @wraps(old_factory)
        def factory(*args, **kwargs):
            with ledger.scope("GOAL_GENERATION"):
                return old_factory(*args, **kwargs)
        self.active = True
        reset_class.reset, simulation_class.do_simulation, factory_module._make_tasks = reset, simulate, factory
        try:
            yield self
        finally:
            reset_class.reset, simulation_class.do_simulation, factory_module._make_tasks = old_reset, old_simulation, old_factory
            self.active = False

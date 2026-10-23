"""Inspectable-state software qualification; no MetaWorld factories or seeds."""
from collections import deque
from contextlib import ExitStack
from copy import deepcopy
import json
import random
import unittest
from unittest.mock import patch

import gymnasium as gym
import mujoco
import numpy as np

from src.analysis import continuous_state_witness_v1 as witness
from src.analysis.state_capsule_v1 import layers, native_hash, python_state, state_signature
from tests.test_state_capsule_v1 import ToyEnv, Policy

SOFTWARE_RECEIPTS = []
WITNESS_EXAMPLES = []


class ContinuousStateWitnessTest(unittest.TestCase):
    def setUp(self):
        self.numpy_state = np.random.get_state();self.python_state = random.getstate()
        self.envs = [];self.frames = self.forward_calls = self.steps = self.queries = self.resets = 0
        self.stack = ExitStack();original_native = mujoco.mj_step;original_forward = mujoco.mj_forward
        original_step = ToyEnv.step;original_action = Policy.action
        def native(*args, **kwargs):
            result = original_native(*args, **kwargs)
            self.frames += int(kwargs.get("nstep", args[2] if len(args) > 2 else 1));return result
        def forward(*args, **kwargs):
            result = original_forward(*args, **kwargs);self.forward_calls += 1;return result
        def step(env, action):
            self.steps += 1;return original_step(env, action)
        def reset(*args, **kwargs):
            self.resets += 1;raise AssertionError("witness qualification must not reset")
        def action(policy):
            self.queries += 1;return original_action(policy)
        for owner, name, value in ((mujoco, "mj_step", native), (mujoco, "mj_forward", forward),
                                  (ToyEnv, "step", step), (ToyEnv, "reset", reset), (Policy, "action", action)):
            self.stack.enter_context(patch.object(owner, name, value))
        self.env, self.policy, self.context = self.make()

    def make(self, start=100.0):
        limited = gym.wrappers.TimeLimit(ToyEnv(), max_episode_steps=2);limited._elapsed_steps = 0
        env = gym.wrappers.RecordEpisodeStatistics(limited);env.episode_start_time = start
        self.envs.append(env)
        return env, Policy(), {"cursor": 0, "remaining_budget": 500, "noise": np.arange(30.).reshape(10, 3)}

    def take(self, env=None, policy=None, context=None):
        return witness.capture_witness(env or self.env, policy or self.policy, self.context if context is None else context)

    def tearDown(self):
        for env in self.envs: env.close()
        self.stack.close();np.random.set_state(self.numpy_state);random.setstate(self.python_state)
        SOFTWARE_RECEIPTS.append({"test": self.id(), "native_frames": self.frames, "native_forward_calls": self.forward_calls,
            "constructed_tiny_envs": len(self.envs), "environment_step_attempts": self.steps, "policy_queries": self.queries,
            "environment_reset_attempts": self.resets, "new_metaworld_steps": 0, "new_scientific_seeds": 0, "new_api_calls": 0})

    def test_matches_frozen_hash_and_survives_json_roundtrip(self):
        value = self.take();base = self.env.unwrapped
        self.assertEqual(value["full_python_sha256"], state_signature(python_state(layers(self.env), self.policy, self.context), base.model, base.data))
        self.assertEqual(value["native_sha256"], native_hash(base.model, base.data))
        restored = json.loads(json.dumps(value));witness.verify_witness(restored, full_sha256=value["full_python_sha256"], native_sha256=value["native_sha256"])
        self.assertTrue(witness.compare_witnesses(value, restored)["comparison_equal"])

    def test_independent_wrapped_instances_keep_only_timing_difference(self):
        self.env.time_queue.extend([1.25, 2.5]);left = self.take()
        other, policy, context = self.make(start=200.0);other.time_queue.extend([3.75, 5.0]);right = self.take(other, policy, context)
        result = witness.compare_witnesses(left, right)
        self.assertFalse(result["same_full_python"]);self.assertTrue(result["comparison_equal"])
        self.assertTrue(result["only_registered_timing_components_differ"])
        self.assertEqual({r["path"][-1] for r in result["component_differences"]}, {"episode_start_time", "time_queue"})
        WITNESS_EXAMPLES.append({"scope": "SOFTWARE_ONLY_TWO_INDEPENDENT_WRAPPED_TINY_ENVS", "left": left, "right": right, "comparison": result})

    def test_uninitialized_timer_and_queue_structure_are_not_erased(self):
        first = self.take()
        for kind in ("uninitialized", "queue_length", "queue_capacity"):
            other, policy, context = self.make()
            if kind == "uninitialized": other.episode_start_time = -1
            elif kind == "queue_length": other.time_queue.append(1.0)
            else: other.time_queue = deque(maxlen=99)
            with self.subTest(kind=kind): self.assertFalse(witness.compare_witnesses(first, self.take(other, policy, context))["comparison_equal"])

    def test_task_counters_rewards_policy_context_and_native_differences_remain(self):
        first = self.take()
        for kind in ("episode_length", "episode_return", "episode_count", "return_queue", "length_queue",
                     "elapsed_steps", "policy", "budget", "context_time_name", "environment", "native"):
            env, policy, context = self.make()
            if kind == "episode_length": env.episode_lengths = 1
            elif kind == "episode_return": env.episode_returns = .5
            elif kind == "episode_count": env.episode_count = 1
            elif kind == "return_queue": env.return_queue.append(.5)
            elif kind == "length_queue": env.length_queue.append(1)
            elif kind == "elapsed_steps": env.env._elapsed_steps = 1
            elif kind == "policy": policy.calls = 1
            elif kind == "budget": context["remaining_budget"] = 499
            elif kind == "context_time_name": context["episode_start_time"] = 200.0
            elif kind == "environment": env.unwrapped.prev[0] = 1.
            elif kind == "native": env.unwrapped.model.opt.gravity[2] += 1.
            result = witness.compare_witnesses(first, self.take(env, policy, context))
            with self.subTest(kind=kind): self.assertFalse(result["comparison_equal"])

    def test_all_random_states_are_preserved(self):
        baseline = self.take()
        for kind in ("numpy_global", "python_global", "env", "action_space", "observation_space"):
            env, policy, context = self.make()
            if kind == "numpy_global": np.random.random()
            elif kind == "python_global": random.random()
            elif kind == "env": env.unwrapped.np_random.random()
            elif kind == "action_space": env.unwrapped.action_space.np_random.random()
            else: env.unwrapped.observation_space.np_random.random()
            with self.subTest(kind=kind): self.assertFalse(witness.compare_witnesses(baseline, self.take(env, policy, context))["comparison_equal"])
            np.random.set_state(self.numpy_state);random.setstate(self.python_state)

    def test_alias_topology_and_future_noise_remain_in_comparison(self):
        self.context["shared_history"] = self.env.unwrapped.history_view;first = self.take()
        self.context["shared_history"] = self.context["shared_history"].copy();second = self.take()
        self.assertFalse(witness.compare_witnesses(first, second)["same_comparison_python"])
        self.context["shared_history"] = self.env.unwrapped.history_view
        self.context["noise"][-1, -1] += 1.;third = self.take()
        self.assertFalse(witness.compare_witnesses(first, third)["same_comparison_python"])

    def test_timing_queue_alias_cannot_be_silently_projected(self):
        self.context["controller_input"] = self.env.time_queue
        with self.assertRaisesRegex(ValueError, "alias escapes"): self.take()

    def test_only_exact_statistics_class_and_fields_are_reviewed(self):
        class DerivedStatistics(gym.wrappers.RecordEpisodeStatistics): pass
        wrapped = DerivedStatistics(self.env.env)
        with self.assertRaisesRegex(ValueError, "no subclass"): self.take(wrapped)
        self.env.controller_delay = 1.0
        with self.assertRaisesRegex(ValueError, "unreviewed statistics wrapper fields"): self.take()

    def test_live_method_changes_rejected(self):
        with patch.object(gym.wrappers.RecordEpisodeStatistics, "step", lambda env, action: None):
            with self.assertRaisesRegex(ValueError, "changed in memory"): self.take()

    def test_invalid_timing_values_fail_closed(self):
        for value in (float("nan"), float("inf"), -.5, 0, True):
            self.env.episode_start_time = value
            with self.subTest(timer=repr(value)), self.assertRaises(ValueError): self.take()
        self.env.episode_start_time = 100.0
        for value in (-1.0, float("nan"), 0, True):
            self.env.time_queue.clear();self.env.time_queue.append(value)
            with self.subTest(queue=repr(value)), self.assertRaises(ValueError): self.take()

    def test_raw_graph_edits_components_and_source_bindings_are_checked(self):
        first = self.take()
        for kind in ("raw", "comparison", "edit", "component", "runtime", "extra", "boolean_index"):
            value = deepcopy(first)
            if kind == "raw": value["raw_graph"][2].append("a" * 64)
            elif kind == "comparison": value["comparison_python_sha256"] = "a" * 64
            elif kind == "edit": value["projection_edits"][0]["field"] = "remaining_budget"
            elif kind == "component": value["components"][0]["comparison_sha256"] = "a" * 64
            elif kind == "runtime": value["statistics_source_sha256"] = "a" * 64
            elif kind == "extra": value["seed"] = 123
            elif kind == "boolean_index": value["projection_edits"][0]["layer_index"] = False
            with self.subTest(kind=kind), self.assertRaises(ValueError): witness.verify_witness(value)
        with self.assertRaises(ValueError): witness.verify_witness(first, native_sha256="a" * 64)
        with self.assertRaises(ValueError): witness.verify_witness(first, full_sha256="a" * 64)

    def test_comparison_does_not_accept_different_wrapper_identity(self):
        first = self.take();other = deepcopy(first);other["layer_types"][-1] = "unknown.ControlledByWallTime"
        with self.assertRaisesRegex(ValueError, "different wrapper stack"): witness.compare_witnesses(first, other)

    def test_actual_native_steps_are_counted_and_witness_reads_add_none(self):
        first = self.take();self.assertEqual((self.frames, self.steps, self.resets), (0, 0, 0))
        self.env.step(self.policy.action());middle = self.take()
        self.env.step(self.policy.action());last = self.take()
        self.assertEqual((self.frames, self.steps, self.queries, self.resets), (10, 2, 2, 0))
        self.assertFalse(witness.compare_witnesses(first, middle)["comparison_equal"])
        self.assertFalse(witness.compare_witnesses(middle, last)["comparison_equal"])
        self.assertEqual(len(self.env.time_queue), 1)
        WITNESS_EXAMPLES.append({"scope": "SOFTWARE_NATIVE_TWO_STEPS_TEN_FRAMES", "before": first, "after": last})


if __name__ == "__main__": unittest.main()

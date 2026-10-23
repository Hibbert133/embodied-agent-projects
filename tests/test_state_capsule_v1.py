"""Tiny MuJoCo software fixtures only: no MetaWorld factory or scientific seeds."""
import random
from collections import deque
import unittest
from unittest.mock import patch

import gymnasium as gym
import mujoco
import numpy as np

from src.analysis.state_capsule_v1 import capture, restore, PythonGraph, native_hash, python_state, layers, state_signature


XML = """<mujoco><option timestep="0.0025"/><size nuserdata="4"/>
<worldbody><body mocap="true" name="target" pos="0 0 .3"><site size=".01"/></body>
<body name="ball" pos="0 0 .1"><joint name="slide" type="slide" axis="1 0 0"/>
<geom type="sphere" size=".04" mass="1"/></body></worldbody>
<actuator><general joint="slide" dyntype="filter" dynprm=".1"/></actuator></mujoco>"""


class ToyEnv(gym.Env):
    def __init__(self):
        self.model = mujoco.MjModel.from_xml_string(XML)
        self.data = mujoco.MjData(self.model)
        self.action_space = gym.spaces.Box(-1, 1, (1,), dtype=np.float32)
        self.observation_space = gym.spaces.Box(-np.inf, np.inf, (5,), dtype=np.float64)
        self.action_space.seed(7); self.observation_space.seed(8)
        self.np_random = np.random.default_rng(9)
        self.render_mode = None; self.counter = 0
        self.history = np.arange(12., dtype=np.float64).reshape(3, 4).copy()
        self.history_view = self.history[::-1, 1:3]
        self.position_view = self.data.xpos[1]
        self.prev = np.zeros(5)
        mujoco.mj_forward(self.model, self.data)

    def __getstate__(self):
        raise AssertionError("must not pickle an environment")

    def reset(self, **kwargs):
        raise AssertionError("capture/restore must not reset")

    def step(self, action):
        self.counter += 1; self.data.ctrl[:] = action
        self.data.mocap_pos[:, 0] += float(action[0])*.01
        self.data.userdata[0] = self.np_random.normal()
        self.history_view[0, 0] += 1.
        mujoco.mj_step(self.model, self.data, nstep=5)
        obs = np.array([*self.data.qpos, *self.data.qvel, self.counter,
                        np.random.random(), random.random()])
        self.prev = obs.copy()
        return obs, float(self.data.act[0]), False, False, {
            "action_rng": float(self.action_space.np_random.random()),
            "obs_rng": float(self.observation_space.np_random.random())}


class Policy:
    def __init__(self): self.calls = 0
    def action(self):
        self.calls += 1
        return np.array([np.sin(self.calls)*.4], np.float32)


def run(env, policy, context, count):
    rows = []
    for _ in range(count):
        context["cursor"] += 1
        obs, reward, term, trunc, info = env.step(policy.action())
        rows.append((obs.copy(), reward, term, trunc, info, float(env.unwrapped.data.time)))
    return rows


class StateCapsuleTest(unittest.TestCase):
    def setUp(self):
        self.numpy_global, self.python_global = np.random.get_state(), random.getstate()
        np.random.seed(11); random.seed(12)
        self.env = gym.wrappers.TimeLimit(ToyEnv(), max_episode_steps=11)
        self.env._elapsed_steps = 0
        self.policy = Policy(); self.context = {"cursor": 3, "noise": np.arange(30.).reshape(10, 3)}

    def tearDown(self):
        np.random.set_state(self.numpy_global); random.setstate(self.python_global)

    def test_exact_continuation_restores_native_python_rng_policy_and_wrapper(self):
        run(self.env, self.policy, self.context, 3)
        capsule = capture(self.env, self.policy, self.context)
        semantic = state_signature(python_state(layers(self.env), self.policy, self.context), self.env.unwrapped.model, self.env.unwrapped.data)
        addresses = (self.env.unwrapped.model._address, self.env.unwrapped.data._address)
        first = run(self.env, self.policy, self.context, 8)
        b = self.env.unwrapped
        b.model.body_pos[-1, 0] += .3; b.model.opt.gravity[2] += .5
        b.data.qacc_warmstart[:] += 2.; b.data.mocap_pos[:] += .2
        b.prev[:] = 99; b.counter = 100; self.context["noise"][:] = -1
        recovered = restore(capsule, self.env, self.policy)
        self.assertEqual(state_signature(python_state(layers(self.env), self.policy, recovered), b.model, b.data), semantic)
        second = run(self.env, self.policy, recovered, 8)
        for a, c in zip(first, second):
            np.testing.assert_array_equal(a[0], c[0]); self.assertEqual(a[1:], c[1:])
        self.assertTrue(second[-1][3]); self.assertFalse(second[-2][3])
        self.assertEqual(addresses, (b.model._address, b.data._address))
        np.testing.assert_array_equal(recovered["noise"], np.arange(30.).reshape(10, 3))

    def test_native_and_python_array_aliases_preserved(self):
        b = self.env.unwrapped
        capsule = capture(self.env, self.policy, {"same_array": b.history_view})
        b.history[:] = -9; b.data.xpos[:] = -4
        context = restore(capsule, self.env, self.policy)
        self.assertIs(context["same_array"], b.history_view)
        self.assertTrue(np.shares_memory(b.history_view, b.history))
        self.assertTrue(np.shares_memory(b.position_view, b.data.xpos))
        b.history[2, 1] = 7.; self.assertEqual(b.history_view[0, 0], 7.)
        b.data.xpos[1, 2] = 8.; self.assertEqual(b.position_view[2], 8.)

    def test_snapshot_is_detached_and_repeatable(self):
        capsule = capture(self.env, self.policy, self.context)
        expected = native_hash(capsule._model, capsule._data)
        for _ in range(3):
            run(self.env, self.policy, self.context, 2)
            self.context = restore(capsule, self.env, self.policy)
            self.assertEqual(native_hash(capsule._model, capsule._data), expected)

    def test_capture_after_restore_keeps_shared_buffers(self):
        first = capture(self.env, self.policy, self.context)
        context = restore(first, self.env, self.policy)
        second = capture(self.env, self.policy, context)
        expected = run(self.env, self.policy, context, 2)
        recovered = restore(second, self.env, self.policy)
        actual = run(self.env, self.policy, recovered, 2)
        for a, b in zip(expected, actual):
            np.testing.assert_array_equal(a[0], b[0]); self.assertEqual(a[1:], b[1:])
        base = self.env.unwrapped
        self.assertTrue(np.shares_memory(base.history, base.history_view))

    def test_capture_and_restore_call_no_env_reset_step_or_constructor(self):
        with patch.object(ToyEnv, "__init__", side_effect=AssertionError("constructor")), patch.object(ToyEnv, "step", side_effect=AssertionError("step")):
            capsule = capture(self.env, self.policy, self.context)
            restore(capsule, self.env, self.policy)

    def test_wrong_owner_and_replaced_native_objects_rejected(self):
        capsule = capture(self.env, self.policy, self.context)
        with self.assertRaises(ValueError): restore(capsule, self.env, Policy())
        b = self.env.unwrapped; b.model = mujoco.MjModel.from_xml_string(XML)
        with self.assertRaisesRegex(ValueError, "owner objects"): restore(capsule, self.env, self.policy)

    def test_modified_saved_native_state_rejected_before_live_mutation(self):
        capsule = capture(self.env, self.policy, self.context)
        capsule._data.qpos[:] += 1
        before = self.env.unwrapped.data.qpos.copy()
        with self.assertRaisesRegex(ValueError, "mutated"): restore(capsule, self.env, self.policy)
        np.testing.assert_array_equal(before, self.env.unwrapped.data.qpos)

    def test_opaque_callable_and_environment_payloads_rejected(self):
        for value in [object(), lambda: None, self.env]:
            with self.assertRaises(ValueError): capture(self.env, self.policy, {"opaque": value})

    def test_object_and_structured_arrays_rejected(self):
        for value in [np.array([object()], dtype=object), np.zeros(2, dtype=[("x", "f8")])]:
            with self.assertRaises(ValueError): capture(self.env, self.policy, {"bad": value})

    def test_numpy_generator_alias_and_random_random_state(self):
        gen = np.random.default_rng(17); rng = random.Random(18)
        capsule = capture(self.env, self.policy, {"g1": gen, "g2": gen, "r": rng})
        expected = (gen.normal(), rng.random())
        saved = restore(capsule, self.env, self.policy)
        self.assertIs(saved["g1"], saved["g2"])
        self.assertEqual(expected, (saved["g1"].normal(), saved["r"].random()))

    def test_class_state_change_is_rejected(self):
        capsule = capture(self.env, self.policy, self.context)
        old = ToyEnv.metadata
        try:
            ToyEnv.metadata = {"changed": True}
            with self.assertRaisesRegex(ValueError, "class state"): restore(capsule, self.env, self.policy)
        finally: ToyEnv.metadata = old

    def test_callback_and_active_renderer_rejected(self):
        with patch.object(mujoco, "get_mjcb_control", return_value=object()):
            with self.assertRaisesRegex(ValueError, "callback"): capture(self.env, self.policy, self.context)
        class Renderer:
            _viewers = {"active": True}; viewer = None
        self.env.unwrapped.mujoco_renderer = Renderer()
        with self.assertRaisesRegex(ValueError, "renderer"): capture(self.env, self.policy, self.context)

    def test_version_change_rejected(self):
        with patch.object(mujoco, "__version__", "0.0.0"):
            with self.assertRaisesRegex(ValueError, "ABI"): capture(self.env, self.policy, self.context)

    def test_empty_readonly_fortran_arrays_and_cycles(self):
        f = np.asfortranarray(np.arange(12.).reshape(3, 4)); ro = f[:, ::-1]; ro.flags.writeable = False
        context = {"f": f, "ro": ro, "empty": np.zeros(0)}; context["cycle"] = context
        capsule = capture(self.env, self.policy, context); saved = restore(capsule, self.env, self.policy)
        self.assertIs(saved, saved["cycle"]); self.assertFalse(saved["ro"].flags.writeable)
        self.assertTrue(np.shares_memory(saved["f"], saved["ro"]))
        np.testing.assert_array_equal(saved["ro"], ro)

    def test_real_registered_callable_metadata_and_deques_without_factory(self):
        import metaworld  # registration only; no Env/task population created
        from gymnasium.envs.registration import EnvSpec, registry
        callback = registry['Meta-World/MT1'].entry_point
        self.env.unwrapped.spec = EnvSpec(id='software-fixture', entry_point=callback)
        self.context['queue'] = deque([np.array([1., 2.])], maxlen=3)
        capsule = capture(self.env, self.policy, self.context)
        saved = restore(capsule, self.env, self.policy)
        self.assertIs(self.env.unwrapped.spec.entry_point, callback)
        self.assertEqual(saved['queue'].maxlen, 3)
        np.testing.assert_array_equal(saved['queue'][0], [1., 2.])
        with self.assertRaises(ValueError): capture(self.env, self.policy, {'callable': callback})


if __name__ == "__main__": unittest.main()

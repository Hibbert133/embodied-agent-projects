"""Software callback integration only: no MetaWorld factory/physics is executed."""
import contextlib
import copy
import gzip
import io
import json
from pathlib import Path
import random
import tempfile
import types
import unittest
from unittest.mock import patch

import gymnasium as gym
import numpy as np
from scripts import run_state_capsule_qualification_v2 as collector


class RecordOnlyFixture(gym.Env):
    def __init__(self):
        self.data=types.SimpleNamespace(time=0.)
        self.action_space=gym.spaces.Box(-1,1,(4,),dtype=np.float32)
        self.observation_space=gym.spaces.Box(-10,10,(39,),dtype=np.float64)
        self.goal_space=gym.spaces.Box(-1,1,(3,),dtype=np.float64)
        self.calls=0
    def reset(self,*,seed=None,options=None):
        super().reset(seed=seed);return np.zeros(39),{}
    def step(self,action):
        self.calls+=1;self.data.time+=.0125
        return np.full(39,self.calls/100),np.float64(1),np.bool_(False),np.bool_(False),{'success':np.bool_(False),'nested':np.array([.1,.2],np.float32)}


class CapsuleCollectorRecordingTest(unittest.TestCase):
    def test_initial_and_eight_numpy_step_records_reach_capture_entry(self):
        fixture=RecordOnlyFixture();c=collector.io.read(collector.CONFIG)
        m={'experiment_run_id':'SOFTWARE_RECORD_CALLBACK_ONLY','manifest_id':'a'*64,'source_git_commit':'b'*40,
           'config':c,'population_oracle':[{'case':0,'seed':19000,'replicate':0,'prefix_steps':8,'task':'push-v3'}]}
        numpy_state,python_state=np.random.get_state(),random.getstate()
        try:
            with (tempfile.TemporaryDirectory() as tmp, patch.object(collector,'load',return_value=m),patch.object(collector.io,'clean'),
                 patch.object(collector.io,'git',return_value='b'*40),patch.object(collector,'create_task_environment',return_value=fixture) as factory,
                 patch.object(collector,'create_task_policy',return_value=object()),patch.object(collector,'capture',side_effect=RuntimeError('SOFTWARE_CAPTURE_ENTRY_REACHED')) as entry,
                 contextlib.redirect_stdout(io.StringIO())):
                path=Path(tmp)/'manifest.json'
                with self.assertRaises(SystemExit):collector.run(path)
                factory.assert_called_once();entry.assert_called_once();self.assertEqual(fixture.calls,8)
                summary=json.loads((Path(tmp)/'collection/summary.json').read_text())
                self.assertEqual(summary['failure']['reason'],'SOFTWARE_CAPTURE_ENTRY_REACHED')
                self.assertEqual(summary['actual_controlled_steps'],8)
                with gzip.open(Path(tmp)/'collection/events.jsonl.gz','rt',encoding='utf-8') as handle:events=[json.loads(line) for line in handle]
                self.assertEqual([e['sequence'] for e in events],list(range(len(events))))
                self.assertEqual(sum(e['event']=='STEP_COMPLETE' for e in events),8)
                initial=next(e for e in events if e['event']=='CONTROLLED_INITIAL')
                self.assertEqual(initial['observation'],[0.]*39)
        finally:
            np.random.set_state(numpy_state);random.setstate(python_state)

    def test_new_protocol_population_and_prior_failure_are_separate(self):
        c=collector.io.read(collector.CONFIG);collector.validate(c)
        self.assertEqual([r['seed'] for r in collector.population(c)],list(range(19000,19012)))
        self.assertEqual(c['reserved'],[19012,19199])
        changed=copy.deepcopy(c);changed['seed_start']=18800
        with self.assertRaises(ValueError):collector.validate(changed)

    def test_installed_wrapper_stack_restores_tiny_native_fixture(self):
        # Actual wrapper classes; tiny XML software physics, no task constructor.
        import metaworld
        from metaworld.types import Task
        from metaworld.wrappers import CheckpointWrapper,RandomTaskSelectWrapper,AutoTerminateOnSuccessWrapper
        from gymnasium.envs.registration import EnvSpec,registry
        from tests.test_state_capsule_v1 import ToyEnv,Policy,run
        from src.analysis.state_capsule_v1 import capture,restore
        base=ToyEnv();base.spec=EnvSpec(id='SOFTWARE_WRAPPER_ONLY',entry_point=registry['Meta-World/MT1'].entry_point)
        env=gym.wrappers.TimeLimit(base,11);env._elapsed_steps=0
        env=AutoTerminateOnSuccessWrapper(env);env.toggle_terminate_on_success(False)
        env=gym.wrappers.RecordEpisodeStatistics(env);env.episode_start_time=0.
        env=RandomTaskSelectWrapper(env,[Task('SOFTWARE_ONLY',b'fixture')],False)
        env=CheckpointWrapper(env,'SOFTWARE_ONLY');env=gym.wrappers.PassiveEnvChecker(env)
        env.checked_step=True;env.checked_reset=True
        env=gym.wrappers.OrderEnforcing(env);env._has_reset=True
        numpy_state,python_state=np.random.get_state(),random.getstate()
        try:
            policy=Policy();context={'cursor':0};run(env,policy,context,3)
            saved=capture(env,policy,context);first=run(env,policy,context,8)
            recovered=restore(saved,env,policy);second=run(env,policy,recovered,8)
            for a,b in zip(first,second):
                np.testing.assert_array_equal(a[0],b[0]);self.assertEqual(a[1:4],b[1:4]);self.assertEqual(a[5],b[5])
                left,right=copy.deepcopy(a[4]),copy.deepcopy(b[4])
                for info in (left,right):
                    if 'episode' in info:info['episode'].pop('t',None)
                self.assertEqual(left,right)
            self.assertTrue(second[-1][3])
        finally:
            np.random.set_state(numpy_state);random.setstate(python_state)


if __name__=='__main__':unittest.main()

"""Tiny native fixture: no MetaWorld task creation or scientific seeds executed."""
import copy
import io
import unittest
from unittest.mock import patch
import gymnasium as gym
import mujoco
import numpy as np
from src.analysis.capsule_record_json_v2 import JsonJournal
from src.analysis.paired_probe_host_v1 import ProbeSession,physical_comparison,fresh_tail
from src.probe.cache_acquisition_evidence_v1 import CacheAcquisitionEvidenceV1
from src.probe.chronological_cache_reference import BLOCK8
from src.probe.cold_start_response import ColdPrefix
from src.probe.lifecycle_ledger import LifecycleLedger


XML='''<mujoco><option timestep="0.0025"/><worldbody><body mocap="true"><site size=".01"/></body>
<body pos="0 0 .1"><joint name="x" type="slide" axis="1 0 0"/><geom type="sphere" size=".04" mass="1"/></body>
</worldbody><actuator><motor joint="x"/></actuator></mujoco>'''


class TinyEnv(gym.Env):
    def __init__(self):
        self.model=mujoco.MjModel.from_xml_string(XML);self.data=mujoco.MjData(self.model)
        self.calls=0;self.render_mode=None
        self.action_space=gym.spaces.Box(-1,1,(4,),dtype=np.float32)
        self.observation_space=gym.spaces.Box(-10,10,(39,),dtype=np.float64)
        self.np_random=np.random.default_rng(17)
    def do_simulation(self,ctrl,n_frames):
        self.data.ctrl[:]=ctrl;mujoco.mj_step(self.model,self.data,nstep=n_frames)
    def step(self,action):
        self.calls+=1;self.data.mocap_pos[0,:2]+=np.asarray(action[:2])*.01
        self.do_simulation([action[0]],5)
        obs=np.zeros(39);obs[:2]=[self.data.qpos[0],self.data.qvel[0]];obs[2]=self.calls/100
        return obs,float(self.calls),False,False,{'success':self.calls>=12}


class TinyPolicy:
    def get_action(self,obs):return np.asarray([.4,.3,0,0],np.float32)


def packet(session):
    c=session.ctx;prefix=ColdPrefix('push-v3',tuple(c['initial_observation']),tuple(map(tuple,c['commands'])),tuple(map(tuple,c['observations'])),True)
    return CacheAcquisitionEvidenceV1(prefix,(1,0,.1,0,1,-.1),tuple(map(tuple,np.eye(6))),
        'reach-v3',1,False,(.4,.3,0,0),496)


class PairedProbeHostTest(unittest.TestCase):
    def setUp(self):
        self.text=io.StringIO();self.writer=JsonJournal(self.text,{'manifest_id':'SOFTWARE_ONLY'})
        self.events=[]
        def emit(event,payload):
            value=self.writer.emit(event,payload);self.events.append(value);return value
        self.emit=emit;self.ledger=LifecycleLedger(emit,100000);self.budget={'completed':0,'maximum':10000}
        self.env=TinyEnv();self.policy=TinyPolicy();original=TinyEnv.do_simulation
        self.instrument=patch.object(TinyEnv,'do_simulation',lambda env,ctrl,n_frames:self.ledger.simulation_call(original,env,ctrl,n_frames))
        self.instrument.start()
        fault={'matrix_xy':[[1,0],[0,1]],'bias_xy':[.1,-.06],'deadzone_xy':[0,0]}
        self.session=ProbeSession(self.env,self.policy,np.zeros(39),'push-v3',700001,fault,emit,self.ledger,self.budget)
    def tearDown(self):self.instrument.stop()

    def test_matched_fresh_future_replay_and_source_return_preserve_real_costs(self):
        s=self.session;s.prefix4(BLOCK8[:4]);e=packet(s);before=s.snapshot('FOUR')
        fit={'valid':True,'matrix_xy':[[1,0],[0,1]],'bias_xy':[0,0],'nfev':1}
        with patch('src.probe.probe_effect_program_v1.infer_operator',return_value=fit):
            source,_=s.execute('PROBE_UPDATE',{},e,role='SOURCE',future=0)
            source_ctx=copy.deepcopy(s.ctx);after=s.snapshot('SOURCE_AFTER')
            recorded=None
            for repeat in range(2):
                s.recover(before,'EVAL');s.replace_future(1)
                s.execute('REUSE_OLD',{},e,role='EVAL' if repeat==0 else 'SENTINEL',future=1)
                rows=[physical_comparison(row) for row in s.last_rows]
                if recorded is None:recorded=rows
                else:self.assertEqual(recorded,rows)
            count=self.budget['completed'];s.recover(after,'SOURCE_RETURN')
        self.assertEqual(s.ctx['calls'],source['outcome']['total_steps'])
        np.testing.assert_array_equal(s.ctx['noise_rows'],source_ctx['noise_rows'])
        self.assertEqual(self.budget['completed'],count);self.assertGreater(count,s.ctx['calls'])
        self.assertEqual(self.ledger.counts['simulation_frames_completed'],5*count)

    def test_probe_keep_update_and_fallback_share_physical_prefix(self):
        s=self.session;s.prefix4(BLOCK8[:4]);e=packet(s);cap=s.snapshot('FOUR');witnesses=[];trajectories=[]
        fit={'valid':True,'matrix_xy':[[1,0],[0,1]],'bias_xy':[0,0],'nfev':1}
        with patch('src.probe.probe_effect_program_v1.infer_operator',return_value=fit):
            for program in ('PROBE_KEEP','PROBE_UPDATE','PROBE_UPDATE_KEEP'):
                s.recover(cap,'EVAL');s.replace_future(2)
                r,_=s.execute(program,{},e,role='EVAL',future=2);witnesses.append(r['boundary8'])
                trajectories.append([physical_comparison(row) for row in s.last_rows])
        self.assertEqual(witnesses[0],witnesses[1]);self.assertEqual(witnesses[1],witnesses[2])
        self.assertEqual(trajectories[1],trajectories[2])

    def test_private_noise_is_replaced_only_after_observed_four_steps(self):
        s=self.session
        with self.assertRaises(ValueError):s.replace_future(1)
        s.prefix4(BLOCK8[:4]);past=s.ctx['noise_rows'][:4].copy()
        s.replace_future(3);np.testing.assert_array_equal(past,s.ctx['noise_rows'][:4])
        np.testing.assert_array_equal(s.ctx['noise_rows'][4:],fresh_tail(700001,3))
        self.assertFalse(s.ctx['noise_rows'].flags.writeable)

    def test_actor_acknowledgement_and_execution_are_saved_before_physics(self):
        s=self.session;s.prefix4(BLOCK8[:4]);e=packet(s)
        s.execute('REUSE_OLD',{},e,role='SOURCE',future=0)
        byseq={v['sequence']:v for v in self.events}
        for row in s.last_rows:
            command=byseq[row['global_command_sequence']];intent=byseq[row['intent_sequence']]
            self.assertEqual(command['public_payload']['command'],row['command'])
            self.assertLess(command['saved_ns'],row['execution_started_ns'])
            self.assertLess(intent['saved_ns'],row['execution_started_ns'])
        self.assertTrue(all('seed' not in v.get('public_payload',{}) for v in self.events))


if __name__=='__main__':unittest.main()

"""One-axis native software fixture only, not a robot calibration population."""
from copy import deepcopy
from dataclasses import asdict
import io
import unittest
from unittest.mock import patch

import mujoco
import numpy as np

from src.analysis.capsule_record_json_v2 import JsonJournal
from src.analysis.paired_probe_host_v1 import ProbeSession
from src.analysis.physical_reprobe_host_v1 import execute_reprobe
from src.probe.lifecycle_ledger import LifecycleLedger
from src.probe.operator_identification import affine_controller, encode_controller
from src.probe.physical_reprobe_v1 import ANCHOR, PROGRAM
from tests.test_paired_probe_host_v1 import TinyEnv, TinyPolicy


SOFTWARE_RECEIPTS = []


class WarmTinyEnv(TinyEnv):
    def observation(self):
        result=np.zeros(39);result[:3]=ANCHOR;result[0]+=float(self.data.qpos[0])
        result[4:7]=[0.,.8,.02]
        return result

    def reset(self, **kwargs):
        mujoco.mj_resetData(self.model,self.data);self.calls=0
        return self.observation(),{}

    def step(self, action):
        self.calls+=1;self.do_simulation([action[0]],5)
        return self.observation(),0.,False,False,{"success":False}


class PhysicalReprobeHostTests(unittest.TestCase):
    def setUp(self):
        self.log=io.StringIO();self.journal=JsonJournal(self.log,{"manifest_id":"SOFTWARE_ONLY"})
        self.events={};self.frames=0;self.native_resets=0
        def emit(kind,payload):
            value=self.journal.emit(kind,payload);self.events[value["sequence"]]=deepcopy(value);return value
        self.emit=emit;self.ledger=LifecycleLedger(emit,10000);self.env=WarmTinyEnv()
        original_sim=WarmTinyEnv.do_simulation;original_reset=WarmTinyEnv.reset
        original_native=mujoco.mj_step;original_native_reset=mujoco.mj_resetData
        def native(*args,**kwargs):
            result=original_native(*args,**kwargs);self.frames+=int(kwargs.get("nstep",args[2] if len(args)>2 else 1));return result
        def native_reset(*args,**kwargs):
            result=original_native_reset(*args,**kwargs);self.native_resets+=1;return result
        self.patches=[patch.object(WarmTinyEnv,"do_simulation",lambda env,ctrl,n:self.ledger.simulation_call(original_sim,env,ctrl,n)),
            patch.object(WarmTinyEnv,"reset",lambda env,**kw:self.ledger.reset_call(original_reset,env,**kw)),
            patch.object(mujoco,"mj_step",native),patch.object(mujoco,"mj_resetData",native_reset)]
        for p in self.patches:p.start()
        with self.ledger.scope("CONTROLLED_RESET"):initial,_=self.env.reset()
        fault={"matrix_xy":[[1,0],[0,1]],"bias_xy":[0,0],"deadzone_xy":[0,0]}
        self.session=ProbeSession(self.env,TinyPolicy(),initial,"push-v3",700101,fault,emit,self.ledger,{"completed":0,"maximum":500})
        s=self.session;s.branch={"role":"SOFTWARE_PREFIX","future":0,"program":"FIXTURE"}
        source=s._agent_emit("CHOICE",{"action":"FIXTURE_PREFIX","at_calls":0})
        for command in PROGRAM:
            saved=s._agent_emit("COMMAND",{"at_calls":s.ctx["calls"],"phase":"FIXED_PROBE", "before":asdict(s.public()),
                "decision_sequence":source["sequence"],"command":list(command),"raw_policy":None})
            s._agent_step(saved)
        fit={"valid":True,"matrix_xy":[[1.,0.],[0.,1.]],"bias_xy":[0.,0.],"nfev":0,"software_stub":True}
        fitted=s._agent_emit("FIT_RESULT",{"at_calls":8,"fit":fit})
        correction=affine_controller(fit["matrix_xy"],fit["bias_xy"])
        self.choice=s._agent_emit("CHOICE",{"at_calls":8,"action":"RUN_FITTED","purpose":"CURRENT_POLICY_CONTROLLER",
            "fitted_prefix_steps":8,"fit_sequence":fitted["sequence"],"controller":correction})["sequence"]
        raw=s.policy_query(s.public().observation)
        saved=s._agent_emit("COMMAND",{"at_calls":8,"phase":"POLICY","before":asdict(s.public()),
            "decision_sequence":self.choice,"command":encode_controller(correction,raw).tolist(),"raw_policy":raw.tolist()})
        s._agent_step(saved)

    def tearDown(self):
        SOFTWARE_RECEIPTS.append({"test":self.id(),"native_frames":self.frames,"native_resets":self.native_resets,
            "host_control_steps":self.session.completed,"host_policy_queries":self.session.policy_queries,
            "lifecycle":self.ledger.snapshot(),"new_metaworld_steps":0,"new_scientific_seeds":0,"new_api_calls":0,
            "scope":"One-axis native fixture with a synthetic known correction; no qualified identification."})
        for p in reversed(self.patches):p.stop()
        self.env.close()

    def execute(self, lookup=None):
        return execute_reprobe(self.session,self.choice,lookup or (lambda i:deepcopy(self.events[i])))

    def test_saved_operation_physically_executes_without_reset_or_new_fit(self):
        s=self.session;tape=s.ctx["noise_rows"];before=s.ctx["calls"];clock=float(self.env.data.time)
        result=self.execute()
        self.assertEqual(result["public"]["reason"],"COMPLETE_UNQUALIFIED")
        self.assertEqual(self.native_resets,1)
        self.assertIs(s.ctx["noise_rows"],tape)
        self.assertEqual(result["new_simulation_frames"],5*(s.ctx["calls"]-before))
        self.assertEqual(self.frames,5*s.completed)
        self.assertAlmostEqual(float(self.env.data.time)-clock,.0125*result["new_control_steps"],places=10)
        self.assertEqual((s.captures,s.restores,result["new_parameter_fits"],result["new_policy_queries"]),(0,0,0,0))
        for row in s.last_rows[before:]:
            command=self.events[row["global_command_sequence"]]
            self.assertEqual(command["public_payload"]["command"],row["command"])
            self.assertLess(command["saved_ns"],row["execution_started_ns"])
            self.assertEqual(row["noise_cursor_after"],row["logical_step"]+1)
            self.assertNotIn("seed",command["public_payload"])

    def test_repeated_acquisition_is_rejected_without_more_physics(self):
        self.execute();before=self.frames
        with self.assertRaisesRegex(ValueError,"already consumed"):self.execute()
        self.assertEqual(self.frames,before)

    def test_source_correction_must_match_saved_fit(self):
        def changed(index):
            row=deepcopy(self.events[index])
            if index==self.session._map[self.choice]:row["public_payload"]["controller"]["offset"][0]=.1
            return row
        before=self.frames
        with self.assertRaisesRegex(ValueError,"saved valid fit"):self.execute(changed)
        self.assertEqual(self.frames,before)

    def test_source_must_be_the_last_actually_applied_correction(self):
        target=self.session.last_rows[-1]["global_command_sequence"]
        def changed(index):
            row=deepcopy(self.events[index])
            if index==target:row["public_payload"]["decision_sequence"]=-1
            return row
        with self.assertRaisesRegex(ValueError,"last actually applied"):self.execute(changed)

    def test_prior_restore_or_copy_is_not_admitted(self):
        self.session.captures=1;before=self.frames
        with self.assertRaisesRegex(ValueError,"copy or restoration"):self.execute()
        self.assertEqual(self.frames,before)

    def test_source_fit_saved_after_command_is_rejected(self):
        choice=self.events[self.session._map[self.choice]]["public_payload"]
        local=choice["fit_sequence"];old=self.session._map[local]
        future=max(self.events)+100
        self.events[future]=deepcopy(self.events[old]);self.session._map[local]=future
        with self.assertRaisesRegex(ValueError,"precede physical use"):self.execute()

    def test_last_command_must_apply_saved_controller_to_its_raw_policy(self):
        target=self.session.last_rows[-1]["global_command_sequence"]
        def changed(index):
            row=deepcopy(self.events[index])
            if index==target:row["public_payload"]["raw_policy"][0]=-.7
            return row
        with self.assertRaisesRegex(ValueError,"did not apply source correction"):self.execute(changed)

    def test_stale_or_changed_initial_public_observation_is_rejected(self):
        self.session.ctx["observation"][0]+=.01
        with self.assertRaisesRegex(ValueError,"last physical receipt"):self.execute()

    def test_real_mid_operation_reset_is_detected(self):
        original=self.session._agent_step
        def reset(saved):
            result=original(saved)
            with self.ledger.scope("CONTROLLED_RESET"):self.env.reset()
            return result
        with patch.object(self.session,"_agent_step",reset):
            with self.assertRaisesRegex(ValueError,"mid-operation reset"):self.execute()
        self.assertEqual(self.native_resets,2)

    def test_equal_valued_replacement_noise_tape_is_rejected(self):
        original=self.session._agent_step
        def replace(saved):
            result=original(saved);tape=self.session.ctx["noise_rows"].copy();tape.flags.writeable=False
            self.session.ctx["noise_rows"]=tape;return result
        with patch.object(self.session,"_agent_step",replace):
            with self.assertRaisesRegex(ValueError,"noise tape replaced"):self.execute()

    def test_additional_native_frames_are_detected_immediately(self):
        original=self.session._agent_step
        def extra(saved):
            result=original(saved)
            with self.ledger.scope("CONTROL"):self.env.do_simulation([0.],5)
            return result
        before=self.frames
        with patch.object(self.session,"_agent_step",extra):
            with self.assertRaisesRegex(ValueError,"physical frame work"):self.execute()
        self.assertEqual(self.frames-before,10)

    def test_missing_whole_study_budget_does_not_start(self):
        self.session.run_budget["maximum"]=self.session.run_budget["completed"]+71;before=self.frames
        with self.assertRaisesRegex(ValueError,"whole-study budget"):self.execute()
        self.assertEqual(self.frames,before)


if __name__=="__main__":unittest.main()

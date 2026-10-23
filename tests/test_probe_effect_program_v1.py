import copy
import unittest
from unittest.mock import patch
import numpy as np
from src.probe.cache_acquisition_evidence_v1 import CacheAcquisitionEvidenceV1
from src.probe.chronological_cache_reference import BLOCK8
from src.probe.cold_start_response import ColdPrefix
from src.probe.continuous import StepObservation
from src.probe.probe_effect_program_v1 import execute_warm, execute_cold


def evidence():
    obs=tuple(np.zeros(39));prefix=ColdPrefix('push-v3',obs,BLOCK8[:4],(obs,)*4,True)
    return CacheAcquisitionEvidenceV1(prefix,(1,0,.1,0,1,-.1),tuple(map(tuple,np.eye(6))),
        'reach-v3',1,False,(.4,.3,0,0),496)


class PublicCallbackFixture:
    def __init__(self,start=4,finish=10):self.calls=start;self.finish=finish;self.events=[];self.sent=[]
    def emit(self,event,payload):
        saved={**copy.deepcopy(payload),'sequence':len(self.events),'saved_ns':100+len(self.events)}
        self.events.append((event,saved));return saved
    def step(self,saved):
        self.calls+=1;self.sent.append(saved['command'])
        return StepObservation(tuple(np.zeros(39)),False,False,self.calls>=self.finish)


class ProbeEffectProgramTest(unittest.TestCase):
    def test_valid_legal_choices_change_real_commands(self):
        records={};hosts={};fit={'valid':True,'matrix_xy':[[1,0],[0,1]],'bias_xy':[0,0],'nfev':1}
        for program in ('REUSE_OLD','PROBE_KEEP','PROBE_UPDATE','PROBE_UPDATE_KEEP'):
            host=PublicCallbackFixture();hosts[program]=host
            with patch('src.probe.probe_effect_program_v1.infer_operator',return_value=fit):
                records[program]=execute_warm(program,evidence(),StepObservation(tuple(np.zeros(39)),False,False,False),{},lambda obs:np.array([.4,.3,0,0]),host.step,host.emit)
        self.assertEqual(records['REUSE_OLD']['outcome']['fixed_probe_suffix_steps'],0)
        self.assertEqual(records['PROBE_KEEP']['outcome']['fixed_probe_suffix_steps'],4)
        self.assertNotEqual(hosts['REUSE_OLD'].sent[0],hosts['PROBE_KEEP'].sent[0])
        self.assertNotEqual(hosts['PROBE_KEEP'].sent[-1],hosts['PROBE_UPDATE'].sent[-1])
        self.assertEqual(hosts['PROBE_UPDATE'].sent,hosts['PROBE_UPDATE_KEEP'].sent)

    def test_invalid_update_stops_or_really_continues_as_registered(self):
        with patch('src.probe.probe_effect_program_v1.infer_operator',return_value={'valid':False,'reason':'TEST_INVALID','nfev':0}):
            stop=PublicCallbackFixture();keep=PublicCallbackFixture()
            a=execute_warm('PROBE_UPDATE',evidence(),StepObservation(tuple(np.zeros(39)),False,False,False),{},lambda obs:np.zeros(4),stop.step,stop.emit)
            b=execute_warm('PROBE_UPDATE_KEEP',evidence(),StepObservation(tuple(np.zeros(39)),False,False,False),{},lambda obs:np.zeros(4),keep.step,keep.emit)
        self.assertEqual((a['outcome']['total_steps'],a['outcome']['deadline_loss']),(8,500))
        self.assertTrue(a['outcome']['stopped']);self.assertTrue(b['outcome']['success'])
        self.assertFalse(b['outcome']['applied_new_controller']);self.assertEqual(keep.calls,10)

    def test_probe_ending_success_does_not_fabricate_a_fit(self):
        host=PublicCallbackFixture(finish=6)
        with patch('src.probe.probe_effect_program_v1.infer_operator') as fit:
            result=execute_warm('PROBE_UPDATE',evidence(),StepObservation(tuple(np.zeros(39)),False,False,False),{},lambda obs:np.zeros(4),host.step,host.emit)
        fit.assert_not_called();self.assertEqual(result['outcome']['total_steps'],6)
        self.assertTrue(result['outcome']['success']);self.assertIsNone(result['fit'])

    def test_exhaustion_keeps_real_steps_and_penalizes_failure(self):
        host=PublicCallbackFixture(finish=999)
        result=execute_warm('REUSE_OLD',evidence(),StepObservation(tuple(np.zeros(39)),False,False,False),{},lambda obs:np.zeros(4),host.step,host.emit)
        self.assertEqual(host.calls,500);self.assertEqual(result['outcome']['suffix_steps'],496)
        self.assertEqual(result['outcome']['deadline_loss'],500);self.assertFalse(result['outcome']['success'])

    def test_unknown_program_extra_evidence_and_host_oracle_ack_rejected(self):
        host=PublicCallbackFixture()
        with self.assertRaises(ValueError):execute_warm('BAD',evidence(),StepObservation(tuple(np.zeros(39)),False,False,False),{},lambda obs:np.zeros(4),host.step,host.emit)
        packet=evidence().to_dict();packet['seed']=1
        with self.assertRaises(ValueError):CacheAcquisitionEvidenceV1.from_dict(packet)
        def bad_ack(event,payload):return {**host.emit(event,payload),'fault_oracle':1}
        with self.assertRaises(ValueError):execute_warm('REUSE_OLD',evidence(),StepObservation(tuple(np.zeros(39)),False,False,False),{},lambda obs:np.zeros(4),host.step,bad_ack)
        self.assertEqual(host.calls,4)

    def test_cold_source_uses_actual_eight_response_terms(self):
        host=PublicCallbackFixture(start=0,finish=10);fit={'valid':True,'matrix_xy':[[1,0],[0,1]],'bias_xy':[0,0],'nfev':1}
        with patch('src.probe.probe_effect_program_v1.infer_operator',return_value=fit) as infer:
            result=execute_cold('push-v3',StepObservation(tuple(np.zeros(39)),False,False,False),{},lambda obs:np.zeros(4),host.step,host.emit)
        self.assertEqual(len(infer.call_args.args[1].commands),8)
        self.assertEqual(result['outcome']['fixed_probe_suffix_steps'],8);self.assertTrue(result['outcome']['applied_new_controller'])


if __name__=='__main__':unittest.main()

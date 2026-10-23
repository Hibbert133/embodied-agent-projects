"""Synthetic chronology audit and guarded no-interaction/fitting boundaries."""
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
import socket
import os
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from src.analysis import linear_command_preflight_io_v1 as allocation
from scripts import audit_linear_command_preflight_v1 as auditor
from tests.test_linear_command_preflight_v1 import query


class PreflightPipelineTests(unittest.TestCase):
    def test_raw_record_audit_detects_future_values_even_with_current_timestamps(self):
        q=query(); history=list(q.observations)
        t={'task':q.task,'initial':list(history[0]),'observations':[list(history[1]),list(history[2]),list(np.asarray(history[2])+.1)],
           'commands':[[0.,0.,0.,0.]]*2+[list(q.baseline_command)]}
        raw=q.to_dict(); raw['decision_step']=2; raw['observation_steps']=[0,1,2]
        auditor.current_query(raw,t,2)
        raw['observations']=[*history[1:],t['observations'][-1]]
        with self.assertRaisesRegex(ValueError,'future observation'): auditor.current_query(raw,t,2)

    def test_raw_record_audit_detects_candidate_and_command_cursor_changes(self):
        q=query(); history=list(q.observations)
        t={'task':q.task,'initial':history[0],'observations':history[1:],
           'commands':[[0.,0.,0.,0.]]*2+[list(q.baseline_command)]}
        raw=q.to_dict(); raw['decision_step']=2; raw['observation_steps']=[0,1,2]
        altered=deepcopy(raw); altered['baseline_command']=(0.,0.,0.,0.)
        with self.assertRaises(ValueError): auditor.current_query(altered,t,2)
        altered=deepcopy(raw); altered['candidates'][0]['command']=(.9,1.,.3,-.2)
        with self.assertRaises(ValueError): auditor.current_query(altered,t,2)

    def test_independent_features_match_known_geometry(self):
        q=query(); current=np.asarray(q.observations)[2]; result=auditor.feature(q.observations,q.baseline_command,'F20')
        np.testing.assert_array_equal(result[9:13],q.baseline_command)
        np.testing.assert_array_equal(result[14:17],current[4:7]-current[:3])

    def test_guard_blocks_network_and_simulator_before_execution(self):
        with allocation.numeric_guard(()) as counts:
            with self.assertRaises(RuntimeError): socket.socket()
            with self.assertRaises(RuntimeError): __import__('mujoco')
        self.assertEqual(counts['network_attempts'],1); self.assertEqual(counts['forbidden_imports'],1)

    def test_guard_blocks_fits_without_computing_parameters(self):
        with allocation.numeric_guard(()) as counts:
            with self.assertRaises(RuntimeError): np.linalg.lstsq(np.eye(2),np.ones(2))
            with self.assertRaises(RuntimeError): np.linalg.solve(np.eye(2),np.ones(2))
            np.linalg.svd(np.eye(2))
        self.assertEqual(counts['model_fit_attempts'],2)

    def test_guard_blocks_old_dev_test_and_private_source_reads(self):
        for name in ('dev_public.json','evaluation_metadata.json','training/FEEDBACK8_push-v3_F20_ISO_W16_R0.json'):
            with allocation.numeric_guard(()) as counts:
                with self.assertRaises(RuntimeError): (allocation.SOURCE/name).read_bytes()
            self.assertEqual(counts['forbidden_reads'],1)

    def test_guard_restores_solvers_and_imports(self):
        before=np.linalg.solve
        with allocation.numeric_guard(()): self.assertIsNot(np.linalg.solve,before)
        self.assertIs(np.linalg.solve,before)
        np.testing.assert_array_equal(np.linalg.solve(np.eye(2),[1,2]),[1,2])

    def test_guard_protects_allowlisted_source_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); source=root/'outputs/previous/source.json'; source.parent.mkdir(parents=True)
            source.write_bytes(b'original')
            with patch.object(allocation,'ROOT',root),patch.object(allocation,'OUTPUT',root/'outputs/linear_command_preflight/analysis_v1'):
                with allocation.numeric_guard((source,)) as counts:
                    self.assertEqual(source.read_bytes(),b'original')
                    with self.assertRaises(RuntimeError):
                        with source.open('wb') as handle: handle.write(b'only temporary fixture')
                self.assertEqual(source.read_bytes(),b'original'); self.assertEqual(counts['forbidden_reads'],1)

    def test_guard_blocks_shell_before_launch(self):
        with allocation.numeric_guard(()) as counts:
            with self.assertRaises(RuntimeError): os.system('echo never-executed')
        self.assertEqual(counts['child_process_attempts'],1)


if __name__=='__main__': unittest.main()

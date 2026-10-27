from copy import deepcopy
import unittest
from src.analysis.occam_window_envelope_v1 import bind_case
from src.analysis.response_qualification_io_v1 import digest


def example():
    m=dict(experiment_run_id='fixture',manifest_id='a'*64,source_git_commit='b'*40)
    spec=dict(group=0,task='push-v3',seed=164000,context='UNCHANGED',planned_boundary=16,acquisition_action='CONTINUE',fixture_sign=1)
    case={**m,**spec,'event_start_sequence':0,'event_end_sequence_exclusive':1,'total_steps':5,'deadline_loss':5}
    events=[dict(**m,**spec,event='CASE_ALLOCATION',sequence=0,saved_ns=1),
        dict(**m,**spec,event='CASE_COMPLETE',sequence=1,saved_ns=2,case_record_sha256=digest(case),total_steps=5,deadline_loss=5)]
    return m,spec,case,events


class EnvelopeTests(unittest.TestCase):
    def test_source_bound_closed_case_advances_global_cursors(self):
        m,s,c,e=example();self.assertEqual(bind_case(m,s,c,e,[],(0,0,-1,-1)),(2,0,2,-1))

    def test_manifest_or_cross_case_ownership_rejected(self):
        for field,value in (('manifest_id','x'*64),('fixture_sign',-1)):
            m,s,c,e=example();e[0][field]=value
            with self.assertRaises(ValueError):bind_case(m,s,c,e,[],(0,0,-1,-1))

    def test_changed_case_or_absent_closure_rejected(self):
        m,s,c,e=example();c['deadline_loss']=500
        with self.assertRaises(ValueError):bind_case(m,s,c,e,[],(0,0,-1,-1))
        m,s,c,e=example()
        with self.assertRaises(ValueError):bind_case(m,s,c,e[:-1],[],(0,0,-1,-1))

    def test_reversed_global_time_and_private_identity_rejected(self):
        m,s,c,e=example()
        with self.assertRaises(ValueError):bind_case(m,s,c,e,[],(0,0,10,-1))
        p=deepcopy(e[:1]);p[0].update(sequence=0,saved_ns=4,source_git_commit='q'*40)
        with self.assertRaises(ValueError):bind_case(m,s,c,e,p,(0,0,-1,-1))

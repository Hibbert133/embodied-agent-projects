from copy import deepcopy
from unittest import TestCase
import gzip,hashlib,json,uuid
from src.analysis import occam_training_failure_v2 as d


def spec(i):return dict(cohort='TRAIN',group=i,task='push-v3',seed=42+i,context='UNCHANGED',planned_boundary=16,acquisition_action='CONTINUE',behavior='RANDOM_WINDOW')


class FailureDiagnosticTests(TestCase):
    def test_stream_detects_cursor_clock_identity_and_hashes_every_decoded_byte(self):
        manifest={k:'ARRAY_FIXTURE_NOT_RESEARCH' for k in d.a.IDENTITY};owner=spec(0)
        original=[{**manifest,**owner,'event':'CASE_ALLOCATION','sequence':0,'saved_ns':1},
            {**manifest,**owner,'event':'CASE_COMPLETE','sequence':1,'saved_ns':2,'case_record_sha256':'a'*64,'total_steps':0,'deadline_loss':500}]
        folder=d.BASE/'array_stream_fixtures_v1';folder.mkdir(exist_ok=True)
        def run(rows):
            raw=b''.join((json.dumps(row,separators=(',',':'))+'\r\n').encode() for row in rows)
            path=folder/(uuid.uuid4().hex+'.jsonl.gz')
            with gzip.open(path,'wb') as file:file.write(raw)
            return d.stream(path,manifest,[owner]),raw
        actual,raw=run(original);self.assertEqual(actual['records'],2);self.assertEqual(actual['decoded_sha256'],hashlib.sha256(raw).hexdigest())
        for field,value,message in (('sequence',3,'cursor'),('saved_ns',1,'time'),('manifest_id','foreign','identity')):
            rows=deepcopy(original);rows[1][field]=value
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,message):run(rows)

    def test_census_keeps_complete_partial_and_unstarted_without_imputed_loss(self):
        rows=d.census([spec(i) for i in range(4)],[{**spec(0),'total_steps':20,'success':True,'deadline_loss':20}],{**spec(1),'total_steps':0})
        self.assertEqual(len(rows),4);self.assertEqual(rows[0]['deadline_loss'],20)
        self.assertTrue(all(r['deadline_loss'] is None for r in rows[1:]));self.assertTrue(all(r['success'] is None for r in rows[1:]))

    def test_foreign_partial_allocation_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'partial allocation'):d.census([spec(0),spec(1)],[],{**spec(1),'total_steps':0})

    def test_independent_reset_and_control_integer_costs(self):
        empty=dict(counts={},by_phase={});intent=dict(event='LIFECYCLE_RESET_INTENT',phase='CONTROLLED_RESET',sequence=3,before=empty)
        ledger,pending=d.ledger_event(empty,None,intent)
        expected=dict(counts=dict(reset_attempts=1,simulation_attempts=100,simulation_frames_attempted=500,simulation_completed=100,simulation_frames_completed=500,reset_completed=1),
            by_phase={'CONTROLLED_RESET':dict(reset_attempts=1,simulation_attempts=100,simulation_frames_attempted=500,simulation_completed=100,simulation_frames_completed=500,reset_completed=1)})
        ledger,pending=d.ledger_event(ledger,pending,dict(event='LIFECYCLE_RESET_COMPLETE',phase='CONTROLLED_RESET',intent_sequence=3,after=expected))
        self.assertEqual(ledger,expected);self.assertIsNone(pending);self.assertEqual(empty,dict(counts={},by_phase={}))

    def test_orphan_and_overlapping_reset_are_rejected(self):
        ledger=dict(counts={},by_phase={})
        with self.assertRaisesRegex(ValueError,'reset closure'):d.ledger_event(ledger,None,dict(event='LIFECYCLE_RESET_COMPLETE',phase='CONTROLLED_RESET',intent_sequence=0))
        with self.assertRaisesRegex(ValueError,'overlapping'):d.ledger_event(ledger,{},dict(event='LIFECYCLE_RESET_INTENT'))

    def test_step_before_accounting_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'step before'):d.ledger_event(dict(counts={},by_phase={}),None,dict(event='STEP_INTENT',ledger_before={'wrong':1}))

    def test_case_closure_hash_and_counts_are_not_optional(self):
        case=dict(event_start_sequence=2,event_end_sequence_exclusive=7,total_steps=1,host_attempts=1,host_returned=1,deadline_loss=500)
        block=dict(first='CASE_ALLOCATION',last='CASE_COMPLETE',events={'CASE_ALLOCATION':1,'CASE_COMPLETE':1},start=2,end=7,step_intents=1,step_complete=1,
            closure=dict(case_record_sha256=d.io.digest(case),total_steps=1,deadline_loss=500))
        d.case_closure(case,block);bad=deepcopy(block);bad['closure']['case_record_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'closure hash'):d.case_closure(case,bad)

    def test_boundary_preserves_unknown_native_call_and_missing_task_outcome(self):
        failed=dict(total_steps=0,host_attempts=0,host_returned=0,state_witness_refs=[],environment_closed=True,error={'type':'RuntimeError','message':'bytes allocation failed'})
        block=dict(first='CASE_ALLOCATION',last='NOISE_COMMITMENT',events={'CONTROLLED_INITIAL':1},step_intents=0,step_complete=0)
        result=d.failed_boundary(failed,block);self.assertFalse(result['exact_native_call_known']);self.assertFalse(result['task_outcome_available'])
        bad=deepcopy(block);bad['step_intents']=1
        with self.assertRaisesRegex(ValueError,'no task command'):d.failed_boundary(failed,bad)

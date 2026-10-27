"""Record-only population-loop integration; physics/math interiors are stubbed.

Unlike a single-case envelope test, this crosses successive matched pairs and
early-end pairs, exercising the exact stream-variable shadowing failure path.
"""
from contextlib import ExitStack,contextmanager
from copy import deepcopy
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
from src.analysis import occam_window_audit_v3 as reader
from src.analysis import release_learning_guard_v1 as guards


def fixture(*,early=False,corrupt=None):
    specs=reader.a.population();m=dict(experiment_run_id='array',manifest_id='a'*64,source_git_commit='b'*40)
    cases=[];events=[];private=[]
    for i,s in enumerate(specs):
        c={**s,**m,'total_steps':20,'policy_queries':20,'performance_windows':1,'full_feedback_windows':1,'boundary_applied':True,
            'success':True,'deadline_loss':20,'event_start_sequence':2*i,'event_end_sequence_exclusive':2*i+1}
        if early and i<2:c.update(performance_windows=0,full_feedback_windows=0,boundary_applied=False)
        cases.append(c)
        events.extend([{**s,**m,'event':'CASE_ALLOCATION','sequence':2*i,'saved_ns':2*i+1},
            {**s,**m,'event':'CASE_COMPLETE','sequence':2*i+1,'saved_ns':2*i+2,'case_record_sha256':reader.io.digest(c),'total_steps':20,'deadline_loss':20}])
        private.append({**s,**m,'event':'STATE_WITNESS','sequence':i,'saved_ns':i+1})
    if corrupt=='identity':events[4]['manifest_id']='z'*64
    if corrupt=='clock':events[4]['saved_ns']=1
    compact=[{k:c[k] for k in (*reader.a.KEYS,'total_steps','deadline_loss','success','policy_queries','performance_windows','full_feedback_windows','boundary_applied')} for c in cases]
    summary={**m,'allocated_executions':36,'executions':36,'rows':compact,'lifecycle':dict(counts={'executions':36},by_phase={}),
        'events':72,'private_records':36,'control_steps':720}
    def read(path):
        name=Path(path).name
        if name=='completion.json':return dict(status='COLLECTED_FOR_INDEPENDENT_AUDIT',manifest_id=m['manifest_id'],artifact_sha256={})
        if name=='summary.json':return deepcopy(summary)
        raise AssertionError('unexpected file read '+name)
    def rows(path):return iter(deepcopy({'cases.jsonl.gz':cases,'events.jsonl.gz':events,'witnesses.jsonl.gz':private}[Path(path).name]))
    def reconstruct(spec,case,es,ps,ledger):
        steps=[dict(command=[0.,0.,0.,0.]) for _ in range(16)]+[dict(command=[float(spec['fixture_sign']),0.,0.,0.]) for _ in range(4)]
        public=[] if case['performance_windows']==0 else [dict(agent_event='WINDOW_DECISION',public_payload=dict(at_calls=16,
            declaration=dict(selected_rate=.125 if spec['fixture_sign']==-1 else 8.)))]
        witness={'POST_ACQUISITION':{'witness':{k:spec[k] for k in reader.a.KEYS if k!='fixture_sign'}}}
        return dict(counts={'executions':ledger['counts'].get('executions',0)+1},by_phase={}),steps,public,witness,case['full_feedback_windows']
    @contextmanager
    def fake_guard(receipt,**kw):
        receipt.update(record_loop_fixture=True,new_physical_interactions=0);yield
    with ExitStack() as st:
        st.enter_context(patch.object(reader.a,'checked',lambda p:deepcopy(m)))
        st.enter_context(patch.object(reader.io,'read',read));st.enter_context(patch.object(reader.io,'rows',rows));st.enter_context(patch.object(reader.io,'write',lambda *a,**k:None))
        st.enter_context(patch.object(reader,'reconstruct',reconstruct));st.enter_context(patch.object(reader,'replay',lambda s,c,p,r:c['policy_queries']))
        st.enter_context(patch.object(reader,'compare_witnesses',lambda a,b:dict(comparison_equal=a==b)))
        st.enter_context(patch.object(reader,'physical_rows_equal',lambda a,b,n:a[:n]==b[:n]));st.enter_context(patch.object(guards,'read_only',fake_guard))
        return reader.audit(Path('array_fixture/manifest.json'))


class PopulationReaderTests(TestCase):
    def test_all_36_cases_cross_multiple_matched_pairs_and_keep_stream_cursor(self):
        r=fixture();self.assertEqual(r['integrity'],'PASSED');self.assertEqual(r['counts']['executions'],36)
        self.assertEqual(r['counts']['live_fixture_pairs'],18);self.assertEqual(r['counts']['first_actual_command_different'],18)

    def test_early_pair_does_not_erase_global_cursors_or_remaining_denominator(self):
        r=fixture(early=True);self.assertEqual(r['counts']['early_end_fixture_pairs'],1)
        self.assertEqual(r['counts']['live_fixture_pairs'],17);self.assertEqual(r['counts']['executions'],36)

    def test_later_case_wrong_manifest_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'manifest identity'):fixture(corrupt='identity')

    def test_later_pair_reversed_global_clock_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'clock reversed'):fixture(corrupt='clock')

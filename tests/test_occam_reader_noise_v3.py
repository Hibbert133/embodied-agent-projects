"""Saved arrays only: no factory, environment, policy queries or simulation."""
from copy import deepcopy
from itertools import groupby
from unittest import TestCase
from unittest.mock import patch
import numpy as np
from src.analysis import occam_reader_extension_v3 as extension
from src.analysis import occam_reference_train_audit_v2 as old
from src.analysis import occam_reference_train_audit_v3 as new


def fixture():
    raw=extension.TARGET.parent/'native';case=next(new.io.rows(raw/'cases.jsonl.gz'))
    _,events=next(groupby(new.io.rows(raw/'events.jsonl.gz'),new.a.key))
    _,private=next(groupby(new.io.rows(raw/'witnesses.jsonl.gz'),new.a.key))
    return new.a.population('NATIVE')[0],case,list(events),list(private),dict(counts={},by_phase={})


class ReaderNoiseTests(TestCase):
    def test_saved_actual_first_case_passes_correct_registry_and_complete_execution_chain(self):
        spec,case,events,private,ledger=fixture();result=new.reconstruct(spec,case,events,private,ledger)
        self.assertEqual(len(result[1]),case['total_steps']);self.assertEqual(result[0],case['ledger_after_close'])
        self.assertGreater(len(result[4]['windows']),0)

    def test_original_reader_stale_assertion_is_reproduced_without_physics(self):
        with self.assertRaisesRegex(ValueError,'independent record mismatch'):old.reconstruct(*fixture())

    def test_wrong_namespace_is_still_rejected(self):
        values=list(fixture());event=next(e for e in values[2] if e['event']=='NOISE_COMMITMENT');event['noise_namespace_oracle']=2026102832
        with self.assertRaisesRegex(ValueError,'frozen noise namespace'):new.reconstruct(*values)

    def test_wrong_full_tape_hash_is_still_rejected(self):
        values=list(fixture());next(e for e in values[2] if e['event']=='NOISE_COMMITMENT')['tape_sha256_oracle']='0'*64
        with self.assertRaisesRegex(ValueError,'noise tape commitment'):new.reconstruct(*values)

    def test_shifted_noise_cursor_cannot_pass_commitment(self):
        values=fixture();shifted=np.roll(new.a.noise(values[0]),1,axis=0)
        with patch.object(new.a,'noise',lambda spec:shifted),self.assertRaisesRegex(ValueError,'noise tape commitment'):new.reconstruct(*values)

    def test_future_history_remains_rejected(self):
        values=list(fixture());query=next(e for e in values[2] if e['event']=='AGENT_EVENT' and e['agent_event']=='WINDOW_QUERY')
        query['public_payload']['value']['history'].append(deepcopy(query['public_payload']['value']['history'][-1]))
        with self.assertRaisesRegex(ValueError,'future/omitted actual history'):new.reconstruct(*values)

    def test_repaired_native_output_preserves_failed_export_and_train_schema(self):
        root=extension.TARGET.parent
        self.assertEqual(new.output_directory(extension.TARGET,'NATIVE'),root/'native/audit_repair_v3')
        self.assertEqual(new.output_directory(extension.TARGET,'TRAIN'),root/'train')
        self.assertEqual((root/'native/public_trajectories.jsonl.gz').stat().st_size,51)

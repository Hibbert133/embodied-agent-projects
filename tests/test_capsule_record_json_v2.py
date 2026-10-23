import io
import json
import unittest
import numpy as np
from src.analysis.capsule_record_json_v2 import normalize,JsonJournal


class CapsuleRecordJSONTest(unittest.TestCase):
    def test_nested_observations_actions_rewards_and_flags_become_json_values(self):
        value={'observation':np.arange(39,dtype=np.float64),'nested':{'action':np.array([.1,.2],np.float32)},
               'reward':np.float64(3.4),'terminated':np.bool_(False),'count':np.int64(7)}
        encoded=normalize(value);decoded=json.loads(json.dumps(encoded,allow_nan=False))
        self.assertEqual(decoded['observation'],list(range(39)));self.assertIs(decoded['terminated'],False)
        self.assertEqual(decoded['count'],7);np.testing.assert_array_equal(np.asarray(decoded['nested']['action'],np.float32),value['nested']['action'])

    def test_nonfinite_opaque_and_nonstring_key_records_rejected(self):
        for value in [np.array([np.inf]),np.float64(np.nan),np.array([object()],dtype=object),
                      object(),b'opaque',{1:'ambiguous'},np.zeros(1,dtype=[('x','f8')])]:
            with self.assertRaises(ValueError):normalize(value)

    def test_serialization_failure_consumes_no_sequence_or_bytes(self):
        handle=io.StringIO();journal=JsonJournal(handle,{'manifest_id':'software-fixture'})
        journal.emit('INITIAL',{'observation':np.zeros(39)})
        before=handle.getvalue()
        with self.assertRaises(ValueError):journal.emit('BAD',{'x':np.nan})
        self.assertEqual(before,handle.getvalue());self.assertEqual(journal.sequence,1)
        journal.emit('FAILED',{'reason':'test'})
        self.assertEqual([json.loads(line)['sequence'] for line in handle.getvalue().splitlines()],[0,1])

    def test_envelope_identity_cannot_be_overridden_by_payload(self):
        journal=JsonJournal(io.StringIO(),{'manifest_id':'software-fixture'})
        for key in ('manifest_id','sequence','event','saved_ns'):
            with self.assertRaises(ValueError):journal.emit('BAD',{key:0})
        self.assertEqual(journal.sequence,0)


if __name__=='__main__':unittest.main()

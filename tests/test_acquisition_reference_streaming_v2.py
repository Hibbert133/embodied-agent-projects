"""Storage regression only: synthetic journals and already-audited saved arrays."""
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch
import json,unittest
from src.analysis import acquisition_reference_streaming_audit_v2 as v2
from src.analysis import acquisition_reference_audit_v1 as v1
from src.analysis import acquisition_reference_io_v1 as a
from src.analysis.capsule_record_json_v2 import normalize
from src.probe import task_passive_program_v1 as legacy
io=a.io
MANIFEST=a.OUTPUT/'acquisition_reference_20261022T133659Z_dc7058a8f6d5/manifest.json'


def fixture():
    identity={k:'fixture' for k in a.IDENTITY};specs=a.population('SOFTWARE_NATIVE')[:2];cases=[];events=[];private=[]
    for i,spec in enumerate(specs):
        case={**spec,'event_start_sequence':2*i,'event_end_sequence_exclusive':2*i+1,'state_witness_refs':[{'sequence':i}]}
        events.extend([{**identity,**spec,'sequence':2*i,'saved_ns':2*i,'event':'FIXTURE_ONLY'},
            {**identity,**spec,'sequence':2*i+1,'saved_ns':2*i+1,'event':'CASE_COMPLETE','case_record_sha256':io.digest(case)}])
        private.append({**identity,**spec,'sequence':i,'saved_ns':i,'event':'STATE_WITNESS'});cases.append(case)
    return identity,specs,cases,events,private


class StreamingTests(unittest.TestCase):
    def test_reader_rejects_sequence_time_and_other_manifest(self):
        identity,_,_,events,_=fixture()
        for mode in ('sequence','saved_ns','manifest_id'):
            rows=deepcopy(events[:2]);rows[1][mode]=99 if mode=='sequence' else -1 if mode=='saved_ns' else 'other'
            reader=v2.JournalReader(rows,identity);reader.take()
            with self.assertRaises(ValueError):reader.take()

    def test_partitions_all_records_without_dropping_private_or_case_markers(self):
        identity,specs,cases,events,private=fixture();er=v2.JournalReader(events,identity);pr=v2.JournalReader(private,identity)
        for spec,case in zip(specs,cases):
            chunk,priv=v2.case_chunk(spec,case,er,pr);self.assertEqual(len(chunk),1);self.assertEqual(len(priv),1)
            self.assertEqual(chunk[0]['program'],spec['program']);self.assertEqual(priv[0]['program'],spec['program'])
        self.assertEqual((er.count,pr.count),(4,2));er.finish();pr.finish()

    def test_missing_extra_changed_case_and_future_private_are_rejected(self):
        identity,specs,cases,events,private=fixture()
        reader=v2.JournalReader([],identity)
        with self.assertRaises(ValueError):reader.take()
        reader=v2.JournalReader(events,identity)
        with self.assertRaises(ValueError):reader.finish()
        for what in ('digest','future_private','boundary'):
            ev=deepcopy(events);pv=deepcopy(private);case=deepcopy(cases[0])
            if what=='digest':ev[1]['case_record_sha256']='wrong'
            elif what=='future_private':pv[0]['program']=specs[1]['program']
            else:case['event_start_sequence']=1
            with self.assertRaises(ValueError):v2.case_chunk(specs[0],case,v2.JournalReader(ev,identity),v2.JournalReader(pv,identity))

    def test_reader_does_not_load_future_cases(self):
        identity,specs,cases,events,private=fixture();seen=[]
        def event_rows():
            for row in events:
                seen.append(row['sequence'])
                if row['sequence']>=2:raise AssertionError('future case loaded before it is needed')
                yield row
        er=v2.JournalReader(event_rows(),identity);pr=v2.JournalReader(private,identity)
        v2.case_chunk(specs[0],cases[0],er,pr);self.assertEqual(seen,[0,1]);self.assertEqual(pr.count,1)

    def test_full_saved_native_verdict_matches_frozen_v1_without_new_fits(self):
        folder=MANIFEST.parent/'software_native';receipt=io.read(folder/'record_audit_process_receipt_v1.json')
        trace=folder/'independent_refit_trace_v1.jsonl';self.assertEqual(receipt['status'],'PASSED');self.assertEqual(io.sha(trace),receipt['trace_sha256'])
        cache={};calls=[]
        for line in trace.read_text(encoding='utf-8').splitlines():
            row=json.loads(line);self.assertEqual(row['status'],'RETURNED');key=(row['function'],row['nominal_sha256'],row['prefix_sha256'])
            if key in cache:self.assertEqual(cache[key],row['result'])
            cache[key]=row['result']
        def cached(name):
            def call(nominal,prefix):
                key=(name,io.digest(normalize(nominal)),io.digest(normalize(asdict(prefix))));calls.append(key)
                return deepcopy(cache[key])
            return call
        captured=[]
        def save(path,result,*args,**kw):
            self.assertEqual(Path(path),folder/'audit.json');captured.append(deepcopy(result))
        with patch.object(legacy,'infer_four',cached('infer_four')),patch.object(legacy,'infer_operator',cached('infer_operator')):
            with patch.object(io,'write',save):old=v1.audit(MANIFEST,'SOFTWARE_NATIVE')
            new=v2.compute(MANIFEST,'SOFTWARE_NATIVE')
        self.assertEqual(len(captured),1);self.assertEqual(len(calls),48)
        self.assertEqual({k:v for k,v in old.items() if k!='wall_ns'},{k:v for k,v in new.items() if k!='wall_ns'})
        self.assertEqual(new['costs'],io.read(folder/'audit.json')['costs']);self.assertEqual(new['executions'],60)


if __name__=='__main__':unittest.main()

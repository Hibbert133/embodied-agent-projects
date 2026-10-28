"""Pure metadata/array and tiny temporary archive checks, no real QUAL reads."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import gzip
import hashlib
import json
import unittest

import qual_result_delivery_v1 as d


def index():
    files={d.RUN_NAME+'/qual/case_%04d/'%i+n:dict(bytes=1,sha256='h') for i in range(1,1567) for n in d.CHILD}
    aliases={}
    for n in ('events.jsonl.gz','witnesses.jsonl.gz'):
        anchor=d.RUN_NAME+'/qual/'+n;files[anchor]=dict(bytes=1566,sha256='all')
        for i in range(1,1567):
            aliases[d.RUN_NAME+'/qual/case_%04d/'%i+n]=dict(anchor=anchor,offset=i-1,bytes=1,sha256='h')
    for n in (*d.REQUIRED_SIDE,'manifest.json','seed_scope.json','seed_scope_audit.json'):
        files[d.RUN_NAME+'/'+n]=dict(bytes=1,sha256='h')
    files[d.REPORT.relative_to(d.ROOT).as_posix()]=dict(bytes=1,sha256='h')
    return dict(schema='OCCAM_QUALIFICATION_ZIP_ALIASES_V1',delivery_scope='FULL_INDEPENDENT_QUAL_RESULT_V1',
        phase='QUAL',executions=1566,manifest_id=d.gate.MID,source_git_commit=d.gate.SCIENCE,
        files=files,aliases=aliases,bundle_bytes=1,
        parts=[dict(path='outputs/occam_reference_qualification_v1/qual_delivery_v1/bundle_parts/part_001.bin',bytes=1,sha256='x')])


class QualificationResultDeliveryTests(unittest.TestCase):
    def test_complete_metadata_all_1566_cases(self):d.validate_index(index())
    def test_missing_failed_case_file_is_rejected(self):
        x=index();del x['files'][d.RUN_NAME+'/qual/case_1566/case.json']
        with self.assertRaises(ValueError):d.validate_index(x)
    def test_native_cannot_masquerade_as_qual(self):
        x=index();x.update(phase='NATIVE',executions=174)
        with self.assertRaises(ValueError):d.validate_index(x)
    def test_missing_independent_statistics_is_rejected(self):
        x=index();del x['files'][d.RUN_NAME+'/statistics_v1/independent_audit.json']
        with self.assertRaises(ValueError):d.validate_index(x)
    def test_missing_failure_table_is_rejected(self):
        x=index();del x['files'][d.RUN_NAME+'/report_v1/all_complete_task_failures.csv']
        with self.assertRaises(ValueError):d.validate_index(x)
    def test_alias_gap_is_rejected(self):
        x=index();x['aliases'][d.RUN_NAME+'/qual/case_0001/events.jsonl.gz']['offset']=1
        with self.assertRaises(ValueError):d.validate_index(x)
    def test_unowned_shard_path_is_rejected(self):
        x=index();x['parts'][0]['path']='../outside.bin'
        with self.assertRaises(ValueError):d.validate_index(x)
    def test_foreign_result_file_is_rejected(self):
        x=index();x['files']['elsewhere/private.json']=dict(bytes=1,sha256='h')
        with self.assertRaises(ValueError):d.validate_index(x)
    def test_partial_qualification_rejected_before_metadata_read(self):
        with TemporaryDirectory() as folder,patch.object(d,'RUN',Path(folder)),patch.object(d.b.c,'read',side_effect=AssertionError('must not read partial results')):
            with self.assertRaises(ValueError):d.complete_gate()
    def test_archive_only_does_not_claim_original_byte_comparison(self):
        value=d.describe_recovery(dict(all_files_byte_identical=True,files=3),True)
        self.assertIsNone(value['all_files_byte_identical']);self.assertFalse(value['original_raw_byte_comparison'])
        self.assertTrue(value['size_and_SHA_against_committed_index'])
    def test_original_comparison_mode_preserves_true_result(self):
        value=d.describe_recovery(dict(all_files_byte_identical=True,files=3),False)
        self.assertTrue(value['all_files_byte_identical']);self.assertTrue(value['original_raw_byte_comparison'])
    def test_tiny_original_and_archive_only_real_bytes(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);original=root/'original';original.mkdir();f=original/'events.jsonl.gz'
            with gzip.open(f,'wb') as g:g.write(b'{"event":"failure_retained"}\n')
            raw=f.read_bytes();anchor='events.jsonl.gz';alias='case_0001/events.jsonl.gz'
            (original/'case_0001').mkdir();(original/alias).write_bytes(raw)
            z=root/'bundle.zip';aliases={alias:dict(anchor=anchor,offset=0,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())}
            i=d.b.bundle(original,[f,original/alias],aliases,z)
            checked=[];result=d.b.recover(original,z,i,root/'with_original',scan=lambda raw,name:checked.append((raw,name)))
            self.assertTrue(result['all_files_byte_identical']);self.assertEqual(result['files'],2);self.assertEqual(len(checked),1)
            dest=root/'archive_only';result=d.b.recover(dest,z,i,dest,scan=lambda raw,name:None)
            self.assertEqual((dest/alias).read_bytes(),raw)
            self.assertIsNone(d.describe_recovery(result,True)['all_files_byte_identical'])


if __name__=='__main__':unittest.main()

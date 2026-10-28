"""Pure metadata/files; no environments, scientific fits or real subprocesses."""
from copy import deepcopy
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
import gzip,json,tempfile,zipfile
from outputs.occam_reference_qualification_v1.delivery_tools_v1 import qualification_bundle_v1 as b


def metadata():
    ledger=dict(counts={},by_phase={});m=dict(manifest_id='array',config=dict(populations=dict(NATIVE=[{}]*174)))
    summary=dict(status='COLLECTED_FOR_INDEPENDENT_AUDIT',manifest_id='array',allocated_executions=174,executions=174,rows=[{}]*174,
        outcomes=[dict(status='COMPLETE')]*174,lifecycle=ledger,control_steps=10)
    completion=dict(status=summary['status'],manifest_id='array')
    process=dict(integrity='PASSED_ISOLATED_PROCESS_AND_BYTE_CONTINUITY_ONLY',executions=174,ledger=ledger,control_steps=10)
    audit=dict(integrity='PASSED',counts=dict(executions=174,control_steps=10),ledger=ledger,manifest_id='array',phase='NATIVE')
    return m,summary,completion,process,audit


class TrainBundleTests(TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.spawn=patch('subprocess.Popen',side_effect=AssertionError('real process forbidden'));self.spawn.start();self.addCleanup(self.spawn.stop)
    def fixture(self):
        first=gzip.compress(b'{"array":1}\n');second=gzip.compress(b'{"array":2}\n')
        (self.root/'canonical.gz').write_bytes(first+second);(self.root/'one.gz').write_bytes(first);(self.root/'two.gz').write_bytes(second);(self.root/'meta.json').write_text('{"fixture":true}',encoding='utf8')
        aliases={name:dict(anchor='canonical.gz',offset=offset,bytes=len(raw),sha256=b.c.sha(self.root/name)) for name,offset,raw in (('one.gz',0,first),('two.gz',len(first),second))}
        paths={self.root/name for name in ('canonical.gz','one.gz','two.gz','meta.json')};target=self.root/'records.zip';index=b.bundle(self.root,paths,aliases,target)
        return target,index
    def test_complete_metadata_requires_all174(self):
        v=metadata();b.metadata_gate(*v);v[1]['executions']=173
        with self.assertRaisesRegex(ValueError,'denominator'):b.metadata_gate(*v)
    def test_audit_failure_and_unstarted_cases_rejected(self):
        v=metadata();v[3]['integrity']='FAILED'
        with self.assertRaisesRegex(ValueError,'process audit'):b.metadata_gate(*v)
        v=metadata();v[1]['outcomes'][-1]=dict(status='NOT_STARTED')
        with self.assertRaisesRegex(ValueError,'partial or unstarted'):b.metadata_gate(*v)
    def test_mismatched_manifest_and_costs_rejected(self):
        v=metadata();v[4]['manifest_id']='other'
        with self.assertRaisesRegex(ValueError,'allocated data'):b.metadata_gate(*v)
        v=metadata();v[3]['control_steps']=11
        with self.assertRaisesRegex(ValueError,'costs'):b.metadata_gate(*v)
    def test_running_study_rejected_before_any_output(self):
        phase=self.root/'native';phase.mkdir();(phase/'summary.json').write_text(json.dumps(dict(status='RUNNING')),encoding='utf8')
        out=self.root/'must_not_exist'
        with patch.object(b,'manifest_metadata',return_value=metadata()[0]),self.assertRaisesRegex(ValueError,'still live or partial'):b.export(self.root/'array_metadata.json',out,self.root/'restore')
        self.assertFalse(out.exists())
    def test_exact_two_members_restore_without_duplicate_zip_storage(self):
        target,index=self.fixture();seen=[];r=b.recover(self.root,target,index,self.root/'restore',scan=lambda raw,name:seen.append((name,raw)))
        self.assertEqual(r['files'],4);self.assertEqual(r['canonical_files'],2);self.assertEqual(r['reconstructed_member_files'],2);self.assertEqual(r['decoded_canonical_gzip_lines'],2)
        with zipfile.ZipFile(target) as archive:self.assertEqual(set(archive.namelist()),{'canonical.gz','meta.json'})
        for name in index['files']:self.assertEqual((self.root/name).read_bytes(),(self.root/'restore'/name).read_bytes())
    def test_member_overlap_gap_and_uncovered_tail_rejected(self):
        target,index=self.fixture()
        for delta in (-1,1):
            bad=deepcopy(index['aliases']);bad['two.gz']['offset']+=delta
            with self.assertRaisesRegex(ValueError,'gap or overlap'):b.validate_ranges(index['files'],bad)
        bad=deepcopy(index['aliases']);bad.pop('two.gz')
        with self.assertRaisesRegex(ValueError,'cover whole'):b.validate_ranges(index['files'],bad)
    def test_alias_chain_and_wrong_original_hash_rejected(self):
        target,index=self.fixture();bad=deepcopy(index['aliases']);bad['one.gz']['anchor']='two.gz'
        with self.assertRaisesRegex(ValueError,'alias chains'):b.validate_ranges(index['files'],bad)
        bad=deepcopy(index['aliases']);bad['one.gz']['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'byte binding'):b.validate_ranges(index['files'],bad)
    def test_corrupt_archive_or_changed_original_is_rejected(self):
        target,index=self.fixture();before=target.read_bytes();target.write_bytes(before+b'corrupt')
        with self.assertRaisesRegex(ValueError,'ZIP bytes'):b.recover(self.root,target,index,self.root/'restore',scan=lambda *a:None)
        self.assertFalse((self.root/'restore').exists())
        target.write_bytes(before);(self.root/'meta.json').write_text('changed',encoding='utf8')
        with self.assertRaisesRegex(ValueError,'original file restored'):b.recover(self.root,target,index,self.root/'restore',scan=lambda *a:None)
    def test_path_escape_is_rejected_before_external_write(self):
        target=self.root/'bad.zip'
        with zipfile.ZipFile(target,'w') as z:z.writestr('../escape',b'bad')
        index=dict(schema='OCCAM_QUALIFICATION_ZIP_ALIASES_V1',bundle_sha256=b.c.sha(target),files={'../escape':dict(bytes=3,sha256='x')},aliases={})
        with self.assertRaisesRegex(ValueError,'safe relative'):b.recover(self.root,target,index,self.root/'restore',scan=lambda *a:None)
        self.assertFalse((self.root/'escape').exists())
    def test_canonical_gzip_contents_reach_the_scanner(self):
        target,index=self.fixture()
        def scan(raw,name):
            if b'"array":2' in raw:raise ValueError('constructed scanner rejection')
        with self.assertRaisesRegex(ValueError,'scanner rejection'):b.recover(self.root,target,index,self.root/'restore',scan=scan)

    def test_wrong_phase_audit_rejected(self):
        v=metadata();v[4]['phase']='QUAL'
        with self.assertRaisesRegex(ValueError,'full audit'):b.metadata_gate(*v)
    def test_QUAL_requires_all1566_not_NATIVE(self):
        v=metadata();v[0]['config']['populations']['QUAL']=[{}]*1566
        with self.assertRaisesRegex(ValueError,'denominator'):b.metadata_gate(*v,phase='QUAL')
    def test_unknown_phase_rejected(self):
        with self.assertRaisesRegex(ValueError,'registered delivery phase'):b.metadata_gate(*metadata(),phase='TRAIN')

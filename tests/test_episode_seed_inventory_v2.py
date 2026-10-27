"""No environment, numerical estimator, allocator, or network is used here."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from src.analysis import episode_seed_inventory_v2 as inventory
from src.analysis.episode_seed_inventory_audit_v2 import audit

class SeedInventory(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
    def write(self,name,value):
        p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True)
        p.write_bytes(value if isinstance(value,bytes) else json.dumps(value).encode());return p
    def scan(self,value,lo=45,hi=45,name='configs/sample.json'):
        p=self.write(name,value);r=inventory.scan(self.root,lo,hi,[p]);audit(self.root,r);return r
    def test_nested_two_element_ranges_include_interior(self):
        r=self.scan({'split_seed_ranges':{'train':[[40,50],[80,90]]}})
        self.assertEqual(r['status'],'REGISTERED_COLLISION');self.assertEqual(r['blockers'][0]['lower'],40)
    def test_independent_audit_detects_original_endpoint_only_bug(self):
        r=self.scan({'seed_ranges':[[40,50]]});bad=copy.deepcopy(r)
        bad['records']=[dict(r['records'][0],upper=40),dict(r['records'][0],lower=50)]
        with self.assertRaisesRegex(ValueError,'missing registered interval interior'):audit(self.root,bad)
    def test_named_nested_ranges_and_explicit_members_differ(self):
        self.assertEqual(self.scan({'seeds':[40,50]})['status'],'NO_REGISTERED_COLLISION')
        self.assertEqual(self.scan({'reserved_seeds':[40,50]})['status'],'REGISTERED_COLLISION')
        self.assertEqual(self.scan({'seed_ranges':{'train':{'lower':40,'upper':50}}})['status'],'REGISTERED_COLLISION')
    def test_registry_legacy_unlabelled_pair_is_conservative(self):
        self.assertEqual(self.scan({'heldout_reserved_not_executed':[40,50]},name='docs/protocols/seed_registry.json')['status'],'REGISTERED_COLLISION')
    def test_registry_partitions_preserve_ranges_below_seed_container(self):
        self.assertEqual(self.scan({'episode_seed_partitions':{'development':[40,50]}},name='docs/protocols/seed_registry.json')['status'],'REGISTERED_COLLISION')
    def test_start_end_and_start_count(self):
        for v in ({'seed_start':40,'seed_end':50},{'seeds':{'start':40,'count':11}},{'seed_start':40,'num_seeds':11}):
            with self.subTest(v=v):self.assertEqual(self.scan(v)['status'],'REGISTERED_COLLISION')
    def test_start_to_reserved_hull_does_not_claim_actual_use(self):
        r=self.scan({'seed_start':40,'reserved_seed_range':[48,60]})
        self.assertEqual(r['status'],'REGISTERED_COLLISION');self.assertEqual(r['blockers'][0]['kind'],'CONSERVATIVE_START_TO_RESERVED_END')
    def test_missing_bound_and_invalid_count_are_indeterminate(self):
        for v in ({'seed_start':40},{'seed_start':40,'count':False},{'seed_start':40,'count':0},{'seed_ranges':[50,40]}):
            with self.subTest(v=v):self.assertEqual(self.scan(v)['status'],'INDETERMINATE')
    def test_scalar_bool_float_and_null_are_not_seed_numbers(self):
        for v in (True,1.5,None,-1):
            with self.subTest(v=v):self.assertEqual(self.scan({'seed':v})['status'],'INDETERMINATE')
    def test_metadata_boolean_flags_and_hashes(self):
        r=self.scan({'preserve_old_reserved_seeds':True,'zero_episode_seeds':True,'source_hashes':{'seed_ranges':[40,50]},'seeds_sha256':'40--50'})
        self.assertEqual(r['status'],'NO_REGISTERED_COLLISION');self.assertEqual(r['records'],[])
    def test_rng_namespace_visible_and_episode_override(self):
        r=self.scan({'noise_seed_ranges':[40,50],'bootstrap_seed':45})
        self.assertEqual(r['status'],'NO_REGISTERED_COLLISION');self.assertTrue(r['records'])
        r=self.scan({'noise':{'episode_seed':45}});self.assertEqual(r['status'],'REGISTERED_COLLISION')
    def test_unknown_generator_is_not_broadly_ignored(self):
        self.assertEqual(self.scan({'generation_episode_seeds':[45]})['status'],'REGISTERED_COLLISION')
    def test_empty_range_has_explicit_reason(self):
        r=self.scan({'seed_ranges':[]});self.assertEqual(r['status'],'NO_REGISTERED_COLLISION');self.assertEqual(r['issues'][0]['code'],'EMPTY_DECLARED_RANGE')
    def test_unsupported_range_fails_closed(self):
        for value in ('unspecified',1.25,False):
            with self.subTest(value=value):self.assertEqual(self.scan({'seed_ranges':value})['status'],'INDETERMINATE')
    def test_unicode_and_text_range(self):
        for value in ('40--50','40–50','40—50','40..50','40至50'):
            with self.subTest(value=value):self.assertEqual(self.scan({'reserved_seeds':value})['status'],'REGISTERED_COLLISION')
    def test_markdown_date_is_not_reversed_seed_range(self):
        p=self.write('docs/a.md','2026-10-22；保留种子 40–50。'.encode());r=inventory.scan(self.root,45,45,[p]);audit(self.root,r)
        self.assertEqual(r['status'],'REGISTERED_COLLISION');self.assertEqual(len(r['records']),1)
    def test_markdown_singletons_and_negative_command_prose(self):
        p=self.write('docs/a.md','种子：45；命令 -1；保留记录。'.encode());r=inventory.scan(self.root,45,45,[p]);audit(self.root,r)
        self.assertEqual(r['status'],'REGISTERED_COLLISION');self.assertEqual(len(r['records']),1)
    def test_chinese_adjacent_range_and_leading_zero_singleton(self):
        p=self.write('docs/a.md','保留种子40–50；单个种子045。'.encode());r=inventory.scan(self.root,45,45,[p]);audit(self.root,r)
        self.assertEqual(r['status'],'REGISTERED_COLLISION');self.assertEqual(len(r['records']),2)
    def test_registry_reference_list_closure_and_cycles(self):
        a=self.write('configs/a.json',{'seed_registry':['docs/b.json','configs/a.json']});self.write('docs/b.json',{'seed_ranges':[[40,50]]})
        r=inventory.scan(self.root,45,45,[a]);audit(self.root,r)
        self.assertEqual(r['status'],'REGISTERED_COLLISION');self.assertEqual(len(r['sources']),2)
    def test_missing_invalid_and_escaping_reference_fail_closed(self):
        for value in ('missing.json','../outside.json','not-a-file',None):
            with self.subTest(value=value):self.assertEqual(self.scan({'seed_registry':value})['status'],'INDETERMINATE')
    def test_unreadable_and_invalid_json_are_catalogued(self):
        for raw in (b'\xff',b'{bad'):
            p=self.write('configs/a.json',raw);r=inventory.scan(self.root,45,45,[p]);audit(self.root,r)
            self.assertEqual(r['status'],'INDETERMINATE');self.assertIn('configs/a.json',r['sources'])
    def test_inclusive_boundary_and_disjoint_range(self):
        for seed in (40,50):self.assertEqual(self.scan({'seed_ranges':[40,50]},seed,seed)['status'],'REGISTERED_COLLISION')
        self.assertEqual(self.scan({'seed_ranges':[40,50]},51,51)['status'],'NO_REGISTERED_COLLISION')
    def test_input_changed_after_inventory_is_rejected(self):
        r=self.scan({'seed':45});self.write('configs/sample.json',{'seed':99})
        with self.assertRaises(ValueError):inventory.verify_unchanged(self.root,r)
        with self.assertRaises(ValueError):audit(self.root,r)
    def test_empty_scope_is_not_clearance(self):
        r=inventory.scan(self.root,1,9,[]);audit(self.root,r);self.assertEqual(r['status'],'INDETERMINATE')
    def test_escaped_json_pointer_roundtrip(self):
        self.assertEqual(self.scan({'seed_ranges':{'a/b~c':[40,50]}})['status'],'REGISTERED_COLLISION')
    def test_independent_audit_does_not_call_production_parser(self):
        r=self.scan({'seed_ranges':[[40,50]]})
        with patch.object(inventory,'extract_json',side_effect=AssertionError('production disabled')),patch.object(inventory,'scan',side_effect=AssertionError('production disabled')):
            self.assertEqual(audit(self.root,r)['integrity'],'PASSED')
    def test_discovery_includes_docs_and_manifest_not_raw_data(self):
        for name in ('configs/a.json','outputs/a/manifest.json','docs/protocols/seed_registry.json'):self.write(name,{'seed':45})
        self.write('docs/research/a.md',b'seed 45');self.write('outputs/a/secret_records.json',b'not read')
        r=inventory.scan(self.root,45,45);audit(self.root,r);self.assertEqual(len(r['sources']),4)
    def test_audit_rejects_omitted_discovery_source(self):
        self.write('configs/a.json',{'seed':45});r=inventory.scan(self.root,45,45);r['sources']={};r['records']=[]
        with self.assertRaisesRegex(ValueError,'source omitted'):audit(self.root,r)
    def test_unknown_episode_range_blocks_despite_rng_collision(self):
        r=self.scan({'noise_seed_ranges':[40,50],'episode_seed_ranges':'unknown'})
        self.assertEqual(r['status'],'INDETERMINATE')
    def test_negative_or_boolean_query_rejected(self):
        for lo,hi in ((-1,1),(1,False),(5,4)):
            with self.subTest(lo=lo,hi=hi),self.assertRaises(ValueError):inventory.scan(self.root,lo,hi,[])

if __name__=='__main__':unittest.main()

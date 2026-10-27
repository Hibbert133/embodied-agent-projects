"""New entry/ownership/lock and saved-record contracts. No native sampling."""
from pathlib import Path
from contextlib import contextmanager
from copy import deepcopy
from unittest.mock import patch
import tempfile,unittest
import numpy as np
from src.analysis import graybox_qualification_io_v2 as a
from scripts import run_graybox_qualification_v2 as command
from src.probe import graybox_response_model_v1 as model
from src.analysis import graybox_response_independent_v1 as independent
from tests.test_graybox_response_v1 import fixture,saved_evaluation_fixture
io=a.io

class QualificationSupplement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract=a.source_contract();cls.bank=io.read(a.SOURCE/'training/models.json')['bank']
    @contextmanager
    def prepared(self):
        with tempfile.TemporaryDirectory() as name:
            base=Path(name);out=base/'runs';validation=base/'validation';validation.mkdir();n='src/analysis/graybox_qualification_io_v2.py'
            io.write(validation/'complete.json',dict(integrity='PASSED',source_sha256={n:io.sha(a.ROOT/n)}))
            def git(*args):
                if args[0]=='ls-files':return n
                if args[:2]==('rev-parse','HEAD'):return '0'*40
                if args[0]=='status':return ''
                raise AssertionError(args)
            with patch.object(a,'OUTPUT',out),patch.object(a,'VALIDATION',validation),patch.object(io,'git',git),\
                patch.object(a,'source_contract',return_value=deepcopy(self.contract)),patch.object(a,'seed_scope',return_value=dict(integrity='CONSTRUCTED_SCOPE_NOT_REAL_CENSUS')):
                path=a.prepare((n,));yield path
    def test_actual_source_is_terminal_and_holdouts_unspent(self):
        self.assertEqual(self.contract['integrity'],'PASSED_UNSPENT_EXISTING_RESERVATION');self.assertEqual(self.contract['actual_source_costs']['executions'],459)
        self.assertTrue(self.contract['no_original_CAL_or_QUAL_attempt']);self.assertEqual(self.contract['model_sha256'],a.MODEL_SHA)
    def test_whole_registered_assignments_and_noise_namespaces_unchanged(self):
        for split in a.SPLITS:
            self.assertEqual(a.population(split),a.prior.population(split));self.assertEqual(a.limits(split),a.prior.limits(split))
            for v in (a.population(split)[0],a.population(split)[-1]):
                self.assertEqual(a.packets(v),a.prior.packets(v));self.assertEqual(a.destination(v),a.prior.destination(v));np.testing.assert_array_equal(a.noise(v),a.prior.noise(v))
    def test_budget_literal_and_full_source_cost_not_double_charged(self):
        c=a.config();self.assertEqual(c['combined_limits'],dict(executions=432,control_steps=40320,controlled_resets=432,factory_resets=21600,all_resets=22032,physical_frames=11217600))
        self.assertEqual(c['imported_source_costs_separate']['control_steps']+40320,71337);self.assertEqual(c['imported_source_costs_separate']['physical_frames']+11217600,23077185)
        self.assertEqual(c['new_primary_training'],0);self.assertEqual(c['new_episode_seed_allocations'],0)
    def test_scientific_selection_and_qualification_rules_exact_original(self):
        c=a.config()
        for key,value in c['scientific_rules'].items():self.assertEqual(value,a.prior.config()[key])
        self.assertEqual(c['fixed_model_sha256'],a.MODEL_SHA)
    def test_no_training_or_repeated_software_collection_entry(self):
        for split in ('TRAIN','NOMINAL','SOFTWARE','OTHER'):
            with self.subTest(split=split),patch.object(command.prior.collector,'collect') as collect,self.assertRaises(ValueError):command.collect('unused',split)
            collect.assert_not_called()
    def test_dependency_binding_is_explicit_and_exception_restores_every_module(self):
        original=[m.a for m in command.MODULES]
        with self.assertRaisesRegex(RuntimeError,'constructed'):
            with command.binding():
                self.assertTrue(all(m.a is a for m in command.MODULES));raise RuntimeError('constructed')
        self.assertEqual([m.a for m in command.MODULES],original);self.assertFalse(command._BOUND)
    def test_binding_refuses_nesting_and_foreign_binding(self):
        with command.binding():
            with self.assertRaises(ValueError):
                with command.binding():pass
        with patch.object(command.MODULES[0],'a',object()),self.assertRaises(ValueError):
            with command.binding():pass
        self.assertFalse(command._BOUND)
    def test_pipeline_has_only_frozen_cal_lock_qual_stages(self):
        from scripts.run_graybox_qualification_pipeline_v2 import stages
        self.assertEqual([n for n,_ in stages('unused')],['CAL_collect','CAL_record_audit','CAL_evaluate','CAL_statistics_audit','model_lock','QUAL_collect','QUAL_record_audit','QUAL_evaluate','QUAL_statistics_audit'])
    def test_unspent_check_rejects_existing_attempt_directory_or_intent_or_lock(self):
        for relative in ('cal','qual','pipeline_control/CAL_collect_intent.json','pipeline_control/QUAL_collect_failure.json','model_lock.json'):
            with tempfile.TemporaryDirectory() as name:
                root=Path(name);p=root/relative;p.parent.mkdir(parents=True,exist_ok=True)
                if p.suffix:p.write_bytes(b'{}')
                else:p.mkdir()
                with self.subTest(relative=relative),self.assertRaises(ValueError):a.require_unspent(root)
    def test_full_ownership_census_allows_only_exact_declared_sources(self):
        owners={'one','two'};value=dict(query=dict(lower=113000,upper=113999),blocking_issues=[],sources={n:{} for n in owners},blockers=[dict(source='one')])
        a.validate_owner_inventory(value,owners)
        for change in ('foreign','missing','unknown','wrong_query'):
            bad=deepcopy(value)
            if change=='foreign':bad['blockers'].append(dict(source='one/subfolder/other.json'))
            elif change=='missing':bad['sources'].pop('two')
            elif change=='unknown':bad['blocking_issues']=[dict(code='UNPARSED')]
            else:bad['query']['lower']=113200
            with self.subTest(change=change),self.assertRaises(ValueError):a.validate_owner_inventory(bad,owners)
    def test_prepare_imports_exact_model_and_marks_audit_as_supplemental(self):
        with self.prepared() as path:
            self.assertEqual(io.sha(path.parent/'training/models.json'),a.MODEL_SHA);self.assertEqual(io.read(path.parent/'training/models.json')['bank'],self.bank)
            m=a.phase_gate(path,'CAL');self.assertTrue(m['imported_training_not_new_fitting']);self.assertTrue(io.read(path.parent/'training/audit.json')['imported_supplemental_audit'])
            self.assertFalse((a.SOURCE/'training/audit.json').exists())
    def test_second_prepare_rejected_without_sampling(self):
        with self.prepared():
            with self.assertRaises(ValueError):a.prepare(('src/analysis/graybox_qualification_io_v2.py',))
    def test_imported_source_mutation_is_rejected(self):
        with self.prepared() as path:
            with (path.parent/'training/models.json').open('ab') as f:f.write(b' ')
            with self.assertRaises(ValueError):a.checked(path)
    def test_qual_cannot_start_without_cal_lock(self):
        with self.prepared() as path:
            with self.assertRaises(FileNotFoundError):a.phase_gate(path,'QUAL')
    def test_model_digest_includes_process_choice_without_mutating_import(self):
        with self.prepared() as path:
            original=io.sha(path.parent/'training/models.json');io.write(path.parent/'model_lock.json',dict(selected_q_index=1))
            bank,digest=a.phase_model(path,'QUAL');self.assertEqual(bank['selected_q_index'],1);self.assertEqual(digest,io.digest(bank));self.assertEqual(original,io.sha(path.parent/'training/models.json'))
    def test_frozen_bank_forecasts_match_independent_scalar_and_batch_math(self):
        q=fixture();before=io.digest(self.bank)
        for index in (None,1):
            bank=deepcopy(self.bank);bank['selected_q_index']=index;counts={};actual,errors=model.predict(bank,q,counts);expected,other=independent.evaluate(bank,q)
            self.assertEqual(errors,{});self.assertEqual(other,{});self.assertEqual(len(actual),8 if index is None else 6)
            self.assertEqual(counts['rls_updates'],22);self.assertEqual(counts['axis_observations'],192 if index is None else 96)
            for name in actual:
                for pair in actual[name]:np.testing.assert_allclose(actual[name][pair],expected[name][pair],atol=2e-8,rtol=2e-7)
        self.assertEqual(io.digest(self.bank),before)
    def test_full_saved_cal_lock_qual_statistics_path_with_main_scoring_disabled(self):
        with self.prepared() as path:
            root=path.parent
            for split in a.SPLITS:
                data=saved_evaluation_fixture(root,split)
                with patch.object(command.prior.evaluation,'families',return_value=data):result=command.evaluate(path,split)
                receipt=command.audit_statistics(path,split);self.assertEqual(receipt['integrity'],'PASSED');self.assertEqual(result['allocated_families'],36 if split=='CAL' else 108)
                if split=='CAL':
                    io.write(root/'cal/completion.json',dict(status='CONSTRUCTED_ONLY'));lock=command.lock(path);self.assertEqual(lock['selected_q_index'],2)
                    a.phase_gate(path,'QUAL');self.assertEqual(a.phase_model(path,'QUAL')[0]['selected_q_index'],2)
                else:self.assertEqual(result['status'],'QUALIFIED_RESPONSE_CONTRAST_COMPONENT_ONLY')
            with self.assertRaises(ValueError):command.lock(path)
    def test_qual_lock_artifact_mutation_rejected(self):
        with self.prepared() as path:
            io.write(path.parent/'model_lock.json',dict(status='FROZEN_BEFORE_QUAL',artifact_sha256={'training/models.json':'0'*64}))
            with self.assertRaises(ValueError):a.phase_gate(path,'QUAL')

if __name__=='__main__':unittest.main()

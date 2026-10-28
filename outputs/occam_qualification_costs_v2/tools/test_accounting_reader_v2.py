"""Synthetic corruption checks and four immutable saved-metadata regressions."""
from pathlib import Path
from copy import deepcopy
from collections import Counter
from unittest.mock import patch
import hashlib,json,sys,unittest
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'outputs/occam_qualification_costs_v1/tools'))
import costs_engine_v1 as e
import costs_audit_v1 as old_audit
import test_costs_v1 as fixture
import accounting_reader_v2 as r
import accounting_audit_v2 as a
RUN=ROOT/'outputs/occam_reference_qualification_v1/qualification_v1/occam_reference_qualification_v1_20261028T125131Z_7abaec83b085'


def data(program='DIRECT_C8',*,omit=True):
    c,s=fixture.case(program,50,0,0)
    if omit:del c['online_LLM_API_calls']
    ac=dict(status='COMPLETE',failure=None,cohort=c['cohort'],case_index=1,ledger_start=deepcopy(c['ledger_before']),
        ledger_after=deepcopy(c['ledger_after_close']),control_steps_start=0,control_steps_after=c['total_steps'],
        online_LLM_API_calls=0,network_guard=dict(attempted_network_calls=0))
    raw=json.dumps(c).encode();araw=json.dumps(ac).encode()
    p=dict(cohort=c['cohort'],case_index=1,status='RETURNED',expected_status='RETURNED',expected_contract_observed=True,returncode=0,
        artifact_sha256={'case.json':hashlib.sha256(raw).hexdigest(),'accounting.json':hashlib.sha256(araw).hexdigest()})
    return c,s,ac,p,raw,araw


def auth(d,index=1):
    c,s,ac,p,raw,araw=d
    return r.authenticate(c,s,ac,p,index=index,case_bytes=raw,accounting_bytes=araw)


class AccountingTests(unittest.TestCase):
    def test_legacy_uses_explicit_accounting_without_mutating_raw_case(self):
        d=data();c,s,ac,p,raw,araw=d;before=deepcopy(c)
        self.assertEqual(auth(d),'LEGACY_ACCOUNTING_EXPLICIT_ZERO_CASE_FIELD_ABSENT')
        row=r.project(c,s,ac);old_audit.verify_case(c,s,row);a.verify(c,s,ac,p,1,raw,araw,row)
        self.assertEqual(c,before);self.assertNotIn('online_LLM_API_calls',c)
    def test_modern_case_and_accounting_agree(self):
        d=data('META_ADAPT__CONTINUE',omit=False);self.assertEqual(auth(d),'CASE_AND_ACCOUNTING_EXPLICIT_ZERO')
    def test_missing_accounting_counter_is_not_zero(self):
        d=data();del d[2]['online_LLM_API_calls']
        with self.assertRaises(KeyError):auth(d)
    def test_nonzero_accounting_counter_rejected(self):
        d=data();d[2]['online_LLM_API_calls']=1
        with self.assertRaises(ValueError):auth(d)
    def test_attempted_network_call_rejected(self):
        d=data();d[2]['network_guard']['attempted_network_calls']=1
        with self.assertRaises(ValueError):auth(d)
    def test_modern_case_missing_counter_rejected(self):
        d=data('META_ADAPT__CONTINUE')
        with self.assertRaises(ValueError):auth(d)
    def test_original_case_counter_disagreement_rejected(self):
        d=data(omit=False);d[0]['online_LLM_API_calls']=1
        with self.assertRaises(ValueError):auth(d)
    def test_parent_artifact_hash_tamper_rejected(self):
        d=data();d[3]['artifact_sha256']['accounting.json']='0'*64
        with self.assertRaises(ValueError):auth(d)
    def test_foreign_case_index_rejected(self):
        with self.assertRaises(ValueError):auth(data(),index=2)
    def test_ledger_disagreement_rejected(self):
        d=data();d[2]['ledger_start']['counts']['reset_attempts']=1
        with self.assertRaises(ValueError):auth(d)
    def test_boolean_counter_not_an_integer_zero(self):
        d=data();d[2]['online_LLM_API_calls']=False
        with self.assertRaises(ValueError):auth(d)
    def test_independent_api_cost_tamper_rejected(self):
        c,s,ac,p,raw,araw=data();row=r.project(c,s,ac);row['online_LLM_API_calls']=1
        with self.assertRaises(ValueError):a.verify(c,s,ac,p,1,raw,araw,row)
    def test_independent_check_disables_main_adapter_and_projection(self):
        c,s,ac,p,raw,araw=data();row=r.project(c,s,ac)
        with patch.object(r,'authenticate',None),patch.object(r,'project',None),patch.object(e,'case_cost',None),patch.object(e,'increment',None):
            a.verify(c,s,ac,p,1,raw,araw,row);old_audit.verify_case(c,s,row)
    def test_real_saved_legacy_and_modern_metadata(self):
        m=json.loads((RUN/'manifest.json').read_text(encoding='utf8'))
        for phase,index in (('NATIVE',1),('NATIVE',28),('QUAL',1),('QUAL',28)):
            with self.subTest(phase=phase,index=index):
                folder=RUN/phase.lower()/('case_%04d'%index);raw=(folder/'case.json').read_bytes();araw=(folder/'accounting.json').read_bytes()
                c=json.loads(raw);ac=json.loads(araw);p=json.loads((folder/'result.json').read_text(encoding='utf8'));s=m['config']['populations'][phase][index-1]
                source=r.authenticate(c,s,ac,p,index=index,case_bytes=raw,accounting_bytes=araw);row=r.project(c,s,ac)
                self.assertEqual(a.verify(c,s,ac,p,index,raw,araw,row),source);old_audit.verify_case(c,s,row)
    def test_phase_evidence_must_be_explicit_and_registered(self):
        c,s,ac,p,raw,araw=data();row=r.project(c,s,ac);sources=Counter({auth((c,s,ac,p,raw,araw)):1})
        summary=dict(online_LLM_API_calls=0);audit=dict(online_LLM_API_calls=0,guard=dict(network=dict(attempted_network_calls=0)))
        saved=r.check_phase_api(summary,audit,[row],sources);a.verify_phase(summary,audit,[row],list(sources.elements()),saved)
        with self.assertRaises(KeyError):r.check_phase_api({},audit,[row],sources)
        with self.assertRaises(ValueError):r.check_phase_api(summary,audit,[row],{'UNKNOWN':1})


if __name__=='__main__':unittest.main()

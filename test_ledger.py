from dataclasses import FrozenInstanceError,replace
import unittest
from ledger import *
class Tests(unittest.TestCase):
    def case(self,mode):return compare(*fixture(mode))['decisions']
    def test_contradiction(self):self.assertEqual(self.case('contradiction')[0]['status'],'contradicted')
    def test_removed_stale(self):self.assertEqual(self.case('removed')[0]['status'],'stale')
    def test_condition_review(self):self.assertEqual(self.case('condition')[0]['status'],'review-required')
    def test_missing_context_abstains(self):self.assertEqual(self.case('missing-context')[0]['status'],'review-required')
    def test_synonym_negative(self):self.assertEqual(self.case('synonym')[0]['status'],'unchanged')
    def test_formatting_negative(self):self.assertTrue(all(p['status']=='unchanged' for p in self.case('formatting')))
    def test_unrelated_negative(self):
        for mode in ('contradiction','removed','condition'):self.assertEqual(self.case(mode)[1]['status'],'unchanged')
    def test_combined_propagates(self):self.assertEqual(self.case('contradiction')[2]['status'],'contradicted')
    def test_source_span_exact(self):
        b,_,_=fixture()
        with self.assertRaises(ValueError):replace(b,claims=(replace(b.claims[0],start=1),))
    def test_bounds_reject(self):
        b,_,_=fixture()
        for lo,hi in [(-1,3),(0,1000),(True,3),(3,2)]:
            with self.assertRaises(ValueError):replace(b,claims=(replace(b.claims[0],start=lo,end=hi),))
    def test_immutable_versions(self):
        b,a,_=fixture();store=Ledger();store.add(b);store.add(a)
        with self.assertRaises(ValueError):store.add(a)
        with self.assertRaises(FrozenInstanceError):b.text='mutate'
        self.assertEqual(store.get(b.id,1).text,b.text)
    def test_provenance_hash_and_span(self):
        b,a,d=fixture('formatting');packet=compare(b,a,d)['decisions'][0]['dependencies'][0]
        self.assertNotEqual(packet['before']['sha256'],packet['after']['sha256'])
        for doc,side in [(b,'before'),(a,'after')]:
            lo,hi=packet[side]['span'];self.assertEqual(doc.text[lo:hi],packet[side]['quote'])
    def test_mutable_claim_fields_reject(self):
        b,_,_=fixture()
        for field,value in [('condition',{'cell':'A'}),('entity',['MAPK1']),('id',['c1']),('quote',['x']),('predicate',{'effect':'growth'})]:
            with self.assertRaises(ValueError):replace(b.claims[0],**{field:value})
    def test_mutable_document_fields_reject(self):
        b,_,_=fixture()
        for field,value in [('id',['study']),('text',['source']),('text','\ud800'),('claims',list(b.claims))]:
            with self.assertRaises(ValueError):replace(b,**{field:value})
    def test_mutable_decision_fields_reject(self):
        for id,deps in [('d',['c1']),(['d'],('c1',)),('d',({'id':'c1'},)),('d',())]:
            with self.assertRaises(ValueError):Decision(id,deps)
    def test_bad_dependency(self):
        b,a,_=fixture()
        with self.assertRaises(ValueError):compare(b,a,[Decision('x',('missing',))])
    def test_version_order(self):
        b,a,d=fixture();store=Ledger()
        with self.assertRaises(ValueError):store.add(a)
        with self.assertRaises(ValueError):compare(a,b,d)
    def test_gold_affected_decisions(self):
        expected={'contradiction':{'experiment-A','combined'},'removed':{'experiment-A','combined'},
                  'condition':{'experiment-A','combined'},'formatting':set(),'synonym':set()}
        for mode,gold in expected.items():
            actual={p['decision'] for p in self.case(mode) if p['status']!='unchanged'}
            self.assertEqual(actual,gold)
if __name__=='__main__':unittest.main()

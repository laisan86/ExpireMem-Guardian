import copy
import json
import unittest
from d4_model_adapters import (META_MODEL,BASETEN_MODEL,PROVENANCE,
    DecodeFailure, MetaResponsesAdapter as Meta, BasetenChatAdapter as Base,
    evidence_decision,canon_hash)
from d4_offline_review import review, synthetic_responses, EXCERPT, CLAIM

class D4AdaptersTests(unittest.TestCase):
    def setUp(self):
        self.meta,self.baseten=synthetic_responses()

    def test_offline_frozen_cases(self):
        r=review()
        self.assertEqual((r['frozen_d2_cases'],r['frozen_d2_agreement']),(14,14))
        self.assertTrue(r['removed_rule_dominates_model_verdict'])
        self.assertEqual(r['model_requests'],0)
        self.assertEqual(r['reported_provenance'],PROVENANCE)

    def test_meta_request_only_serializes(self):
        req=Meta.request_payload(CLAIM,EXCERPT)
        self.assertEqual(req['model'],META_MODEL)
        self.assertFalse(req['store'])
        self.assertEqual(req['max_output_tokens'],2048)
        self.assertEqual(req['stream'],False)

    def test_baseten_request_shape(self):
        req=Base.request_payload(CLAIM,EXCERPT)
        self.assertEqual(req['model'],BASETEN_MODEL)
        self.assertEqual(req['messages'][0]['role'],'system')
        self.assertEqual(req['max_tokens'],2048)

    def test_meta_parse(self):
        parsed=Meta.parse(self.meta,EXCERPT)
        self.assertEqual(parsed.verdict,'SUPPORTED')
        self.assertEqual(parsed.provenance,PROVENANCE)
        self.assertEqual(parsed.usage['output_tokens'],1)
        self.assertEqual(parsed.response_sha256,canon_hash(self.meta))

    def test_baseten_parse(self):
        parsed=Base.parse(self.baseten,EXCERPT)
        self.assertEqual(parsed.verdict,'SUPPORTED')
        self.assertEqual(parsed.provenance,PROVENANCE)
        self.assertEqual(parsed.usage['input_tokens'],1)

    def test_meta_truncation_reject(self):
        self.meta['status']='incomplete'
        with self.assertRaises(DecodeFailure):Meta.parse(self.meta,EXCERPT)

    def test_baseten_truncation_reject(self):
        self.baseten['choices'][0]['finish_reason']='length'
        with self.assertRaises(DecodeFailure):Base.parse(self.baseten,EXCERPT)

    def test_meta_wrong_model_reject(self):
        self.meta['model']='muse-wonder-full'
        with self.assertRaises(DecodeFailure):Meta.parse(self.meta,EXCERPT)

    def test_baseten_wrong_model_reject(self):
        self.baseten['model']='another-model'
        with self.assertRaises(DecodeFailure):Base.parse(self.baseten,EXCERPT)

    def test_hallucinated_quote_reject(self):
        payload=json.dumps({'verdict':'SUPPORTED','quote':'Text never in document','explanation':'claim'})
        self.baseten['choices'][0]['message']['content']=payload
        with self.assertRaises(DecodeFailure):Base.parse(self.baseten,EXCERPT)

    def test_multiple_content_texts_reject(self):
        self.meta['output'][0]['content'].append({'type':'output_text','text':'{}'})
        with self.assertRaises(DecodeFailure):Meta.parse(self.meta,EXCERPT)

    def test_usage_inconsistent_reject(self):
        self.baseten['usage']['total_tokens']=20
        with self.assertRaises(DecodeFailure):Base.parse(self.baseten,EXCERPT)

    def test_bad_reasoning_reject(self):
        self.meta['usage']['output_tokens_details']['reasoning_tokens']=4
        with self.assertRaises(DecodeFailure):Meta.parse(self.meta,EXCERPT)

    def test_deprecated_and_removed_cannot_be_upgraded(self):
        p=Base.parse(self.baseten,EXCERPT)
        for decision in ('WARN','ABSTAIN'):
            with self.subTest(decision=decision):
                r=evidence_decision(p,decision)
                self.assertEqual(r['decision'],decision)
                self.assertFalse(r['override'])

    def test_bounds_of_request(self):
        with self.assertRaises(ValueError):Meta.request_payload(CLAIM,EXCERPT,10)
        with self.assertRaises(ValueError):Base.request_payload(CLAIM,EXCERPT,10000)

    def test_no_raw_private_identity_upgrade(self):
        # Raw may be supplied by anyone: strings claiming real origin mean nothing.
        self.baseten['transport_kind']='baseten_real'
        self.assertEqual(Base.parse(self.baseten,EXCERPT).provenance,PROVENANCE)

if __name__=='__main__':unittest.main()

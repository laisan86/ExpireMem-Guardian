import ast
import json
from pathlib import Path
import tempfile
import unittest

from guardian_core import (
    BUGGY_CODE, EVIDENCE_ID, OFFICIAL_DOC, inspect_source, version_gate,
    verify_official_document, fix_fixture_code, run_demo, deterministic_expression,
    validate_candidate_expression, make_muse_prompt, parse_muse_reply
)
from muse_baseten import BasetenOneShotProposer, ACKNOWLEDGEMENT

SAMPLE_HTML = ('<html><body><h1>pandas 2.0</h1><p>Removed deprecated '
               'Series.append(), DataFrame.append(), use concat() instead (GH 35407)</p></body></html>')

def fake_fetch(url, timeout):
    assert url == OFFICIAL_DOC
    return url, SAMPLE_HTML

def mock_muse(_prompt):
    return json.dumps({'replacement_expr': deterministic_expression(BUGGY_CODE)})

class GuardianTests(unittest.TestCase):
    def test_ast_detect(self):
        self.assertTrue(inspect_source(BUGGY_CODE)['recognized'])
    def test_version_removed_abstains(self):
        for v in ('2.0.0','2.2.3','3.0.2'):
            with self.subTest(v=v):
                self.assertEqual(version_gate(BUGGY_CODE,v)['decision'],'ABSTAIN')
    def test_version_deprecated_warns(self):
        self.assertEqual(version_gate(BUGGY_CODE,'1.5.3')['decision'],'WARN')
    def test_version_old_passes(self):
        self.assertEqual(version_gate(BUGGY_CODE,'1.3.5')['decision'],'PASS')
    def test_no_call(self):
        self.assertEqual(version_gate('import pandas as pd\ndf = pd.DataFrame([])','3.0.2')['decision'],'PASS')
    def test_ambiguous_abstains(self):
        self.assertEqual(version_gate('def f(x):\n  return x.append(1)','3.0.2')['decision'],'ABSTAIN')
    def test_verified_doc(self):
        self.assertEqual(verify_official_document(fetch=fake_fetch)['status'],'VERIFIED_TEST_INJECTION')
    def test_redirect_external_rejected(self):
        self.assertEqual(verify_official_document(fetch=lambda url,t:('https://example.com',SAMPLE_HTML))['status'],'UNAVAILABLE')
    def test_redirect_path_rejected(self):
        self.assertEqual(verify_official_document(fetch=lambda url,t:('https://pandas.pydata.org/other',SAMPLE_HTML))['status'],'UNAVAILABLE')
    def test_unrelated_doc_rejected(self):
        self.assertEqual(verify_official_document(fetch=lambda url,t:(url,'<html>append removed</html>'))['status'],'UNAVAILABLE')
    def test_verified_patch_from_abstain(self):
        ev=verify_official_document(fetch=fake_fetch)
        fixed=fix_fixture_code(BUGGY_CODE,'3.0.2',ev)
        self.assertIn('pd.concat',fixed)
        self.assertNotIn('df.append',fixed)
    def test_patch_unverified_denied(self):
        with self.assertRaises(RuntimeError):
            fix_fixture_code(BUGGY_CODE,'3.0.2',{'status':'UNAVAILABLE','evidence_id':EVIDENCE_ID})
    def test_patch_warn_denied(self):
        with self.assertRaises(RuntimeError):
            fix_fixture_code(BUGGY_CODE,'1.5.3',verify_official_document(fetch=fake_fetch))
    def test_candidate_safe(self):
        expr=deterministic_expression(BUGGY_CODE)
        self.assertTrue(validate_candidate_expression(BUGGY_CODE,expr))
    def test_model_payload_side_effects_rejected(self):
        bad=["__import__('os').system('echo bad')",
             "pd.concat([df, pd.DataFrame([{'id': 999}])], ignore_index=True)",
             "pd.concat([df, pd.DataFrame([{'id': 2, 'name': 'new'}])], ignore_index=True); print(1)",
             "pd.concat([df, pd.DataFrame([{'id': 2, 'name': 'new'}])], ignore_index=False)"]
        for s in bad:
            with self.subTest(s=s), self.assertRaises(ValueError):
                validate_candidate_expression(BUGGY_CODE,s)
    def test_model_json_schema(self):
        expr = deterministic_expression(BUGGY_CODE)
        self.assertEqual(parse_muse_reply(json.dumps({'replacement_expr':expr})),expr)
        for bad in ('{"replacement_expr":"x","notes":"evil"}','```json\n{}\n```','{"nope":1}'):
            with self.subTest(bad=bad), self.assertRaises((ValueError,json.JSONDecodeError)):
                parse_muse_reply(bad)
    def test_live_mock_muse_pipeline(self):
        with tempfile.TemporaryDirectory() as d:
            r=run_demo(Path(d)/'run',fetch=fake_fetch,muse_proposer=mock_muse)
            self.assertEqual(r['outcome'],'GREEN_TEST_INJECTION_MUSE')
            self.assertEqual(r['decision']['decision'],'ABSTAIN')
            self.assertEqual(r['patched_decision']['decision'],'PASS')
            self.assertEqual(r['post_refresh']['remediation_authorization'],'AUTHORIZED')
            self.assertEqual(r['green']['returncode'],0)
            stages = [entry['stage'] for entry in r['audit_trace']]
            self.assertLess(stages.index('ASSESS'),stages.index('REFRESH'))
            self.assertLess(stages.index('REFRESH'),stages.index('REASSESS'))
            self.assertLess(stages.index('REASSESS'),stages.index('PROPOSE'))
            self.assertLess(stages.index('PROPOSE'),stages.index('EXECUTE_PATCHED'))
    def test_live_mock_bad_muse_denied_no_file(self):
        with tempfile.TemporaryDirectory() as d:
            r=run_demo(Path(d)/'run',fetch=fake_fetch,muse_proposer=lambda x: json.dumps({'replacement_expr':'__import__("os").system("date")'}))
            self.assertEqual(r['outcome'],'ABSTAIN')
            self.assertFalse((Path(d)/'run'/'fixed_pandas_concat.py').exists())
            self.assertIsNotNone(r['proposal_rejected'])
    def test_live_rule_baseline(self):
        with tempfile.TemporaryDirectory() as d:
            r=run_demo(Path(d)/'run',fetch=fake_fetch)
            self.assertEqual(r['outcome'],'GREEN_TEST_INJECTION_RULE')
            self.assertTrue(r['red_confirmed'])
    def test_missing_docs_fail_closed_muse_never_called(self):
        with tempfile.TemporaryDirectory() as d:
            seen=[]
            r=run_demo(Path(d)/'run',fetch=lambda u,t: (_ for _ in ()).throw(OSError('offline')),
                       muse_proposer=lambda p: seen.append(p))
            self.assertEqual(r['outcome'],'ABSTAIN')
            self.assertEqual(seen,[])
            self.assertFalse((Path(d)/'run'/'fixed_pandas_concat.py').exists())
    def test_offline_replay_never_calls_muse(self):
        with tempfile.TemporaryDirectory() as d:
            seen=[]
            r=run_demo(Path(d)/'run',fetch=lambda u,t: (_ for _ in ()).throw(OSError('offline')),
                       allow_offline_replay=True,muse_proposer=lambda p: seen.append(p))
            self.assertEqual(r['outcome'],'GREEN_OFFLINE_REPLAY')
            self.assertEqual(seen,[])
    def test_run_dir_overwrite_denied(self):
        with tempfile.TemporaryDirectory() as d:
            r=run_demo(Path(d)/'run',fetch=fake_fetch)
            with self.assertRaises(RuntimeError): run_demo(Path(d)/'run',fetch=fake_fetch)
    def test_public_prompt_requires_live_evidence(self):
        with self.assertRaises(RuntimeError):
            make_muse_prompt(BUGGY_CODE,'oops',{'status':'UNAVAILABLE'})
    def test_baseten_requires_auth(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(PermissionError):
                BasetenOneShotProposer(private_dir=Path(d),api_key='fake')
    def test_baseten_one_shot_mock(self):
        with tempfile.TemporaryDirectory() as d:
            calls=[]
            def fake_transport(prompt):
                calls.append(prompt)
                return json.dumps({'replacement_expr':deterministic_expression(BUGGY_CODE)}), {'prompt_tokens':12,'completion_tokens':22}
            b=BasetenOneShotProposer(private_dir=Path(d),api_key='dummy',allow_paid=True,
                                      acknowledgement=ACKNOWLEDGEMENT,transport=fake_transport)
            p=make_muse_prompt(BUGGY_CODE,'AttributeError',verify_official_document(fetch=fake_fetch))
            self.assertTrue(b(p))
            self.assertEqual(len(calls),1)
            self.assertTrue((Path(d)/'baseten_muse_raw_response_private.json').exists())
            self.assertEqual(b.receipt['transport_kind'], 'test_injection')
            with self.assertRaises(FileExistsError): b(p)
    def test_mock_proposer_cannot_claim_live_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            def fake_transport(prompt):
                return json.dumps({'replacement_expr': deterministic_expression(BUGGY_CODE)}), {'total_tokens': 100}
            adapter = BasetenOneShotProposer(private_dir=Path(d)/'private', api_key='dummy',
                         allow_paid=True, acknowledgement=ACKNOWLEDGEMENT,transport=fake_transport)
            result=run_demo(Path(d)/'demo',fetch=fake_fetch,muse_proposer=adapter)
            self.assertEqual(result['outcome'],'GREEN_TEST_INJECTION_MUSE')
            self.assertEqual(result['model_evidence']['transport_kind'],'test_injection')
            self.assertTrue((Path(d)/'demo'/'fixed_pandas_concat.py').exists())
            self.assertTrue((Path(d)/'demo'/'candidate_patch.diff').is_file())

    def test_fake_receipt_provenance_cannot_claim_live(self):
        class Fake:
            receipt={'transport_kind':'baseten_real','response_id':'fake', 'response_sha256':'123'}
            def __call__(self, _):
                return json.dumps({'replacement_expr': deterministic_expression(BUGGY_CODE)})
        with tempfile.TemporaryDirectory() as d:
            result=run_demo(Path(d)/'demo',fetch=fake_fetch,muse_proposer=Fake())
            self.assertEqual(result['outcome'],'GREEN_TEST_INJECTION_MUSE')

    def test_invalid_muse_json_saves_raw_and_denies_patch(self):
        with tempfile.TemporaryDirectory() as d:
            adapter = BasetenOneShotProposer(private_dir=Path(d)/'private', api_key='dummy',
                         allow_paid=True, acknowledgement=ACKNOWLEDGEMENT,
                         transport=lambda p:('```not json```', {'total_tokens': 10}))
            result=run_demo(Path(d)/'demo',fetch=fake_fetch,muse_proposer=adapter)
            self.assertEqual(result['outcome'],'ABSTAIN')
            self.assertTrue((Path(d)/'private'/'baseten_muse_raw_response_private.json').is_file())
            self.assertFalse((Path(d)/'demo'/'fixed_pandas_concat.py').exists())
            self.assertTrue(result['model_evidence']['response_sha256'])

    def test_subprocess_drops_secret_environment(self):
        from guardian_core import run_in_same_environment
        import os
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'envcheck.py'
            path.write_text('import os\nassert os.environ.get("BASETEN_API_KEY") is None\nprint("clean")\n')
            original=os.environ.get('BASETEN_API_KEY')
            try:
                os.environ['BASETEN_API_KEY']='DO_NOT_EXPOSE'
                result=run_in_same_environment(path)
                self.assertEqual(result['returncode'],0, result['stderr'])
            finally:
                if original is None: os.environ.pop('BASETEN_API_KEY',None)
                else: os.environ['BASETEN_API_KEY']=original

    def test_baseten_error_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            def boom(prompt): raise TimeoutError('simulated')
            b=BasetenOneShotProposer(private_dir=Path(d),api_key='dummy',allow_paid=True,
                                      acknowledgement=ACKNOWLEDGEMENT,transport=boom)
            p=make_muse_prompt(BUGGY_CODE,'AttributeError',verify_official_document(fetch=fake_fetch))
            with self.assertRaises(RuntimeError): b(p)
            with self.assertRaises(FileExistsError): b(p)

if __name__ == '__main__': unittest.main()

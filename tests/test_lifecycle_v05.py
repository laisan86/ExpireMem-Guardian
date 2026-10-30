"""D3 lifecycle & verification verifier contract. No installations or model calls."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from lifecycle import assess_np_bool, find_segment, scan_np_bool
from verify_corpus import evaluate_case, load_manifest, run_verification, PROBES

ROOT=Path(__file__).resolve().parents[1]
SRC='import numpy as np\nimport json\njson.dumps(np.bool(True))\n'

class LifecycleTests(unittest.TestCase):
    def test_boundaries_existence_only(self):
        for v, dec, state in [('1.20.0','WARN','DEPRECATED_AVAILABLE'),
                               ('1.23.5','WARN','DEPRECATED_AVAILABLE'),
                               ('1.24.0','ABSTAIN','REMOVED'),
                               ('1.26.4','ABSTAIN','REMOVED'),
                               ('2.0.0','PASS','ACTIVE'),
                               ('2.5.3','PASS','ACTIVE')]:
            with self.subTest(v=v):
                r=assess_np_bool(SRC,v)
                self.assertEqual(r['decision'],dec)
                self.assertEqual(r['availability'],state)

    def test_json_semantics_separate_from_availability(self):
        for v,compat in [('1.23.5','COMPATIBLE'),('1.26.4','NOT_APPLICABLE'),
                         ('2.0.0','INCOMPATIBLE'),('2.5.3','INCOMPATIBLE')]:
            with self.subTest(v=v):
                r=assess_np_bool(SRC,v,'json_builtin_bool')
                self.assertEqual(r['semantic_compatibility'],compat)
                self.assertEqual(r['decision'],'WARN' if compat=='COMPATIBLE' else 'ABSTAIN')

    def test_unknown_and_below_documented_boundary_fail_closed(self):
        for v in ['1.19.5','unknown','2.0rc1','2.6.0','3.0.0','3.0.0rc1']:
            self.assertEqual(assess_np_bool(SRC,v)['decision'],'ABSTAIN')

    def test_syntax_and_shadow_name_no_false_match(self):
        self.assertEqual(scan_np_bool('import numpy as np\n# np.bool\ns="np.bool"'),'NO_MATCH')
        self.assertEqual(scan_np_bool('np.bool(True)'),'AMBIGUOUS')
        self.assertEqual(scan_np_bool('import numpy as np\nnp = 5\nnp.bool'),'AMBIGUOUS')
        self.assertEqual(scan_np_bool('import numpy as np\ndef f(np): return np.bool'),'AMBIGUOUS')
        self.assertEqual(scan_np_bool('import numpy as np\nx=np.bool(True)'),'MATCH')
        self.assertEqual(scan_np_bool('import numpy as np\ndef bad(:'),'INVALID_SYNTAX')

    def test_verifier_labels_requires_observation(self):
        case={'case_id':'abc','package':'numpy','target_version':'2.5.3','probe_kind':'numpy.bool',
              'expected_existence':True,'expected_semantic_pass':False}
        self.assertEqual(evaluate_case(case,None,{'status':'NOT_INSTALLED'})['verification_status'],'NOT_RUN')
        observation={'actual_version':'2.5.3','existence':True,'semantic_checked':True,'semantic_passed':False}
        self.assertEqual(evaluate_case(case,observation,{'status':'CACHED_ENV'})['verification_status'],'VERIFIED_SEMANTICS')
        observation['actual_version']='2.3.5'
        self.assertEqual(evaluate_case(case,observation,{'status':'CACHED_ENV'})['verification_status'],'VERSION_MISMATCH')
        observation['actual_version']='2.5.3'
        observation['semantic_passed']=True
        self.assertEqual(evaluate_case(case,observation,{'status':'CACHED_ENV'})['verification_status'],'OBSERVED_CONTRADICTION')

    def test_no_execution_of_manifest_source_code(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'m.jsonl'
            p.write_text(json.dumps({'case_id':'evil','package':None,'target_version':None,
                'probe_kind':None,'source_code':'raise RuntimeError("must not run")'})+'\n')
            c=load_manifest(p)
            rows=run_verification(c,sys.executable,Path(td)/'envs')
            self.assertEqual(rows[0]['verification_status'],'STATIC_ONLY')

    def test_disallow_custom_execution_kind(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'m.jsonl'
            p.write_text(json.dumps({'case_id':'x','probe_kind':'os.system','target_version':'1.0','package':'numpy'})+'\n')
            with self.assertRaises(ValueError):load_manifest(p)

    def test_manifest_contains_frozen_d2_and_lifecycle(self):
        cases=load_manifest(ROOT/'data/d3_verification_manifest.jsonl')
        self.assertEqual(len(cases),19)
        self.assertEqual(len([c for c in cases if c['source']=='D2_FIXED_BASELINE']),14)
        self.assertEqual(len([c for c in cases if c['probe_kind']=='numpy.bool']),5)

    def test_replay_bootstraps_from_clean_python_process(self):
        # v0.4 imported muse_baseten only when Streamlit/test path was injected;
        # guard against falsely rejecting a completed green replay on CLI.
        proc=subprocess.run([sys.executable,'-c',
            'from replay import run_offline; r=run_offline(); print(r["outcome"])'],
            cwd=ROOT,capture_output=True,text=True,timeout=40)
        self.assertEqual(proc.returncode,0,proc.stderr[-1200:])
        self.assertIn('GREEN_OFFLINE_REPLAY',proc.stdout)

    def test_offline_probe_recount_p8_fixture(self):
        from audit_probes import analyze
        with tempfile.TemporaryDirectory() as td:
            f=Path(td)/'p8.jsonl'
            f.write_text('\n'.join(json.dumps({'cond':c, 'case':'C1','code':'ok',
                'leaked_doc_value':False,'used_task_value':True,'used_removed_api':False})
                for c in ['NO_DOC','STALE_DOC','CURRENT_DOC']))
            r=analyze(f,'p8')
            self.assertEqual(r['total_calls'],3)
            self.assertEqual(r['condition_counts']['STALE_DOC']['task_value_pattern_hits'],1)
            self.assertEqual(r['condition_counts']['STALE_DOC']['doc_value_leak_pattern_hits'],0)

    def test_current_numpy_probe_true_behavior(self):
        # This exercises the actual installed NumPy without installing a package.
        import numpy as np
        completed=subprocess.run([sys.executable,'-I',str(ROOT/'runtime_probe.py'),'numpy.bool'],
                                 capture_output=True,text=True,timeout=20)
        self.assertEqual(completed.returncode,0,completed.stderr)
        obj=json.loads(completed.stdout)['result']
        self.assertEqual(obj['actual_version'],np.__version__)
        parsed=tuple(int(x) for x in np.__version__.split('.')[:2])
        if parsed >= (2,0):
            self.assertTrue(obj['existence'])
            self.assertTrue(obj['semantic_checked'])
            self.assertFalse(obj['semantic_passed'])
            self.assertEqual(obj['observations']['json_dumps']['exception_class'],'TypeError')
        elif parsed >= (1,24):
            self.assertFalse(obj['existence'])
        else:
            self.assertTrue(obj['existence'])
            self.assertTrue(obj['semantic_passed'])

if __name__=='__main__':unittest.main()

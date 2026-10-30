import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from guardian_d2 import load_cases, assess, targets, version_tuple

class BenchmarkTests(unittest.TestCase):
    def test_all_official_cases(self):
        for c in load_cases():
            with self.subTest(case=c['case_id']):
                self.assertEqual(assess(c)['decision'], c['expected_decision'])
    def test_comments_do_not_trigger(self):
        self.assertEqual(targets('# np.float_\n# df.append(x)\n'),set())
    def test_syntax_error_abstains(self):
        self.assertEqual(assess({'source_code':'def bad(:','target_version':'2.0.0'})['decision'],'ABSTAIN')
    def test_bad_versions_abstain(self):
        self.assertIsNone(version_tuple('3.0rc1'))
        self.assertIsNone(version_tuple('unknown'))
    def test_no_execution(self):
        # AST only: should never run code even if side effects appear
        source='import numpy as np\nraise RuntimeError("do not execute")\nx=np.float_\n'
        self.assertEqual(targets(source), {'numpy.float_'})

if __name__=='__main__': unittest.main()

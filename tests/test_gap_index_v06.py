"""Case A and P8-derived Case C: no provider calls, exact external oracle."""
import hashlib
import ast
import subprocess
import sys
import unittest
from pathlib import Path

from gap_index_cases import (CASE_A_GAPPED_SOURCE, EXPECTED_ALL,
                             EXPECTED_ORIGINAL, FROZEN_CANDIDATES, _case_c_fixture,
                             run_case_a_gapped, run_case_c)
from core.guardian_core import version_gate, validate_candidate_expression

ROOT = Path(__file__).resolve().parents[1]


class GappedIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case_a = run_case_a_gapped()
        cls.case_c = run_case_c()
        cls.rows = {r['candidate']: r for r in cls.case_c['tested_candidates']}

    def test_case_a_genuine_red_and_green_same_interpreter(self):
        a = self.case_a
        self.assertEqual(a['outcome'], 'GREEN_OFFLINE_GAPPED')
        self.assertTrue(a['red']['confirmed'])
        self.assertNotEqual(a['red']['exit_code'], 0)
        self.assertEqual(a['green']['exit_code'], 0)
        self.assertTrue(a['green']['postcondition_pass'])
        self.assertEqual(a['green']['verified_rows'], EXPECTED_ALL)
        self.assertEqual(a['python_executable'], sys.executable)

    def test_case_a_ast_and_gate(self):
        a = self.case_a
        self.assertEqual(a['version_gate_before'], 'ABSTAIN')
        self.assertEqual(a['version_gate_after'], 'PASS')
        self.assertEqual(a['ast_whitelist'], 'PASS')
        self.assertEqual(a['before_index'], [0, 1, 3])
        self.assertFalse(a['prior_real_baseten_receipt_reused'])
        self.assertFalse(a['prior_v03_core_modified'])
        self.assertEqual(a['official_refresh'], 'NOT_REQUESTED_OFFLINE')

    def test_case_c_silent_overwrites_are_rejected_by_external_oracle(self):
        for name in ('silent_loc_dict', 'silent_loc_list'):
            with self.subTest(name=name):
                r = self.rows[name]
                self.assertEqual(r['syntax_check'], 'PASS')
                self.assertEqual(r['removed_api_version_gate'], 'PASS')
                self.assertEqual(r['subprocess_exit_code'], 0)
                self.assertTrue(r['would_pass_exit_code_only'])
                self.assertEqual(r['row_count_after'], 3)
                self.assertEqual(r['index_before'], [0, 1, 3])
                self.assertEqual(r['task_oracle'], 'FAIL')
                self.assertFalse(r['guardian_candidate_accepted'])
                self.assertNotIn({'id': 4, 'name': 'd'}, r['rows_after'])

    def test_multiline_concat_is_same_ast_as_prior_one_line_candidate(self):
        # Styling must change neither the parsed program nor executable fixture.
        one_line = "df = pd.concat([df, pd.DataFrame([{'id': 7, 'name': 'carol'}])], ignore_index=True)"
        multiline = FROZEN_CANDIDATES['correct_concat']
        self.assertIn('\n', multiline)
        # Studio half-width code panes must show all text without horizontal scrolling.
        self.assertLessEqual(max(map(len, multiline.splitlines())), 36)
        self.assertEqual(ast.dump(ast.parse(one_line), include_attributes=False),
                         ast.dump(ast.parse(multiline), include_attributes=False))
        self.assertEqual(multiline, self.rows['correct_concat']['candidate_code'])
        self.assertEqual(self.rows['correct_concat']['source_sha256'],
                         hashlib.sha256(_case_c_fixture('correct_concat').encode()).hexdigest())
        self.assertEqual(self.rows['correct_concat']['task_oracle'], 'PASS')

    def test_case_c_correct_concat_accepted(self):
        r = self.rows['correct_concat']
        self.assertEqual(r['removed_api_version_gate'], 'PASS')
        self.assertEqual(r['subprocess_exit_code'], 0)
        self.assertEqual(r['row_count_after'], 4)
        self.assertEqual(r['task_oracle'], 'PASS')
        self.assertEqual(r['rows_after'], EXPECTED_ALL)
        self.assertTrue(r['guardian_candidate_accepted'])

    def test_case_c_not_misreported_as_old_v03_ast_whitelist(self):
        for name in FROZEN_CANDIDATES:
            self.assertIn('NOT_APPLICABLE', self.rows[name]['v03_repair_ast_whitelist'])
        # v0.3's patch-only whitelist continues to reject an arbitrary loc assignment.
        with self.assertRaises(ValueError):
            validate_candidate_expression(CASE_A_GAPPED_SOURCE,
                                          "df.loc[len(df)] = {'id': 7, 'name': 'carol'}")

    def test_no_execution_of_arbitrary_candidate(self):
        from gap_index_cases import _case_c_fixture
        with self.assertRaises(ValueError):
            _case_c_fixture('__import__("os").system("echo this-must-not-run")')

    def test_case_c_reproducible_fingerprint_and_original_rows(self):
        for name in FROZEN_CANDIDATES:
            self.assertEqual(self.rows[name]['candidate_sha256'],
                             hashlib.sha256(FROZEN_CANDIDATES[name].encode()).hexdigest())
            self.assertEqual(self.case_c['before_rows'], EXPECTED_ORIGINAL)
        self.assertEqual(self.case_c['model_requests'], 0)

    def test_command_line_runs_without_studio_bootstrap(self):
        proc = subprocess.run([sys.executable, '-c',
            'from gap_index_cases import run_case_c; print(run_case_c()["outcome"])'],
            cwd=ROOT, text=True, capture_output=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr[-1200:])
        self.assertIn('OFFLINE_SEMANTIC_ORACLE_EVALUATED', proc.stdout)


if __name__ == '__main__':
    unittest.main()

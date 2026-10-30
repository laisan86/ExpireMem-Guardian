"""No provider calls. The oracle cannot attest to its own reliability."""
import ast
import unittest

from d4_oracle_guard import (REFERENCE_ORACLE, OracleRejected, frozen_witnesses,
                             guarded_predicate, review_oracle, review_reference, prompt_for_model,
                             extract_oracle_source, review_response_baseten)
from gap_index_cases import FROZEN_CANDIDATES

class OracleGuardTests(unittest.TestCase):
    def test_reference_is_explicitly_not_muse(self):
        r=review_reference()
        self.assertEqual(r['status'],'VALIDATED_ON_FROZEN_WITNESSES')
        self.assertEqual(r['provenance'],'HANDWRITTEN_REFERENCE_NO_MODEL')
        self.assertEqual(r['model_requests'],0)
        self.assertTrue(all(item['pass'] for item in r['evaluations']))
        self.assertGreaterEqual(len(r['evaluations']),10)

    def test_observed_candidate_is_unchanged(self):
        self.assertEqual(FROZEN_CANDIDATES['silent_loc_dict'],
                         "df.loc[len(df)] = {'id': 7, 'name': 'carol'}")
        self.assertTrue(FROZEN_CANDIDATES['silent_loc_dict'].endswith('}'))

    def test_obvious_constant_oracle_rejected(self):
        code='def verify_postcondition(before_rows, after_rows, task_row):\n    return True'
        self.assertEqual(review_oracle(code)['status'],'REJECTED')

    def test_insufficient_oracle_fails_witnesses(self):
        code='def verify_postcondition(before_rows, after_rows, task_row):\n    return len(after_rows) == len(before_rows) + 1 and after_rows[-1] == task_row'
        r=review_oracle(code)
        self.assertEqual(r['status'],'REJECTED')
        self.assertIn('negative_mutated_existing_row',[w['witness_id'] for w in r['evaluations'] if not w['pass']])

    def test_task_row_only_rejected(self):
        code='def verify_postcondition(before_rows, after_rows, task_row):\n    return after_rows[-1] == task_row and len(before_rows) >= 1'
        self.assertEqual(review_oracle(code)['status'],'REJECTED')

    def test_reject_arbitrary_execution_and_import(self):
        variants=(
            'import os\ndef verify_postcondition(before_rows, after_rows, task_row):\n    return True',
            'def verify_postcondition(before_rows, after_rows, task_row):\n    return __import__("os").system("true")',
            'def verify_postcondition(before_rows, after_rows, task_row):\n    return before_rows.__class__ == after_rows.__class__',
            'def verify_postcondition(before_rows, after_rows, task_row):\n    return [x for x in after_rows]',
            'def verify_postcondition(before_rows, after_rows, task_row):\n    while True: pass',
            'def verify_postcondition(before_rows, after_rows, task_row):\n    before_rows.clear()\n    return True',
        )
        for code in variants:
            with self.subTest(code=code[:30]):
                self.assertEqual(review_oracle(code)['status'],'REJECTED')

    def test_overfitted_exact_values_forbidden(self):
        s='def verify_postcondition(before_rows, after_rows, task_row):\n    return after_rows[-1]["name"] == "carol"'
        self.assertEqual(review_oracle(s)['status'],'REJECTED')

    def test_no_unspecified_provider_claim(self):
        r=review_oracle(REFERENCE_ORACLE)
        self.assertEqual(r['provenance'],'UNTRUSTED_PROPOSAL_OFFLINE')
        self.assertNotIn('baseten_real',str(r))

    def test_alternative_good_predicate_passes(self):
        text='def verify_postcondition(before_rows, after_rows, task_row):\n    return after_rows == before_rows + [task_row]'
        self.assertEqual(review_oracle(text)['status'],'VALIDATED_ON_FROZEN_WITNESSES')

    def test_witnesses_fixed_and_correct(self):
        witnesses=frozen_witnesses()
        self.assertGreaterEqual(sum(x.expected for x in witnesses),3)
        self.assertGreaterEqual(sum(not x.expected for x in witnesses),7)
        self.assertNotIn('negative_silent_overwrite',prompt_for_model())
        self.assertTrue(ast.parse(REFERENCE_ORACLE))

    def test_wrong_return_type_is_rejected(self):
        text='def verify_postcondition(before_rows, after_rows, task_row):\n    return len(after_rows) + len(before_rows) + len(task_row)'
        self.assertEqual(review_oracle(text)['status'],'REJECTED')


    def test_witness_v2_covers_independent_head_and_tail_changes(self):
        labels={w.witness_id: w for w in frozen_witnesses()}
        for label in ('negative_mutated_first_row','negative_mutated_last_original_row',
                      'negative_dropped_head_shifted', 'negative_prepended_task_row',
                      'negative_middle_inserted_task_row'):
            self.assertIn(label,labels)
            self.assertIs(labels[label].expected,False)
        self.assertEqual(len(labels),16)

    def test_positionally_overfit_oracles_fail_v2(self):
        candidates=(
            'after_rows[1] == before_rows[1]',
            'after_rows[:2] == before_rows[:2]',
            'after_rows[1:-1] == before_rows[1:]',
        )
        for fragment in candidates:
            with self.subTest(fragment=fragment):
                code=('def verify_postcondition(before_rows, after_rows, task_row):\n'
                      '    return len(after_rows) == len(before_rows) + 1 '
                      'and after_rows[-1] == task_row and '+fragment)
                r=review_oracle(code)
                self.assertEqual(r['status'],'REJECTED')
                self.assertTrue((any(not x['pass'] for x in r['evaluations'])) or r.get('reason','').startswith('OracleRejected:'))

    def test_valid_other_semantic_forms_still_pass(self):
        forms=(
            'after_rows == before_rows + [task_row]',
            'len(after_rows) == len(before_rows) + 1 and after_rows[:-1] == before_rows and after_rows[-1] == task_row',
            'len(after_rows) == len(before_rows) + 1 and after_rows[:len(before_rows)] == before_rows and after_rows[-1] == task_row',
        )
        for expr in forms:
            with self.subTest(expr=expr):
                s='def verify_postcondition(before_rows, after_rows, task_row):\n    return '+expr
                self.assertEqual(review_oracle(s)['status'],'VALIDATED_ON_FROZEN_WITNESSES')


    def test_adversarial_or_and_demorgan_are_denied(self):
        variants=(
            "after_rows == before_rows + [task_row] or after_rows[0] == task_row",
            "not (after_rows != before_rows + [task_row] and after_rows[0] != task_row)",
            "(after_rows != before_rows + [task_row] and after_rows[0] != task_row) == False",
        )
        for clause in variants:
            with self.subTest(clause=clause):
                source='def verify_postcondition(before_rows, after_rows, task_row):\n    return '+clause
                result=review_oracle(source)
                self.assertEqual(result['status'], 'REJECTED')

    def test_boolean_comparison_rewrite_cannot_escape_conjunction_only_rule(self):
        # Old 14-witness guard accepted this: it silently accepts inserting
        # task_row in the middle for one schema, without accepting prepend.
        clause=('(after_rows != before_rows + [task_row] and '
                '(len(before_rows) > len(task_row) and after_rows[1] == task_row) '
                '== False) == False')
        source='def verify_postcondition(before_rows, after_rows, task_row):\n    return '+clause
        result=review_oracle(source)
        self.assertEqual(result['status'], 'REJECTED')
        self.assertIn('Boolean result cannot be compared',result['reason'])

    def test_valid_reference_rejects_new_prepend_and_middle_insertion(self):
        labels={w.witness_id:w for w in frozen_witnesses()}
        reference=guarded_predicate(REFERENCE_ORACLE)
        for name in ('negative_prepended_task_row', 'negative_middle_inserted_task_row'):
            w=labels[name]
            self.assertFalse(reference(w.before_rows,w.after_rows,w.target_row))
        self.assertEqual(review_reference()['status'],'VALIDATED_ON_FROZEN_WITNESSES')

    def test_prompt_matches_allowed_language(self):
        prompt=prompt_for_model()
        self.assertIn("NEVER use 'or' or 'not'",prompt)
        self.assertIn('Boolean expression',prompt)

    def test_transport_extracts_common_presentation_wrappers(self):
        raw=REFERENCE_ORACLE
        examples=(
            (raw, 'VERBATIM'),
            ('```python\n'+raw+'\n```', 'UNFENCED'),
            ('```\n'+raw+'\n```', 'UNFENCED'),
            ('Here is the function:\n'+raw, 'TRIMMED'),
            ('Here is the function:\n```python\n'+raw+'\n```\nIt checks every row.', 'UNFENCED'),
            (raw+'\nThis checks both the existing records and the requested row.', 'TRIMMED'),
        )
        for content,expected_note in examples:
            with self.subTest(note=expected_note, content=content[:20]):
                source,note=extract_oracle_source(content)
                self.assertEqual(note,expected_note)
                self.assertEqual(source,REFERENCE_ORACLE)
                self.assertEqual(review_oracle(source)['status'],'VALIDATED_ON_FROZEN_WITNESSES')

    def test_transport_rejects_hidden_executable_payloads(self):
        raw=REFERENCE_ORACLE
        bad=(
            '',
            '```python\n'+raw+'\n',
            '```python\n'+raw+'\n```\n```python\n'+raw+'\n```',
            '```python\n'+raw+'\nprint(1)\n```',
            '```python\n'+raw+'\n```\nprint(1)',
            raw+'\nimport os',
            raw+'\nos.system("touch /tmp/pwned")',
            raw+'\nx == 1',
            raw+'\ndef second_function():\n    return True',
            'import os\n'+raw,
            '```json\n'+raw+'\n```',
        )
        for content in bad:
            with self.subTest(content=content[:30]):
                with self.assertRaises(OracleRejected):
                    extract_oracle_source(content)

    def test_provider_receipt_includes_both_hashes_and_extraction(self):
        from d4_model_adapters import BASETEN_MODEL
        import hashlib
        content='Explanation:\n```python\n'+REFERENCE_ORACLE+'\n```'
        raw={'id':'mock-only','model':BASETEN_MODEL,
             'choices':[{'finish_reason':'stop','message':{'content':content}}],
             'usage':{'prompt_tokens':100,'completion_tokens':240,'total_tokens':340,
                      'completion_tokens_details':{'reasoning_tokens':180}}}
        report=review_response_baseten(raw)
        self.assertEqual(report['status'],'VALIDATED_ON_FROZEN_WITNESSES')
        self.assertEqual(report['extraction'],'UNFENCED')
        self.assertEqual(report['raw_content_sha256'],hashlib.sha256(content.encode()).hexdigest())
        self.assertEqual(report['oracle_sha256'],hashlib.sha256(REFERENCE_ORACLE.encode()).hexdigest())
        self.assertEqual(report['provenance'],'SUPPLIED_BASETEN_RESPONSE_UNVERIFIED')
        self.assertEqual(report['model_requests'],0)
        raw['choices'][0]['message']['content'] = '```python\n'+REFERENCE_ORACLE+'\nprint(1)\n```'
        rejected=review_response_baseten(raw)
        self.assertEqual(rejected['status'],'REJECTED')
        self.assertEqual(rejected['extraction'],'REJECTED')
        self.assertIn('response_sha256',rejected)

    def test_provider_finish_reason_must_be_stop(self):
        from d4_model_adapters import BASETEN_MODEL
        mock={'id':'mock','model':BASETEN_MODEL,
              'choices':[{'finish_reason':'length','message':{'content':REFERENCE_ORACLE}}],
              'usage':{'prompt_tokens':1,'completion_tokens':1}}
        with self.assertRaises(OracleRejected):
            review_response_baseten(mock)

if __name__=='__main__':unittest.main()

import copy
import json
import tempfile
import unittest
from pathlib import Path
from d5_evaluation import (fixed_evaluation,read_score_records,make_split,
    calibration_report,pav_fit,pav_predict,group_key)


def sample(n=20):
    return [{'case_id':f'event-{i}-rep-{j}','ecosystem':'python','package':['pandas','numpy','django'][i%3],
             'canonical_symbol':f'symbol_{i}', 'deprecation_event':f'event_{i}',
             'label':'ACTIVE' if i%2==0 else 'REMOVED','rule_status':'UNKNOWN_RULE',
             'self_reported_validity_score':0.95 if i%2==0 else 0.05}
            for i in range(n) for j in (0,1)]

class D5Tests(unittest.TestCase):
    def test_default_no_calibration_claim(self):
        r=fixed_evaluation()
        self.assertEqual(r['d2_rule_baseline']['correct'],14)
        self.assertEqual(r['calibration']['status'],'NO_LABELLED_UNKNOWN_RULE_MODEL_SCORES_SUPPLIED')
        self.assertEqual(r['model_requests'],0)

    def test_b_lifecycle_nonmonotonic(self):
        m=fixed_evaluation()['case_b_lifecycle_static_predictions']
        self.assertEqual(m['1.23.5']['availability'],'DEPRECATED_AVAILABLE')
        self.assertEqual(m['1.26.4']['availability'],'REMOVED')
        self.assertEqual(m['2.5.3']['availability'],'ACTIVE')
        self.assertEqual(m['2.5.3']['semantic_compatibility'],'INCOMPATIBLE')
        self.assertEqual(m['2.6.0']['availability'],'UNKNOWN')

    def test_group_repeats_cannot_leak(self):
        rows=sample()
        train,test,summary=make_split(rows)
        self.assertFalse({group_key(r) for r in train}&{group_key(r) for r in test})
        self.assertEqual(summary['group_overlap'],0)
        self.assertEqual(len(train)+len(test),len(rows))

    def test_stable_frozen_split(self):
        rows=sample()
        a,b,_=make_split(rows)
        c,d,_=make_split(list(reversed(rows)))
        self.assertEqual({r['case_id'] for r in a},{r['case_id'] for r in c})
        self.assertEqual({r['case_id'] for r in b},{r['case_id'] for r in d})

    def test_lo_lo(self):
        train,test,summary=make_split(sample(),'django')
        self.assertTrue(all(r['package']=='django' for r in test))
        self.assertTrue(all(r['package']!='django' for r in train))
        self.assertEqual(summary['method'],'LEAVE_ONE_LIBRARY_OUT')

    def test_missing_lo_library(self):
        with self.assertRaises(ValueError):make_split(sample(),'tensorflow')

    def test_insufficient_not_fitted(self):
        result=calibration_report(sample(3),'a'*64)
        self.assertEqual(result['status'],'CALIBRATION_INSUFFICIENT')
        self.assertNotIn('holdout_ece_descriptive',result)

    def test_fit_when_independent_groups_exist(self):
        r=calibration_report(sample(50),'b'*64)
        self.assertEqual(r['status'],'EXPLORATORY_FITTED_NOT_RELEASE_CALIBRATED')
        self.assertEqual(r['split']['group_overlap'],0)
        self.assertGreaterEqual(r['holdout_brier'],0)
        self.assertLessEqual(r['holdout_brier'],1)

    def test_pav_monotonic(self):
        rows=sample(30)
        b=pav_fit(rows)
        preds=[pav_predict(i/20,b) for i in range(21)]
        self.assertEqual(preds,sorted(preds))

    def test_file_validation(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'scores.jsonl'
            rows=sample(2);path.write_text('\n'.join(json.dumps(r) for r in rows)+'\n')
            out,digest=read_score_records(path)
            self.assertEqual(len(out),4)
            self.assertEqual(len(digest),64)

    def test_prevent_wrong_rule_calibration(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'x.jsonl';x=sample(1)[0];x['rule_status']='ABSTAIN'
            p.write_text(json.dumps(x)+'\n')
            with self.assertRaises(ValueError):read_score_records(p)

    def test_prevent_deprecated_binary_mapping(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'x.jsonl';x=sample(1)[0];x['label']='DEPRECATED_AVAILABLE'
            p.write_text(json.dumps(x)+'\n')
            with self.assertRaises(ValueError):read_score_records(p)

    def test_prevent_duplicate_case_ids(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'x.jsonl';x=sample(1)[0]
            p.write_text(json.dumps(x)+'\n'+json.dumps(x)+'\n')
            with self.assertRaises(ValueError):read_score_records(p)

    def test_prevent_out_of_range(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'x.jsonl';x=sample(1)[0];x['self_reported_validity_score']=1.5
            p.write_text(json.dumps(x)+'\n')
            with self.assertRaises(ValueError):read_score_records(p)

    def test_prevent_bool_score(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'x.jsonl';x=sample(1)[0];x['self_reported_validity_score']=True
            p.write_text(json.dumps(x)+'\n')
            with self.assertRaises(ValueError):read_score_records(p)

if __name__=='__main__':unittest.main()

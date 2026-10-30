"""D5: no-cost, group-safe evaluation and *optional* score calibration.

Default: frozen deterministic benchmark only. Calibration can run only on a
separate, user-supplied labelled UNKNOWN_RULE score file. No scores invented.
The score is model self-report, not a calibrated probability until validated.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from benchmark_suite import evaluate_cases, evaluate_summary
from lifecycle import assess_np_bool

ROOT=Path(__file__).resolve().parent
SEED='expiremem-public-d5-fixed-split-v1'
MIN_GROUPS=12
VALID_LABELS={'ACTIVE','REMOVED'}
REQUIRED={'case_id','ecosystem','package','canonical_symbol','deprecation_event',
          'label','rule_status','self_reported_validity_score'}


def _hash(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def group_key(row):
    return '|'.join(row[k].strip() for k in
                    ('ecosystem','package','canonical_symbol','deprecation_event'))


def read_score_records(path):
    p=Path(path);raw=p.read_bytes()
    if len(raw)>5_000_000:raise ValueError('Score file exceeds 5 MB')
    rows=[];ids=set()
    for ln,line in enumerate(raw.decode('utf-8').splitlines(),1):
        if not line.strip():continue
        try:r=json.loads(line)
        except ValueError as e:raise ValueError(f'Invalid JSON line {ln}') from e
        if not isinstance(r,dict) or not REQUIRED <= set(r):raise ValueError(f'Missing required score fields at line {ln}')
        if any(not isinstance(r[k],str) or not (1<=len(r[k].strip())<=128) for k in
               ('case_id','ecosystem','package','canonical_symbol','deprecation_event')):
            raise ValueError(f'Invalid group identity line {ln}')
        if r['case_id'] in ids:raise ValueError('Duplicate case_id')
        ids.add(r['case_id'])
        if r['label'] not in VALID_LABELS:raise ValueError('Only ACTIVE and REMOVED are eligible for binary calibration')
        if r['rule_status']!='UNKNOWN_RULE':
            raise ValueError('Only UNKNOWN_RULE cases are eligible for model score calibration')
        s=r['self_reported_validity_score']
        if type(s) not in (float,int) or not (0<=s<=1):raise ValueError('Score must be numeric within [0,1]')
        r['self_reported_validity_score']=float(s)
        rows.append(r)
    if not rows:raise ValueError('Score file is empty')
    return rows, hashlib.sha256(raw).hexdigest()


def make_split(rows,holdout_library=None):
    """Assign all repeats of one API event to the same partition."""
    groups={group_key(r) for r in rows}
    if holdout_library:
        if not any(r['package']==holdout_library for r in rows):
            raise ValueError('Holdout library absent')
        train=[r for r in rows if r['package']!=holdout_library]
        test=[r for r in rows if r['package']==holdout_library]
        split_type='LEAVE_ONE_LIBRARY_OUT'
    else:
        ordered=sorted(groups,key=lambda g:_hash(SEED+':'+g))
        test_count=max(1,round(len(ordered)*0.30))
        test_groups=set(ordered[:test_count])
        train=[r for r in rows if group_key(r) not in test_groups]
        test=[r for r in rows if group_key(r) in test_groups]
        split_type='FROZEN_GROUP_HASH'
    a={group_key(r) for r in train};b={group_key(r) for r in test}
    if a & b:raise AssertionError('Group leakage')
    return train,test,{'method':split_type,'seed_sha256':_hash(SEED),
                       'training_groups':len(a),'holdout_groups':len(b),
                       'training_rows':len(train),'holdout_rows':len(test),
                       'group_overlap':len(a & b)}


def pav_fit(rows):
    """Monotonic binning (pool adjacent violators) on calibration split only."""
    entries=sorted((r['self_reported_validity_score'],int(r['label']=='ACTIVE')) for r in rows)
    blocks=[]
    for score,y in entries:
        blocks.append({'lo':score,'hi':score,'positive':y,'count':1})
        while len(blocks)>1:
            l,r=blocks[-2:]
            if l['positive']/l['count'] <= r['positive']/r['count']:
                break
            blocks[-2:] = [{'lo':l['lo'],'hi':r['hi'],
                            'positive':l['positive']+r['positive'],
                            'count':l['count']+r['count']}]
    return [{'score_upper':b['hi'],'fitted_fraction':b['positive']/b['count'],
             'training_count':b['count']} for b in blocks]


def pav_predict(x,blocks):
    for b in blocks:
        if x<=b['score_upper']:return b['fitted_fraction']
    return blocks[-1]['fitted_fraction']


def calibration_report(rows,input_sha256,holdout_library=None):
    training,holdout,split=make_split(rows,holdout_library)
    groups={group_key(r) for r in rows}
    out={'status':'CALIBRATION_INSUFFICIENT','provenance':'USER_SUPPLIED_SCORES_NOT_INDEPENDENTLY_ATTESTED',
         'source_score_file_sha256':input_sha256,'total_rows':len(rows),
         'independent_event_groups':len(groups),'split':split,
         'label_counts':dict(Counter(r['label'] for r in rows)),
         'score_field':'self_reported_validity_score',
         'warnings':['Scores are model self-reports, not native token probabilities.',
                     'Repeated phrasings of one API event must stay in one split.',
                     'Only documented UNKNOWN_RULE cases are eligible.']}
    tr_labels={r['label'] for r in training};te_labels={r['label'] for r in holdout}
    if (len(groups)<MIN_GROUPS or split['training_groups']<6 or split['holdout_groups']<3
        or tr_labels!=VALID_LABELS or te_labels!=VALID_LABELS):
        out['reason']='Insufficient independent event groups and/or binary label coverage; do not fit or publish ECE.'
        return out
    blocks=pav_fit(training)
    points=[(pav_predict(r['self_reported_validity_score'],blocks),int(r['label']=='ACTIVE')) for r in holdout]
    brier=sum((p-y)**2 for p,y in points)/len(points)
    # Descriptive only; release-grade ECE demands larger independent holdout.
    bins=[]
    for bin_idx in range(5):
        subset=[(p,y) for p,y in points if min(int(p*5),4)==bin_idx]
        if subset:
            confidence=sum(p for p,y in subset)/len(subset)
            frequency=sum(y for p,y in subset)/len(subset)
            bins.append({'bin':bin_idx,'count':len(subset),
                         'average_calibrated_estimate':confidence,'empirical_fraction_active':frequency})
    ece=sum(b['count']/len(points)*abs(b['average_calibrated_estimate']-b['empirical_fraction_active']) for b in bins)
    out.update(status='EXPLORATORY_FITTED_NOT_RELEASE_CALIBRATED',
               fitted_blocks=blocks,holdout_brier=brier,holdout_ece_descriptive=ece,
               holdout_bins=bins,
               warnings=out['warnings']+['Holdout metrics are descriptive unless adequately powered and independently verified.'])
    return out


def fixed_evaluation(execute_fixed=False):
    cases=evaluate_cases();summary=evaluate_summary(cases)
    source='import numpy as np\nimport json\njson.dumps(np.bool(True))\n'
    b_versions={v:assess_np_bool(source,v,'json_builtin_bool') for v in
                ('1.23.5','1.26.4','2.0.0','2.5.3','2.6.0')}
    out={'schema':'D5_READINESS_v1','phase':'PRE_FREEZE_NOT_FINAL',
         'evaluation_mode':'FROZEN_OFFLINE_VERSION_RULES',
         'network_requests':0,'model_requests':0,
         'd2_rule_baseline':summary,
         'case_b_lifecycle_static_predictions':{
             v:{'decision':r['decision'],'availability':r['availability'],
                'semantic_compatibility':r['semantic_compatibility']} for v,r in b_versions.items()},
         'case_b_static_predictions_not_cross_version_execution':True,
         'calibration':{'status':'NO_LABELLED_UNKNOWN_RULE_MODEL_SCORES_SUPPLIED',
                        'reason':'No independent self-reported score dataset has been supplied; calibration not claimed.'},
         'p5_to_p8':'Negative probe findings are separate tasks; do not pool to claim improved accuracy.',
         'no_guardian_intervention_trial':'No Guardian causally attributable performance uplift measured'}
    if execute_fixed:
        from gap_index_cases import run_both
        result=run_both()
        a=result['case_a'];c=result['case_c']
        checks=(a['outcome']=='GREEN_OFFLINE_GAPPED' and
                len(c['tested_candidates'])==3 and
                [x['task_oracle'] for x in c['tested_candidates']]==['FAIL','FAIL','PASS'] and
                all(x['subprocess_exit_code']==0 for x in c['tested_candidates']))
        if not checks:raise AssertionError('D5 offline executable assertions did not match frozen contract')
        out['fixed_case_runtime']={'status':'VERIFIED_LOCAL_FIXED_FIXTURE',
                                   'case_a':a['outcome'],'case_c_postconditions':['FAIL','FAIL','PASS'],
                                   'case_c_exit_codes':[x['subprocess_exit_code'] for x in c['tested_candidates']],
                                   'python_executable':a.get('python_executable'),
                                   'pandas_version':a.get('pandas_version'),
                                   'prior_baseten_receipt_reused':False}
    return out


def main():
    parser=argparse.ArgumentParser(description='D5 offline baseline + optional evidence-safe group calibration')
    parser.add_argument('--scores',help='User-supplied real labelled UNKNOWN_RULE model self-scores (JSONL)')
    parser.add_argument('--holdout-library',help='Leave one package out, instead of group hash split')
    parser.add_argument('--execute-fixed-cases',action='store_true',help='Run offline trusted pandas fixtures')
    parser.add_argument('--output',help='Write new JSON receipt (never overwrite)')
    args=parser.parse_args()
    if args.holdout_library and not args.scores:parser.error('Holdout requires scores')
    result=fixed_evaluation(args.execute_fixed_cases)
    if args.scores:
        rows,sha=read_score_records(args.scores)
        result['calibration']=calibration_report(rows,sha,args.holdout_library)
    if args.output:
        target=Path(args.output)
        with target.open('x',encoding='utf-8') as fp:
            json.dump(result,fp,ensure_ascii=False,indent=2);fp.write('\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()

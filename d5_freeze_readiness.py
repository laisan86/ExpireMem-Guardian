"""Check immutable public core, offline D4/D5 prerequisites and open blockers.

This is PRE-FREEZE readiness, not an assertion that actual model calibration,
third-party provider spend, or pinned NumPy environment checks are complete.
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from d4_offline_review import review
from d5_evaluation import fixed_evaluation
ROOT=Path(__file__).resolve().parent


def inspect():
    frozen=json.loads((ROOT/'data/d4_d5_protected_hashes.json').read_text())
    digests={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in frozen}
    mismatches=[p for p,expected in frozen.items() if digests[p]!=expected]
    d4=review();d5=fixed_evaluation()
    return {'schema':'D5_PRE_FREEZE_INSPECTION_v1',
            'status':'PRE_FREEZE_BASELINE_PASSED' if not mismatches and
              d4['frozen_d2_agreement']==14 and d4['removed_rule_dominates_model_verdict']
              else 'PRE_FREEZE_FAILED',
            'public_protected_files_checked':len(frozen),
            'public_protected_hash_mismatches':mismatches,
            'core_preserved':not mismatches,
            'd4':{'offline_adapter_contracts_pass':d4['wire_shapes_parse_pass'],
                  'no_override_of_removed_rule':d4['removed_rule_dominates_model_verdict'],
                  'real_provider_calls':0,'live_document_fetches':0},
            'd5':{'d2_baseline_matches':d5['d2_rule_baseline']['correct'],
                  'd2_baseline_count':d5['d2_rule_baseline']['count'],
                  'calibration':d5['calibration']['status']},
            'open_tasks':['Pinned NumPy 1.26.4 and 2.x cross-version runtime receipts not included',
                          'Independent UNKNOWN_RULE scored corpus unavailable for calibration',
                          'Additional public API events not imported; 14-case baseline is narrow',
                          'Full Streamlit D4/D5 expander needs Mac browser review',
                          'Muse-authored task oracle real one-shot experiment NOT performed; reference is handwritten',
                          'Final submission review and public-release clearance still required'],
            'no_real_model_call_made':True,
            'note':'Functional readiness only; no claim of final D5 model calibration or full hackathon release.'}


def main():
    p=argparse.ArgumentParser();p.add_argument('--output')
    args=p.parse_args();report=inspect()
    if args.output:
        with Path(args.output).open('x',encoding='utf-8') as f:
            json.dump(report,f,indent=2);f.write('\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if report['status']!='PRE_FREEZE_BASELINE_PASSED':raise SystemExit(1)
if __name__=='__main__':main()

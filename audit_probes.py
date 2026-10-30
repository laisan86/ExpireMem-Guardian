"""Offline source-level tallies for P6/P7/P8 local raw JSONL files.

Never uploads or copies raw provider outputs. P5 aggregate is reported as
user-supplied because no P5 raw file is distributed here.
"""
from __future__ import annotations
import argparse, hashlib, json
from collections import Counter
from pathlib import Path

def analyze(path: Path, phase: str) -> dict:
    rows=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    conds={}
    for cond in sorted(set(r['cond'] for r in rows)):
        sub=[r for r in rows if r['cond']==cond]
        truncated=sum(bool(r.get('truncated',False)) for r in sub)
        empty=sum(not bool(r.get('code','').strip()) for r in sub)
        used_removed=sum(r.get('used_removed_api') is True for r in sub)
        metric={'calls':len(sub),'empty_output':empty,'truncated_flag_true':truncated,
                'removed_api_pattern_hits':used_removed}
        if phase=='p8':
            metric['doc_value_leak_pattern_hits']=sum(r.get('leaked_doc_value') is True for r in sub)
            metric['task_value_pattern_hits']=sum(r.get('used_task_value') is True for r in sub)
        conds[cond]=metric
    return {'phase':phase,'filename':path.name,'input_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'total_calls':len(rows), 'condition_counts':conds,
            'scoring_warning':'pattern matches from original experiment; not runtime verification'}

def main():
    ap=argparse.ArgumentParser()
    for p in ('p6','p7','p8'):
        ap.add_argument('--'+p,type=Path,required=True)
    a=ap.parse_args()
    reports=[analyze(getattr(a,p),p) for p in ('p6','p7','p8')]
    print(json.dumps({'source':'OFFLINE_USER_RECORD_RECOUNT','phases':reports},indent=2))
if __name__=='__main__':main()

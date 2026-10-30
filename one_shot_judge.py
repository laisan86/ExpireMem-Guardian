"""Explicit, single-attempt optional Baseten document judge. NEVER auto invoked.

python one_shot_judge.py --policy pandas.DataFrame.append --accept 'I AUTHORIZE ONE BASETEN DOCUMENT JUDGE'

Uses allowlisted official public pages, private immutable output directory and max_retries=0.
Not a universal web browser, not a cost cap, and not a replacement for rule baseline.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time

from document_judge import fetch_official_excerpt, judge_prompt, validate_judge_reply, claim_for_policy
from benchmark.guardian_d2 import POLICIES

ACK='I AUTHORIZE ONE BASETEN DOCUMENT JUDGE'
MODEL='meta-models/muse-spark-open-1026'
URL='https://inference.baseten.co/v1'
MAX_TOKENS=2048


def write_new(path:Path,payload:dict):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as f:
        json.dump(payload,f,ensure_ascii=False,indent=2,default=str); f.flush();os.fsync(f.fileno())


def execute(policy_id:str, private_dir:Path, key:str, ack:str, *, transport=None, fetched=None):
    if ack!=ACK: raise PermissionError('Explicit acknowledgement required')
    if not key: raise ValueError('BASETEN_API_KEY not provided')
    if policy_id not in POLICIES: raise ValueError('Unknown policy')
    rule=POLICIES[policy_id]
    if not rule['evidence_urls']: raise ValueError('Policy has no official URL')
    if fetched is None:
        term_map={'pandas.DataFrame.append':['DataFrame.append()'],
                  'numpy.float_':['float_'],
                  'django.utils.encoding.force_text':['force_text']}
        fetched=fetch_official_excerpt(rule['evidence_urls'][-1],term_map[policy_id])
    if fetched.get('status') != 'FETCHED_OFFICIAL_PAGE':
        raise ValueError('No real official page evidence; refuse paid judge')
    # Lock is written only after official retrieval, BEFORE provider call.
    private_dir=Path(private_dir)
    lock=private_dir/'judge_attempt_lock.json'
    claim=claim_for_policy(policy_id)
    prompt=judge_prompt(claim,fetched['excerpt'])
    write_new(lock,{'state':'ATTEMPT_UNKNOWN','policy_id':policy_id,
                    'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),
                    'created_at_utc':datetime.now(timezone.utc).isoformat(),
                    'no_automatic_retry':True})
    started=time.perf_counter()
    try:
        if transport is not None:
            raw=transport(prompt)
            provider='TEST_INJECTION'
        else:
            from openai import OpenAI
            client=OpenAI(api_key=key,base_url=URL,max_retries=0,timeout=90)
            response=client.chat.completions.create(
                model=MODEL, messages=[
                    {'role':'system','content':'Return exactly one JSON object. No Markdown or extra prose.'},
                    {'role':'user','content':prompt}],
                max_tokens=MAX_TOKENS)
            raw=response.model_dump(mode='json');provider='BASETEN_REAL'
        # Capture before parsing. No credential in request or log artifacts.
        write_new(private_dir/'judge_raw_private.json',raw)
        first=(raw.get('choices') or [{}])[0]
        text=(first.get('message') or {}).get('content')
        if first.get('finish_reason')!='stop' or not isinstance(text,str):
            raise ValueError('No complete answer; fail closed')
        verdict=validate_judge_reply(text,fetched['excerpt'])
        report={'mode':provider,'model_requested':MODEL,'model_returned':raw.get('model'),
                'response_id':raw.get('id'), 'elapsed_seconds':round(time.perf_counter()-started,3),
                'usage':raw.get('usage'),'claim':claim, 'verdict':verdict,
                'source_url':fetched['source_url'], 'source_sha256':fetched['source_sha256'],
                'not_rule_override':True,'billing_verified':False}
        write_new(private_dir/'judge_result_private.json',report)
        return report
    except Exception as ex:
        write_new(private_dir/'judge_failure_private.json',{
            'error_type':type(ex).__name__,'http_status':getattr(ex,'status_code',None),
            'at_utc':datetime.now(timezone.utc).isoformat(),
            'may_be_billed':True,'do_not_retry':True})
        raise RuntimeError('Judge failed; lock stays. Inspect PRIVATE artifacts, do NOT auto-retry.') from None


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--policy',required=True,choices=sorted(POLICIES))
    ap.add_argument('--private-dir',required=True)
    ap.add_argument('--accept',default='')
    args=ap.parse_args()
    result=execute(args.policy,Path(args.private_dir),os.getenv('BASETEN_API_KEY',''),args.accept)
    print(json.dumps({'mode':result['mode'],'verdict':result['verdict']['verdict'],
                     'elapsed_seconds':result['elapsed_seconds'],'note':'Private raw saved; no auto retry'},indent=2))

if __name__=='__main__':main()
